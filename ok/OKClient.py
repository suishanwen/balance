import sys
import importlib

sys.path.append("/home/balance")
importlib.reload(sys)

import time
import configparser
import api.OkexClient as OkexClient
import random
import json

# read config
config = configparser.ConfigParser()
config.read("config.ini")

OkexClient.get_account_info()

symbol = OkexClient.SYMBOL_OKB
amount = float(config.get("trade", "transaction"))
currentBase = float(config.get("trade", "currentBase"))
percentage = float(config.get("trade", "percentage"))


def order_process(my_order_info):
    my_order_info.set_amount(my_order_info.get_unhandled_amount())
    state = OkexClient.trade(my_order_info)
    if my_order_info.amount < 1 and state == 2:
        OkexClient.write_log(my_order_info)
    elif my_order_info.dealAmount > 0:
        my_order_info.set_price(0)
        order_process(my_order_info)


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


def get_next_buy_sell_rate():
    seconds_now = int(time.time())
    history_list = load_history()
    trend_count = 0
    buy_sell_rate = 1, 1
    for history in history_list:
        if history["orderType"] == OkexClient.TRADE_BUY:
            trend_count += 1
        else:
            trend_count -= 1
        seconds_now_diff = seconds_now - history["triggerSeconds"]
        # <15min buy twice
        if trend_count == 2 and seconds_now_diff < 900:
            buy_sell_rate = 2, 1
        # <30min buy three times
        elif trend_count == 3 and seconds_now_diff < 1800:
            buy_sell_rate = 3, 1
        # <60min buy four times
        elif trend_count == 4 and seconds_now_diff < 1800:
            buy_sell_rate = 4, 1
        # <60min buy five times
        elif trend_count == 5 and seconds_now_diff < 1800:
            buy_sell_rate = 5, 1
        # <15min sell twice
        elif trend_count == -2 and seconds_now_diff < 900:
            buy_sell_rate = 1, 2
        # <30min sell three times
        elif trend_count == -3 and seconds_now_diff < 1800:
            buy_sell_rate = 1, 3
        # <60min sell four times
        elif trend_count == -4 and seconds_now_diff < 1800:
            buy_sell_rate = 1, 4
        # <60min sell five times
        elif trend_count == -5 and seconds_now_diff < 1800:
            buy_sell_rate = 1, 4
    return buy_sell_rate


def get_next_buy_sell_info():
    buy_rate, sell_rate = get_next_buy_sell_rate()
    _ret = round(random.uniform(0.01 * percentage, 0.1 * percentage), 3)
    _num = random.randint(1, 10)
    if _num > 5:
        _ret = -_ret
    _next_buy = round(currentBase * (100 - percentage * buy_rate - _ret) * 0.01, 4)
    _next_sell = round(currentBase * (100 + percentage * sell_rate - _ret) * 0.01, 4)
    _next_buy_amount = amount * buy_rate
    _next_sell_amount = amount * sell_rate
    return _next_buy, _next_buy_amount, _next_sell, _next_sell_amount


next_buy, next_buy_amount, next_sell, next_sell_amount = get_next_buy_sell_info()

if __name__ == '__main__':
    counter = 0
    while True:
        try:
            if counter > 300:
                next_buy, next_buy_amount, next_sell, next_sell_amount = get_next_buy_sell_info()
                counter = 0
            OkexClient.get_coin_price(symbol)
            priceInfo = OkexClient.priceInfo
            buyPrice = priceInfo[symbol]["buy"]
            buyAmount = priceInfo[symbol]["buyAmount"]
            sellPrice = priceInfo[symbol]["sell"]
            sellAmount = priceInfo[symbol]["sellAmount"]
            print('\nBase:', currentBase, ",Buy:", next_buy, ',Sell:', next_sell,
                  '|buy1:', buyPrice, '(+', round(next_sell - buyPrice, 4), ')',
                  ',sell1:', sellPrice, '(', round(next_buy - sellPrice, 4), ')',
                  )
            orderInfo = {}
            if next_buy >= sellPrice and sellAmount >= next_buy_amount:
                buyOrder = OkexClient.MyOrderInfo(symbol, OkexClient.TRADE_BUY, sellPrice, next_buy_amount)
                orderInfo = buyOrder
            elif next_sell <= buyPrice and buyAmount >= next_sell_amount:
                sellOrder = OkexClient.MyOrderInfo(symbol, OkexClient.TRADE_SELL, buyPrice, next_sell_amount)
                orderInfo = sellOrder
            if orderInfo != {}:
                order_process(orderInfo)
                if orderInfo.amount < 1:
                    currentBase = round(orderInfo.avgPrice, 4)
                    config.read("config.ini")
                    config.set("trade", "currentBase", str(currentBase))
                    config.set("trade", "history", str(re_org_history(orderInfo)))
                    fp = open("config.ini", "w")
                    config.write(fp)
                    fp.close()
                    next_buy, next_buy_amount, next_sell, next_sell_amount = get_next_buy_sell_info()
        except Exception as err:
            print(err)
        time.sleep(0.1)
        counter += 1
