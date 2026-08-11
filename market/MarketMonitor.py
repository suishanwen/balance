import configparser
import copy
import json
import threading

import gevent

from api.websocket.WsPublic import WsPublic
from market.MarketPersist import market_lock, write_snapshot
from module.CfEnv import MARKET_PATH
from module.Logger import logger
from util.DepthUtil import merge_order_book
from util.MyUtil import get_ms, safe_set_val

priceInfo = {}
marketConfig = configparser.ConfigParser()
marketConfig.read(MARKET_PATH)

# HF 汇率对注册表: token -> [(t1, t2, is_swap), ...]
# 当 token 的行情更新时，重新计算所有包含该 token 的汇率对
_hf_pairs = {}  # e.g. {"XPL": [("XPL","ORDI",False), ("XPL","OKB",True)], "ORDI": [("XPL","ORDI",False)], ...}

OUTDATED_MS = 200
MAX_PENDING = 5
url = "wss://ws.okx.com:8443/ws/v5/public"
url_business = "wss://ws.okx.com:8443/ws/v5/business"
ws = WsPublic(url=url)
ws2 = WsPublic(url=url)
ws_business = WsPublic(url=url_business)
ws.start()
ws2.start()
ws_business.start()


def is_spec_swap_symbol(symbol):
    symbols = symbol.split('-')
    return len(symbols) == 3 and 'USD' not in symbols[1] and symbols[2] == 'SWAP'


def get_split_swap_symbols(symbol, s="USDT"):
    return [f"{symbol.split('-')[0]}-{s}-SWAP", f"{symbol.split('-')[1]}-{s}-SWAP"]


def is_spec_symbol(symbol):
    symbols = symbol.split('-')
    return len(symbols) == 2 and symbols[1] not in ("BTC", "ETH", "USDT")


def get_split_symbols(symbol):
    return [f"{symbol.split('-')[0]}-USDT", f"{symbol.split('-')[1]}-USDT"]


def get_market_price_info(symbol):
    if priceInfo.get(symbol) is None:
        priceInfo[symbol] = {"depth": {"version": 0, "asks": [], "bids": [], "pending": 0}}
    return priceInfo[symbol]


def set_market_depth(symbol, asks, bids):
    depth = get_market_price_info(symbol)["depth"]
    depth["asks"] = asks
    depth["bids"] = bids
    depth["version"] = get_ms()


def set_market_klines(symbol, period, data, size):
    klines = get_market_price_info(symbol)[period]
    for i in range(len(data)):
        klines["data"].insert(0, data[len(data) - i - 1])
        if len(klines["data"]) > size:
            klines["data"].pop()
    klines["version"] = get_ms()


def get_depth(client, emergency=False):
    symbol = client.SYMBOL_T
    depth = get_market_price_info(symbol)["depth"]
    ms = get_ms()
    if (ms - depth["version"] > OUTDATED_MS and depth["pending"] < MAX_PENDING) or emergency:
        client.get_coin_price(symbol)
        persist_market(symbol)


def set_t1_t2_swap(t1, t2, s="USDT"):
    if t1 == t2:
        return
        # EOS-BTC-USD
    symbol = f"{t1}-{t2}-SWAP"
    t1_bid1 = safe_get_val(marketConfig, f"{t1}-{s}-SWAP", "bid1", 0)
    t1_ask1 = safe_get_val(marketConfig, f"{t1}-{s}-SWAP", "ask1", 0)
    t2_bid1 = safe_get_val(marketConfig, f"{t2}-{s}-SWAP", "bid1", 0)
    t2_ask1 = safe_get_val(marketConfig, f"{t2}-{s}-SWAP", "ask1", 0)
    bid1 = float(t1_bid1) / float(t2_ask1) if t2_ask1 != 0 else 0
    ask1 = float(t1_ask1) / float(t2_bid1) if t2_bid1 != 0 else 0
    safe_set_val(marketConfig, symbol, "bid1", round(bid1, 8))
    safe_set_val(marketConfig, symbol, "bid1_amt", 0)
    safe_set_val(marketConfig, symbol, "ask1", round(ask1, 8))
    safe_set_val(marketConfig, symbol, "ask1_amt", 0)


def set_t1_t2(t1, t2):
    symbol = f"{t1}-{t2}"
    t1_bid1 = safe_get_val(marketConfig, f"{t1}-USDT", "bid1", 0)
    t1_ask1 = safe_get_val(marketConfig, f"{t1}-USDT", "ask1", 0)
    t2_bid1 = safe_get_val(marketConfig, f"{t2}-USDT", "bid1", 0)
    t2_ask1 = safe_get_val(marketConfig, f"{t2}-USDT", "ask1", 0)
    bid1 = float(t1_bid1) / float(t2_ask1) if t2_ask1 != 0 else 0
    ask1 = float(t1_ask1) / float(t2_bid1) if t2_bid1 != 0 else 0
    safe_set_val(marketConfig, symbol, "bid1", round(bid1, 8))
    safe_set_val(marketConfig, symbol, "bid1_amt", 0)
    safe_set_val(marketConfig, symbol, "ask1", round(ask1, 8))
    safe_set_val(marketConfig, symbol, "ask1_amt", 0)


def register_hf_pair(symbol):
    """注册 HF 汇率对，使 persist_market 在组件币种行情更新时自动计算汇率。
    symbol: 如 "OKB-ORDI"(现货) 或 "XPL-ORDI-SWAP"(合约)
    """
    if is_spec_swap_symbol(symbol):
        parts = symbol.split('-')
        t1, t2, is_swap = parts[0], parts[1], True
    elif is_spec_symbol(symbol):
        parts = symbol.split('-')
        t1, t2, is_swap = parts[0], parts[1], False
    else:
        return
    entry = (t1, t2, is_swap)
    for token in (t1, t2):
        if token not in _hf_pairs:
            _hf_pairs[token] = []
        if entry not in _hf_pairs[token]:
            _hf_pairs[token].append(entry)
    logger.warning(f"register_hf_pair: {symbol} -> {entry}, registry: {_hf_pairs}")


def is_swap(symbol):
    return symbol.find("SWAP") != -1


def safe_get_val(config, section, option, default=''):
    try:
        return config.get(section, option)
    except Exception:
        return default


def get_bid1_ask1(symbol):
    """同一把锁内取出买一/卖一，避免写入线程在两次读之间刷新导致买卖价来自不同 tick"""
    with market_lock:
        return (safe_get_val(marketConfig, symbol, "bid1", 0),
                safe_get_val(marketConfig, symbol, "ask1", 0))


def is_usdt_symbol(symbol):
    symbols = symbol.split('-')
    return len(symbols) == 2 and symbols[1] == 'USDT'


def is_usd_swap_symbol(symbol, u='USDT'):
    symbols = symbol.split('-')
    return len(symbols) == 3 and symbols[1] == u and symbols[2] == 'SWAP'


def get_usd_swap_symbol(u='USDT'):
    symbols = depth_task_symbols
    _symbols = []
    for symbol in symbols:
        arr = symbol.split("-")
        if len(arr) == 3 and arr[1] == u and arr[2] == 'SWAP':
            _symbols.append(arr[0])
    return _symbols


def get_usdt_symbol():
    symbols = depth_task_symbols
    _symbols = []
    for symbol in symbols:
        arr = symbol.split("-")
        if len(arr) == 2 and arr[1] == 'USDT':
            _symbols.append(arr[0])
    return _symbols


def persist_market(symbol):
    depth = get_market_price_info(symbol)["depth"]
    with market_lock:
        safe_set_val(marketConfig, symbol, "bid1", str(depth["bids"][0][0]))
        safe_set_val(marketConfig, symbol, "bid1_amt",
                     str(int(depth["bids"][0][1])) if is_swap(symbol) else str(depth["bids"][0][1]))
        safe_set_val(marketConfig, symbol, "ask1", str(depth["asks"][0][0]))
        safe_set_val(marketConfig, symbol, "ask1_amt",
                     str(int(depth["asks"][0][1])) if is_swap(symbol) else str(depth["asks"][0][1]))
        # 固定汇率计算（始终需要）
        if is_usd_swap_symbol(symbol) and ("XPL" in symbol or "ORDI" in symbol or "OKB" in symbol):
            set_t1_t2_swap("XPL", "ORDI")
            set_t1_t2_swap("XPL", "OKB")
            set_t1_t2_swap("OKB", "ORDI")
        if is_usdt_symbol(symbol) and ("XPL" in symbol or "ORDI" in symbol or "OKB" in symbol):
            set_t1_t2("XPL", "ORDI")
            set_t1_t2("XPL", "OKB")
            set_t1_t2("OKB", "ORDI")
        # 动态更新注册的 HF 汇率对（通过策略页面新增的）
        token = symbol.split('-')[0]
        if token in _hf_pairs:
            done = set()
            for t1, t2, is_swap_pair in _hf_pairs[token]:
                pair_key = (t1, t2, is_swap_pair)
                if pair_key not in done:
                    done.add(pair_key)
                    if is_swap_pair:
                        set_t1_t2_swap(t1, t2)
                    else:
                        set_t1_t2(t1, t2)
        write_snapshot(marketConfig, MARKET_PATH)


def get_klines(client):
    klines = get_market_price_info(client.SYMBOL_T)[client.period]
    ms = get_ms()
    if ms - klines["version"] > OUTDATED_MS and klines["pending"] < MAX_PENDING:
        ts = int(klines['data'][0][5]) if len(klines['data']) > 0 else ''
        client.get_klines(client.SYMBOL_T, client.period, client.size2, ts)


kline_task_symbols = []
depth_task_symbols = []


def start_kline_task(client):
    if is_spec_swap_symbol(client.SYMBOL_T) or is_spec_symbol(client.SYMBOL_T):
        return
    kline_symbol = f"{client.SYMBOL_T}"
    # kline_symbol = f"{client.SYMBOL_T}-{client.period}"
    if kline_symbol in kline_task_symbols:
        logger.info(f"duplicate kline_task {kline_symbol}")
        return
    logger.info(f"START kline_task {kline_symbol}")
    kline_task_symbols.append(kline_symbol)
    get_market_price_info(client.SYMBOL_T)
    priceInfo[client.SYMBOL_T][client.period] = {"version": 0, "data": [], "pending": 0}
    sleep = 1 if client.period == "1m" else 10 if client.period == "1D" else 0.2 if client.period == "1s" else 1
    logger.warning(
        f"kline_task_symbols: {kline_task_symbols},kline_symbol:{kline_symbol},sleep:{sleep},period:{client.period}")
    if client.period == '1s':
        now = get_ms()
        ts = now - (client.size2 + 3) * 1000
        i = 1
        client.get_klines(client.SYMBOL_T, client.period, client.size2, ts)
        gevent.sleep(1)
        logger.warning(
            f"{kline_symbol} pre loading {i} {len(get_market_price_info(client.SYMBOL_T)[client.period]['data'])}")
        while len(get_market_price_info(client.SYMBOL_T)[client.period]['data']) < client.size2:
            i += 1
            get_klines(client)
            logger.warning(
                f"{kline_symbol} pre loading {i} {len(get_market_price_info(client.SYMBOL_T)[client.period]['data'])}")
            gevent.sleep(sleep)
    logger.warning(f"start_kline_task {kline_symbol}")
    # threading.Thread(target=kline_task, args=(client, sleep,)).start()
    if client.method == 'api':
        logger.info(f"thread kline task start:{client.SYMBOL_T}")
        threading.Thread(target=kline_task, args=(client, sleep,)).start()
    else:
        ws_kline_task(client)


def kline_task(client, sleep):
    while True:
        try:
            get_klines(client)
            gevent.sleep(sleep)
        except Exception as e:
            logger.error("get_kline_data err:{}".format(str(e)))


def on_ws_kline_data(message):
    message = json.loads(message)
    if message.get('arg') and message.get('arg').get('channel') == 'candle1s' and message.get('data'):
        data = message.get('data')[0]
        symbol = message.get('arg').get('instId')
        data = [float(data[1]), float(data[2]), float(data[3]), float(data[4]), float(data[5]), data[0]]
        set_market_klines(symbol, "1s", [data], 300)


def ws_kline_task(client):
    params = [{"channel": "candle1s", "instId": client.SYMBOL_T, "instType": client.type}]
    logger.info(f"ws kline task start: {params}")
    ws_business.subscribe(params, on_ws_kline_data)


def on_ws_depth_data(message):
    message = json.loads(message)
    event = message.get('event')
    channel = message.get('arg').get('channel') if message.get('arg') is not None else None
    if event == 'unsubscribe' or event == 'subscribe':
        logger.warning(message)
        return
    if ('books' in channel or 'tbt' in channel) and message.get('data'):
        data = message.get('data')[0]
        symbol = message.get('arg').get('instId')
        asks = list(map(lambda x: list(map(lambda d: float(d), x)), data["asks"]))
        bids = list(map(lambda x: list(map(lambda d: float(d), x)), data["bids"]))
        if 'books' == channel:
            depth = get_market_price_info(symbol)["depth"]
            merge_depth = merge_order_book(depth, {'asks': asks, 'bids': bids})
            asks = merge_depth['asks']
            bids = merge_depth['bids']
        set_market_depth(symbol, asks, bids)
        persist_market(symbol)


def ws_depth_task(client, _ws):
    params = [{"channel": client.channel, "instId": client.SYMBOL_T, "instType": client.type}]
    logger.info(f"ws depth task start:{params}")
    _ws.subscribe(params, on_ws_depth_data)
    if client.old_channel:
        params = [{"channel": client.old_channel, "instId": client.SYMBOL_T, "instType": client.type}]
        _ws.unsubscribe(params, on_ws_depth_data)


def start_depth_task(client, _ws=ws):
    if client.old_channel:
        depth_task_symbols.remove(client.SYMBOL_T)
    if is_spec_swap_symbol(client.SYMBOL_T) or is_spec_symbol(client.SYMBOL_T):
        register_hf_pair(client.SYMBOL_T)
        # 确保组件币种的深度已订阅（HF 依赖组件币种的行情数据）
        if is_spec_swap_symbol(client.SYMBOL_T):
            component_symbols = get_split_swap_symbols(client.SYMBOL_T)
        else:
            component_symbols = get_split_symbols(client.SYMBOL_T)
        for comp_sym in component_symbols:
            if comp_sym not in depth_task_symbols:
                import copy
                _comp_client = copy.copy(client)
                _comp_client.SYMBOL_T = comp_sym
                _comp_client.type = 'SWAP' if 'SWAP' in comp_sym else 'SPOT'
                _comp_client.old_channel = None
                _comp_client.channel = 'books5'
                logger.warning(f"HF auto-subscribe component: {comp_sym}")
                # 递归调用自身（组件币不是 spec symbol，会走正常订阅流程）
                start_depth_task(_comp_client, _ws)
        return
    if client.SYMBOL_T in depth_task_symbols:
        logger.warning(f"duplicate depth_task {client.SYMBOL_T}")
        return
    logger.warning(f"START depth_task {client.SYMBOL_T} {client.channel}")
    depth_task_symbols.append(client.SYMBOL_T)
    with market_lock:
        if not marketConfig.has_section(client.SYMBOL_T):
            marketConfig.add_section(client.SYMBOL_T)
    logger.warning(f"depth_task_symbols: {depth_task_symbols}")
    get_depth(client)
    if client.method == 'api':
        logger.info(f"thread depth task start:{client.SYMBOL_T}")
        threading.Thread(target=depth_task, args=(client,)).start()
    else:
        ws_depth_task(client, _ws)


def depth_task(client):
    task_channel = client.channel
    while task_channel == client.channel:
        try:
            get_depth(client)
            gevent.sleep(0.02)
        except Exception as e:
            logger.error("get_depth_data err:{}".format(str(e)))


def ws_stop_task(channel, symbol, _ws=ws2):
    logger.warning(f"stop_depth_task channel:{channel} instId:{symbol}")
    _ws.unsubscribe([{"channel": channel, "instId": symbol}], on_ws_depth_data)
    depth_task_symbols.remove(symbol)
    logger.warning(f"depth_task_symbols: {depth_task_symbols}")


def on_ws_stop(data):
    logger.warning(data)


def start_market_task(client):
    symbols = []
    client.symbols = json.loads(safe_get_val(client.config, "trade", "symbol", '[]'))
    while True:
        for smb in client.symbols:
            if smb not in symbols:
                _client = copy.deepcopy(client)
                _client.set_symbol(smb, client.config)
                start_depth_task(_client, ws2)
                logger.warning(f'start {smb}')
        for smb in symbols:
            if smb not in client.symbols:
                ws_stop_task(client.channel, smb, ws2)
                logger.warning(f'stop {smb}')
        symbols = client.symbols
        gevent.sleep(1)
