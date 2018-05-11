import configparser
import json
import math
import time

import api.OrderInfo as OrderInfo
from util.MyUtil import sendEmail

# read config
config = configparser.ConfigParser()
config.read("config.ini")
percentage = float(config.get("trade", "percentage"))
rate_p = (100 + percentage) * 0.01


def order_process(client, my_order_info):
    my_order_info.set_amount(my_order_info.get_unhandled_amount())
    state = client.trade(my_order_info)
    if my_order_info.totalAmount - my_order_info.totalDealAmount < client.MIN_AMOUNT \
            and state == client.COMPLETE_STATUS:
        client.write_log(my_order_info)
    elif my_order_info.totalDealAmount > 0:
        if state == 'canceled' or state == 'partial-canceled' or state == -1:
            client.write_log(my_order_info)
        my_order_info.set_price(0)
        order_process(client, my_order_info)


def load_history():
    history_list = []
    history = ""
    try:
        history = config.get("trade", "history")
    except Exception as _err:
        print(_err)
    if history != "":
        history_list = json.loads(history)
    return history_list


def re_org_history(my_order_info):
    history_list = load_history()
    history_list.insert(0, my_order_info.__dict__)
    if len(history_list) > 5:
        history_list.pop()
    return json.dumps(history_list)


def get_next_buy_sell_rate(client):
    seconds_now = int(time.time())
    history_list = load_history()
    trend_count = 0
    buy_sell_rate = 1, 1
    for history in history_list:
        if history["orderType"] == client.TRADE_BUY:
            trend_count += 1
        else:
            trend_count -= 1
        seconds_now_diff = seconds_now - history["triggerSeconds"]
        # <25min buy twice
        if trend_count == 2 and seconds_now_diff < 1500:
            buy_sell_rate = 2, 1
        # <1.5h buy three times
        elif trend_count == 3 and seconds_now_diff < 5400:
            buy_sell_rate = 3, 1
        # <2.5h buy four times
        elif trend_count == 4 and seconds_now_diff < 9000:
            buy_sell_rate = 4, 1
        # <4h buy five times
        elif trend_count == 5 and seconds_now_diff < 14400:
            buy_sell_rate = 5, 1
        # <25min sell twice
        elif trend_count == -2 and seconds_now_diff < 1500:
            buy_sell_rate = 1, 2
        # <1.5h sell three times
        elif trend_count == -3 and seconds_now_diff < 5400:
            buy_sell_rate = 1, 3
        # <2.5h sell four times
        elif trend_count == -4 and seconds_now_diff < 9000:
            buy_sell_rate = 1, 4
        # <4h sell five times
        elif trend_count == -5 and seconds_now_diff < 14400:
            buy_sell_rate = 1, 5
    return buy_sell_rate


def get_next_buy_sell_info(client):
    transaction = float(config.get("trade", "transaction"))
    current_base = float(config.get("trade", "currentbase"))
    buy_rate, sell_rate = get_next_buy_sell_rate(client)
    _next_buy = round(current_base / math.pow(rate_p, buy_rate), 4)
    _next_sell = round(current_base * math.pow(rate_p, sell_rate), 4)
    _next_buy_trans = transaction * buy_rate
    _next_sell_trans = transaction * sell_rate
    return _next_buy, _next_buy_trans, _next_sell, _next_sell_trans


def modify_trans_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_transaction, _next_sell, _next_sell_transaction):
    transaction = float(config.get("trade", "transaction"))
    current_base = float(config.get("trade", "currentbase"))
    buy_rate = math.floor(math.log(current_base / _avg_sell, rate_p))
    buy_transaction_rate = _next_buy_transaction / transaction
    if buy_rate > 1 and buy_rate > buy_transaction_rate:
        return round(buy_rate * transaction, 3), round(current_base / math.pow(rate_p, buy_rate),
                                                       4), _next_sell_transaction, _next_sell
    sell_rate = math.floor(math.log(_avg_buy / current_base, rate_p))
    sell_transaction_rate = _next_sell_transaction / transaction
    if sell_rate > 1 and sell_rate > sell_transaction_rate:
        return _next_buy_transaction, _next_buy, round(sell_rate * transaction, 3), round(
            current_base * math.pow(rate_p, sell_rate), 4)
    return _next_buy_transaction, _next_buy, _next_sell_transaction, _next_sell


def add_statistics(client, my_order_info):
    amount = float(config.get("statistics", "amount"))
    transaction = float(config.get("statistics", "transaction"))
    abs_amount = float(config.get("statistics", "absamount"))
    abs_transaction = float(config.get("statistics", "abstransaction"))
    new_abs_amount = round(abs_amount + my_order_info.totalDealAmount, 4)
    new_abs_transaction = round(abs_transaction + abs(my_order_info.transaction), 3)
    new_transaction = round(transaction + my_order_info.transaction, 3)
    if my_order_info.orderType == client.TRADE_BUY:
        new_amount = round(amount + my_order_info.totalDealAmount, 4)
    else:
        new_amount = round(amount - my_order_info.totalDealAmount, 4)
    abs_avg_price = round(new_abs_transaction / abs(new_abs_amount), 4)
    avg_price = round(new_transaction / abs(new_amount), 4)
    config.set("statistics", "absamount", str(new_abs_amount))
    config.set("statistics", "abstransaction", str(new_abs_transaction))
    config.set("statistics", "absavgprice", str(abs_avg_price))
    config.set("statistics", "transaction", str(new_transaction))
    config.set("statistics", "amount", str(new_amount))
    config.set("statistics", "avgprice", str(avg_price))


def balance_temp_out(client):
    client.get_account_info()
    available = client.accountInfo[client.BALANCE_HT]["available"]
    if available >= 10000 and client.priceInfo[client.SYMBOL_HT]["bids"][0][0] >= 3.8:
        order_info = OrderInfo.MyOrderInfo(client.SYMBOL_HT, client.TRADE_SELL, 3.7, 10000, 3.8)
        order_process(client, order_info)
        sendEmail("HT unlocked！")
        exit()


def __main__(client, symbol):
    global buy, avg_buy, buy_amount, next_buy_amount, sell, avg_sell, sell_amount, next_sell_amount, next_base
    current_base = float(config.get("trade", "currentbase"))
    min_amount = float(config.get("trade", "minamount"))
    client.get_account_info()
    counter = 0
    next_buy, next_buy_trans, next_sell, next_sell_trans = get_next_buy_sell_info(client)
    while True:
        try:
            if counter > 300:
                next_buy, next_buy_trans, next_sell, next_sell_trans = get_next_buy_sell_info(client)
                counter = 0
            client.get_coin_price(symbol)
            # temp wait ht unlock and sell
            balance_temp_out(client)
            for i in range(3):
                buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, i + 1)
                next_buy_trans_p, next_buy_p, next_sell_trans_p, next_sell_p = modify_trans_by_price(avg_buy,
                                                                                                     avg_sell,
                                                                                                     next_buy,
                                                                                                     next_buy_trans,
                                                                                                     next_sell,
                                                                                                     next_sell_trans)
                next_buy_amount = round(next_buy_trans_p / avg_sell, 2)
                next_sell_amount = round(next_sell_trans_p / avg_buy, 2)
                if not ((next_buy_p >= avg_sell and sell_amount < next_buy_amount) or (
                        next_sell_p <= avg_buy and buy_amount < next_sell_amount)):
                    break
            print(
                "\nBase:{} ,nextSell:[{},{}] - buy:[{},{}] (+{}) | nextBuy:[{},{}] - sell:[{},{}]({})".format(
                    current_base,
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
            if next_buy_p >= avg_sell and sell_amount >= next_buy_amount:
                next_base = next_buy_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_BUY, sell, next_buy_amount, next_base)
            elif next_sell_p <= avg_buy and buy_amount >= next_sell_amount:
                next_base = next_sell_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_SELL, buy, next_sell_amount, next_base)
            if order_info is not None:
                order_process(client, order_info)
                if order_info.totalAmount - order_info.totalDealAmount < min_amount:
                    current_base = round(next_base, 4)
                    config.read("config.ini")
                    config.set("trade", "currentBase", str(current_base))
                    config.set("trade", "history", str(re_org_history(order_info)))
                    add_statistics(client, order_info)
                    fp = open("config.ini", "w")
                    config.write(fp)
                    fp.close()
                    next_buy, next_buy_trans, next_sell, next_sell_trans = get_next_buy_sell_info(client)
        except Exception as err:
            print(err)
        # time.sleep(0.1)
        counter += 1
