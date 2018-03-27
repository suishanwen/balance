import sys
import importlib
import time
import configparser
import api.HuobiProClient as HuobiClient

sys.path.append("/home/myRobot")
importlib.reload(sys)

# read config
config = configparser.ConfigParser()
config.read("config.ini")

HuobiClient.get_account_info([HuobiClient.BALANCE_HT, HuobiClient.BALANCE_USDT])

symbol = HuobiClient.SYMBOL_HT
transaction = float(config.get("trade", "transaction"))
currentBase = float(config.get("trade", "currentBase"))
percentage = float(config.get("trade", "percentage"))


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
        return
    if state != 'filled' and (my_order_info.dealAmount != 0 or state == "failed"):
        order_process(my_order_info)


nextBuy = round(currentBase * (100 - percentage) * 0.01, 4)
nextSell = round(currentBase * (100 + percentage) * 0.01, 4)

while True:
    try:
        HuobiClient.get_coin_price(symbol)
        priceInfo = HuobiClient.priceInfo
        buyPrice = priceInfo[symbol]["buy"]
        sellPrice = priceInfo[symbol]["sell"]
        print('\nBase:', currentBase, ",Buy:", nextBuy, ',Sell:', nextSell,
              '|buy1:', buyPrice, '(+', round(nextSell - buyPrice, 4), ')',
              ',sell1:', sellPrice, '(', round(nextBuy - sellPrice, 4), ')',
              )
        orderInfo = {}
        if nextBuy >= sellPrice:
            buyOrder = HuobiClient.MyOrderInfo(symbol, HuobiClient.TRADE_BUY, sellPrice, transaction)
            orderInfo = buyOrder
        elif nextSell <= buyPrice:
            sellOrder = HuobiClient.MyOrderInfo(symbol, HuobiClient.TRADE_SELL, buyPrice, transaction)
            orderInfo = sellOrder
        if orderInfo != {}:
            order_process(orderInfo)
            currentBase = orderInfo.avgPrice
            config.read("config.ini")
            config.set("trade", "currentBase", str(currentBase))
            fp = open("config.ini", "w")
            config.write(fp)
            nextBuy = round(currentBase * (100 - percentage) * 0.01, 4)
            nextSell = round(currentBase * (100 + percentage) * 0.01, 4)
    except Exception as err:
        print(err)
    time.sleep(0.1)
