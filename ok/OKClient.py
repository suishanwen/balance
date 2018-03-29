import sys
import importlib

sys.path.append("/home/balance")
importlib.reload(sys)

import time
import configparser
import api.OkexClient as OkexClient
import random


# read config
config = configparser.ConfigParser()
config.read("config.ini")

OkexClient.get_account_info()

symbol = OkexClient.SYMBOL_OKB
transaction = float(config.get("trade", "transaction"))
currentBase = float(config.get("trade", "currentBase"))
percentage = float(config.get("trade", "percentage"))

#
#
# def order_process(my_order_info):
#     my_order_info.set_amount(my_order_info.get_unhandled_amount())
#     state = HuobiClient.trade(my_order_info)
#     if my_order_info.amount < 0.1 and state == 'filled':
#         HuobiClient.write_log(my_order_info)
#     elif my_order_info.dealAmount > 0:
#         my_order_info.set_price(0)
#         order_process(my_order_info)
#
#
# ret = round(random.uniform(0.01, 0.1), 3)
# num = random.randint(1, 10)
# if num > 5:
#     ret = -ret
# nextBuy = round(currentBase * (100 - percentage - ret) * 0.01, 4)
# nextSell = round(currentBase * (100 + percentage - ret) * 0.01, 4)
#
# while True:
#     try:
#         HuobiClient.get_coin_price(symbol)
#         priceInfo = HuobiClient.priceInfo
#         buyPrice = priceInfo[symbol]["buy"]
#         buyAmount = priceInfo[symbol]["buyAmount"]
#         sellPrice = priceInfo[symbol]["sell"]
#         sellAmount = priceInfo[symbol]["sellAmount"]
#         print('\nBase:', currentBase, ",Buy:", nextBuy, ',Sell:', nextSell,
#               '|buy1:', buyPrice, '(+', round(nextSell - buyPrice, 4), ')',
#               ',sell1:', sellPrice, '(', round(nextBuy - sellPrice, 4), ')',
#               )
#         orderInfo = {}
#         if nextBuy >= sellPrice and sellAmount >= transaction:
#             buyOrder = HuobiClient.MyOrderInfo(symbol, HuobiClient.TRADE_BUY, sellPrice, transaction)
#             orderInfo = buyOrder
#         elif nextSell <= buyPrice and buyAmount >= transaction:
#             sellOrder = HuobiClient.MyOrderInfo(symbol, HuobiClient.TRADE_SELL, buyPrice, transaction)
#             orderInfo = sellOrder
#         if orderInfo != {}:
#             order_process(orderInfo)
#             if orderInfo.amount < 0.1:
#                 currentBase = round(orderInfo.avgPrice, 4)
#                 config.read("config.ini")
#                 config.set("trade", "currentBase", str(currentBase))
#                 fp = open("config.ini", "w")
#                 config.write(fp)
#                 fp.close()
#                 ret = round(random.uniform(0.01, 0.1), 3)
#                 num = random.randint(1, 10)
#                 if num > 5:
#                     ret = -ret
#                 nextBuy = round(currentBase * (100 - percentage - ret) * 0.01, 4)
#                 nextSell = round(currentBase * (100 + percentage - ret) * 0.01, 4)
#     except Exception as err:
#         print(err)
#     time.sleep(0.1)
