# -*- coding: utf-8 -*-
# encoding: utf-8

import time
import sys

from api.HuobiProAPI import *
from util.MyUtil import fromDict, fromTimeStamp

BALANCE_HT = "ht"
BALANCE_USDT = "usdt"

SYMBOL_HT = "htusdt"

TRADE_BUY = "buy-limit"
TRADE_SELL = "sell-limit"

# read config
config = configparser.ConfigParser()
config.read("config.ini")

# getConfig
tradeWaitCount = int(config.get("trade", "tradeWaitCount"))
orderDiff = float(config.get("trade", "orderDiff"))
accountId = config.get("account", "id")

# global variable
accountInfo = {BALANCE_USDT: {"total": 0, "available": 0, "freezed": 0},
               BALANCE_HT: {"total": 0, "available": 0, "freezed": 0}}
priceInfo = {SYMBOL_HT: {"sell": 0, "buy": 0}}
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
        return round(float(self.amount) - float(self.dealAmount), accuracy)


def get_coin_num(symbol):
    return fromDict(accountInfo, symbol, "available")


def make_order(my_order_info):
    print(
        u'\n---------------------------------------------spot order--------------------------------------------------')
    result = send_order(accountId, my_order_info.amount, my_order_info.symbol, my_order_info.orderType,
                        my_order_info.price)
    if result['status'] == 'ok':
        print("OrderId", result['data'], my_order_info.symbol, my_order_info.orderType, my_order_info.price,
              my_order_info.amount, "  ", fromTimeStamp(int(time.time())))
        return result['data']
    else:
        print("order failed！", my_order_info.symbol, my_order_info.orderType, my_order_info.price, my_order_info.amount)
        return "-1"


def cancel_my_order(my_order_info):
    print(u'\n-----------------------------------------spot cancel order----------------------------------------------')
    result = cancel_order(my_order_info.orderId)
    if result['status'] == 'ok':
        print(u"order", result['data'], "canceled")
        write_log(my_order_info)
        write_log(my_order_info, "order " + result['data'] + " canceled")
    else:
        print(u"order", my_order_info.orderId, "not canceled or cancel failed！！！")
    state = check_order_status(my_order_info)
    # not canceled or cancel failed(part dealed) continue cancel
    if state != 'canceled' and state != 'partial-canceled' and state != 'filled':
        cancel_my_order(my_order_info)
    return state


def add_order_list(order):
    global orderList
    orderList = list(filter(lambda order_in: order_in["id"] != order["id"], orderList))
    if float(order["field-amount"]) > 0:
        orderList.append(order)


def check_order_status(my_order_info, wait_count=0):
    order_id = my_order_info.orderId
    order_result = order_info(order_id)
    if order_result["status"] == 'ok':
        order = order_result["data"]
        order_id = order["id"]
        state = order["state"]
        my_order_info.set_deal_amount(float(order["field-amount"]))
        if my_order_info.dealAmount > 0:
            my_order_info.set_avg_price(float(order["field-cash-amount"]) / float(order["field-amount"]))
        add_order_list(order)
        if state == 'canceled':
            print("order", order_id, "canceled")
        elif state == 'partial-canceled':
            print("part dealed ", my_order_info.dealAmount, " and canceled")
        elif state == ' partial-filled':
            if wait_count == tradeWaitCount:
                print("part dealed ", my_order_info.dealAmount)
            else:
                print("part dealed ", my_order_info.dealAmount, end=" ")
                sys.stdout.flush()
        elif state == 'filled':
            print("order", order_id, "complete deal")
        else:
            if wait_count == tradeWaitCount:
                print("timeout no deal")
            else:
                print("no deal", end=" ")
                sys.stdout.flush()
        return state
    else:
        print(order_id, "checkOrderStatus failed,try again.")
        check_order_status(my_order_info, wait_count)


def trade(my_order_info):
    if my_order_info.price == 0:
        my_order_info.set_price(get_trade_price(my_order_info.symbol, my_order_info.orderType))
    if my_order_info.amount < 0.1:
        return 'filled'
    order_id = make_order(my_order_info)
    if order_id != "-1":
        my_order_info.set_order_id(order_id)
        wait_count = 0
        state = ''
        deal_amount_bak = my_order_info.dealAmount
        while wait_count < (tradeWaitCount + 1) and state != 'filled':
            state = check_order_status(my_order_info, wait_count)
            time.sleep(0.1)
            wait_count += 1
            if wait_count == tradeWaitCount and state != 'filled':
                trade_price = get_trade_price(my_order_info.symbol, my_order_info.orderType)
                if my_order_info.orderType == TRADE_BUY and trade_price == my_order_info.price + orderDiff:
                    wait_count -= 1
                elif my_order_info.orderType == TRADE_SELL and trade_price == my_order_info.price - orderDiff:
                    wait_count -= 1
        if state != 'filled':
            state = cancel_my_order(my_order_info)
            my_order_info.set_deal_amount(deal_amount_bak + my_order_info.dealAmount)
        return state
    else:
        return 'failed'


def get_coin_price(symbol):
    data = get_ticker(symbol)
    if data["status"] == 'ok':
        priceInfo[symbol]["sell"] = round(float(data["tick"]["ask"][0]), 5)
        priceInfo[symbol]["buy"] = round(float(data["tick"]["bid"][0]), 5)


def get_trade_price(symbol, order_type):
    get_coin_price(symbol)
    if order_type == TRADE_BUY:
        return priceInfo[symbol]["buy"] + orderDiff
    else:
        return priceInfo[symbol]["sell"] - orderDiff


def write_log(my_order_info, text=""):
    f = open(r'log.txt', 'a')
    if text == "":
        f.writelines(' '.join(
            ["\n", my_order_info.orderId, my_order_info.symbol, my_order_info.orderType, str(my_order_info.price),
             str(my_order_info.avgPrice),
             str(my_order_info.dealAmount),
             str(round(my_order_info.avgPrice * my_order_info.dealAmount, 3)), str(fromTimeStamp(int(time.time())))]))
    else:
        f.writelines("\n" + text)
    f.close()


def get_account_info(symbol):
    print(u'---------------------------------------spot account info------------------------------------------------')
    my_account_info = get_balance(accountId)
    if my_account_info["status"] == 'ok':
        data = fromDict(my_account_info, "data", "list")
        for sy in symbol:
            _sy = list(filter(lambda x: x["currency"] == sy, data))
            accountInfo[sy]["available"] = float(_sy[0]["balance"])
            accountInfo[sy]["freezed"] = float(_sy[1]["balance"])
            accountInfo[sy]["total"] = accountInfo[sy]["available"] + accountInfo[sy]["freezed"]
            print(sy.upper(), accountInfo[sy]["total"], "available", accountInfo[sy]["available"],
                  "freezed", accountInfo[sy]["freezed"])
    else:
        print("getAccountInfo Fail,Try again!")
        get_account_info(symbol)

# getAccountInfo([BALANCE_HT, BALANCE_USDT])
# getCoinPrice(SYMBOL_HT)
