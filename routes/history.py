import datetime
import sys

import gevent

from flask import Blueprint, request

from .server_core import (
    get_symbol, get_all_symbol, get_market_price,
    get_month_history_price, is_spec_symbol, is_spec_swap_symbol,
    get_split_symbols, get_split_swap_symbols,
    is_fish, is_manual_order, is_spec_cid, is_user_cid,
    get_last_order,
    TRANSFER_CACHE, HISTORY_CACHE, last_orders,
)
from .month_stat import compute_month_outcome
import json
import os

from module.Logger import logger
from util.ServerUtil import (
    get_api, get_ms, get_user, require_auth, write_config_text,
)
from util.DataUtil import (
    copy_obj, get_last_lines, get_today_ts, log_to_order, order_to_log,
)

history_bp = Blueprint('history', __name__)

MONTH_HISTORY_DELTA_BASE = -99
MONTH_HISTORY_DELTA_THIS_YEAR = -3
MONTH_HISTORY_DELTA_ALL = -2
MONTH_HISTORY_DELTA_TODAY = -1
MONTH_HISTORY_BASE_BEGIN_MS = 1738598400000 - 1

_ORDER_VERSION_CACHE = {}
_USER_ORDERS_CACHE = {}
_HEAD_BYTES = 128


def _get_month_history_begin(delta):
    if delta == MONTH_HISTORY_DELTA_BASE:
        return MONTH_HISTORY_BASE_BEGIN_MS, MONTH_HISTORY_BASE_BEGIN_MS
    if delta == MONTH_HISTORY_DELTA_ALL:
        return 0, 0

    today = datetime.datetime.today()
    if delta == MONTH_HISTORY_DELTA_THIS_YEAR:
        first_day = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        month = today.month if delta < 0 else today.month - delta
        year = today.year if delta < 0 or month > 0 else today.year - 1
        month = month if month > 0 else month + 12
        day = today.day if delta == MONTH_HISTORY_DELTA_TODAY else 1
        first_day = today.replace(year=year, month=month, day=day, hour=0, minute=0, second=0, microsecond=0)

    day_delta = 1 if delta < 0 else 3
    begin = int(first_day.timestamp() * 1000)
    begin_query = int((first_day.timestamp() - day_delta * 3600 * 24) * 1000)
    return begin, begin_query


def _invalidate_order_cache(file):
    _USER_ORDERS_CACHE.pop(file, None)
    stale_keys = [k for k in _ORDER_VERSION_CACHE if k[0] == file]
    for k in stale_keys:
        _ORDER_VERSION_CACHE.pop(k, None)


def get_user_order_version(user, symbol, offset=sys.maxsize):
    file = _get_user_order_file(user, symbol)
    if not os.path.exists(file):
        return 0, []
    try:
        mtime = os.path.getmtime(file)
    except OSError:
        mtime = 0
    key = (file, offset)
    cached = _ORDER_VERSION_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    last_lines = get_last_lines(file, offset)
    version = int(last_lines[0][4]) if len(last_lines) > 0 else 0
    ord_ids = list(map(lambda x: x[1], last_lines)) if len(last_lines) > 0 else []
    result = (version, ord_ids)
    _ORDER_VERSION_CACHE[key] = (mtime, result)
    return result


def _get_user_order_file(user, symbol):
    path = f"order/{user}_{symbol}"
    if not os.path.exists(path.split("/")[0]):
        os.makedirs(path.split("/")[0])
    if not os.path.exists(path):
        write_config_text(path, "")
    return path


def _check_user_orders(user, symbol, data):
    file = _get_user_order_file(user, symbol)
    user_orders = get_user_orders(user, symbol)
    existing_ids = {x['ordId'] for x in user_orders}
    data_check = []
    for x in data:
        if x['ordId'] not in existing_ids:
            data_check.append(x)
            existing_ids.add(x['ordId'])
    order_id_remove = 0
    seen_ids = set()
    user_orders_distinct = []
    for order in user_orders:
        ord_id = order['ordId']
        if ord_id in seen_ids:
            order_id_remove += 1
            continue
        user_orders_distinct.append(order)
        seen_ids.add(ord_id)
    for order in data_check:
        ord_id = order['ordId']
        if ord_id in seen_ids:
            order_id_remove += 1
            continue
        user_orders_distinct.append(order)
        seen_ids.add(ord_id)
    logger.info(
        f"[{user}]{symbol} user_orders:{len(user_orders) + len(data_check)},data:{len(data)},data_check:{len(data_check)},removed:{order_id_remove}")
    if len(data_check) > 0 or order_id_remove > 0:
        user_orders_distinct.sort(key=lambda o: o['uTime'], reverse=False)
        with open(file, 'w') as f:
            f.write("")
            for order in user_orders_distinct:
                f.writelines(f"{order_to_log(order)}\n")
        _invalidate_order_cache(file)


def _save_user_orders(user, symbol, data, version, ord_ids):
    file = _get_user_order_file(user, symbol)
    cnt = 0
    ord_ids_set = set(ord_ids) if ord_ids else set()
    with open(file, 'a') as f:
        data = sorted(data, key=lambda o: o['uTime'], reverse=False)
        for line in data:
            if int(line['uTime']) >= version and line['ordId'] not in ord_ids_set:
                f.writelines(f"{order_to_log(line)}\n")
                cnt = cnt + 1
                ord_ids.append(line['ordId'])
                ord_ids_set.add(line['ordId'])
    if cnt > 0:
        logger.info(f"{user} {symbol} {cnt} order persisted!")


def get_user_orders(user, symbol):
    file = _get_user_order_file(user, symbol)
    if not os.path.exists(file):
        return []
    try:
        st = os.stat(file)
    except OSError:
        return []
    mtime, size = st.st_mtime, st.st_size
    cached = _USER_ORDERS_CACHE.get(file)
    if cached is not None and cached['mtime'] == mtime and cached['size'] == size:
        return cached['data']
    if (cached is not None
            and size > cached['size']
            and cached['head']
            and size >= len(cached['head'])):
        try:
            with open(file, 'rb') as f:
                head = f.read(len(cached['head']))
                if head == cached['head']:
                    f.seek(cached['size'])
                    tail = f.read()
                    data = cached['data']
                    for line in tail.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        data.append(log_to_order(symbol, line))
                    _USER_ORDERS_CACHE[file] = {'mtime': mtime, 'size': size,
                                                'head': cached['head'], 'data': data}
                    return data
        except Exception:
            pass
    data = []
    head = b''
    try:
        with open(file, 'rb') as f:
            head = f.read(_HEAD_BYTES)
            f.seek(0)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data.append(log_to_order(symbol, line))
    except Exception:
        pass
    _USER_ORDERS_CACHE[file] = {'mtime': mtime, 'size': size, 'head': head, 'data': data}
    return data


def _should_include_history_order(order, user, symbol, request_symbol, _type):
    cid = order['clOrdId']
    is_user = is_user_cid(cid, user)
    is_manual = is_manual_order(cid)
    fish = is_fish(order)
    if not is_user and _type != 'all':
        return False
    if _type == 'user' and (not is_spec_cid(cid, symbol) or is_manual or fish):
        return False
    if _type == 'manual' and (not is_manual or not is_spec_cid(cid, request_symbol)):
        return False
    return True


def _get_user_history_orders_by_time(user, symbol, request_symbol, _type, start_time=None, end_time=None):
    orders = []
    for order in reversed(get_user_orders(user, symbol)):
        if not _should_include_history_order(order, user, symbol, request_symbol, _type):
            continue
        order_time = int(order['uTime'])
        if end_time is not None and order_time >= end_time:
            continue
        if start_time is not None and order_time < start_time:
            break
        orders.append(order)
    return orders


def _get_user_history_orders(user, symbol, _type, limit, offset=0, up=False):
    data = []
    cur = 0
    ts = get_today_ts() - (offset - 1) * 3600 * 24 * 1000
    te = get_today_ts() - offset * 3600 * 24 * 1000
    request_symbol = get_symbol()
    for order in reversed(get_user_orders(user, symbol)):
        if not _should_include_history_order(order, user, symbol, request_symbol, _type):
            continue
        if up:
            uTime = int(order['uTime'])
            if uTime > ts:
                continue
            cid = order['clOrdId']
            if uTime < te and ("SWAP" in symbol and "CLOS" in cid):
                break
            data.append(order)
        else:
            cur += 1
            if cur < offset * limit + 1:
                continue
            data.append(order)
            if len(data) >= limit:
                break
    return data


def _get_archive_history_data(user, inst_type, symbol, limit, state='', before='', after='', begin='', end=''):
    _count = 0
    result = None
    trade_api = get_api(user)
    while _count < 3:
        try:
            _count += 1
            result = trade_api.orders_history_archive(inst_type, "", symbol, limit=100 if limit > 100 else limit,
                                                      state=state, before=before, after=after, begin=begin, end=end)
            if result['code'] != '0':
                raise ValueError(result['msg'])
            break
        except Exception as e:
            logger.warning(f"get_orders_history err:{e},retry {_count}")
            gevent.sleep(0.2)
    if result is not None and result.get('code') == "0":
        return result['data']
    return []


def _fetch_order_and_persist(user, inst_type, symbol, check=None, begin='', end='', month=False):
    # 归档首页的请求参数不依赖挂单查询结果，先发出与挂单查询并行，省掉一次串行网络往返
    first_page = gevent.spawn(_get_archive_history_data, user, inst_type, symbol, 100, '',
                              before='', after='', begin=begin, end=end)
    if not month or user not in last_orders:
        get_last_order(user, symbol, 3)
    offset = last_orders[user][symbol][0] if not month else sys.maxsize
    version, ord_ids = get_user_order_version(user, symbol, offset) if check is None else (0, '')
    ord_ids_set = set(ord_ids) if ord_ids else set()
    data = []
    while True:
        if first_page is not None:
            resp = first_page.get()
            first_page = None
        else:
            after = data[-1].get("ordId") if len(data) > 0 else ''
            resp = _get_archive_history_data(user, inst_type, symbol, 100, '',
                                             before='', after=after, begin=begin, end=end)
        if len(resp) == 0:
            break
        hit_known = False
        for order in resp:
            if order['ordId'] in ord_ids_set:
                hit_known = True
                continue
            data.append(copy_obj(order))
        if hit_known:
            break
    new_orders = data
    if len(new_orders) > 0:
        please_check = len(list(filter(lambda x: int(x['uTime']) < version, new_orders))) > 0
        if please_check:
            logger.info(f"please_check version={version}")
        check = check or please_check
        check and _check_user_orders(user, symbol, data)
        if not check:
            if len(list(filter(lambda x: int(x['uTime']) >= version, new_orders))) > 0:
                _save_user_orders(user, symbol, data, version, ord_ids)


def _get_history_new(user, inst_type, _type, symbol, limit, offset, up):
    _fetch_order_and_persist(user, inst_type, symbol)
    return _get_user_history_orders(user, symbol, _type, limit, offset, up)


def _fetch_multi_history(user, _type, request_symbol, symbols, limit, offset):
    filtered_orders = {}
    upper_bound = None
    tasks = [gevent.spawn(_fetch_order_and_persist, user,
                          'SWAP' if 'SWAP' in sym else 'SPOT', sym)
             for sym in symbols]
    gevent.joinall(tasks)
    for sym in symbols:
        filtered_orders[sym] = _get_user_history_orders_by_time(user, sym, request_symbol, _type)
    page_data = []
    last = True
    for _ in range(offset + 1):
        page_candidates = {}
        tail_times = []
        for sym in symbols:
            orders = filtered_orders[sym]
            if upper_bound is None:
                visible = orders
            else:
                visible = list(filter(lambda order: int(order['uTime']) < upper_bound, orders))
            page_candidates[sym] = visible[:limit]
            if page_candidates[sym]:
                tail_times.append(int(page_candidates[sym][-1]['uTime']))
        if not tail_times:
            return {"data": [], "last": True}
        lower_bound = max(tail_times)
        page_data = []
        older_exists = False
        for sym in symbols:
            for order in filtered_orders[sym]:
                order_time = int(order['uTime'])
                if upper_bound is not None and order_time >= upper_bound:
                    continue
                if order_time < lower_bound:
                    older_exists = True
                    break
                page_data.append(order)
        page_data.sort(key=lambda order: int(order['uTime']), reverse=True)
        last = not older_exists
        upper_bound = lower_bound
    return {"data": page_data, "last": last}


def _fetch_history(user, _type, request_symbol, symbols, limit, offset):
    if len(symbols) > 1:
        return _fetch_multi_history(user, _type, request_symbol, symbols, limit, offset)
    all_data = []
    last = True
    day = datetime.datetime.today().day
    today_ts = get_today_ts()
    for sym in symbols:
        inst_type = 'SWAP' if 'SWAP' in sym else 'SPOT'
        up = HISTORY_CACHE.get(user + sym) == day
        data = _get_history_new(user, inst_type, _type, sym, limit, offset, up)
        all_data.extend(data)
        if len(data) == limit:
            last = False
        if not up and offset == 0 and len(data) == limit and data and int(data[-1]['cTime']) >= today_ts:
            logger.warning(f"{user} {sym} up!")
            HISTORY_CACHE[user + sym] = day
    all_data.sort(key=lambda o: o['uTime'], reverse=True)
    return {"data": all_data, "last": last}


@history_bp.route('/set-transfer', methods=['post'])
@require_auth('w')
def set_transfer():
    req_data = json.loads(request.data)
    cid = req_data.get('cid')
    idx = cid.find("TRANSFER")
    if idx == -1:
        TRANSFER_CACHE[cid] = 1
    else:
        TRANSFER_CACHE.pop(cid[0:idx])
    with open('TRANSFER_CACHE', 'w') as f:
        f.write(json.dumps(TRANSFER_CACHE))
    return "1"


@history_bp.route('/history', methods=['post'])
@require_auth('r')
def history():
    user = get_user()
    symbol = get_symbol()
    req_data = json.loads(request.data)
    _type = req_data.get('_type')
    offset = req_data.get('offset')
    offset = offset if offset is not None else 0
    limit = 100
    if is_spec_swap_symbol(symbol):
        symbols = get_split_swap_symbols(symbol)
    elif is_spec_symbol(symbol):
        symbols = get_split_symbols(symbol)
    else:
        symbols = get_all_symbol() if symbol == "*" else [symbol]
    result = _fetch_history(user, _type, symbol, symbols, limit, offset)
    return json.dumps(result)


@history_bp.route('/month-history', methods=['post'])
@require_auth('r')
def month_history():
    user = get_user()
    req_data = json.loads(request.data)
    check = req_data.get('check')
    symbol = req_data.get('symbol')
    delta = req_data.get('delta')
    inst_type = 'SWAP' if symbol.find("SWAP") != -1 else 'SPOT'
    begin, begin_query = _get_month_history_begin(delta)
    end = get_ms()
    _begin = str(begin_query) if check is None else str(begin)
    _end = str(end)
    is_spec = is_spec_symbol(symbol) or is_spec_swap_symbol(symbol)
    data = []
    price_task = None
    if not is_spec:
        # 行情价与订单拉取是两条互不依赖的网络往返，并行发出减少一次串行等待
        price_task = gevent.spawn(get_month_history_price, symbol, user)
        _fetch_order_and_persist(user, inst_type, symbol, check, _begin, _end, True)
        data = get_user_orders(user, symbol)
    data_f = []
    data = sorted(list(filter(lambda x: TRANSFER_CACHE.get(x['clOrdId']) is None, data)), key=lambda o: o['uTime'],
                  reverse=True)
    for order in data:
        if int(order['uTime']) >= begin:
            data_f.append(order)
        else:
            break
    data = data_f
    price = price_task.get() if len(data) > 0 else 0
    return json.dumps(compute_month_outcome(data, price), separators=(',', ':'))


@history_bp.route('/week-history', methods=['post'])
@require_auth('r')
def week_history():
    user = get_user()
    req_data = json.loads(request.data)
    symbol = req_data.get('symbol')
    is_spec = is_spec_symbol(symbol) or is_spec_swap_symbol(symbol)
    if is_spec:
        return json.dumps({'data': [], 'price': 0})
    inst_type = 'SWAP' if symbol.find("SWAP") != -1 else 'SPOT'
    today = datetime.datetime.today()
    delta = req_data.get('delta')
    today_begin = datetime.datetime.today().replace(year=today.year, month=today.month, day=today.day,
                                                    hour=0, minute=0, second=0, microsecond=0)
    today_ms = int(today_begin.timestamp()) * 1000
    one_day = 3600 * 24 * 1000
    if delta == 1:
        begin = today_ms - one_day * (today.weekday() + 7)
        end = today_ms - one_day * today.weekday() - 1
    elif delta == 2:
        first_day = datetime.datetime.today().replace(year=today.year, month=today.month, day=1, hour=0, minute=0,
                                                      second=0, microsecond=0)
        begin = int(first_day.timestamp() * 1000)
        end = get_ms()
    else:
        begin = today_ms - one_day * today.weekday()
        end = get_ms()
    all_local = get_user_orders(user, symbol)
    ord_ids_set = {o['ordId'] for o in all_local}
    new_orders = []
    while True:
        resp = _get_archive_history_data(user, inst_type, symbol, 100, '',
                                         after=new_orders[-1].get("ordId") if new_orders else '',
                                         begin=str(begin), end=str(end))
        if len(resp) == 0:
            break
        hit_known = False
        for order in resp:
            if order['ordId'] in ord_ids_set:
                hit_known = True
                continue
            new_orders.append(copy_obj(order))
        if hit_known:
            break
    local_in_window = [o for o in all_local if begin <= int(o['uTime']) <= end]
    data = sorted(new_orders + local_in_window, key=lambda o: o['uTime'], reverse=True)
    return json.dumps({'data': data, 'price': get_market_price(symbol)})
