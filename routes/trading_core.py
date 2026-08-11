import configparser
import json
import math
import traceback

from .server_core import (
    get_symbol_lite, is_spec_swap_symbol, get_split_swap_symbols,
    is_spec_symbol, get_split_symbols, get_market_price, get_config,
    get_order_list, active_job_users, user_job,
    JOB_STOPPED, FISHNET_PATH, do_restart,
)
from module.Logger import logger
from util.ServerUtil import (
    get_api, get_contract_position_info,
    safe_get_val, safe_set_val, write_config,
)
from util.DataUtil import get_today_ts
from util.IM import push_msg


def do_cancel_orders(user, symbol, order_ids):
    trade_api = get_api(user)
    try:
        orders_data = []
        for order_id in order_ids:
            orders_data.append({'instId': symbol, 'ordId': order_id})
        logger.info(f"batch cancel orders,order_ids:{order_ids}")
        result = trade_api.cancel_multiple_orders(orders_data)
        logger.info(f"batch cancel orders,result:{result}")
        if result is not None and result.get('code') == "0":
            return "1"
    except Exception as e:
        logger.warning(f"batch cancel order failed {e}")
    return '0'


def check_order_limit(config, user, symbol, type, amount):
    limit = int(safe_get_val(config, symbol, "limit", "0"))
    if limit == 0:
        return False
    available, direction = get_contract_position_info(user, symbol)
    after_order = available
    if direction == "net" or direction == "long":
        if type == 'buy':
            after_order += amount
        else:
            after_order -= amount
    elif direction == "short":
        if type == 'buy':
            after_order -= amount
        else:
            after_order += amount
    if abs(after_order) >= limit:
        JOB_STOPPED.append(user)
        logger.warning(f"[{user}]|order limit exceeded, volume:{available},order:{amount},limit:{limit}")
        return True
    return False


def transfer_order(user, counterpart_user, symbol, mode, type, ord_type, amount, cid, pft):
    buy_api = get_api(user)
    sell_api = get_api(counterpart_user)
    result = buy_api.place_order(user, symbol, mode, type, ord_type, amount, '', '', cid + "TRANSFER")
    if buy_api.resp_data(result):
        avg_price = float(result['data'][0]['avgPx'])
        diff = pft * float(avg_price) * float(avg_price) / (int(amount) * 10) if 'USD-SWAP' in symbol else pft
        result = sell_api.place_order(counterpart_user, symbol, mode, 'sell', 'limit', amount, '',
                                      round(avg_price + diff, 4), cid + "TRANSFER")
    return result


def do_make_order(user, symbol, type, price, amount, tt=False, pft=1, adjust=True, cid=''):
    cid = cid + get_symbol_lite(symbol)
    trade_api = get_api(user)
    config = get_config(user)
    trade_type = safe_get_val(config, symbol, "type", "SWAP" if symbol.find("SWAP") != -1 else "SPOT")
    if trade_type == 'SWAP' and 'fishpre' not in cid:
        if check_order_limit(config, user, symbol, type, int(amount)):
            return "order limit exceeded"
    earn_coin = float(safe_get_val(config, symbol, "earncoin", "0"))
    market_price = float(get_market_price(symbol))
    adjust = adjust and market_price >= earn_coin
    cost = float(safe_get_val(config, symbol, "cost", '0'))
    if not symbol or not type or not price or not amount:
        return "param error"
    ord_type = 'limit' if float(price) > 0 and f'{user}MT' not in cid else 'market'
    mode = 'cash' if trade_type == 'SPOT' else 'cross'
    logger.info(f'[{user}]|---------------------make {symbol} order------------------------------')
    try:
        if is_spec_swap_symbol(symbol, 'USDT'):
            market_price = float(get_market_price(symbol))
            result = trade_api.m_batch_swap2(user, type, int(amount), cid, get_split_swap_symbols(symbol), market_price,
                                             True)
        elif is_spec_symbol(symbol):
            market_price = float(get_market_price(symbol))
            result = trade_api.m_batch_swap2(user, type, float(amount), cid, get_split_symbols(symbol), market_price)
        else:
            if not tt:
                logger.warning(
                    f'[{user}]|------------------ {type} {amount} {price}-----------------------')
                result = trade_api.place_order(user, symbol, mode, type, ord_type, amount, '', price, cid)
            else:
                if float(price) > 0:
                    result = trade_api.place_multiple_orders_tt(user, symbol, mode, type, ord_type, amount, '', price,
                                                                pft, adjust, cost, cid)
                else:
                    transfer = int(safe_get_val(config, symbol, "transfer", "0"))
                    counterpart_user = safe_get_val(config, symbol, "transfer_user", "")
                    if transfer and type == 'buy' and counterpart_user:
                        result = transfer_order(user, counterpart_user, symbol, mode, type, ord_type, amount, cid, pft)
                    else:
                        price = get_market_price(symbol)
                        result = trade_api.place_orders_tt(user, symbol, mode, type, ord_type, amount, '',
                                                           price, pft, adjust, cost, cid)
                if user in active_job_users:
                    user_job[user]['version'] = 0
        if not trade_api.resp_data(result):
            logger.warning(f"[{user}]|order result: {result}")
        if result is not None and result.get('code') == "0" and len(result['data']) > 0:
            if trade_type == 'SWAP' and not tt and f'{user}MT' in cid:
                logger.warning(f"[{user}] {cid} {result['data'][0]}")
                reset_mt_statistics(user, symbol, result['data'][0])
            return "1"
    except Exception as e:
        logger.warning(f"[{user}]|make order failed: {e}, {traceback.format_exc()}")
    return 'order not succeed'


# --- Stats helpers ---
def get_statistics(user, symbol):
    config = get_config(user)
    cfg_field = f"{symbol}-stat"
    amount = transaction = price = avg_price = 0
    count = []
    try:
        amount = float(config.get(cfg_field, "amount"))
        transaction = float(config.get(cfg_field, "transaction"))
        price = float(config.get(cfg_field, "price"))
        avg_price = float(config.get(cfg_field, "avgprice"))
        count = json.loads(config.get(cfg_field, "count"))
    except Exception as err:
        if str(err).find("No section") > -1:
            config.add_section(cfg_field)
            config.set(cfg_field, "amount", str(amount))
            config.set(cfg_field, "transaction", str(transaction))
            config.set(cfg_field, "price", str(price))
            config.set(cfg_field, "avgprice", str(avg_price))
            config.set(cfg_field, "count", json.dumps(count))
    return config, amount, transaction, price, avg_price, count


def reset_mt_statistics(user, symbol, order):
    config, amount, transaction, price, avg_price, count = get_statistics(user, symbol)
    sz = int(order['accFillSz'])
    price = round(float(order['avgPx']), 2)
    side = order['side']
    amt = round(sz * 10 / price, 4)
    transaction += int(order['accFillSz']) * 10 if side == 'sell' else -int(order['accFillSz']) * 10
    amount += -amt if side == 'sell' else amt
    avg_price = abs(round(transaction / amount, 2))
    cfg_field = f"{symbol}-stat"
    config.set(cfg_field, "amount", str(amount))
    config.set(cfg_field, "transaction", str(transaction))
    config.set(cfg_field, "avgprice", str(avg_price))
    write_config(f"ok/{user}.ini", config)
    do_restart()


def get_mt_dir(user, symbol, _type):
    config, amount, transaction, price, avg_price, count = get_statistics(user, symbol)
    if _type == 'buy':
        if amount > 0:
            mt_dir = "LAPND"
        elif amount < 0:
            mt_dir = 'SCLOS'
        else:
            mt_dir = "LOPEN"
    else:
        if amount > 0:
            mt_dir = "LCLOS"
        elif amount < 0:
            mt_dir = 'SAPND'
        else:
            mt_dir = "SOPEN"
    return mt_dir


# --- Fill cost ---
def fill_cost(user, symbol, earn, _type):
    if earn == 0:
        return
    config = get_config(user)
    reduce = int(safe_get_val(config, symbol, 'reduce', '0'))
    cost = float(safe_get_val(config, symbol, 'cost', '0'))
    cost_fill = int(safe_get_val(config, symbol, 'costfill', '0'))
    cost_filled = int(safe_get_val(config, symbol, 'costfilled', '0'))
    _earn = int(safe_get_val(config, _type, 'earn', '0'))
    logger.info(f"cost:{cost},cost_fill:{cost_fill},_earn:{_earn}")
    if cost_fill != 0 and cost > 0:
        cost_fill -= earn
        cost_filled += earn
    _earn += earn
    logger.info(f"cost:{cost},cost_fill:{cost_fill},cost_filled:{cost_filled},{_type}_earn:{_earn}")
    if _type == 'manual':
        safe_set_val(config, symbol, 'reduce', str(reduce + 1))
    safe_set_val(config, symbol, 'costfill', str(cost_fill))
    safe_set_val(config, symbol, 'costfilled', str(cost_filled))
    safe_set_val(config, _type, 'earn', str(_earn))
    write_config(f"ok/{user}.ini", config)


# --- Remake helpers ---
def remake_multi_orders(user, expired_orders):
    trade_api = get_api(user)
    orders_data = list(
        map(lambda o: {'instId': o['instId'], 'tdMode': o['tdMode'], 'side': o['side'], 'ordType': o['ordType'],
                       'sz': int(o['sz']) - int(o['accFillSz']), 'ccy': '',
                       'clOrdId': o['clOrdId'], 'tag': o['tag'], 'posSide': o['posSide'], 'px': o['px'],
                       'reduceOnly': '', 'tgtCcy': ''}, expired_orders))
    for i in range(3):
        resp = None
        exp = False
        try:
            logger.info(f"remake_multi_orders,param: {orders_data}")
            resp = trade_api.place_multiple_orders(orders_data)
            logger.info(f"remake_multi_orders,resp: {resp}")
        except TimeoutError as e:
            logger.warning(f"remake_multi_orders timeout: {e}")
            exp = True
        except Exception as e:
            logger.warning(f"remake_multi_orders exp: {e}")
            exp = True
        if exp or trade_api.req_timeout(resp):
            logger.warning(f"remake_multi_orders retry:{i + 1}")
        else:
            break


def remake_expire_orders(user, symbol, expired_orders=None):
    if expired_orders is None:
        result = get_order_list(user, symbol, 10)
        expired_orders = result['data'] if result and len(result['data']) > 0 else []
    check = False
    config = configparser.ConfigParser()
    config.read(FISHNET_PATH)
    today_ts = get_today_ts()
    remake_ts = int(safe_get_val(config, "remake", user, 0))
    if today_ts > remake_ts:
        if len(expired_orders) > 0:
            logger.warning(f"JOB_USER : {user},remake expire orders")
            expired_orders = sorted(expired_orders, key=lambda o: o['px'], reverse=False)
            groups = math.ceil(len(expired_orders) / 20)
            for i in range(groups):
                _expired_orders = expired_orders[i * 20:(i + 1) * 20]
                order_ids = list(map(lambda o: o['ordId'], _expired_orders))
                push_msg(user, f"new day coming, re-order {repr(order_ids)}")
                resp = do_cancel_orders(user, symbol, order_ids)
                if resp == "1":
                    remake_multi_orders(user, _expired_orders)
                    check = True
            if check:
                safe_set_val(config, "remake", user, str(today_ts))
                write_config(FISHNET_PATH, config)
    return check
