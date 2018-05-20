import time
import configparser
import json
import math
import api.OrderInfo as OrderInfo

# read config
config = configparser.ConfigParser()
config.read("config.ini")
percentage = float(config.get("trade", "percentage"))
rate_p = (100 + percentage) * 0.01
period = config.get("klines", "period")
size1 = int(config.get("klines", "size1"))
size2 = int(config.get("klines", "size2"))


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
    amount = float(config.get("trade", "amount"))
    current_base = float(config.get("trade", "currentbase"))
    buy_rate, sell_rate = get_next_buy_sell_rate(client)
    _next_buy = round(current_base / math.pow(rate_p, buy_rate), 4)
    _next_sell = round(current_base * math.pow(rate_p, sell_rate), 4)
    _next_buy_amount = round(amount * buy_rate + amount * (rate_p - 1) * (1 + buy_rate) * buy_rate / 2, 2)
    _next_sell_amount = amount * sell_rate
    return _next_buy, _next_buy_amount, _next_sell, _next_sell_amount


def modify_amt_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_amount, _next_sell, _next_sell_amount):
    amount = float(config.get("trade", "amount"))
    current_base = float(config.get("trade", "currentbase"))
    buy_rate = math.floor(math.log(current_base / _avg_sell, rate_p))
    buy_amount_rate = _next_buy_amount / amount
    if buy_rate > 1 and buy_rate > buy_amount_rate:
        return buy_rate * amount, round(current_base / math.pow(rate_p, buy_rate),
                                        4), _next_sell_amount, _next_sell
    sell_rate = math.floor(math.log(_avg_buy / current_base, rate_p))
    sell_amount_rate = _next_sell_amount / amount
    if sell_rate > 1 and sell_rate > sell_amount_rate:
        return _next_buy_amount, _next_buy, sell_rate * amount, round(
            current_base * math.pow(rate_p, sell_rate), 4)
    return _next_buy_amount, _next_buy, _next_sell_amount, _next_sell


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


def get_ma(client, symbol):
    data2 = client.get_klines(symbol, period, size2)
    data1 = data2[0:size1]
    sum1 = sum2 = 0
    for i in data1:
        sum1 += i
    for i in data2:
        sum2 += i
    return round(sum1 / len(data1) - sum2 / len(data2), 4)


def __main__(client, symbol):
    global buy, avg_buy, buy_amount, sell, avg_sell, sell_amount, next_base
    ma = get_ma(client, symbol)
    current_base = float(config.get("trade", "currentbase"))
    min_amount = float(config.get("trade", "minamount"))
    client.get_account_info()
    counter = 0
    next_buy, next_buy_amount, next_sell, next_sell_amount = get_next_buy_sell_info(client)
    while True:
        try:
            if counter > 300:
                next_buy, next_buy_amount, next_sell, next_sell_amount = get_next_buy_sell_info(client)
                counter = 0
            elif counter % 30 == 0:
                ma = get_ma(client, symbol)
            client.get_coin_price(symbol)
            for i in range(3):
                buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, i + 1)
                next_buy_amount_p, next_buy_p, next_sell_amount_p, next_sell_p = modify_amt_by_price(avg_buy,
                                                                                                     avg_sell,
                                                                                                     next_buy,
                                                                                                     next_buy_amount,
                                                                                                     next_sell,
                                                                                                     next_sell_amount)
                if not ((next_buy_p >= avg_sell and sell_amount < next_buy_amount_p) or (
                        next_sell_p <= avg_buy and buy_amount < next_sell_amount_p)):
                    break
            print(
                "\nBase:{} ,ma:{} ,nextSell:[{},{}] - buy:[{},{}] (+{}) | nextBuy:[{},{}] - sell:[{},{}]({})".format(
                    current_base,
                    ma,
                    next_sell_p,
                    next_sell_amount_p,
                    buy,
                    buy_amount,
                    round(
                        next_sell_p - buy,
                        4),
                    next_buy_p,
                    next_buy_amount_p,
                    sell,
                    sell_amount,
                    round(
                        next_buy_p - sell,
                        4)))
            order_info = None
            if ma > 0 and next_buy_p >= avg_sell and sell_amount >= next_buy_amount_p:
                next_base = next_buy_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_BUY, sell, next_buy_amount_p, next_base)
            elif ma < 0 and next_sell_p <= avg_buy and buy_amount >= next_sell_amount_p:
                next_base = next_sell_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_SELL, buy, next_sell_amount_p, next_base)
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
                    next_buy, next_buy_amount, next_sell, next_sell_amount = get_next_buy_sell_info(client)
        except Exception as err:
            print(err)
        # time.sleep(0.1)
        counter += 1
