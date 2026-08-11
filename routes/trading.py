import copy
import json
import math
import os
import subprocess

import gevent

from flask import Blueprint, Response, request

from api.okex_sdk_v5.Trade_api import OPEN, CLOSE, MANUAL
from .server_core import (
    FISHNET_PATH, PRICE_TMP,
    get_symbol, get_all_symbol, get_stat_symbols, get_config, get_market_price,
    is_spec_swap_symbol, get_split_swap_symbols,
    is_spec_symbol, get_split_symbols, get_symbol_lite,
    get_symbol_balance, get_symbol_positions, get_symbol_counts,
    get_limit_info, get_order_list,
    do_restart, markerUserConfig, MARKET_USER_PATH,
    fishConfig,
)
from .trading_core import do_make_order, do_cancel_orders, get_mt_dir
from module.Logger import logger
from util.ServerUtil import (
    KEY_PATH, admins, auth_user, get_api, get_sid, get_user, require_auth,
    safe_get_val, set_mask_symbol, user_version, write_config, write_key,
)
from util.DataUtil import get_all, get_log, get_log_b
from util.ActiveUser import get_alive_users
from util.IM import push_refresh

trading_bp = Blueprint('trading', __name__)


@trading_bp.route('/mask', methods=['post'])
@require_auth('r')
def mask():
    req_data = json.loads(request.data)
    symbol_mask = req_data.get('symbol')
    sid = get_sid()
    if symbol_mask == "CLEAR" or get_symbol(True) == symbol_mask:
        set_mask_symbol(sid, None)
    else:
        set_mask_symbol(sid, symbol_mask)
    return "1"


@trading_bp.route('/hello', methods=['post'])
@require_auth('r')
def hello():
    user_info = copy.copy(user_version())
    if user_info is not None:
        user_info['symbol'] = get_symbol()
        user_info['symbols'] = get_all_symbol()
        user_info['stats'] = get_stat_symbols()
    return user_info


@trading_bp.route('/login', methods=['post'])
def login():
    return auth_user()


@trading_bp.route('/count', methods=['post'])
@require_auth('r')
def count():
    user = get_user()
    symbol = get_symbol()
    symbols = get_all_symbol() if symbol == '*' else get_split_swap_symbols(symbol) if is_spec_swap_symbol(
        symbol) else get_split_symbols(
        symbol) if is_spec_symbol(symbol) else [symbol]
    # 限价档位查询与各币种余额/持仓互不依赖，一并发出避免多一次串行网络往返
    g_limit = gevent.spawn(get_limit_info, user, symbol)
    per_symbol_tasks = []
    for sym in symbols:
        ccy = sym.split('-')[1] if sym.find("-ETH") != -1 or sym.find("-BTC") != -1 else sym.split('-')[0]
        g_bal = gevent.spawn(get_symbol_balance, ccy, user)
        g_pos = gevent.spawn(get_symbol_positions, sym, user)
        per_symbol_tasks.append((sym, g_bal, g_pos))
    gevent.joinall([g_limit] + [t for _, b, p in per_symbol_tasks for t in (b, p)])
    limit_info = g_limit.get()
    results = []
    for sym, g_bal, g_pos in per_symbol_tasks:
        balance, ratio = g_bal.value
        volume, direction, explode = g_pos.value
        day, month = get_symbol_counts(sym)
        results.append(
            {'day': round(day, 4), 'month': round(month, 4), 'balance': balance, 'ratio': ratio, 'volume': volume,
             'direction': direction, 'explode': explode, 'limit': limit_info[0], 'state': limit_info[1]})
    return json.dumps(results)


@trading_bp.route('/orders', methods=['post'])
@require_auth('r')
def orders():
    user = get_user()
    symbol = get_symbol()
    if symbol == '*':
        return Response('[]', mimetype='application/json; charset=utf-8')
    result = get_order_list(user, symbol, 3)
    data = '[]'
    if result is not None and result.get('code') == "0":
        data = json.dumps(result['data'])
    return Response(data, mimetype='application/json; charset=utf-8')


@trading_bp.route('/make-order', methods=['post'])
@require_auth('w')
def make_order():
    user = get_user()
    symbol = get_symbol()
    if symbol == '*':
        return "0"
    data = json.loads(request.data)
    type = data['type']
    price = data['price']
    amount = data['amount']
    adjust = data['adjust'] if data.get('adjust') is not None else False
    is_mt = data.get('mt') is not None
    is_fish_pre = data.get('fish') is not None and not is_mt
    tt = data['tt'] if data.get('tt') is not None and not is_fish_pre and not is_mt else False
    diff = data['diff'] if data.get("diff") is not None else 1
    mt_dir = get_mt_dir(user, symbol, type) if is_mt else ''
    cid = f'{user}MT{mt_dir}' if is_mt else f'{user}fishpre' if is_fish_pre else f'{user}{MANUAL}'
    logger.warning(f"make_order:{(user, symbol, type, price, amount, tt, diff, adjust, cid)}")
    return do_make_order(user, symbol, type, price, amount, tt, diff, adjust, cid)


@trading_bp.route('/cancel-order', methods=['post'])
@require_auth('w')
def cancel_order():
    user = get_user()
    symbol = get_symbol()
    data = json.loads(request.data)
    return do_cancel_orders(user, symbol, [data['orderId']])


@trading_bp.route('/batch-cancel-order', methods=['post'])
@require_auth('w')
def batch_cancel_order():
    user = get_user()
    symbol = get_symbol()
    data = json.loads(request.data)
    return do_cancel_orders(user, symbol, data['orderIds'])


@trading_bp.route('/flash', methods=['post'])
@require_auth('w')
def flash():
    user = get_user()
    data = json.loads(request.data)
    order = data.get('order')
    cid = order.get('clOrdId')
    symbol = order.get('instId')
    symbol_lite = get_symbol_lite(symbol)
    side = order.get('side')
    fill_sz = float(order.get('accFillSz'))
    trade_api = get_api(user)
    sz = float(order['sz']) - fill_sz
    if cid.find(f"{MANUAL}{symbol_lite}{CLOSE}") != -1:
        rev_cid = cid.replace(f"{MANUAL}{symbol_lite}{CLOSE}", f"{MANUAL}{symbol_lite}{OPEN}")
        resp = trade_api.check_order(user, symbol, rev_cid, 3)
        if trade_api.resp_filled(resp):
            open_sz = float(resp['data'][0]['accFillSz'])
            price = float(resp['data'][0]['avgPx'])
            market_price = float(get_market_price(symbol))
            if (side == 'sell' and market_price > price) or (side == 'buy' and market_price < price):
                earn = abs(price - market_price) / max(price, market_price) * int(open_sz) * 0.996
                config = get_config(user)
                cost = float(safe_get_val(config, symbol, "cost", '0'))
                earn = math.floor(earn * cost / (cost - market_price)) if cost > market_price else math.floor(earn)
                sz = open_sz + earn - fill_sz if side == 'sell' else open_sz - earn - fill_sz
            else:
                sz = open_sz - fill_sz
    if do_cancel_orders(user, symbol, [order['ordId']]) == "0":
        return "0"
    resp = trade_api.place_instant_order(user, symbol, order['tdMode'], side, sz, order['posSide'], cid)
    return "1" if trade_api.resp_filled(resp) else "0"


@trading_bp.route('/fix', methods=['post'])
@require_auth('w')
def fix():
    user = get_user()
    logger.warning(f"{user} do fix")
    backup_path = os.environ.get("MARTIN_KEY_BACKUP_PATH", f"{KEY_PATH}.bak")
    subprocess.Popen(["cp", "-f", backup_path, KEY_PATH],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return "1"


@trading_bp.route('/restart', methods=['post'])
@require_auth('w')
def restart():
    user = get_user()
    write_key(user, "enable", "1")
    do_restart()
    return "1"


@trading_bp.route('/shutdown', methods=['post'])
@require_auth('w')
def shutdown():
    user = get_user()
    write_key(user, "enable", "0")
    subprocess.Popen(["service", "ok", "restart"],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return "1"


@trading_bp.route('/update', methods=['post'])
@require_auth('w')
def update():
    fishConfig.read(FISHNET_PATH)
    fishConfig.set('job', 'user', get_user())
    write_config(FISHNET_PATH, fishConfig)
    markerUserConfig.read(MARKET_USER_PATH)
    markerUserConfig.set('signal', 'update', str(1))
    write_config(MARKET_USER_PATH, markerUserConfig)
    subprocess.Popen(["service", "cfg", "restart"],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return "1"


@trading_bp.route('/active-users', methods=['post'])
@require_auth('w')
def active_users():
    users = get_alive_users()
    return Response(json.dumps(users), mimetype='application/json; charset=utf-8')


@trading_bp.route('/refresh', methods=['post'])
@require_auth('w')
def refresh():
    users = get_alive_users()
    for user in users:
        push_refresh(user['user'])
    return "1"


@trading_bp.route('/market-price', methods=['post'])
@require_auth('r')
def query_market_price():
    req_data = json.loads(request.data)
    symbol = req_data.get('symbol')
    return Response(json.dumps(PRICE_TMP.get(symbol)), mimetype='application/json; charset=utf-8')


@trading_bp.route('/log', methods=['post'])
@require_auth('r')
def log():
    user = get_user()
    if user in admins:
        return get_log_b('ok/nohup.out')
    log_text = get_log(user, 'ok/log.txt')
    return log_text if log_text.strip() != "" else "empty!"


@trading_bp.route('/log-bg', methods=['post'])
@require_auth('r')
def log_bg():
    return get_log_b('nohup.out')


@trading_bp.route('/xpl-monitor', methods=['post'])
@require_auth('r')
def xpl_monitor():
    return get_all('xpl_monitor_log.txt')
