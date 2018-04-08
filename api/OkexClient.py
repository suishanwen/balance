# -*- coding: utf-8 -*-
# encoding: utf-8

import time
import sys

from api.HuobiProAPI import *
from util.MyUtil import fromDict, fromTimeStamp
from api.OkexSpotAPI import OkexSpot

BALANCE_OKB = "okb"
BALANCE_USDT = "usdt"

SYMBOL_OKB = "okb_usdt"

TRADE_BUY = "buy"
TRADE_SELL = "sell"

# read config
configBase = configparser.ConfigParser()
config = configparser.ConfigParser()
configBase.read("../key.ini")
config.read("config.ini")

# init apikey,secretkey,url
okcoinRESTURL = 'www.okex.com'
apikey = configBase.get("okex", "apiKey")
secretkey = configBase.get("okex", "secretKey")

# currentAPI
okcoinSpot = OkexSpot(okcoinRESTURL, apikey, secretkey)

# getConfig
tradeWaitCount = int(config.get("trade", "tradeWaitCount"))
# global variable
accountInfo = {BALANCE_USDT: {"total": 0, "available": 0, "freezed": 0},
               BALANCE_OKB: {"total": 0, "available": 0, "freezed": 0}}
priceInfo = {SYMBOL_OKB: {"sell": 0, 'sellAmount': 0, "buy": 0, 'buyAmount': 0}}
orderList = []


class MyOrderInfo:
    def __init__(self, symbol, order_type, price=0, amount=0, transaction=0):
        self.orderId = ""
        self.symbol = symbol
        self.orderType = order_type
        self.amount = amount
        self.transaction = transaction
        self.price = price
        self.dealAmount = 0
        self.avgPrice = 0

    def set_order_id(self, order_id):
        self.orderId = order_id

    def set_price(self, price):
        self.price = price

    def set_avg_price(self, avg_price):
        self.avgPrice = avg_price

    def set_amount(self, amount):
        self.amount = amount

    def set_deal_amount(self, deal_amount):
        self.dealAmount = deal_amount

    def set_transaction(self, trans_type):
        if trans_type == 'plus':
            self.transaction = round(self.transaction + self.dealAmount * self.avgPrice, 3)
        else:
            self.transaction = round(self.transaction - self.dealAmount * self.avgPrice, 3)

    def get_buy_amount(self, price, accuracy=2):
        return round(self.transaction / price, accuracy)

    def get_unhandled_amount(self, accuracy=2):
        return round(self.amount - self.dealAmount, accuracy)


def get_coin_num(symbol):
    return fromDict(accountInfo, symbol, "available")


def make_order(my_order_info):
    print(
        u'\n---------------------------------------------spot order--------------------------------------------------')
    result = okcoinSpot.trade(my_order_info.symbol, my_order_info.orderType, my_order_info.price, my_order_info.amount)
    if result['result']:
        print("OrderId", result['order_id'], my_order_info.symbol, my_order_info.orderType, my_order_info.price,
              my_order_info.amount, "  ", fromTimeStamp(int(time.time())))
        return result['order_id']
    else:
        print("order failed！", my_order_info.symbol, my_order_info.orderType, my_order_info.price, my_order_info.amount)
        return "-1"


def cancel_my_order(my_order_info):
    print(u'\n-----------------------------------------spot cancel order----------------------------------------------')
    result = okcoinSpot.cancelOrder(my_order_info.symbol, my_order_info.orderId)
    if result['result']:
        write_log(my_order_info)
        write_log(my_order_info, "order " + result['order_id'] + " canceled")
    else:
        print(u"order", my_order_info.orderId, "not canceled or cancel failed！！！")
    status = check_order_status(my_order_info)
    if status != -1 and status != 2:  # not canceled or cancel failed(part dealed) continue cancel
        cancel_my_order(my_order_info)
    return status


def add_order_list(order):
    global orderList
    orderList = list(filter(lambda order_in: order_in["order_id"] != order["order_id"], orderList))
    if order["deal_amount"] > 0:
        orderList.append(order)


def check_order_status(my_order_info, wait_count=0):
    order_id = my_order_info.orderId
    order_result = okcoinSpot.orderinfo(my_order_info.symbol, my_order_info.orderId)
    if order_result["result"]:
        orders = order_result["orders"]
        if len(orders) > 0:
            order = orders[0]
            order_id = order["order_id"]
            status = order["status"]
            my_order_info.set_deal_amount(float(order["deal_amount"]))
            my_order_info.set_avg_price(order["avg_price"])
            add_order_list(order)
            if status == -1:
                print("order", order_id, "canceled")
            elif status == 0:
                if wait_count == tradeWaitCount:
                    print("timeout no deal")
                else:
                    print("no deal", end=" ")
                    sys.stdout.flush()
            elif status == 1:
                if wait_count == tradeWaitCount:
                    print("part dealed ", my_order_info.dealAmount)
                else:
                    print("part dealed ", my_order_info.dealAmount, end=" ")
                    sys.stdout.flush()
            elif status == 2:
                print("order", order_id, "complete deal")
            elif status == 3:
                print("order", order_id, "canceling")
            return status
    else:
        print(order_id, "checkOrderStatus failed,try again.")
        check_order_status(my_order_info, wait_count)


def trade(my_order_info):
    if my_order_info.price == 0:
        my_order_info.set_price(get_trade_price(my_order_info.symbol, my_order_info.orderType))
    if my_order_info.amount < 1:
        return 2
    order_id = make_order(my_order_info)
    if order_id != -1:
        my_order_info.set_order_id(order_id)
        wait_count = 0
        status = 0
        deal_amount_bak = my_order_info.dealAmount
        avg_price_bak = my_order_info.avgPrice
        while wait_count < tradeWaitCount and status != 2:
            status = check_order_status(my_order_info, wait_count)
            time.sleep(0.1)
            wait_count += 1
            if wait_count == tradeWaitCount and status != 2:
                trade_price = get_trade_price(my_order_info.symbol, my_order_info.orderType)
                if trade_price == my_order_info.price:
                    wait_count -= 1
        my_order_info.set_avg_price(
            (deal_amount_bak * avg_price_bak + my_order_info.dealAmount * my_order_info.avgPirce) / (
                    deal_amount_bak + my_order_info.dealAmount))
        my_order_info.set_deal_amount(deal_amount_bak + my_order_info.dealAmount)
        if status != 2:
            status = cancel_my_order(my_order_info)
        return status
    else:
        return -2


def get_coin_price(symbol):
    data = okcoinSpot.depth(symbol)
    priceInfo[symbol]["sell"] = float(data["asks"][0][0])
    priceInfo[symbol]["sellAmount"] = float(data["asks"][0][1])
    priceInfo[symbol]["buy"] = float(data["bids"][0][0])
    priceInfo[symbol]["buyAmount"] = float(data["bids"][0][1])


def get_trade_price(symbol, order_type):
    get_coin_price(symbol)
    if order_type == TRADE_BUY:
        return priceInfo[symbol]["sell"]
    else:
        return priceInfo[symbol]["buy"]


def write_log(my_order_info, text=""):
    f = open(r'log.txt', 'a')
    if text == "":
        f.writelines(' '.join(
            ["\n", str(my_order_info.orderId), my_order_info.symbol, my_order_info.orderType, str(my_order_info.price),
             str(my_order_info.avgPrice),
             str(my_order_info.dealAmount),
             str(round(my_order_info.avgPrice * my_order_info.dealAmount, 3)), str(fromTimeStamp(int(time.time())))]))
    else:
        f.writelines("\n" + text)
    f.close()


def get_account_info():
    print(u'---------------------------------------spot account info------------------------------------------------')
    my_account_info = okcoinSpot.userinfo()
    if my_account_info["result"]:
        freezed = fromDict(my_account_info, "info", "funds", "freezed")
        free = fromDict(my_account_info, "info", "funds", "free")
        print(u"USDT", free["usdt"], "freezed", freezed["usdt"])
        print(u"OKB", free["okb"], "freezed", freezed["okb"])
    else:
        print("getAccountInfo Fail,Try again!")
        get_account_info()

# getAccountInfo([BALANCE_HT, BALANCE_USDT])
# getCoinPrice(SYMBOL_HT)
