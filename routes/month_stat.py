from decimal import Decimal, ROUND_HALF_UP
import math
import re

from util.DataUtil import from_time_stamp

FEE_BACK_RATE = 0.325
FEE_CCY = 'USDT'
_FLOAT_PREFIX = re.compile(r'^[+-]?(?:Infinity|(?:(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?))')


def js_to_fixed(value, digits):
    if math.isnan(value):
        return 'NaN'
    if math.isinf(value):
        return 'Infinity' if value > 0 else '-Infinity'
    if abs(value) >= 1e21:
        return str(value)
    quant = Decimal(1).scaleb(-digits) if digits > 0 else Decimal(1)
    return str(Decimal(value).quantize(quant, rounding=ROUND_HALF_UP))


def _parse_float(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).lstrip()
    match = _FLOAT_PREFIX.match(text)
    if match is None:
        return math.nan
    return float(match.group(0))


def _to_number(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == '':
        return 0
    try:
        return float(text)
    except ValueError:
        return math.nan


def _js_divide(numerator, denominator):
    if denominator == 0:
        if numerator == 0 or math.isnan(numerator):
            return math.nan
        return math.copysign(math.inf, numerator * denominator)
    return numerator / denominator


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _decimal_len(value):
    text = str(value)
    index = text.find('.')
    return 0 if index == -1 else len(text) - index - 1


def _usdt_swap_enlarge(inst_id):
    if 'BTC' in inst_id or 'ETH' in inst_id:
        return 100
    if 'OKB' in inst_id:
        return 0.01
    if 'ORDI' in inst_id:
        return 0.1
    if 'SATS' in inst_id:
        return 10000000
    return 10


def _swap_enlarge(inst_id):
    if 'BTC' in inst_id or 'ETH' in inst_id:
        return 100
    if 'ORDI' in inst_id:
        return 1
    return 10


def _format_time(ms):
    return from_time_stamp(int(int(ms) / 1000))


def compute_month_outcome(histories, market_price):
    if len(histories) == 0:
        return {'outcome': 0, 'change': 0}

    market_price_text = str(market_price)
    market_price_num = _to_number(market_price)
    change = 0
    change_abs = 0
    swap_change = 0
    swap_abs = 0
    outcome = 0
    fee = 0
    fee_ccy = FEE_CCY
    trx_ccy = ''
    sell = 0
    buy = 0
    swap_sell = 0
    swap_buy = 0
    buy_count = 0
    sell_count = 0
    start = 0
    start_time = None
    end_time = None

    inst_id = histories[0]['instId']
    is_swap = 'USD-SWAP' in inst_id
    is_usdt_swap = 'USDT-SWAP' in inst_id
    swap_enlarge = _swap_enlarge(inst_id) if is_swap else 1
    swap_enlarge = _usdt_swap_enlarge(inst_id) if is_usdt_swap else swap_enlarge
    trx_ccy = inst_id.split('-')[0]

    precision = 2
    for i, order in enumerate(histories):
        if i == 0:
            end_time = _format_time(order['uTime'])

        if i == len(histories) - 1:
            start_time = _format_time(order['uTime'])
            market_price_decimals = _decimal_len(market_price_text)
            order_decimals = _decimal_len(order['avgPx'])
            precision = max(precision, min(market_price_decimals, order_decimals))
            start = js_to_fixed(_parse_float(order['avgPx']), precision)

        sz = order['accFillSz']
        px = order['avgPx'] or order['px']
        px_num = _to_number(px)
        sz_num = _to_number(sz)
        sz_float = _parse_float(sz)
        swap_sz = _parse_float(_js_divide(sz_num * swap_enlarge, px_num)) if is_swap else sz_float * px_num
        swap_sz = sz_float * px_num * swap_enlarge if is_usdt_swap else swap_sz
        fill_sz = sz_float * px_num if is_swap else sz_float

        if order['side'] == 'buy':
            buy += fill_sz
            swap_buy += swap_sz
            buy_count += 1 if fill_sz > 0 else 0
        else:
            sell += fill_sz
            swap_sell += swap_sz
            sell_count += 1 if fill_sz > 0 else 0

        fee_num = _parse_float(order['fee'])
        if order['feeCcy'] == fee_ccy:
            fee += fee_num
        else:
            fee += fee_num * market_price_num

    change = buy - sell
    change_abs = buy + sell
    swap_change = swap_buy - swap_sell
    swap_abs = swap_buy + swap_sell
    fee *= (1 - FEE_BACK_RATE)

    if is_swap:
        outcome = swap_change - _js_divide(change * swap_enlarge, market_price_num) + _js_divide(fee, market_price_num)
    elif is_usdt_swap:
        outcome = change * swap_enlarge - _js_divide(swap_change, market_price_num) + _js_divide(fee, market_price_num)
    else:
        outcome = change - _js_divide(swap_change, market_price_num) + _js_divide(fee, market_price_num)

    return {
        'startTime': start_time,
        'endTime': end_time,
        'feeCcy': fee_ccy,
        'trxCcy': trx_ccy,
        'buy': _json_safe(buy),
        'buy_count': buy_count,
        'sell': _json_safe(sell),
        'sell_count': sell_count,
        'swapBuy': _json_safe(swap_buy),
        'swapSell': _json_safe(swap_sell),
        'swapChange': _json_safe(swap_change),
        'cost': _json_safe(change * swap_enlarge) if is_swap else js_to_fixed(swap_change, 2),
        'txn': _json_safe(change_abs * swap_enlarge) if is_swap else js_to_fixed(swap_abs, 2),
        'change': _json_safe(change),
        'changeAbs': _json_safe(change_abs),
        'fee': js_to_fixed(fee, 2),
        'outcome': _json_safe(outcome),
        'isSwap': is_swap,
        'isUsdtSwap': is_usdt_swap,
        'swapEnlarge': swap_enlarge,
        'merge': False,
        'price': _json_safe(market_price_num),
        'earn': js_to_fixed(outcome * market_price_num, 2),
        'avgPx': 0 if change == 0 else js_to_fixed(_js_divide(swap_change, change), precision),
        'start': start,
    }
