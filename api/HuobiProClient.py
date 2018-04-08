# -*- coding: utf-8 -*-
# encoding: utf-8

import time
import sys

from api.HuobiProAPI import *
from util.MyUtil import fromDict, fromTimeStamp

# read config
config = configparser.ConfigParser()
config.read("config.ini")

# getConfig
trade_wait_count = int(config.get("trade", "tradewaitcount"))
account_id = config.get("account", "id")


class HuobiProClient:
    TRADE_BUY = "buy-limit"
    TRADE_SELL = "sell-limit"

    BALANCE_HT = "ht"
    BALANCE_USDT = "usdt"

    SYMBOL_HT = "htusdt"

    COMPLETE_STATUS = 'filled'

    MIN_AMOUNT = float(config.get("trade", "minamount"))

    # global variable
    accountInfo = {BALANCE_USDT: {"total": 0, "available": 0, "freezed": 0},
                   BALANCE_HT: {"total": 0, "available": 0, "freezed": 0}}

    priceInfo = {SYMBOL_HT: {"sell": 0, 'sellAmount': 0, "buy": 0, 'buyAmount': 0}}

    def get_coin_num(self, symbol):
        return fromDict(self.accountInfo, symbol, "available")

    def make_order(self, my_order_info):
        print(
            u'\n-------------------------------------------spot order------------------------------------------------')
        result = send_order(account_id, my_order_info.amount, my_order_info.symbol, my_order_info.orderType,
                            my_order_info.price)
        if result['status'] == 'ok':
            print("OrderId", result['data'], my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                  my_order_info.amount, "  ", fromTimeStamp(int(time.time())))
            return result['data']
        else:
            print("order failed！", my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                  my_order_info.amount)
            return "-1"

    def cancel_my_order(self, my_order_info):
        print(
            u'\n---------------------------------------spot cancel order--------------------------------------------')
        result = cancel_order(my_order_info.orderId)
        if result['status'] == 'ok':
            # print(u"order", result['data'], "canceled")
            self.write_log(my_order_info)
            self.write_log(my_order_info, "order " + result['data'] + " canceled")
        else:
            print(u"order", my_order_info.orderId, "not canceled or cancel failed！！！")
        state = self.check_order_status(my_order_info)
        # not canceled or cancel failed(part dealed) continue cancel
        if state != 'canceled' and state != 'partial-canceled' and state != 'filled':
            self.cancel_my_order(my_order_info)
        return state

    def check_order_status(self, my_order_info, wait_count=0):
        order_id = my_order_info.orderId
        order_result = order_info(order_id)
        if order_result["status"] == 'ok':
            order = order_result["data"]
            order_id = order["id"]
            state = order["state"]
            my_order_info.set_deal_amount(float(order["field-amount"]))
            if my_order_info.dealAmount > 0:
                my_order_info.set_avg_price(float(order["field-cash-amount"]) / float(order["field-amount"]))
            if state == 'canceled':
                print("order", order_id, "canceled")
            elif state == 'partial-canceled':
                print("part dealed ", my_order_info.dealAmount, " and canceled")
            elif state == ' partial-filled':
                if wait_count == trade_wait_count:
                    print("part dealed ", my_order_info.dealAmount)
                else:
                    print("part dealed ", my_order_info.dealAmount, end=" ")
                    sys.stdout.flush()
            elif state == 'filled':
                print("order", order_id, "complete deal")
            else:
                if wait_count == trade_wait_count:
                    print("timeout no deal")
                else:
                    print("no deal", end=" ")
                    sys.stdout.flush()
            return state
        else:
            print(order_id, "checkOrderStatus failed,try again.")
            self.check_order_status(my_order_info, wait_count)

    def trade(self, my_order_info):
        if my_order_info.price == 0:
            my_order_info.set_price(self.get_trade_price(my_order_info.symbol, my_order_info.orderType))
        if my_order_info.amount < self.MIN_AMOUNT:
            return 'filled'
        order_id = self.make_order(my_order_info)
        if order_id != "-1":
            my_order_info.set_order_id(order_id)
            wait_count = 0
            state = ''
            deal_amount_bak = my_order_info.dealAmount
            avg_price_bak = my_order_info.avgPrice
            while wait_count < trade_wait_count and state != 'filled':
                state = self.check_order_status(my_order_info, wait_count)
                time.sleep(0.1)
                wait_count += 1
                if wait_count == trade_wait_count and state != 'filled':
                    trade_price = self.get_trade_price(my_order_info.symbol, my_order_info.orderType)
                    if trade_price == my_order_info.price:
                        wait_count -= 1
            deal_amount = deal_amount_bak + my_order_info.dealAmount
            if deal_amount > 0:
                my_order_info.set_avg_price(
                    (deal_amount_bak * avg_price_bak + my_order_info.dealAmount * my_order_info.avgPrice) / deal_amount)
            my_order_info.set_deal_amount(deal_amount)
            if state != 'filled':
                state = self.cancel_my_order(my_order_info)
            return state
        else:
            return 'failed'

    def get_coin_price(self, symbol):
        data = get_ticker(symbol)
        if data["status"] == 'ok':
            self.priceInfo[symbol]["sell"] = round(float(data["tick"]["ask"][0]), 5)
            self.priceInfo[symbol]["sellAmount"] = float(data["tick"]["ask"][1])
            self.priceInfo[symbol]["buy"] = round(float(data["tick"]["bid"][0]), 5)
            self.priceInfo[symbol]["buyAmount"] = float(data["tick"]["bid"][1])

    def get_price_info(self, symbol):
        return self.priceInfo[symbol]["buy"], self.priceInfo[symbol]["buyAmount"], self.priceInfo[symbol]["sell"], \
               self.priceInfo[symbol][
                   "sellAmount"]

    def get_trade_price(self, symbol, order_type):
        self.get_coin_price(symbol)
        if order_type == self.TRADE_BUY:
            return self.priceInfo[symbol]["sell"]
        else:
            return self.priceInfo[symbol]["buy"]

    def write_log(self, my_order_info, text=""):
        f = open(r'log.txt', 'a')
        if text == "":
            f.writelines(' '.join(
                ["\n", my_order_info.orderId, my_order_info.symbol, my_order_info.orderType, str(my_order_info.price),
                 str(my_order_info.avgPrice),
                 str(my_order_info.dealAmount),
                 str(round(my_order_info.avgPrice * my_order_info.dealAmount, 4)),
                 str(fromTimeStamp(int(time.time())))]))
        else:
            f.writelines("\n" + text)
        f.close()

    def get_account_info(self):
        print(
            u'---------------------------------------spot account info------------------------------------------------')
        my_account_info = get_balance(account_id)
        symbol = [self.BALANCE_USDT, self.BALANCE_HT]
        if my_account_info["status"] == 'ok':
            data = fromDict(my_account_info, "data", "list")
            for sy in symbol:
                _sy = list(filter(lambda x: x["currency"] == sy, data))
                self.accountInfo[sy]["available"] = float(_sy[0]["balance"])
                self.accountInfo[sy]["freezed"] = float(_sy[1]["balance"])
                self.accountInfo[sy]["total"] = self.accountInfo[sy]["available"] + self.accountInfo[sy]["freezed"]
                print(sy.upper(), self.accountInfo[sy]["total"], "available", self.accountInfo[sy]["available"],
                      "freezed", self.accountInfo[sy]["freezed"])
        else:
            print("getAccountInfo Fail,Try again!")
            self.get_account_info()
