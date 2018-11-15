import configparser
import json
import math
import datetime
import time
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
        if str(err).find("No section") > -1:
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
    if new_abs_amount != 0:
        abs_avg_price = round(new_abs_transaction / abs(new_abs_amount), 4)
        avg_price = round(new_transaction / abs(new_amount), 4)
        config.set(cfg_field, "absavgprice", str(abs_avg_price))
        config.set(cfg_field, "avgprice", str(avg_price))
    config.set(cfg_field, "absamount", str(new_abs_amount))
    config.set(cfg_field, "abstransaction", str(new_abs_transaction))
    config.set(cfg_field, "transaction", str(new_transaction))
    config.set(cfg_field, "amount", str(new_amount))
    config.set(cfg_field, "count", str(json.dumps(count)))


def get_ma(client, symbol):
    data2 = client.get_klines(symbol, period, size2)
    data1 = data2[0:size1]
    sum1 = sum2 = 0
    for i in data1:
        sum1 += i
    for i in data2:
        sum2 += i
    return round(sum1 / len(data1) - sum2 / len(data2), 4), data2[size2 - 1]


def init_config(client, symbol):
    client.mode = config.get(symbol, "mode")
    client.amount = float(config.get(symbol, "amount"))
    client.transaction = float(config.get(symbol, "transaction"))
    client.percentage = 1.0
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
    counter = buy = sell = avg_sell = avg_buy = first_close = last_close = 0
    ma = old_ma = float(config.get(symbol, "ma"))
    while True:
        try:
            if counter > 300:
                counter = 0
            elif counter % 15 == 0:
                ma, first_close = get_ma(client, symbol)
            order_info = None
            print(
                "\nma:[{},{}] ,close:[{},{}]".format(
                    ma,
                    old_ma,
                    first_close,
                    last_close,
                ))
            if ma > 0 and old_ma < 0 and last_close != first_close:
                client.get_coin_price(symbol)
                for i in range(3):
                    buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, i + 1)
                    if sell_amount >= client.amount:
                        break
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_BUY, sell, client.amount, ma)
            elif ma < 0 and old_ma > 0 and last_close != first_close:
                client.get_coin_price(symbol)
                for i in range(3):
                    buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, i + 1)
                    if buy_amount >= client.amount:
                        break
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_SELL, buy, client.amount, ma)
            if order_info is not None:
                order_process(client, order_info)
                if order_info.totalAmount - order_info.totalDealAmount < client.MIN_AMOUNT:
                    config.read("config.ini")
                    config.set(symbol, "ma", str(ma))
                    add_statistics(client, order_info)
                    fp = open("config.ini", "w")
                    config.write(fp)
                    fp.close()
                    send_email("ma:" + str(order_info))
                    old_ma = ma
            counter += 1
            last_close = first_close
            if period == '4hour':
                time.sleep(10)
        except Exception as e:
            print(e, traceback.format_exc())
            send_email("%s:unhandled exception:%s" % (symbol, traceback.format_exc()))
            exit()
