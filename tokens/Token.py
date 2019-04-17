import configparser
import json
import math
import datetime
import time
import traceback
import pytz
import api.OrderInfo as OrderInfo
from util.MyUtil import write_log, send_email
from util.Logger import logger
from util.Statistic import analyze_log, generate_email

# read config
config = configparser.ConfigParser()
config.read("config.ini")
period = config.get("klines", "period")
size1 = int(config.get("klines", "size1"))
size2 = int(config.get("klines", "size2"))


def order_process(client, my_order_info):
    my_order_info.set_amount(my_order_info.get_unhandled_amount(client.ACCURACY))
    state = client.trade(my_order_info)
    if my_order_info.get_unhandled_amount(client.ACCURACY) < client.MIN_AMOUNT \
            and state == client.FILLED_STATUS:
        my_order_info.set_count(client)
        write_log(str(my_order_info))
    elif my_order_info.totalDealAmount > 0:
        if state == 'canceled' or state == 'partial-canceled' or state == -1:
            write_log(str(my_order_info))
        my_order_info.set_price(0)
        order_process(client, my_order_info)


def get_next_buy_sell_info(client):
    client.buyRate = client.sellRate = 1
    _next_buy_price = round(client.currentBase / math.pow(client.rateP, client.buyRate), 4)
    _next_sell_price = round(client.currentBase * math.pow(client.rateP, client.sellRate), 4)
    if client.mode == "transaction":
        next_buy_val = client.transaction * client.buyRate
        next_sell_val = client.transaction * client.sellRate
    else:
        next_buy_val = round(
            client.amount * client.buyRate + client.amount * (client.rateP - 1) * (
                    1 + client.buyRate) * client.buyRate / 2, 2)
        next_sell_val = client.amount * client.sellRate
    return _next_buy_price, next_buy_val, _next_sell_price, next_sell_val


# rate>1 : base>1 earn usdt , base<=1 earn coin
def modify_trans_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_transaction, _next_sell, _next_sell_transaction,
                          client):
    buy_rate = math.log(client.currentBase / _avg_sell, client.rateP)
    client.buyRate = buy_rate = round(math.floor(buy_rate / 0.1) * 0.1, 1)
    buy_transaction_rate = _next_buy_transaction / client.transaction
    if buy_rate > 1 and buy_rate > buy_transaction_rate:
        _next_buy = round(client.currentBase / math.pow(client.rateP, buy_rate), client.ACCURACY)
        if client.currentBase < 1:
            _next_buy_transaction = client.transaction * buy_rate
        else:
            _next_buy_transaction = round(client.transaction * buy_rate - client.transaction * (client.rateP - 1) *
                                          buy_rate * (buy_rate - 1) / 2, 3)
    sell_rate = math.log(_avg_buy / client.currentBase, client.rateP)
    client.sellRate = sell_rate = round(math.floor(sell_rate / 0.1) * 0.1, 1)
    sell_transaction_rate = _next_sell_transaction / client.transaction
    if sell_rate >= 1 and sell_rate >= sell_transaction_rate:
        _next_sell = round(client.currentBase * math.pow(client.rateP, sell_rate), client.ACCURACY)
        if client.currentBase < 1:
            _next_sell_transaction = client.transaction * sell_rate
        else:
            _next_sell_transaction = round(client.transaction * sell_rate + client.transaction * (client.rateP - 1) * (
                    1 + sell_rate) * sell_rate / 2, 3)
    return _next_buy_transaction, _next_buy, _next_sell_transaction, _next_sell


def modify_amt_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_amount, _next_sell, _next_sell_amount, client):
    client.buyRate = buy_rate = math.floor(math.log(client.currentBase / _avg_sell, client.rateP))
    buy_amount_rate = _next_buy_amount / client.amount
    if buy_rate > 1 and buy_rate > buy_amount_rate:
        return buy_rate * client.amount, round(client.currentBase / math.pow(client.rateP, buy_rate),
                                               4), _next_sell_amount, _next_sell
    client.sellRate = sell_rate = math.floor(math.log(_avg_buy / client.currentBase, client.rateP))
    sell_amount_rate = _next_sell_amount / client.amount
    if sell_rate > 1 and sell_rate > sell_amount_rate:
        return _next_buy_amount, _next_buy, sell_rate * client.amount, round(
            client.currentBase * math.pow(client.rateP, sell_rate), 4)
    return _next_buy_amount, _next_buy, _next_sell_amount, _next_sell


def modify_val_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_val, _next_sell, _next_sell_val, client):
    if client.mode == "transaction":
        next_buy_trans_p, next_buy_p, next_sell_trans_p, next_sell_p = modify_trans_by_price(_avg_buy, _avg_sell,
                                                                                             _next_buy, _next_buy_val,
                                                                                             _next_sell, _next_sell_val,
                                                                                             client)
        next_buy_amount = round(next_buy_trans_p / _avg_sell, client.ACCURACY)
        next_sell_amount = round(next_sell_trans_p / _avg_buy, client.ACCURACY)
        return next_buy_amount, next_buy_p, next_sell_amount, next_sell_p
    else:
        return modify_amt_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_val, _next_sell, _next_sell_val, client)


def add_statistics(client, my_order_info):
    cfg_field = my_order_info.symbol + "-stat"
    amount = transaction = abs_amount = abs_transaction = 0
    count = []
    try:
        amount = float(config.get(cfg_field, "amount"))
        transaction = float(config.get(cfg_field, "transaction"))
        abs_amount = float(config.get(cfg_field, "absamount"))
        abs_transaction = float(config.get(cfg_field, "abstransaction"))
        count = json.loads(config.get(cfg_field, "count"))
    except Exception as err:
        logger.error(err)
        if str(err).find("No section") > -1:
            config.add_section(cfg_field)
    day = datetime.date.today().day
    if day == len(count):
        count[day - 1] = round(count[day - 1] + my_order_info.count, 3)
    elif day > len(count):
        for i in range(day - len(count) - 1):
            count.append(0)
        count.append(my_order_info.count)
    elif day < len(count):
        count = [my_order_info.count]
    new_abs_amount = round(abs_amount + my_order_info.totalDealAmount, 4)
    new_abs_transaction = round(abs_transaction + abs(my_order_info.transaction), 3)
    new_transaction = round(transaction + my_order_info.transaction, 3)
    if my_order_info.orderType == client.TRADE_BUY:
        new_amount = round(amount + my_order_info.totalDealAmount, 4)
    else:
        new_amount = round(amount - my_order_info.totalDealAmount, 4)
    if new_abs_amount != 0:
        abs_avg_price = round(new_abs_transaction / abs(new_abs_amount), 4)
        config.set(cfg_field, "absavgprice", str(abs_avg_price))
    if new_amount != 0:
        avg_price = round(new_transaction / abs(new_amount), 4)
        config.set(cfg_field, "avgprice", str(avg_price))
    config.set(cfg_field, "absamount", str(new_abs_amount))
    config.set(cfg_field, "abstransaction", str(new_abs_transaction))
    config.set(cfg_field, "transaction", str(new_transaction))
    config.set(cfg_field, "amount", str(new_amount))
    config.set(cfg_field, "count", str(json.dumps(count)))


def get_trigger_info(client, symbol):
    data = client.get_klines(symbol, period, size2)
    high = max(map(lambda x: x[1], data))
    low = min(map(lambda x: x[2], data))
    data2 = list(map(lambda x: x[3], data))
    data1 = data2[0:size1]
    sum1 = sum2 = 0
    for i in data1:
        sum1 += i
    for i in data2:
        sum2 += i
    prev = data[1]
    prev_grand = data[2]
    dma = round(sum1 / len(data1) - sum2 / len(data2), client.ACCURACY + 2)
    # reverse
    reverse = (prev[2] == low and prev[3] > prev_grand[3]) or \
              (prev[1] == high and prev[3] < prev_grand[3])
    # hammer or star
    hammer = False
    if abs(prev[1] - prev[2]) > 0:
        hammer = abs(prev[0] - prev[3]) / abs(prev[1] - prev[2]) <= 0.4
    # pierce or swallow
    pierce = False
    if abs(prev_grand[3] - prev_grand[0]) > 0:
        pierce = abs(prev[3] - prev_grand[3]) / abs(prev_grand[3] - prev_grand[0]) >= 0.5
    # needle
    data_ex = data[1:size2]
    list_ex = []
    for ex in data_ex:
        list_ex.append(ex[0])
        list_ex.append(ex[3])
    high_ex = max(list_ex)
    low_ex = min(list_ex)
    return dma, reverse and (hammer or pierce), high_ex, low_ex


def get_trigger_no(dma, reverse, client, next_buy_p, avg_sell, next_sell_p, avg_buy, needle_rate):
    if next_buy_p >= avg_sell:
        if dma > 0:
            return 1
        elif reverse and client.buyRate >= 2 / client.percentage:
            return 2
        elif needle_rate >= client.percentage:
            return 3
    elif next_sell_p <= avg_buy:
        if dma < 0:
            return -1
        elif reverse and client.sellRate >= 2 / client.percentage:
            return -2
        elif needle_rate >= client.percentage:
            return -3
    return 0


def init_config(client, symbol):
    client.mode = config.get(symbol, "mode")
    client.amount = float(config.get(symbol, "amount"))
    client.transaction = float(config.get(symbol, "transaction"))
    client.currentBase = float(config.get(symbol, "currentbase"))
    client.percentage = float(config.get(symbol, "percentage"))
    client.rateP = (100 + client.percentage) * 0.01
    client.SYMBOL_T = symbol
    client.BALANCE_T = str(symbol).replace("_", "").replace("usdt", "")
    client.accountInfo[client.BALANCE_T] = {"total": 0, "available": 0, "freezed": 0}
    client.priceInfo[client.SYMBOL_T] = {"asks": [], "bids": []}
    if client.BALANCE_T == "btc":
        client.MIN_AMOUNT = 0.0001
    elif client.BALANCE_T == "eth":
        client.MIN_AMOUNT = 0.001
    elif client.BALANCE_T == "bch":
        client.MIN_AMOUNT = 0.01


def check_statistic_email(client):
    time_stamp = datetime.datetime.fromtimestamp(int(time.time()), pytz.timezone('Asia/Shanghai')).strftime(
        '%Y-%m-%d %H:%M:%S')
    dd = int(time_stamp[8:10])
    hh = int(time_stamp[11:13])
    mm = int(time_stamp[14:16])
    if client.emailDay != dd and hh == 23 and mm >= 55:
        if send_email(generate_email(analyze_log()), "html", "收益统计[bitcoinrobot]"):
            client.emailDay = dd


def __main__(client, symbol):
    # 初始配置
    init_config(client, symbol)
    # 获取账户信息
    client.get_account_info()
    # 程序计数器
    counter = 0
    # 触发器
    trigger = 0
    # 反转
    reverse = False
    # 插针
    needle_rate = high_ex = low_ex = 0
    # 均线差
    dma = 0
    # 下一基准
    next_base = 0
    # 合并深度买入价
    buy = 0
    # 合并深度买入均价
    # avg_buy = 0
    # 合并深度买入量
    buy_amount = 0
    # 合并深度卖出价
    sell = 0
    # 合并深度卖出均价
    # avg_sell = 0
    # 合并深度卖出量
    sell_amount = 0
    # 价格调整买入量
    next_buy_amount = 0
    # 价格调整下一买入基准价
    next_buy_p = 0
    # 价格调整卖出量
    next_sell_amount = 0
    # 价格调整下一卖出基准价
    next_sell_p = 0
    # 下一买入价,下一买入量,下一卖出价,下一卖出量
    next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
    try:
        while True:
            if counter > 300:
                check_statistic_email(client)
                counter = 0
            elif counter % 5 == 0:
                dma, reverse, high_ex, low_ex = get_trigger_info(client, symbol)
            client.get_coin_price(symbol)
            for i in range(10):
                buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, i + 1)
                next_buy_amount, next_buy_p, next_sell_amount, next_sell_p = modify_val_by_price(avg_buy,
                                                                                                 avg_sell,
                                                                                                 next_buy,
                                                                                                 next_buy_val,
                                                                                                 next_sell,
                                                                                                 next_sell_val,
                                                                                                 client)
                if client.sellRate >= client.buyRate:
                    needle_rate = round((avg_buy - high_ex) / (high_ex - low_ex), 6)
                else:
                    needle_rate = round((low_ex - avg_sell) / (high_ex - low_ex), 6)
                trigger = get_trigger_no(dma, reverse, client, next_buy_p, avg_sell, next_sell_p, avg_buy, needle_rate)

                if (trigger > 0 and sell_amount < next_buy_amount) or (trigger < 0 and buy_amount < next_sell_amount):
                    continue
                if i > 0:
                    logger.info("合并{}级深度！".format(i + 1))
                break
            if counter % 3 == 0:
                if client.sellRate >= client.buyRate:
                    info = "↑({}):[{},{}]:[{},{}](+{})".format(client.sellRate,
                                                               next_sell_p,
                                                               next_sell_amount,
                                                               buy,
                                                               buy_amount,
                                                               round(next_sell_p - buy, 4))
                else:
                    info = "↓({}):[{},{}]:[{},{}]({})".format(client.buyRate,
                                                              next_buy_p,
                                                              next_buy_amount,
                                                              sell,
                                                              sell_amount,
                                                              round(next_buy_p - sell, 4))
                logger.info(
                    "B:{},D:{},R:{},N:{},{}".format(
                        client.currentBase,
                        dma,
                        reverse,
                        needle_rate,
                        info))
            order_info = None
            if trigger > 0 and sell_amount >= next_buy_amount:
                next_base = next_buy_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_BUY, sell, next_buy_amount, next_base, trigger)
            elif trigger < 0 and buy_amount >= next_sell_amount:
                next_base = next_sell_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_SELL, buy, next_sell_amount, next_base, trigger)
            if order_info is not None:
                order_process(client, order_info)
                if order_info.totalAmount - order_info.totalDealAmount < client.MIN_AMOUNT:
                    client.currentBase = round(next_base, 4)
                    config.read("config.ini")
                    config.set(symbol, "currentBase", str(client.currentBase))
                    add_statistics(client, order_info)
                    fp = open("config.ini", "w")
                    config.write(fp)
                    fp.close()
                    next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
                    send_email(str(order_info))
            counter += 1
            if period == '4hour':
                time.sleep(10)
    except Exception as e:
        send_email("%s:unhandled exception:%s" % (symbol, traceback.format_exc()))
        logger.error("[unhandled exception]{}:{}".format(e, traceback.format_exc()))
        exit()
