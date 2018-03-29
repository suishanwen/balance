#!/usr/bin/python
# -*- coding: utf-8 -*-
# encoding: utf-8

import time, sys, configparser
from util.MyUtil import fromDict, fromTimeStamp, sendEmail
from api.OkexSpotAPI import OkexSpot

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
orderDiff = float(config.get("trade", "orderDiff"))

# global variable
orderInfo = {"symbol": "", "type": "", "price": 0, "amount": 0, "avgPrice": 0, "dealAmount": 0, "transaction": 0}
orderList = []


def setOrderInfo(symbol, type, amount=0, transaction=0):
    global orderInfo
    orderInfo['symbol'] = symbol
    orderInfo['type'] = type
    orderInfo['amount'] = amount
    orderInfo['price'] = 0
    orderInfo['dealAmount'] = 0
    if amount > 0:
        orderInfo['transaction'] = 0
    elif transaction != 0:
        orderInfo['transaction'] = transaction


def setPrice(price):
    global orderInfo
    orderInfo['price'] = price


def setAvgPrice(avgPrice):
    global orderInfo
    orderInfo['avgPrice'] = avgPrice


def setDealAmount(dealAmount):
    global orderInfo
    orderInfo['dealAmount'] = dealAmount


def setTransaction(type):
    global orderInfo
    print(orderInfo)
    if type == "plus":
        orderInfo['transaction'] = round(orderInfo['transaction'] + orderInfo['dealAmount'] * orderInfo['avgPrice'], 2)
    else:
        orderInfo['transaction'] = round(orderInfo['transaction'] - orderInfo['dealAmount'] * orderInfo['avgPrice'], 2)


def getBuyAmount(price, accuracy=2):
    global orderInfo
    return round(orderInfo['transaction'] / price, accuracy)


def getUnhandledAmount():
    global orderInfo
    return round(float(orderInfo["amount"]) - float(orderInfo["dealAmount"]), 5)


def getCoinNum(symbol):
    myAccountInfo = okcoinSpot.userinfo()
    if myAccountInfo["result"]:
        free = fromDict(myAccountInfo, "info", "funds", "free")
        if symbol == "btc_cny":
            return float(free["btc"])
        else:
            return float(free["ltc"])
    else:
        print("getCoinNum Fail,Try again!")
        getCoinNum(symbol)


def makeOrder(symbol, type, price, amount):
    print(
        u'\n---------------------------------------------spot order--------------------------------------------------')
    result = okcoinSpot.trade(symbol, type, price, amount)
    if result['result']:
        setPrice(price)
        print("OrderId", result['order_id'], symbol, type, price, amount, "  ", fromTimeStamp(int(time.time())))
        return result['order_id']
    else:
        print("order failed！", symbol, type, price, amount)
        global orderInfo
        print(orderInfo)
        return "-1"


def cancelOrder(symbol, orderId):
    print(u'\n-----------------------------------------spot cancel order----------------------------------------------')
    result = okcoinSpot.cancelOrder(symbol, orderId)
    if result['result']:
        print(u"order", result['order_id'], "canceled")
    else:
        print(u"order", orderId, "not canceled or cancel failed！！！")
    status = checkOrderStatus(symbol, orderId)
    if status != -1 and status != 2:  # not canceled or cancel failed(part dealed) continue cancel
        cancelOrder(symbol, orderId)
    return status


def addOrderList(order):
    global orderList
    orderList = list(filter(lambda orderIn: orderIn["order_id"] != order["order_id"], orderList))
    if order["deal_amount"] > 0:
        orderList.append(order)


def checkOrderStatus(symbol, orderId, watiCount=0):
    global tradeWaitCount
    orderResult = okcoinSpot.orderinfo(symbol, orderId)
    if orderResult["result"]:
        orders = orderResult["orders"]
        if len(orders) > 0:
            order = orders[0]
            orderId = order["order_id"]
            status = order["status"]
            setDealAmount(order["deal_amount"])
            setAvgPrice(order["avg_price"])
            addOrderList(order)
            if status == -1:
                print("order", orderId, "canceled")
            elif status == 0:
                if watiCount == tradeWaitCount:
                    print("timeout no deal")
                else:
                    print("no deal", end=" ")
                    sys.stdout.flush()
            elif status == 1:
                global orderInfo
                if watiCount == tradeWaitCount:
                    print("part dealed ", orderInfo["dealAmount"])
                else:
                    print("part dealed ", orderInfo["dealAmount"], end=" ")
                    sys.stdout.flush()
            elif status == 2:
                print("order", orderId, "complete deal")
            elif status == 3:
                print("order", orderId, "canceling")
            return status
    else:
        print(orderId, " order not found")
        return -2


def trade(symbol, type, amount, price=0):
    global tradeWaitCount, orderInfo, orderDiff
    if price == 0:
        price = getTradePrice(symbol, type)
    if type == "buy":
        amount = getBuyAmount(price, 4)
    if amount < 0.01:
        return 2
    orderId = makeOrder(symbol, type, price, amount)
    if orderId != "-1":
        watiCount = 0
        status = 0
        global orderInfo
        dealAmountBak = orderInfo["dealAmount"]
        while watiCount < (tradeWaitCount + 1) and status != 2:
            status = checkOrderStatus(symbol, orderId, watiCount)
            time.sleep(0.5)
            watiCount += 1
            if watiCount == tradeWaitCount and status != 2:
                if getTradePrice(symbol, type) == orderInfo["price"]:
                    watiCount -= 1
        if status != 2:
            status = cancelOrder(symbol, orderId)
            setDealAmount(dealAmountBak + orderInfo["dealAmount"])
        return status
    else:
        return -2


def getCoinPrice(symbol, type):
    if symbol == "btc_cny":
        if type == "buy":
            return round(float(okcoinSpot.ticker('btc_cny')["ticker"]["buy"]), 2)
        else:
            return round(float(okcoinSpot.ticker('btc_cny')["ticker"]["sell"]), 2)
    else:
        if type == "buy":
            return round(float(okcoinSpot.ticker('ltc_cny')["ticker"]["buy"]), 2)
        else:
            return round(float(okcoinSpot.ticker('ltc_cny')["ticker"]["sell"]), 2)


def getTradePrice(symbol, type):
    if symbol == "btc_cny":
        if type == "buy":
            return round(float(okcoinSpot.ticker('btc_cny')["ticker"]["buy"]) + orderDiff, 2)
        else:
            return round(float(okcoinSpot.ticker('btc_cny')["ticker"]["sell"]) - orderDiff, 2)
    else:
        if type == "buy":
            return round(float(okcoinSpot.ticker('ltc_cny')["ticker"]["buy"]) + orderDiff, 2)
        else:
            return round(float(okcoinSpot.ticker('ltc_cny')["ticker"]["sell"]) - orderDiff, 2)


def writeLog(text=""):
    global orderInfo
    f = open(r'log.txt', 'a')
    if text == "":
        f.writelines(' '.join(
            ["\n", orderInfo["symbol"], orderInfo["type"], str(orderInfo["price"]), str(orderInfo["avgPrice"]),
             str(orderInfo["dealAmount"]),
             str(round(orderInfo["avgPrice"] * orderInfo["dealAmount"], 2)), str(fromTimeStamp(int(time.time())))]))
    else:
        f.writelines("\n" + text)
    f.close()


def showAccountInfo():
    print(u'---------------------------------------spot account info------------------------------------------------')
    myAccountInfo = okcoinSpot.userinfo()
    print(myAccountInfo)
    if myAccountInfo["result"]:
        freezed = fromDict(myAccountInfo, "info", "funds", "freezed")
        free = fromDict(myAccountInfo, "info", "funds", "free")
        print(u"USDT", free["usdt"], "freezed", freezed["usdt"])
        print(u"OKB", free["okb"], "freezed", freezed["okb"])
    else:
        print("showAccountInfo Fail,Try again!")
        showAccountInfo()
