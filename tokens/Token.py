import configparser
import json
import math
import datetime
import traceback
# import time
import api.OrderInfo as OrderInfo
from util.MyUtil import write_log, send_email

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
            and state == client.COMPLETE_STATUS:
        my_order_info.set_count(client)
        write_log(str(my_order_info))
    elif my_order_info.totalDealAmount > 0:
        if state == 'canceled' or state == 'partial-canceled' or state == -1:
            write_log(str(my_order_info))
        my_order_info.set_price(0)
        order_process(client, my_order_info)


def load_history(symbol):
    history_list = []
    history = ""
    try:
        history = config.get(symbol, "history")
    except Exception as _err:
        print(_err)
    if history != "":
        history_list = json.loads(history)
    return history_list


def re_org_history(my_order_info):
    history_list = load_history(my_order_info.symbol)
    history_list.insert(0, my_order_info.__dict__)
    if len(history_list) > 5:
        history_list.pop()
    return json.dumps(history_list)


# def get_next_buy_sell_rate(client, symbol):
#     seconds_now = int(time.time())
#     history_list = load_history(symbol)
#     trend_count = 0
#     buy_sell_rate = 1, 1
#     for history in history_list:
#         if history["orderType"] == client.TRADE_BUY:
#             trend_count += 1
#         else:
#             trend_count -= 1
#         seconds_now_diff = seconds_now - history["triggerSeconds"]
#         # <25min buy twice
#         if trend_count == 2 and seconds_now_diff < 1500:
#             buy_sell_rate = 2, 1
#         # <1.5h buy three times
#         elif trend_count == 3 and seconds_now_diff < 5400:
#             buy_sell_rate = 3, 1
#         # <2.5h buy four times
#         elif trend_count == 4 and seconds_now_diff < 9000:
#             buy_sell_rate = 4, 1
#         # <4h buy five times
#         elif trend_count == 5 and seconds_now_diff < 14400:
#             buy_sell_rate = 5, 1
#         # <25min sell twice
#         elif trend_count == -2 and seconds_now_diff < 1500:
#             buy_sell_rate = 1, 2
#         # <1.5h sell three times
#         elif trend_count == -3 and seconds_now_diff < 5400:
#             buy_sell_rate = 1, 3
#         # <2.5h sell four times
#         elif trend_count == -4 and seconds_now_diff < 9000:
#             buy_sell_rate = 1, 4
#         # <4h sell five times
#         elif trend_count == -5 and seconds_now_diff < 14400:
#             buy_sell_rate = 1, 5
#     return buy_sell_rate


def get_next_buy_sell_info(client):
    # buy_rate, sell_rate = get_next_buy_sell_rate(client, symbol)
    buy_rate, sell_rate = 1, 1
    next_buy_price = round(client.currentBase / math.pow(client.rateP, buy_rate), 4)
    _next_sell_price = round(client.currentBase * math.pow(client.rateP, sell_rate), 4)
    if client.mode == "transaction":
        next_buy_val = client.transaction * buy_rate
        next_sell_val = client.transaction * sell_rate
    else:
        next_buy_val = round(
            client.amount * buy_rate + client.amount * (client.rateP - 1) * (1 + buy_rate) * buy_rate / 2, 2)
        next_sell_val = client.amount * sell_rate
    return next_buy_price, next_buy_val, _next_sell_price, next_sell_val


def modify_trans_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_transaction, _next_sell, _next_sell_transaction,
                          client):
    buy_rate = math.floor(math.log(client.currentBase / _avg_sell, client.rateP))
    buy_transaction_rate = _next_buy_transaction / client.transaction
    if buy_rate > 1 and buy_rate > buy_transaction_rate:
        return round(client.transaction * buy_rate - client.transaction * (client.rateP - 1) *
                     buy_rate * (buy_rate - 1) / 2, 3), \
               round(client.currentBase / math.pow(client.rateP, buy_rate), 4), _next_sell_transaction, _next_sell
    sell_rate = math.floor(math.log(_avg_buy / client.currentBase, client.rateP))
    sell_transaction_rate = _next_sell_transaction / client.transaction
    if sell_rate > 1 and sell_rate > sell_transaction_rate:
        return _next_buy_transaction, _next_buy, \
               round(client.transaction * sell_rate + client.transaction * (client.rateP - 1) * (
                       1 + sell_rate) * sell_rate / 2, 3), \
               round(client.currentBase * math.pow(client.rateP, sell_rate), 4)
    return _next_buy_transaction, _next_buy, _next_sell_transaction * client.rateP, _next_sell


def modify_amt_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_amount, _next_sell, _next_sell_amount, client):
    buy_rate = math.floor(math.log(client.currentBase / _avg_sell, client.rateP))
    buy_amount_rate = _next_buy_amount / client.amount
    if buy_rate > 1 and buy_rate > buy_amount_rate:
        return buy_rate * client.amount, round(client.currentBase / math.pow(client.rateP, buy_rate),
                                               4), _next_sell_amount, _next_sell
    sell_rate = math.floor(math.log(_avg_buy / client.currentBase, client.rateP))
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
        print(err)
        if str(err).find("No Section") > -1:
            config.add_section(cfg_field)
    day = datetime.date.today().day
    if day == len(count):
        count[day - 1] = count[day - 1] + my_order_info.count
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
    abs_avg_price = round(new_abs_transaction / abs(new_abs_amount), 4)
    avg_price = round(new_transaction / abs(new_amount), 4)
    config.set(cfg_field, "absamount", str(new_abs_amount))
    config.set(cfg_field, "abstransaction", str(new_abs_transaction))
    config.set(cfg_field, "absavgprice", str(abs_avg_price))
    config.set(cfg_field, "transaction", str(new_transaction))
    config.set(cfg_field, "amount", str(new_amount))
    config.set(cfg_field, "avgprice", str(avg_price))
    config.set(cfg_field, "count", str(json.dumps(count)))


def get_ma(client, symbol):
    data2 = client.get_klines(symbol, period, size2)
    data1 = data2[0:size1]
    sum1 = sum2 = 0
    for i in data1:
        sum1 += i
    for i in data2:
        sum2 += i
    return round(sum1 / len(data1) - sum2 / len(data2), 4)


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
        client.ACCURACY = 4
        client.MIN_AMOUNT = 0.0001


def __main__(client, symbol):
    init_config(client, symbol)
    client.get_account_info()
    counter = 0
    ma = avg_sell = avg_buy = next_base = 0
    next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
    while True:
        try:
            if counter > 300:
                next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
                counter = 0
            elif counter % 15 == 0:
                ma = get_ma(client, symbol)
            client.get_coin_price(symbol)
            for i in range(3):
                buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, i + 1)
                next_buy_amount, next_buy_p, next_sell_amount, next_sell_p = modify_val_by_price(avg_buy,
                                                                                                 avg_sell,
                                                                                                 next_buy,
                                                                                                 next_buy_val,
                                                                                                 next_sell,
                                                                                                 next_sell_val,
                                                                                                 client)
                if not ((next_buy_p >= avg_sell and sell_amount < next_buy_amount) or (
                        next_sell_p <= avg_buy and buy_amount < next_sell_amount)):
                    break
            print(
                "\nBase:{} ,ma:{} ,nextSell:[{},{}] - buy:[{},{}] (+{}) | nextBuy:[{},{}] - sell:[{},{}]({})".format(
                    client.currentBase,
                    ma,
                    next_sell_p,
                    next_sell_amount,
                    buy,
                    buy_amount,
                    round(
                        next_sell_p - buy,
                        4),
                    next_buy_p,
                    next_buy_amount,
                    sell,
                    sell_amount,
                    round(
                        next_buy_p - sell,
                        4)))
            order_info = None
            if ma > 0 and next_buy_p >= avg_sell and sell_amount >= next_buy_amount:
                next_base = next_buy_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_BUY, sell, next_buy_amount, next_base)
            elif ma < 0 and next_sell_p <= avg_buy and buy_amount >= next_sell_amount:
                next_base = next_sell_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_SELL, buy, next_sell_amount, next_base)
            if order_info is not None:
                order_process(client, order_info)
                if order_info.totalAmount - order_info.totalDealAmount < client.MIN_AMOUNT:
                    client.currentBase = round(next_base, 4)
                    config.read("config.ini")
                    config.set(symbol, "currentBase", str(client.currentBase))
                    # config.set(symbol, "history", str(re_org_history(order_info)))
                    add_statistics(client, order_info)
                    fp = open("config.ini", "w")
                    config.write(fp)
                    fp.close()
                    next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
            counter += 1
        except Exception as e:
            print(e, traceback.format_exc())
            send_email("%s:unhandled exception:%s" % (symbol, traceback.format_exc()))
            exit()
