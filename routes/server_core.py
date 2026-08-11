import configparser
import datetime
import math
import os
import signal
import subprocess
import sys
from pathlib import Path

import gevent

import json

from api.okex_sdk_v5.Trade_api import CLOSE, MANUAL, FISH
from module.Logger import logger
from util.ServerUtil import (
    get_api, get_contract_position_info, get_mask_symbol, get_ms,
    get_sid, get_user, safe_get_val, write_config,
)
from util.DataUtil import get_file_key, get_today_ts, is_result_data

# --- Constants ---
PROJECT_PATH = Path(__file__).resolve().parent.parent
DATA_PATH = Path(os.environ.get("MARTIN_DATA_DIR", PROJECT_PATH))
MARKET_USER_PATH = os.environ.get("MARTIN_MARKET_CONFIG_PATH", str(DATA_PATH / "market-user.ini"))
MARKET_PATH = os.environ.get("MARTIN_MARKET_PATH", str(DATA_PATH / "market.ini"))
FISHNET_PATH = os.environ.get("MARTIN_FISHNET_PATH", str(DATA_PATH / "fishnet.ini"))
FISHNET_PATH2 = os.environ.get("MARTIN_FISHNET2_PATH", str(DATA_PATH / "fishnet2.ini"))
NOTE_PATH = os.environ.get("MARTIN_NOTE_PATH", str(DATA_PATH / "note.ini"))
LOG_PATH = os.environ.get("MARTIN_LOG_PATH", str(DATA_PATH / "ok" / "nohup.out"))
BG_LOG_PATH = os.environ.get("MARTIN_BG_LOG_PATH", str(DATA_PATH / "nohup.out"))
ACCESS_PATH = os.environ.get("MARTIN_ACCESS_LOG_PATH", str(DATA_PATH / "access.log"))

uni_symbol = "LTC-USD-SWAP"
coin = "ORDI-USDT-SWAP"

HF_DEFAULT_CONFIG = {
    "lookback": 120, "profitVsFee": 1.5, "gapPct": 0.8,
    "trigger": 0.3, "win": 0.3,
    "buyLimit": 99, "sellLimit": 99,
    "qLow": 0.15, "qHigh": 0.85, "pass": False,
    "minRangePct": 0.003, "lookbackMax": 0
}
HF_DEFAULT_CONFIG_STR = json.dumps(HF_DEFAULT_CONFIG)

# --- Mutable shared state ---
fishConfig = configparser.ConfigParser()
fishConfig.read(FISHNET_PATH)
markerUserConfig = configparser.ConfigParser()
markerUserConfig.read(MARKET_USER_PATH)

LOG_ALIVE = {get_file_key(LOG_PATH): 0, get_file_key(BG_LOG_PATH): 0, get_file_key(ACCESS_PATH): 0}
MARKET_ECHO = {}
LIVE_SOCKET = 0
PRICE_TMP = {}
job_users = []
user_job = {}
active_job_users = []
JOB_STOPPED = []
today = get_today_ts()
last_orders = {}
unsafe_px = 0
TRANSFER_CACHE = {}
HISTORY_CACHE = {}

if os.path.exists('TRANSFER_CACHE'):
    with open('TRANSFER_CACHE', 'r') as f:
        TRANSFER_CACHE = json.loads(f.read())


# --- Symbol helpers ---
def is_spec_swap_symbol(symbol, s="USDT"):
    symbols = symbol.split('-')
    return len(symbols) == 3 and s != symbols[1] and symbols[2] == 'SWAP'


def get_split_swap_symbols(symbol, s="USDT"):
    return [f"{symbol.split('-')[0]}-{s}-SWAP", f"{symbol.split('-')[1]}-{s}-SWAP"]


def is_spec_symbol(symbol):
    symbols = symbol.split('-')
    return len(symbols) == 2 and symbols[1] not in ("BTC", "ETH", "USDT")


def get_split_symbols(symbol, s="USDT"):
    return [f"{symbol.split('-')[0]}-{s}", f"{symbol.split('-')[1]}-{s}"]


def get_symbol_lite(symbol):
    return symbol.replace("-", "")


def normalize_symbol_list(values):
    result = []
    for value in values or []:
        cleaned = str(value).strip().upper()
        if not cleaned or cleaned in result:
            continue
        result.append(cleaned)
    return result


def get_symbol(real=False):
    if not real:
        mask_symbol = get_mask_symbol(get_sid())
        if mask_symbol is not None:
            return mask_symbol
    user = get_user()
    config = get_config(user)
    symbols = json.loads(safe_get_val(config, 'trade', 'symbol', f'["{uni_symbol}"]'))
    return symbols[0] if len(symbols) > 0 else uni_symbol


def get_all_symbol(user=None):
    user = get_user() if user is None else user
    config = get_config(user)
    return json.loads(safe_get_val(config, 'trade', 'symbol', f'["{uni_symbol}"]'))


def get_stat_symbols():
    user = get_user()
    config = get_config(user)
    symbols = json.loads(safe_get_val(config, 'stat', 'symbol', '["LTC-USD-SWAP"]'))
    return normalize_symbol_list(symbols)


# --- Data helpers ---
def parse_boolish(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'no', 'off', ''):
        return False
    return default


def normalize_config_value(option, value):
    if option in ('maoff', 'precalc'):
        return '1' if parse_boolish(value) else '0'
    if option == 'symbol' and isinstance(value, list):
        return json.dumps(normalize_symbol_list(value))
    return value


def safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


# --- Config helper ---
def get_config(user):
    config = configparser.ConfigParser()
    config.read(f"ok/{user}.ini")
    return config


# --- Market helpers ---
# 文件标识与快照作为一个整体发布，多线程并发解析时不会出现标识与内容错配
_market_cache = (None, {})


def refresh_market_snapshot():
    """返回行情快照；文件由写入进程原子替换，标识未变时复用上次解析结果"""
    global _market_cache
    cached_stamp, snapshot = _market_cache
    try:
        st = os.stat(MARKET_PATH)
    except FileNotFoundError:
        return snapshot
    stamp = (st.st_mtime_ns, st.st_size, st.st_ino)
    if stamp == cached_stamp:
        return snapshot
    config = configparser.ConfigParser()
    try:
        config.read(MARKET_PATH)
    except (configparser.Error, UnicodeDecodeError) as e:
        # 记下标识避免对同一份损坏内容反复解析刷屏，继续沿用上一份可用快照
        _market_cache = (stamp, snapshot)
        logger.error("server_core#refresh_market_snapshot 行情文件解析失败 path:%s err:%s", MARKET_PATH, e)
        return snapshot
    snapshot = {section: dict(config.items(section)) for section in config.sections()}
    _market_cache = (stamp, snapshot)
    return snapshot


def get_market_price(symbol):
    section = refresh_market_snapshot().get(symbol)
    return section.get("bid1", 0) if section is not None else 0


def get_instant_market_price(symbol, user):
    market_api = get_api(user, 3)
    try:
        result = market_api.get_orderbook(symbol, '1')
    except Exception as e:
        logger.error("***get_instant_market_price:%s" % e)
        return 0
    if result is not None and result['code'] is not None and len(result['data']) > 0 and len(
            result['data'][0]["asks"]) > 0:
        return result['data'][0]["asks"][0][0]
    else:
        gevent.sleep(0.02)
        return get_instant_market_price(symbol, user)


def get_month_history_price(symbol, user):
    symbols = get_split_symbols(symbol) if is_spec_symbol(symbol) else get_split_swap_symbols(
        symbol) if is_spec_swap_symbol(symbol) else [symbol]
    if len(symbols) == 2:
        return float(get_instant_market_price(symbols[0], user)) / float(get_instant_market_price(symbols[1], user))
    return get_instant_market_price(symbols[0], user)


# --- Account helpers ---
def get_symbol_balance(symbol, user=None):
    if user is None:
        user = get_user()
    account_api = get_api(user, 2)
    result = account_api.get_account(symbol)
    balance = ratio = 0
    if is_result_data(result) and len(result.get('data')[0]['details']) > 0:
        balance = f"{round(float(result.get('data')[0]['details'][0]['eq']), 4)} {symbol}"
        balance_usd = round(float(result.get('data')[0]['details'][0]['eqUsd']), 4)
        total_usd = round(float(result.get('data')[0]['totalEq']), 4)
        ratio = math.floor(balance_usd / total_usd * 100.0)
    return balance, ratio


def get_symbol_positions(symbol, user=None):
    if user is None:
        user = get_user()
    account_api = get_api(user, 2)
    volume = '0'
    direction = explode = '-'
    result = account_api.get_positions("", symbol)
    if is_result_data(result):
        result = list(filter(lambda x: x['mgnMode'] == 'cross', result.get('data')))
        if len(result) == 1:
            volume = result[0]["pos"]
            direction = result[0]["posSide"]
            explode = result[0]["liqPx"]
            explode = '-' if explode == '' else round(float(explode), 4)
    return volume, direction, explode


def get_symbol_counts(symbol):
    user = get_user()
    config = get_config(user)
    day_index = datetime.datetime.now().day
    day = 0
    month = 0
    counts = json.loads(safe_get_val(config, f'{symbol}-stat', 'count', '[]'))
    if len(counts) == day_index:
        day += counts[day_index - 1]
    month += sum(counts)
    return day, month


def get_limit_info(user, symbol):
    if 'SWAP' not in symbol or is_spec_swap_symbol(symbol):
        return 0, 'green'
    config = get_config(user)
    limit = int(safe_get_val(config, symbol, "limit", "0"))
    available, direction = get_contract_position_info(user, symbol)
    amount = int(safe_get_val(config, symbol, "amount", "0"))
    atr_enable = int(safe_get_val(config, symbol, "atr", "0"))
    if atr_enable == 1:
        atr_config = json.loads(safe_get_val(config, f"{symbol}-ATR", "config"))
        pct = float(atr_config.get("gapPct"))
    else:
        pct = float(safe_get_val(config, symbol, "percentage", "0"))
    if pct == 0:
        return 0, 'green'
    amt1 = 1 / pct * amount
    market_price = price = float(get_market_price(symbol))
    job_user = user_job[user] if user_job.get(user) is not None else {'enable': False}
    if job_user.get('enable'):
        start = job_user['start']
        stop = job_user['stop']
        gap = job_user['gap']
        amount = job_user['amount']
        fish_min = min(start, stop)
        fish_max = max(start, stop)
    while available > 0 and available < limit:
        after_price = price * 0.99
        type = 'buy'
        available = _reset_available(direction, available, type, amt1)
        if job_user.get('enable') and after_price > fish_min and after_price < fish_max:
            amt2 = (price - after_price) / gap * amount
            available = _reset_available(direction, available, type, amt2)
        if abs(available) > limit:
            return math.ceil(price), _get_limit_state(price, market_price)
        price = after_price
    while available < 0 and available > limit:
        after_price = price * 1.01
        type = 'sell'
        available = _reset_available(direction, available, type, amt1)
        if job_user.get('enable') and after_price > fish_min and after_price < fish_max:
            amt2 = (price - after_price) / gap * amount
            available = _reset_available(direction, available, type, amt2)
        if abs(available) > limit:
            return math.floor(price), _get_limit_state(price, market_price)
        price = after_price
    return math.ceil(price), _get_limit_state(price, market_price)


def _get_limit_state(price, market_price):
    _min = min(price, market_price)
    _max = max(price, market_price)
    if _min / _max > 0.9:
        return 'red'
    elif _min / _max > 0.8:
        return 'orange'
    else:
        return 'green'


def _reset_available(direction, available, type, amount):
    if direction == "net" or direction == "long":
        if type == 'buy':
            available += amount
        else:
            available -= amount
    elif direction == "short":
        if type == 'buy':
            available -= amount
        else:
            available += amount
    return available


# --- Order ID helpers ---
def is_manual_order(cid):
    return cid.find(MANUAL) != -1 or cid == ""


def is_spec_cid(cid, symbol):
    if cid.find(get_symbol_lite(symbol)) != -1:
        return True
    if 'HF' in cid:
        base_coin = symbol.split('-')[0]
        return base_coin in cid
    return False


def is_user_cid(cid, user):
    return cid.find(user.upper()) == 0 or cid.startswith('HF')


def is_fish(order):
    return order['clOrdId'].find(FISH) != -1


def is_fish_close(order):
    return order['clOrdId'].find(f'{FISH}') != -1 and order['clOrdId'].find(f'{CLOSE}') != -1


# --- Order query helpers ---
def get_order_list(user, symbol, retry):
    result = None
    count = 0
    trade_api = get_api(user)
    while count < retry:
        try:
            count += 1
            result = trade_api.get_order_list("", "", symbol)
            if result['code'] != '0':
                raise ValueError(result['msg'])
            break
        except Exception as e:
            if "timeout" in str(e) or "timed out" in str(e):
                e = "timeout"
            elif "unreachable" in str(e):
                e = "unreachable"
            logger.warning(f"get_order_list err:{e},retry {count}")
            gevent.sleep(0.2)
    return result


def get_last_order(user, symbol, retry):
    result = get_order_list(user, symbol, retry)
    last_order = int(result.get('data')[-1]['uTime']) if is_result_data(result) else sys.maxsize
    if user not in last_orders:
        last_orders[user] = {}
    if symbol not in last_orders[user]:
        last_orders[user][symbol] = [sys.maxsize]
        last_orders[user][f"{symbol}_cc"] = 0
    if last_orders[user][symbol][0] == last_order:
        return
    if last_order not in last_orders[user][symbol]:
        sys.maxsize in last_orders[user][symbol] and last_orders[user][symbol].remove(sys.maxsize)
        last_orders[user][symbol].append(last_order)
        last_orders[user][f"{symbol}_cc"] = 0
    cc = last_orders[user][f"{symbol}_cc"]
    if cc < 10:
        last_orders[user][f"{symbol}_cc"] = cc + 1
        return
    if last_orders[user][symbol][0] != last_order:
        last_orders[user][symbol].pop(0)
    logger.warning(f"last_order :{last_order}")


# --- Market check helpers ---
def market_data_alive(symbol):
    now = get_ms()
    return now - MARKET_ECHO[symbol] < 15000


def check_market_symbol(symbol, is_open):
    markerUserConfig.read(MARKET_USER_PATH)
    symbols = json.loads(safe_get_val(markerUserConfig, "trade", "symbol", "[]"))
    ignores = json.loads(safe_get_val(markerUserConfig, 'trade', 'ignore', '[]'))
    cnt = len(symbols)
    _symbols = get_split_symbols(symbol) if is_spec_symbol(symbol) else get_split_swap_symbols(
        symbol) if is_spec_swap_symbol(symbol) else [symbol]
    for _symbol in _symbols:
        if _symbol in ignores:
            continue
        if is_open and _symbol not in symbols:
            symbols.insert(0, _symbol)
        elif not is_open and _symbol in symbols:
            symbols.remove(_symbol)
    if cnt != len(symbols):
        logger.warning(f"set_market_symbol:{symbols}")
        markerUserConfig.set('trade', 'symbol', json.dumps(symbols))
        write_config(MARKET_USER_PATH, markerUserConfig)
        push_signal("set_symbols")


# --- System helpers ---
def push_signal(op):
    markerUserConfig.read(MARKET_USER_PATH)
    pid = int(safe_get_val(markerUserConfig, 'signal', 'pid', '0'))
    markerUserConfig.set("signal", "op", op)
    write_config(MARKET_USER_PATH, markerUserConfig)
    logger.warning(f"[push_signal] pid: {pid}, op: {op}")
    os.kill(pid, signal.SIGUSR1)


def do_restart():
    user = get_user()
    markerUserConfig.read(MARKET_USER_PATH)
    is_update = markerUserConfig.get("signal", "update") == "1"
    hard_restart = is_update
    logger.warning(f"{user} do restart, hard: {hard_restart}")
    if hard_restart:
        cmd = "service ok restart"
        subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    else:
        markerUserConfig.set("signal", "user", user)
        write_config(MARKET_USER_PATH, markerUserConfig)
        push_signal("restart")
    return "1"


def send_msg(user, msg):
    message_api = get_api(user, 0)
    message_api.send(msg)


def send_report(user, msg):
    message_api = get_api(user, 0)
    message_api.send(msg, True)
