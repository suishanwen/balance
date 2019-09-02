# -*- coding: utf-8 -*-
# encoding: utf-8

import sys
import configparser

from util.MyUtil import from_dict, from_time_stamp, write_log
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


class OkexClient(object):
    BALANCE_T = ""
    BALANCE_E = ""

    SYMBOL_T = ""

    TRADE_BUY = "buy"
    TRADE_SELL = "sell"

    FILLED_STATUS = 2
    CANCELLED_STATUS = -1

    MIN_AMOUNT = 1
    ACCURACY = 4
    TRADE_WAIT_COUNT = 1

    # trade params
    mode = ""
    amount = 0
    transaction = 0
    currentBase = 0
    percentage = 0
    rateP = 0
    emailDay = 0
    buyRate = 1
    sellRate = 1
    nightMode = False
    nightRate = 1
    kill = 0
    maOff = False
    kline_data = []

    # global variable
    accountInfo = {BALANCE_E: {"total": 0, "available": 0, "freezed": 0}}

    priceInfo = {"version": 0, SYMBOL_T: {"asks": [], "bids": []}}

    def get_coin_num(self, symbol):
        return from_dict(self.accountInfo, symbol, "available")

    @classmethod
    def make_order(cls, my_order_info):
        print(
            u'\n-------------------------------------------spot order------------------------------------------------')
        result = {}
        try:
            result = okcoinSpot.trade(my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                                      my_order_info.amount)
        except Exception as e:
            print("***trade:%s" % e)
        if result is not None and result.get('result'):
            print("OrderId", result['order_id'], my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                  my_order_info.amount, "  ", from_time_stamp())
            return result['order_id']
        else:
            print("order failed！", my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                  my_order_info.amount, round(my_order_info.price * my_order_info.amount, 3))
            return -1

    def cancel_my_order(self, my_order_info):
        print(
            u'\n---------------------------------------spot cancel order--------------------------------------------')
        result = {}
        try:
            result = okcoinSpot.cancel_order(my_order_info.symbol, my_order_info.orderId)
        except Exception as e:
            print("***cancel_order:%s" % e)
        if result is None or not result.get('result'):
            print(u"order", my_order_info.orderId, "not canceled or cancel failed！！！")
        status = self.check_order_status(my_order_info)
        if status == self.CANCELLED_STATUS:
            write_log("order " + str(my_order_info.orderId) + " canceled")
        elif status != self.FILLED_STATUS:
            # not canceled or cancel failed(part dealed) and not complete continue cancelling
            return self.cancel_my_order(my_order_info)
        return status

    def check_order_status(self, my_order_info, wait_count=0):
        order_id = my_order_info.orderId
        order_result = {}
        try:
            order_result = okcoinSpot.orderinfo(my_order_info.symbol, my_order_info.orderId)
        except Exception as e:
            print("***orderinfo:%s" % e)
        if order_result is not None and order_result.get('result'):
            orders = order_result["orders"]
            if len(orders) > 0:
                order = orders[0]
                order_id = order["order_id"]
                status = order["status"]
                my_order_info.set_deal_amount(float(order["deal_amount"]))
                my_order_info.set_avg_price(order["avg_price"])
                if status == self.CANCELLED_STATUS:
                    print("order", order_id, "canceled")
                elif status == 0:
                    if wait_count == self.TRADE_WAIT_COUNT:
                        print("timeout no deal")
                    else:
                        print("no deal", end=" ")
                        sys.stdout.flush()
                elif status == 1:
                    if wait_count == self.TRADE_WAIT_COUNT:
                        print("part dealed ", my_order_info.dealAmount)
                    else:
                        print("part dealed ", my_order_info.dealAmount, end=" ")
                        sys.stdout.flush()
                elif status == self.FILLED_STATUS:
                    print("order", order_id, "complete deal")
                elif status == 3:
                    print("order", order_id, "canceling")
                return status
        else:
            print(order_id, "checkOrderStatus failed,try again.")
            return self.check_order_status(my_order_info, wait_count)

    def trade(self, my_order_info):
        if my_order_info.amount < self.MIN_AMOUNT:
            return self.FILLED_STATUS
        if my_order_info.price == 0:
            my_order_info.set_price(self.get_trade_price(my_order_info.symbol, my_order_info.orderType))
        order_id = self.make_order(my_order_info)
        if order_id != -1:
            my_order_info.set_order_id(order_id)
            wait_count = 0
            status = 0
            avg_price_bak = my_order_info.avgPrice
            while wait_count < self.TRADE_WAIT_COUNT and status != self.FILLED_STATUS:
                status = self.check_order_status(my_order_info, wait_count)
                # time.sleep(0.1)
                wait_count += 1
                if wait_count == self.TRADE_WAIT_COUNT and status != self.FILLED_STATUS:
                    trade_price = self.get_trade_price(my_order_info.symbol, my_order_info.orderType)
                    if trade_price == my_order_info.price:
                        wait_count -= 1
            if status != self.FILLED_STATUS:
                status = self.cancel_my_order(my_order_info)
            my_order_info.reset_total_deal_amount(my_order_info.dealAmount)
            if my_order_info.totalDealAmount > 0:
                if my_order_info.orderType == self.TRADE_SELL:
                    my_order_info.set_transaction("plus")
                else:
                    my_order_info.set_transaction("minus")
                my_order_info.set_avg_price(round(
                    ((my_order_info.totalDealAmount - my_order_info.dealAmount) * avg_price_bak
                     + my_order_info.dealAmount * my_order_info.avgPrice) / my_order_info.totalDealAmount, 4))
            return status
        else:
            return -2

    def get_coin_price(self, symbol):
        data = {}
        try:
            data = okcoinSpot.depth(symbol)
        except Exception as e:
            print("***depth:%s" % e)
        price_info = self.priceInfo[symbol]
        if data is not None and data.get("asks") is not None:
            price_info["asks"] = data["asks"][::-1]
            price_info["bids"] = data["bids"]
        else:
            self.get_coin_price(symbol)

    def get_price_info(self, symbol, depth):
        price_info = self.priceInfo[symbol]
        asks = price_info['asks']
        bids = price_info['bids']
        amount_buy_sum = 0
        trans_buy_sum = 0
        amount_sell_sum = 0
        trans_sell_sum = 0
        for i in range(depth):
            amount_buy_sum += bids[i][1]
            trans_buy_sum += bids[i][0] * bids[i][1]
            amount_sell_sum += asks[i][1]
            trans_sell_sum += asks[i][0] * asks[i][1]
        avg_buy = round(trans_buy_sum / amount_buy_sum, 4)
        avg_sell = round(trans_sell_sum / amount_sell_sum, 4)
        return bids[depth - 1][0], avg_buy, amount_buy_sum, asks[depth - 1][0], avg_sell, amount_sell_sum

    def get_trade_price(self, symbol, order_type):
        self.get_coin_price(symbol)
        if order_type == self.TRADE_BUY:
            return self.priceInfo[symbol]["asks"][0][0]
        else:
            return self.priceInfo[symbol]["bids"][0][0]

    def get_account_info(self):
        print(
            u'---------------------------------------spot account info------------------------------------------------')
        try:
            my_account_info = okcoinSpot.userinfo()
            if my_account_info.get('result'):
                freezed = from_dict(my_account_info, "info", "funds", "freezed")
                free = from_dict(my_account_info, "info", "funds", "free")
                print(self.BALANCE_E, free[self.BALANCE_E], "freezed", freezed[self.BALANCE_E])
                print(self.BALANCE_T.upper(), free[self.BALANCE_T], "freezed", freezed[self.BALANCE_T])
            else:
                print("getAccountInfo Fail,Try again!")
                self.get_account_info()
        except Exception as err:
            print(err)
            self.get_account_info()

    @classmethod
    def get_line_data(cls, data):
        return [float(data[1]), float(data[2]), float(data[3]), float(data[4]), float(data[5])]

    # (开,高,低,收,交易量)
    def get_klines(self, symbol, period, size):
        result = {}
        try:
            result = okcoinSpot.klines(symbol, period, size)
        except Exception as e:
            print("***klines:%s" % e)
        if isinstance(result, list):
            self.kline_data = list(map(self.get_line_data, result))[::-1]
        else:
            self.get_klines(symbol, period, size)
