# -*- coding: utf-8 -*-
# encoding: utf-8

import time
import sys

from api.HuobiProAPI import *
from util.MyUtil import fromDict, fromTimeStamp
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
trade_wait_count = int(config.get("trade", "tradewaitcount"))


class OkexClient(object):
    BALANCE_OKB = "okb"
    BALANCE_USDT = "usdt"

    SYMBOL_OKB = "okb_usdt"

    TRADE_BUY = "buy"
    TRADE_SELL = "sell"

    COMPLETE_STATUS = 2

    MIN_AMOUNT = float(config.get("trade", "minamount"))

    # global variable
    accountInfo = {BALANCE_USDT: {"total": 0, "available": 0, "freezed": 0},
                   BALANCE_OKB: {"total": 0, "available": 0, "freezed": 0}}

    priceInfo = {SYMBOL_OKB: {"sell1": 0, 'sellAmount1': 0, "buy1": 0, 'buyAmount1': 0,
                              "sell2": 0, 'sellAmount2': 0, "buy2": 0, 'buyAmount2': 0,
                              "sell3": 0, 'sellAmount3': 0, "buy3": 0, 'buyAmount3': 0}}

    def get_coin_num(self, symbol):
        return fromDict(self.accountInfo, symbol, "available")

    @classmethod
    def make_order(cls, my_order_info):
        print(
            u'\n-------------------------------------------spot order------------------------------------------------')
        result = okcoinSpot.trade(my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                                  my_order_info.amount)
        if result.get('result'):
            print("OrderId", result['order_id'], my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                  my_order_info.amount, "  ", fromTimeStamp(int(time.time())))
            return result['order_id']
        else:
            print("order failed！", my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                  my_order_info.amount)
            return "-1"

    def cancel_my_order(self, my_order_info):
        print(
            u'\n---------------------------------------spot cancel order--------------------------------------------')
        result = okcoinSpot.cancelOrder(my_order_info.symbol, my_order_info.orderId)
        if result.get('result'):
            self.write_log(my_order_info, "order " + result['order_id'] + " canceled")
        else:
            print(u"order", my_order_info.orderId, "not canceled or cancel failed！！！")
        status = self.check_order_status(my_order_info)
        if status != -1 and status != 2:  # not canceled or cancel failed(part dealed) continue cancel
            self.cancel_my_order(my_order_info)
        return status

    def check_order_status(self, my_order_info, wait_count=0):
        order_id = my_order_info.orderId
        order_result = okcoinSpot.orderinfo(my_order_info.symbol, my_order_info.orderId)
        if order_result.get('result'):
            orders = order_result["orders"]
            if len(orders) > 0:
                order = orders[0]
                order_id = order["order_id"]
                status = order["status"]
                my_order_info.set_deal_amount(float(order["deal_amount"]))
                my_order_info.set_avg_price(order["avg_price"])
                if status == -1:
                    print("order", order_id, "canceled")
                elif status == 0:
                    if wait_count == trade_wait_count:
                        print("timeout no deal")
                    else:
                        print("no deal", end=" ")
                        sys.stdout.flush()
                elif status == 1:
                    if wait_count == trade_wait_count:
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
            self.check_order_status(my_order_info, wait_count)

    def trade(self, my_order_info):
        if my_order_info.amount < self.MIN_AMOUNT:
            return 2
        if my_order_info.price == 0:
            my_order_info.set_price(self.get_trade_price(my_order_info.symbol, my_order_info.orderType))
        order_id = self.make_order(my_order_info)
        if order_id != -1:
            my_order_info.set_order_id(order_id)
            wait_count = 0
            status = 0
            avg_price_bak = my_order_info.avgPrice
            while wait_count < trade_wait_count and status != 2:
                status = self.check_order_status(my_order_info, wait_count)
                # time.sleep(0.1)
                wait_count += 1
                if wait_count == trade_wait_count and status != 2:
                    trade_price = self.get_trade_price(my_order_info.symbol, my_order_info.orderType)
                    if trade_price == my_order_info.price:
                        wait_count -= 1
            if status != 2:
                status = self.cancel_my_order(my_order_info)
            if my_order_info.dealAmount > 0:
                my_order_info.reset_total_deal_amount(my_order_info.dealAmount)
                if my_order_info.orderType == self.TRADE_SELL:
                    my_order_info.set_transaction("plus")
                else:
                    my_order_info.set_transaction("minus")
                my_order_info.set_avg_price(
                    ((my_order_info.totalDealAmount - my_order_info.dealAmount) * avg_price_bak
                     + my_order_info.dealAmount * my_order_info.avgPrice) / my_order_info.totalDealAmount)
            return status
        else:
            return -2

    def get_coin_price(self, symbol):
        data = okcoinSpot.depth(symbol)
        price_info = self.priceInfo[symbol]
        if data.get("asks") is not None:
            asks = data["asks"]
            bids = data["bids"]
            price_info["sell1"] = asks[2][0]
            price_info["sellAmount1"] = asks[2][1]
            price_info["buy1"] = bids[0][0]
            price_info["buyAmount1"] = bids[0][1]
            price_info["sell2"] = asks[1][0]
            price_info["sellAmount2"] = asks[1][1]
            price_info["buy2"] = bids[1][0]
            price_info["buyAmount2"] = bids[1][1]
            price_info["sell3"] = asks[0][0]
            price_info["sellAmount3"] = asks[0][1]
            price_info["buy3"] = bids[2][0]
            price_info["buyAmount3"] = bids[2][1]

    def get_price_info(self, symbol, depth):
        if depth == 1:
            return self.get_price_info1(symbol)
        elif depth == 2:
            return self.get_price_info2(symbol)
        elif depth == 3:
            return self.get_price_info3(symbol)

    def get_price_info1(self, symbol):
        price_info = self.priceInfo[symbol]
        return price_info["buy1"], price_info["buy1"], price_info["buyAmount1"], price_info["sell1"], price_info[
            "sell1"], price_info["sellAmount1"]

    def get_price_info2(self, symbol):
        price_info = self.priceInfo[symbol]
        add_up_buy_amount = price_info["buyAmount1"] + price_info["buyAmount2"]
        avg_buy_price = round((price_info["buy1"] * price_info["buyAmount1"] + price_info["buy2"] * price_info[
            "buyAmount2"]) / add_up_buy_amount, 4)
        add_up_sell_amount = price_info["sellAmount1"] + price_info["sellAmount2"]
        avg_sell_price = round((price_info["sell1"] * price_info["sellAmount1"] + price_info["sell2"] * price_info[
            "sellAmount2"]) / add_up_sell_amount, 4)
        return price_info["buy2"], avg_buy_price, add_up_buy_amount, price_info[
            "sell2"], avg_sell_price, add_up_sell_amount

    def get_price_info3(self, symbol):
        price_info = self.priceInfo[symbol]
        add_up_buy_amount = price_info["buyAmount1"] + price_info["buyAmount2"] + price_info["buyAmount3"]
        avg_buy_price = round((price_info["buy1"] * price_info["buyAmount1"] + price_info["buy2"] * price_info[
            "buyAmount2"] + price_info["buy3"] * price_info["buyAmount3"]) / add_up_buy_amount, 4)
        add_up_sell_amount = price_info["sellAmount1"] + price_info["sellAmount2"] + price_info["sellAmount3"]
        avg_sell_price = round((price_info["sell1"] * price_info["sellAmount1"] + price_info["sell2"] * price_info[
            "sellAmount2"] + price_info["sell3"] * price_info["sellAmount3"]) / add_up_sell_amount, 4)
        return price_info["buy3"], avg_buy_price, add_up_buy_amount, price_info[
            "sell3"], avg_sell_price, add_up_sell_amount

    def get_trade_price(self, symbol, order_type):
        self.get_coin_price(symbol)
        if order_type == self.TRADE_BUY:
            return self.priceInfo[symbol]["sell1"]
        else:
            return self.priceInfo[symbol]["buy1"]

    def get_account_info(self):
        print(
            u'---------------------------------------spot account info------------------------------------------------')
        my_account_info = okcoinSpot.userinfo()
        if my_account_info.get('result'):
            freezed = fromDict(my_account_info, "info", "funds", "freezed")
            free = fromDict(my_account_info, "info", "funds", "free")
            print(u"USDT", free["usdt"], "freezed", freezed["usdt"])
            print(u"OKB", free["okb"], "freezed", freezed["okb"])
        else:
            print("getAccountInfo Fail,Try again!")
            self.get_account_info()

    @classmethod
    def write_log(cls, my_order_info, text=""):
        f = open(r'log.txt', 'a')
        if text == "":
            f.writelines(str(my_order_info))
        else:
            f.writelines("\n" + text)
        f.close()
