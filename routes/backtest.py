import configparser

from flask import Blueprint, request

from .server_core import (
    NOTE_PATH,
)
import json
import os

from module.Logger import logger
from util.ServerUtil import get_api, get_user, require_auth, write_config, write_config_text
from util.DataUtil import from_time_stamp, get_last_line

backtest_bp = Blueprint('backtest', __name__)


def get_history_file(symbol, period):
    return f"db/{symbol}_{period}.txt"


def history_to_log(data):
    return json.dumps([from_time_stamp(int(data[0]) / 1000), data[0], data[1], data[2], data[3], data[4], data[5]])


@backtest_bp.route('/back-testing', methods=['post'])
@require_auth('r')
def back_testing():
    data = json.loads(request.data)
    symbol = data['symbol']
    period = data['period']
    atr_trigger_rate = data['trigger']
    atr_loss_rate = data['loss']
    slow = data['size']
    mode = data['mode']
    file = get_history_file(symbol, period)
    data = []
    total_count = win_count = 0
    balance_init = balance = 1000
    trx = 1000
    amount = 0
    fee = 0.0003
    slide = 0
    profit = 0
    ab_profit = 0
    details = []
    price_buys = []
    price_sells = []
    buy_mode = mode == 1 or mode == 3
    sell_mode = mode == 2 or mode == 3
    parameter = f"[balance:{balance} USDT,{trx} USDT/trx,fee:{fee},slide:{slide},interval:{slow}*{period},atr_trigger_rate:{atr_trigger_rate},atr_win_rate:{atr_loss_rate},mode:{mode}]"
    with open(file, 'r') as f:
        for line in f.readlines():
            data.append(json.loads(line))
    for i in range(slow, len(data)):
        sum_slow = sum_atr = 0
        for p in range(i - slow, i):
            row = data[p]
            high = float(row[3])
            low = float(row[4])
            close = float(row[5])
            sum_slow += close
            sum_atr += high - low
        ma_slow = sum_slow / slow
        atr = sum_atr / slow
        current = data[i]
        current_open = float(current[2])
        top_point = ma_slow + atr_trigger_rate * atr
        bottom_point = ma_slow - atr_trigger_rate * atr
        buy_win = bottom_point + atr_loss_rate * atr
        sell_win = top_point - atr_loss_rate * atr
        if buy_mode and current_open >= buy_win and len(price_buys) > 0 and buy_win > price_buys[len(price_buys) - 1]:
            prev_price = price_buys.pop()
            price = buy_win
            op = 'make profit' if price > prev_price else 'stop loss'
            new_amount = trx / price * (1 - fee - slide)
            balance += trx
            amount -= new_amount
            profit = (balance + amount * price - balance_init) / trx * 100
            ab_profit += (price - prev_price) * new_amount * (1 - fee - slide)
            detail = f"{current[0]} epoch:{i + 1} {op} sell {round(new_amount, 4)},price:{round(price, 4)},prev_buy:{round(prev_price, 4)},balance:{round(balance, 4)} USDT, {round(profit, 2)}%"
            details.append(detail)
            total_count += 1
            win_count += 1
        elif sell_mode and current_open <= sell_win and len(price_sells) > 0 and sell_win < price_sells[
            len(price_sells) - 1]:
            price = sell_win
            prev_price = price_sells.pop()
            op = 'make profit' if price < prev_price else 'stop loss'
            new_amount = trx / price * (1 - fee - slide)
            balance -= trx
            amount += new_amount
            profit = (balance + amount * price - balance_init) / trx * 100
            ab_profit += (price - prev_price) * new_amount * (1 - fee - slide)
            detail = f"{current[0]} epoch:{i + 1} {op} buy {round(abs(new_amount), 4)},price:{round(price, 4)},prev_sell:{round(prev_price, 4)},balance:{round(balance, 4)} USDT, {round(profit, 2)}%"
            details.append(detail)
            amount = 0
            total_count += 1
            win_count += 1
        elif buy_mode and current_open <= bottom_point and (
                len(price_buys) == 0 or top_point < price_buys[len(price_buys) - 1]):
            price_buys.append(bottom_point)
            price = bottom_point
            new_amount = trx / price * (1 - fee - slide)
            amount += new_amount
            balance -= trx
            detail = f"{current[0]} epoch:{i + 1} buy {round(new_amount, 4)},price:{round(price, 4)},balance:{round(balance, 4)} USDT {round(amount, 4)} EOS"
            details.append(detail)
        elif sell_mode and current_open >= top_point and (
                len(price_sells) == 0 or bottom_point > price_sells[len(price_sells) - 1]):
            price_sells.append(top_point)
            price = top_point
            new_amount = trx / price * (1 - fee - slide)
            amount -= new_amount
            balance += trx
            detail = f"{current[0]} epoch:{i + 1} sell {round(new_amount, 4)},price:{round(price, 4)},balance:{round(balance, 4)} USDT {round(amount, 4)} EOS"
            details.append(detail)
        price_buys.sort()
        price_buys.reverse()
        price_sells.sort()
    profit = (balance - balance_init + amount * float(data[len(data) - 1][2])) / trx * 100
    win_rate = win_count / total_count * 100
    result = {'parameter': parameter, 'total_count': total_count, 'win_count': win_count, 'ab_profit': ab_profit,
              'win_rate': f'{round(win_rate)}%', 'price_buys': price_buys, 'price_sells': price_sells,
              'profit': f'{round(profit, 2)}%', 'details': details}
    return result


@backtest_bp.route('/back-testing-atr', methods=['post'])
@require_auth('r')
def back_testing_atr():
    data = json.loads(request.data)
    symbol = data['symbol']
    period = data['period']
    atr_trigger_rate = data['trigger']
    atr_loss_rate = data['loss']
    slow = data['size']
    file = get_history_file(symbol, period)
    data = []
    total_count = win_count = 0
    balance_init = balance = 1000
    trx = 1000
    amount = 0
    fee = 0.0008
    slide = 0.001
    prev_price = 0
    details = []
    parameter = f"PARAMETER[balance:{balance} USDT,{trx} USDT/trx,fee:{fee},slide:{slide},interval:{slow}*{period},atr_trigger_rate:{atr_trigger_rate},atr_loss_rate:{atr_loss_rate}]"
    with open(file, 'r') as f:
        for line in f.readlines():
            data.append(json.loads(line))
    for i in range(slow, len(data)):
        sum_slow = sum_atr = 0
        for p in range(i - slow, i):
            row = data[p]
            high = float(row[3])
            low = float(row[4])
            close = float(row[5])
            sum_slow += close
            sum_atr += high - low
        ma_slow = sum_slow / slow
        atr = sum_atr / slow
        current = data[i]
        current_open = float(current[2])
        top_point = ma_slow + atr_trigger_rate * atr
        bottom_point = ma_slow - atr_trigger_rate * atr
        buy_loss = top_point - atr_loss_rate * atr
        sell_loss = bottom_point + atr_loss_rate * atr
        if current_open > top_point and amount == 0:
            price = top_point
            new_amount = trx / price * (1 - fee - slide)
            prev_price = price
            amount += new_amount
            balance -= trx
            detail = f"{current[0]} epoch:{i + 1} buy {round(new_amount, 4)},price:{round(price, 4)},balance:{round(balance, 4)} USDT {round(amount, 4)} EOS"
            details.append(detail)
        elif current_open < bottom_point and amount == 0:
            price = bottom_point
            new_amount = trx / price * (1 - fee - slide)
            prev_price = price
            amount -= new_amount
            balance += trx
            detail = f"{current[0]} epoch:{i + 1} sell {round(new_amount, 4)},price:{round(price, 4)},balance:{round(balance, 4)} USDT {round(amount, 4)} EOS"
            details.append(detail)
        if current_open < buy_loss and amount > 0:
            price = buy_loss
            op = 'make profit' if price > prev_price else 'stop loss'
            balance += amount * price * (1 - fee - slide)
            profit = (balance - balance_init) / trx * 100
            detail = f"{current[0]} epoch:{i + 1} {op} sell {round(amount, 4)},price:{round(price, 4)},prev_buy:{round(prev_price, 4)},balance:{round(balance, 4)} USDT, {round(profit, 2)}%"
            details.append(detail)
            amount = 0
            total_count += 1
            win_count += 1 if price > prev_price else 0
        elif current_open > sell_loss and amount < 0:
            price = sell_loss
            op = 'make profit' if price < prev_price else 'stop loss'
            balance -= abs(amount) * price * (1 - fee - slide)
            profit = (balance - balance_init) / trx * 100
            detail = f"{current[0]} epoch:{i + 1} {op} buy {round(abs(amount), 4)},price:{round(price, 4)},prev_sell:{round(prev_price, 4)},balance:{round(balance, 4)} USDT, {round(profit, 2)}%"
            details.append(detail)
            amount = 0
            total_count += 1
            win_count += 1 if price < prev_price else 0
    if amount > 0:
        current = data[len(data) - 1]
        current_close = float(current[5])
        if amount > 0:
            balance += amount * current_close * (1 - fee - slide)
            profit = (balance - balance_init) / trx * 100
            detail = f"{current[0]} the last epoch:{len(data)} close sell {round(abs(amount), 4)},price:{round(current_close, 4)},prev_buy:{round(prev_price, 4)},balance:{round(balance, 4)} USDT, {round(profit, 2)}%"
            details.append(detail)
            total_count += 1
            win_count += 1 if current_close > prev_price else 0
            amount = 0
        elif amount < 0:
            balance -= abs(amount) * current_close * (1 - fee - slide)
            profit = (balance - balance_init) / trx * 100
            detail = f"{current[0]} the last epoch:{len(data)} close buy {round(abs(amount), 4)},price:{round(current_close, 4)},prev_sell:{round(prev_price, 4)},balance:{round(balance, 4)} USDT, {round(profit, 2)}%"
            details.append(detail)
            total_count += 1
            win_count += 1 if current_close < prev_price else 0
            amount = 0
    profit = (balance - balance_init) / trx * 100
    win_rate = win_count / total_count * 100
    result = {'parameter': parameter, 'total_count': total_count, 'win_count': win_count,
              'win_rate': f'{round(win_rate)}%',
              'profit': f'{round(profit, 2)}%', 'details': details}
    return result


@backtest_bp.route('/get-note', methods=['post'])
@require_auth('r')
def get_note():
    user = get_user()
    config = configparser.ConfigParser()
    config.read(NOTE_PATH)
    if config.has_section(user):
        return config.get(user, 'note')
    return ''


@backtest_bp.route('/set-note', methods=['post'])
@require_auth('w')
def set_note():
    user = get_user()
    data = json.loads(request.data)
    note = data.get('note') if data.get('note') is not None else ''
    config = configparser.ConfigParser()
    config.read(NOTE_PATH)
    config.set(user, 'note', note)
    write_config(NOTE_PATH, config)
    return '1'


@backtest_bp.route('/db-version', methods=['post'])
@require_auth('r')
def get_history_version():
    data = json.loads(request.data)
    symbol = data['symbol']
    period = data['period']
    file = get_history_file(symbol, period)
    if os.path.exists(file):
        data = get_last_line(file)
        if data:
            return json.loads(data)[1]
    if period == '1D':
        return str(1546272000000 - 1)
    else:
        return str(1640966400000 - 1)


@backtest_bp.route('/db-fetch', methods=['post'])
@require_auth('w')
def fetch_history_data():
    user = get_user()
    data = json.loads(request.data)
    symbol = data['symbol']
    period = data['period']
    count = int(data['count'])
    market_api = get_api(user, 3)
    while count > 0:
        version = get_history_version()
        next_version = int(version)
        result = None
        try:
            result = market_api.get_history_candlesticks(symbol, period, 100, next_version)
        except Exception as e:
            logger.error("***klines:%s" % e)
        if result is not None and result['code'] is not None and result["code"] == "0":
            if len(result['data']) == 0:
                break
            file = get_history_file(symbol, period)
            if not os.path.exists(file.split("/")[0]):
                os.makedirs(file.split("/")[0])
            if not os.path.exists(file):
                write_config_text(file, "")
            data = list(result['data'])
            data.reverse()
            with open(file, 'a') as f:
                for line in data:
                    print(history_to_log(line))
                    f.writelines(f"{history_to_log(line)}\n")
        count -= 1
    return "1"
