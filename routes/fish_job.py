import configparser
import time
import traceback

from . import server_core
from api.okex_sdk_v5.Trade_api import OPEN, CLOSE, MANUAL, FISH
from .server_core import (
    FISHNET_PATH, FISHNET_PATH2,
    refresh_market_snapshot, user_job, job_users, active_job_users,
    JOB_STOPPED, get_order_list, get_market_price,
    get_split_symbols, get_symbol_lite,
    is_fish, is_fish_close,
    send_msg,
)
from .trading_core import (
    do_make_order, fill_cost,
    remake_expire_orders,
)
from module.Logger import logger
from util.ServerUtil import get_api, get_ms, safe_get_val, safe_set_val, write_config
from util.DataUtil import get_today_ts
from util.IM import push_msg, push_reload


def _get_target_price(symbol, side, fish, make_list):
    for _ in range(50):
        try:
            option = "bid1" if side == 'sell' else "ask1"
            price = float(refresh_market_snapshot()[symbol][option])
            break
        except Exception:
            time.sleep(0.02)
    else:
        raise RuntimeError(f"failed to get market price for {symbol} after 50 retries")
    target = 0
    for i in make_list:
        if (price > i and side == 'sell') or (price < i and side == 'buy'):
            target = i
            break
    if target != 0:
        target = round(target + fish, 4) if side == 'sell' else round(target - fish, 4)
    else:
        target = make_list[-1] if side == 'sell' else make_list[0]
    return target, price


def _pre_make_orders(user, side, rev_side, target, make_list, data):
    logger.warning(f"JOB_USER : {user},pre make orders")
    symbol = user_job[user]['symbol']
    amount = user_job[user]['amount']
    fish = user_job[user]['fish']
    rev_orders = list(map(lambda x: float(x['px']), filter(lambda x: x['side'] == rev_side, data)))
    check = False
    for i in range(len(make_list) - 1):
        price = make_list[i]
        if (side == 'sell' and price >= target) or (side == 'buy' and price <= target):
            continue
        price = round(price - fish, 4) if side == 'sell' else round(price + fish, 4)
        exists = list(filter(lambda p: p + fish / 2 > price, rev_orders)) if side == 'sell' else list(
            filter(lambda p: p - fish / 2 < price, rev_orders))
        if len(exists) == 0:
            push_msg(user, f"pre make order: {price} {rev_side} {amount}")
            do_make_order(user, symbol, rev_side, price, amount, False, fish, False, f'{user}fishpre')
            time.sleep(0.1)
            check = True
    return check


def _check_fish_order(user, job_info, _orders):
    if len(job_info['fishOrder']) == 0:
        return
    _orders = list(map(lambda x: x['clOrdId'], _orders))
    check_orders = list(filter(lambda x: x['clOrdId'] not in _orders, job_info['fishOrder']))
    if len(check_orders) == 0:
        return
    for order in check_orders:
        if not is_fish_close(order):
            continue
        cid = order['clOrdId']
        order_api = get_api(user)
        resp = order_api.check_order(user, order['instId'], cid, 3)
        rev_cid = cid.replace(CLOSE, OPEN)
        resp2 = order_api.check_order(user, order['instId'], rev_cid, 3)
        if order_api.resp_filled(resp) and order_api.resp_filled(resp2):
            side = resp['data'][0]['side']
            symbol = resp['data'][0]['instId']
            fill_amount = int(resp['data'][0]['accFillSz'])
            open_amount = int(resp2['data'][0]['accFillSz'])
            price = float(resp['data'][0]['avgPx'])
            earn = abs(int(open_amount - fill_amount))
            logger.info(f"earn:{earn}")
            fill_cost(user, symbol, earn, 'fish')
            message = f"[F] {'卖出' if side == 'sell' else '买入'} {symbol.split('-')[0]} {fill_amount}张，{price} 收获"
            push_msg(user, message)
            send_msg(user, message)
            server_core.unsafe_px = 0


def _check_manual_order(user, job_info, _orders):
    if len(job_info['manual']) == 0:
        return
    _orders = list(map(lambda x: x['clOrdId'], _orders))
    check_orders = list(filter(lambda x: x['clOrdId'] not in _orders, job_info['manual']))
    if len(check_orders) == 0:
        return
    ids = []
    inst_id = check_orders[0]['instId']
    for order in check_orders:
        if order['clOrdId'] not in ids:
            ids.append(order['clOrdId'])
    api = get_api(user)
    cache = {}
    for cid in ids:
        resp = api.check_order(user, inst_id, cid, 3) if cache.get(cid) is None else cache.get(cid)
        if api.resp_filled(resp):
            side = resp['data'][0]['side']
            symbol = resp['data'][0]['instId']
            price = round(float(resp['data'][0]['avgPx']), 4)
            fill_amount = float(resp['data'][0]['accFillSz'])
            message = f"[M] {'卖出' if side == 'sell' else '买入'} {symbol.split('-')[0]} {fill_amount}张，{price} 成交"
            push_msg(user, message)
            send_msg(user, message)
            if cid.find(OPEN) == -1 and cid.find(CLOSE) == -1:
                return
            is_close = cid.find(CLOSE) != -1
            rev_cid = cid.replace(CLOSE, OPEN) if is_close else cid.replace(OPEN, CLOSE)
            resp2 = api.check_order(user, inst_id, rev_cid, 3) if cache.get(rev_cid) is None else cache.get(rev_cid)
            logger.info(resp2)
            if api.resp_filled(resp2) and cache.get(cid) is None and cache.get(rev_cid) is None:
                fill_amount2 = float(resp2['data'][0]['accFillSz'])
                earn = abs(int(fill_amount - fill_amount2))
                logger.info(f"fill_cost {earn}")
                fill_cost(user, symbol, earn, 'manual')
                cache[rev_cid] = resp2
            cache[cid] = resp


def _call_job(user, job_info):
    start = job_info['start']
    stop = job_info['stop']
    fish = job_info['fish']
    side = job_info['side']
    amount = job_info['amount']
    make_list = job_info['list']
    symbol = job_info['symbol']
    version = job_info['version']
    overflow_tmp = job_info['overflow']
    enable = job_info['enable']
    epoch = job_info['epoch']
    now = get_ms()
    job_info['epoch'] = min(job_info['epoch'] + 1, 50)
    try:
        target_tmp = job_info['target']
        target, price1 = _get_target_price(symbol, side, fish, make_list)
        overflow = price1 >= start + fish or price1 <= stop - fish / 5 if side == 'buy' else price1 <= start - fish or price1 >= stop + fish / 5
        if overflow != overflow_tmp:
            job_info['overflow'] = overflow
        if now - version > epoch * 100:
            result = get_order_list(user, symbol, 10)
            if result is not None and result.get('code') == "0":
                if len(job_info['orders']) > 0 and len(job_info['orders']) != len(result['data']):
                    job_info['fishOrder'] and _check_fish_order(user, job_info, result['data'])
                    job_info['manual'] and _check_manual_order(user, job_info, result['data'])
                    push_reload(user, symbol)
                job_info['orders'] = result['data']
                job_info['version'] = get_ms()
                job_info['manual'] = list(
                    filter(lambda x: x['clOrdId'].find(f'{user}{MANUAL}'.upper()) != -1, result['data']))
                job_info['fishOrder'] = list(
                    filter(lambda x: x['clOrdId'].find(f'{user}{FISH}'.upper()) != -1, result['data']))
            else:
                return round(abs(target - price1) / fish, 2), target, price1
        if overflow or enable == 0:
            return 1, 0, 0
        if target != 0:
            if target != target_tmp:
                job_info['target'] = target
            if target_tmp != 0 and target_tmp is not None:
                skipped_prices = []
                skipped_fish_multipliers = []
                if side == 'sell' and price1 > target_tmp + fish:
                    n = int((price1 - target_tmp) / fish)
                    for i in range(n):
                        skipped_price = target_tmp + fish * i
                        skipped_price = round(skipped_price, 2)
                        if skipped_price > price1:
                            break
                        skipped_prices.append(skipped_price)
                        skipped_fish_multipliers.append(n - i + 1)
                elif side == 'buy' and price1 < target_tmp - fish:
                    n = int((target_tmp - price1) / fish)
                    for i in range(n):
                        skipped_price = target_tmp - fish * i
                        skipped_price = round(skipped_price, 2)
                        if skipped_price < price1:
                            break
                        skipped_prices.append(skipped_price)
                        skipped_fish_multipliers.append(n - i + 1)
                for skipped_price, multiplier in zip(skipped_prices, skipped_fish_multipliers):
                    do_make_order(user, symbol, side, '0', amount, True, fish * multiplier, True, f'{user}fish')
                    message = f"[补单] {'卖出' if side == 'sell' else '买入'} {symbol.split('-')[0]} {amount}张，{skipped_price} 补单 fish 倍数: {multiplier}"
                    logger.warning(message)
                    push_msg(user, message)
                    send_msg(user, message)
            if (job_info['fishOrder'] is None or len(job_info['fishOrder']) == 0) and (
                    (price1 < target and side == 'sell') or (price1 > target and side == 'buy')):
                return round(abs(target - price1) / fish, 2), target, price1
            for order in job_info['orders']:
                px = float(order['px'])
                if (px + fish * 2.5 > target and order['side'] == 'buy' and side == 'sell' and is_fish(order)) or \
                        (px - fish * 2.5 < target and order['side'] == 'sell' and side == 'buy' and is_fish(order)):
                    next_fish = abs(px + fish * 2 - target) > fish / 2 if side == 'sell' else abs(
                        px - fish * 2 - target) > fish / 2
                    if next_fish:
                        target = target + fish if side == 'sell' else target - fish
                    return round(abs(target - price1) / fish, 2), target, price1
            if abs(price1 - server_core.unsafe_px) < fish * 0.5:
                logger.warning(f"price: {price1} is unsafe[{server_core.unsafe_px}]")
                return 1, 0, 0
            logger.warning(f"[{user}] do make order, trigger price: {price1}")
            do_make_order(user, symbol, side, '0', amount, True, fish, True, f'{user}fish')
            message = f"[F] {'卖出' if side == 'sell' else '买入'} {symbol.split('-')[0]} {amount}张，{price1} 触发"
            server_core.unsafe_px = price1
            push_msg(user, message)
            send_msg(user, message)
            push_reload(user, symbol)
            job_info['version'] = 0
            job_info['epoch'] = 0
        return round(abs(target - price1) / fish, 2), target, price1
    except Exception as e:
        logger.warning(f"call_job err:{e},{traceback.format_exc()}")
        return 1, 0, 0


def _init_user_job(symbol):
    time.sleep(2)
    config = configparser.ConfigParser()
    config.read(FISHNET_PATH)
    job_user = config.get('job', 'user')
    for user in job_users:
        enable = int(config.get(user, 'enable'))
        if enable == 0:
            continue
        active_job_users.append(user)
        user_job[user]['enable'] = enable
        user_job[user]['start'] = float(safe_get_val(config, user, 'start', '0'))
        user_job[user]['stop'] = float(safe_get_val(config, user, 'stop', '0'))
        user_job[user]['gap'] = float(safe_get_val(config, user, 'gap', '0'))
        user_job[user]['fish'] = float(safe_get_val(config, user, 'fish', '0'))
        user_job[user]['amount'] = int(safe_get_val(config, user, 'amount', '0'))
        side = 'sell' if user_job[user]['start'] <= user_job[user]['stop'] else 'buy'
        orders = int(round(abs(round(user_job[user]['stop'] - user_job[user]['start'], 4)) / user_job[user]['gap'])) + 1
        make_list = []
        for i in range(orders):
            if side == 'sell':
                make_list.append(round(user_job[user]['start'] + user_job[user]['gap'] * i, 4))
            else:
                make_list.append(round(user_job[user]['start'] - user_job[user]['gap'] * i, 4))
        make_list.reverse()
        user_job[user]['list'] = make_list
        user_job[user]['side'] = side
        user_job[user]['total'] = orders * user_job[user]['amount']
        user_job[user]['symbol'] = symbol
        user_job[user]['target'] = None
        user_job[user]['orders'] = []
        user_job[user]['version'] = 0
        user_job[user]['epoch'] = 0
        user_job[user]['overflow'] = False
        user_job[user]['fishOrder'] = None
    return job_user


def do_job(symbol):
    job_user = _init_user_job(symbol)
    logger.warning(f"active job users :{active_job_users}, current job user: {job_user}")
    if len(active_job_users) == 0:
        logger.warning("no active job users, exit job")
        return
    for user in active_job_users:
        job_info = user_job[user]
        logger.warning(job_info)
        if job_user == user:
            logger.warning(f"JOB_USER : {user},init job, enable:{job_info['enable']}")
            rev_side = 'buy' if job_info['side'] == 'sell' else 'sell'
            target, price1 = _get_target_price(job_info['symbol'], job_info['side'], job_info['fish'], job_info['list'])
            result = get_order_list(user, job_info['symbol'], 10)
            if result is not None and result.get('code') == "0":
                check = remake_expire_orders(user, symbol, result['data'])
                if job_info['enable'] == 1:
                    check = _pre_make_orders(user, job_info['side'], rev_side, target, job_info['list'],
                                             result['data']) or check
                check and push_reload(user, job_info['symbol'])
    sleep_user = 1
    _today = 0
    remake = False
    while True:
        for user in active_job_users:
            if user in JOB_STOPPED:
                continue
            job_info = user_job[user]
            rate, target, price1 = _call_job(user, job_info)
            if job_info['epoch'] == 100:
                if target != 0 and abs(target - price1) / job_info['fish'] < 0.05:
                    logger.warning("reset epoch to 0")
                    job_info['epoch'] = 0
            sleep_user = job_info['epoch'] * 10 / 1000
        if get_today_ts() > _today:
            for user in active_job_users:
                remake = remake_expire_orders(user, symbol) or remake
            if remake:
                _today = get_today_ts()
                remake = False
        time.sleep(min(1, sleep_user))


def ltc_t(user):
    symbol = 'LTC-ORDI'
    config = configparser.ConfigParser()
    config.read(FISHNET_PATH2)
    enable = int(safe_get_val(config, user, 'enable', '0'))
    base = float(safe_get_val(config, user, 'base', '0'))
    amt = float(safe_get_val(config, user, 'amt', '0'))
    pct = float(safe_get_val(config, user, 'pct', '3'))
    cnt = 0
    symbols = get_split_symbols(symbol)
    cid = f"{user}net{get_symbol_lite(symbol)}"
    price = float(get_market_price(symbol))
    nxt = base * (100 + pct) / 100 if price > base else base * (100 - pct) / 100
    logger.warning(f"[{user}] {symbol} start, price: {price}, nxt: {nxt}, amt:{amt} pct:{pct}")
    while enable == 1:
        price = float(get_market_price(symbol))
        if price > base:
            nxt = base * (100 + pct) / 100
            if price > nxt:
                trade_api = get_api(user)
                resp = trade_api.batch_swap2(user, 'sell', amt, cid, symbols)
                if trade_api.resp_filled(resp):
                    base = price
                    safe_set_val(config, user, 'base', base)
                    write_config(FISHNET_PATH2, config)
                    push_reload(user, symbol)
                    message = f"[O] {symbol}已成交，价格：{base}"
                    push_msg(user, message)
                    send_msg(user, message)
                else:
                    safe_set_val(config, user, 'enable', 0)
                    write_config(FISHNET_PATH2, config)
                    message = f"[O] {symbol}交易异常，已停用"
                    push_msg(user, message)
                    send_msg(user, message)
                    break
        elif price < base:
            nxt = base * (100 - pct) / 100
            if price < nxt:
                trade_api = get_api(user)
                resp = trade_api.batch_swap2(user, 'buy', amt * price * (100 + pct / 2) / 100, cid, symbols)
                if trade_api.resp_filled(resp):
                    base = price
                    safe_set_val(config, user, 'base', base)
                    write_config(FISHNET_PATH2, config)
                    push_reload(user, symbol)
                    message = f"[O] {symbol}已成交，价格：{base}"
                    push_msg(user, message)
                    send_msg(user, message)
                else:
                    safe_set_val(config, user, 'enable', 0)
                    write_config(FISHNET_PATH2, config)
                    message = f"[O] {symbol}交易异常，已停用"
                    push_msg(user, message)
                    send_msg(user, message)
                    break
        if cnt % 6000 == 0:
            cnt = 0 if cnt == 600 else cnt
        cnt += 1
        time.sleep(1)
