import sys
import importlib
import time
import configparser
from threading import Thread
import api.HuobiProClient as HuobiClient

sys.path.append("/home/myRobot")
importlib.reload(sys)

# read config
config = configparser.ConfigParser()
config.read("config.ini")

HuobiClient.get_trade("htusdt")
# HuobiClient.get_accounts()
# HuobiClient.get_account_info([HuobiClient.BALANCE_HT, HuobiClient.BALANCE_USDT])

symbol = HuobiClient.SYMBOL_HT
transaction = float(config.get("trade", "transaction"))

def cal_avg_reward(my_order_info):
    order_buy_list = list(filter(lambda order_in: order_in["type"] == HuobiClient.TRADE_BUY, HuobiClient.orderList))
    order_sell_list = list(filter(lambda order_in: order_in["type"] == HuobiClient.TRADE_SELL, HuobiClient.orderList))
    buy_amount = 0
    buy_cost = 0
    sell_amount = 0
    sell_reward = 0
    fee = 0
    for order in order_buy_list:
        buy_amount += float(order["field-amount"])
        buy_cost += float(order["field-cash-amount"])
        fee += float(order["field-fees"]) * float(order["field-cash-amount"]) / float(order["field-amount"])
    buy_avg = buy_cost / buy_amount
    for order in order_sell_list:
        sell_amount += float(order["field-amount"])
        sell_reward += float(order["field-cash-amount"])
        fee += float(order["field-fees"])
    sell_avg = sell_reward / sell_amount
    avg_reward = round(sell_avg - buy_avg, 5)
    config.read("config.ini")
    config.set("statis", "avgreward", str(round(float(config.get("statis", "avgreward")) + avg_reward, 5)))
    config.set("statis", "reward", str(round(float(config.get("statis", "reward")) + sell_reward - buy_cost, 5)))
    config.set("statis", "transcount", str(int(config.get("statis", "transcount")) + 1))
    config.set("statis", "fee", str(round(float(config.get("statis", "fee")) + fee, 5)))
    config.set("statis", "realReward",
               str(round(
                   float(config.get("statis", "reward")) + sell_reward - buy_cost - float(config.get("statis", "fee")),
                   5)))

    fp = open("config.ini", "w")
    config.write(fp)
    HuobiClient.write_log(my_order_info, ' '.join(
        ["avgPriceDiff:", str(avg_reward), "fee", str(round(fee, 5)), "transactionReward:",
         str(round(sell_reward - buy_cost - fee, 5))]))


def order_process(my_order_info):
    my_order_info.set_amount(my_order_info.get_unhandled_amount())
    state = HuobiClient.trade(my_order_info)
    # dealed or part dealed
    if state != 'partial-canceled' and state != 'canceled':
        my_order_info.set_transaction("minus")
        if state == 'filled':
            HuobiClient.write_log(my_order_info)
    else:
        my_order_info.set_price(0)
        order_process(my_order_info)
    if state != 'filled' and (my_order_info.dealAmount != 0 or state == "failed"):
        order_process(my_order_info)


while True:
    try:
        HuobiClient.get_coin_price(symbol)
        priceInfo = HuobiClient.priceInfo
        buyPrice = priceInfo[symbol]["buy"]
        sellPrice = priceInfo[symbol]["sell"]
        percentage = round((sellPrice - buyPrice) / buyPrice * 100, 2)
        print(percentage, "%")
        buyAmount = round(transaction / (buyPrice + 0.0001), 2)
        if percentage > 0.2:
            HuobiClient.write_log({},
                                  "----------------------------------" + str(
                                      percentage) + "%------------------------------------")
            buyOrder = HuobiClient.MyOrderInfo(symbol, HuobiClient.TRADE_BUY, buyPrice + 0.0001, buyAmount)
            sellOrder = HuobiClient.MyOrderInfo(symbol, HuobiClient.TRADE_SELL, sellPrice - 0.0001, buyAmount)

            t1 = Thread(target=order_process, args=(buyOrder,))
            t2 = Thread(target=order_process, args=(sellOrder,))
            t1.start()
            t2.start()
            while t1.is_alive() or t2.is_alive():
                time.sleep(0.1)
            cal_avg_reward({})
    except Exception as err:
        print(err)
    time.sleep(0.1)
