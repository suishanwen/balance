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
    BALANCE_HT = "ht"
    BALANCE_USDT = "usdt"

    SYMBOL_HT = "htusdt"

    TRADE_BUY = "buy-limit"
    TRADE_SELL = "sell-limit"

    COMPLETE_STATUS = 'filled'

    MIN_AMOUNT = float(config.get("trade", "minamount"))

    # global variable
    accountInfo = {BALANCE_USDT: {"total": 0, "available": 0, "freezed": 0},
                   BALANCE_HT: {"total": 0, "available": 0, "freezed": 0}}

    priceInfo = {SYMBOL_HT: {"sell1": 0, 'sellAmount1': 0, "buy1": 0, 'buyAmount1': 0,
                             "sell2": 0, 'sellAmount2': 0, "buy2": 0, 'buyAmount2': 0,
                             "sell3": 0, 'sellAmount3': 0, "buy3": 0, 'buyAmount3': 0}}

    def get_coin_num(self, symbol):
        return fromDict(self.accountInfo, symbol, "available")

    def make_order(self, my_order_info):
        print(
            u'\n-------------------------------------------spot order------------------------------------------------')
        result = send_order(account_id, my_order_info.amount, my_order_info.symbol, my_order_info.orderType,
                            my_order_info.price)
        if result.get('status') == 'ok':
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
        if result.get('status') == 'ok':
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
        if order_result.get('status') == 'ok':
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
            avg_price_bak = my_order_info.avgPrice
            while wait_count < trade_wait_count and state != 'filled':
                state = self.check_order_status(my_order_info, wait_count)
                # time.sleep(0.1)
                wait_count += 1
                if wait_count == trade_wait_count and state != 'filled':
                    trade_price = self.get_trade_price(my_order_info.symbol, my_order_info.orderType)
                    if trade_price == my_order_info.price:
                        wait_count -= 1
            if state != 'filled':
                state = self.cancel_my_order(my_order_info)
            if my_order_info.dealAmount > 0:
                my_order_info.reset_total_deal_amount(my_order_info.dealAmount)
                if my_order_info.orderType == self.TRADE_SELL:
                    my_order_info.set_transaction("plus")
                else:
                    my_order_info.set_transaction("minus")
                my_order_info.set_avg_price(
                    ((my_order_info.totalDealAmount - my_order_info.dealAmount) * avg_price_bak
                     + my_order_info.dealAmount * my_order_info.avgPrice) / my_order_info.totalDealAmount)
                return state
        else:
            return 'failed'

    def get_coin_price(self, symbol):
        data = get_depth(symbol)
        if data.get('status') == 'ok':
            price_info = self.priceInfo[symbol]
            asks = data["tick"]["asks"]
            bids = data["tick"]["bids"]
            price_info["sell1"] = asks[0][0]
            price_info["sellAmount1"] = asks[0][1]
            price_info["buy1"] = bids[0][0]
            price_info["buyAmount1"] = bids[0][1]
            price_info["sell2"] = asks[1][0]
            price_info["sellAmount2"] = asks[1][1]
            price_info["buy2"] = bids[1][0]
            price_info["buyAmount2"] = bids[1][1]
            price_info["sell3"] = asks[2][0]
            price_info["sellAmount3"] = asks[2][1]
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
        my_account_info = get_balance(account_id)
        symbol = [self.BALANCE_USDT, self.BALANCE_HT]
        if my_account_info.get('status') == 'ok':
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

    def write_log(self, my_order_info, text=""):
        f = open(r'log.txt', 'a')
        if text == "":
            f.writelines(' '.join(
                ["\n", my_order_info.orderId, my_order_info.symbol, my_order_info.orderType,
                 str(my_order_info.price),
                 str(my_order_info.avgPrice),
                 str(my_order_info.dealAmount),
                 str(my_order_info.totalDealAmount),
                 str(my_order_info.transaction),
                 str(fromTimeStamp(int(time.time())))]))
        else:
            f.writelines("\n" + text)
        f.close()
