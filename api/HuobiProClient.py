# -*- coding: utf-8 -*-
# encoding: utf-8

import time
import sys

from api.HuobiProAPI import *
from util.MyUtil import from_dict, from_time_stamp, write_log

# from websocket import create_connection
# import gzip
# import socket

# read config
config = configparser.ConfigParser()
config.read("config.ini")

# getConfig
trade_wait_count = int(config.get("trade", "tradewaitcount"))


class HuobiProClient(object):
    ACCOUNT_ID = ""

    BALANCE_BTC = "btc"
    BALANCE_HT = "ht"
    BALANCE_USDT = "usdt"

    SYMBOL_HT = "htusdt"
    SYMBOL_BTC = "btcusdt"

    TRADE_BUY = "buy-limit"
    TRADE_SELL = "sell-limit"

    COMPLETE_STATUS = 'filled'

    MIN_AMOUNT = float(config.get("trade", "minamount"))

    ACCURACY = 2

    # global variable
    accountInfo = {BALANCE_USDT: {"total": 0, "available": 0, "freezed": 0},
                   BALANCE_BTC: {"total": 0, "available": 0, "freezed": 0},
                   BALANCE_HT: {"total": 0, "available": 0, "freezed": 0}}

    priceInfo = {"version": 0, SYMBOL_BTC: {"asks": [], "bids": []}, SYMBOL_HT: {"asks": [], "bids": []}}

    ws = None

    # @classmethod
    # def ws_connect(cls):
    #     if cls.ws is None or not cls.ws.connected:
    #         while True:
    #             try:
    #                 cls.ws = create_connection("wss://api.huobipro.com/ws", timeout=5)
    #                 print('\nwebsocket connected!')
    #                 break
    #             except socket.timeout:
    #                 print('\nconnect ws error,retry...')
    #                 time.sleep(5)

    def get_coin_num(self, symbol):
        return from_dict(self.accountInfo, symbol, "available")

    def make_order(self, my_order_info):
        print(
            u'\n-------------------------------------------spot order------------------------------------------------')
        result = send_order(self.ACCOUNT_ID, my_order_info.amount, my_order_info.symbol, my_order_info.orderType,
                            my_order_info.price)
        if result.get('status') == 'ok':
            print("OrderId", result['data'], my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                  my_order_info.amount, "  ", from_time_stamp(int(time.time())))
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
            write_log("order " + result['data'] + " canceled")
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
                if my_order_info.dealAmount == 0.0:
                    print("data error!check order status again!")
                    self.check_order_status(my_order_info, wait_count)
            elif state == 'partial-filled':
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
        if my_order_info.amount < self.MIN_AMOUNT:
            return 'filled'
        if my_order_info.price == 0:
            my_order_info.set_price(self.get_trade_price(my_order_info.symbol, my_order_info.orderType))
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
                my_order_info.set_avg_price(round(
                    ((my_order_info.totalDealAmount - my_order_info.dealAmount) * avg_price_bak
                     + my_order_info.dealAmount * my_order_info.avgPrice) / my_order_info.totalDealAmount, 4))
            return state
        else:
            return 'failed'

    def get_coin_price(self, symbol):
        data = get_depth(symbol)
        if data.get('status') == 'ok':
            # check version
            last_version = self.priceInfo["version"]
            version = data["tick"]["version"]
            if version == last_version:
                self.get_coin_price(symbol)
            self.priceInfo["version"] = version
            price_info = self.priceInfo[symbol]
            price_info["asks"] = data["tick"]["asks"]
            price_info["bids"] = data["tick"]["bids"]

    # def get_coin_price(self, symbol):
    #     data = get_depth(symbol)
    #     self.ws_connect()
    #     ws = self.ws
    #     compress_data = ws.recv()
    #     result = gzip.decompress(compress_data).decode('utf-8')
    #     if result[:7] == '{"ping"':
    #         ts = result[8:21]
    #         pong = '{"pong":' + ts + '}'
    #         ws.send(pong)
    #         ws.send("""{"req": "market.$symbol$.depth.step0", "id": "id10"}""".replace("$symbol$", symbol))
    #         self.get_coin_price(symbol)
    #     else:
    #         data = json.loads(result)
    #         if data.get('status') == 'ok':
    #             price_info = self.priceInfo[symbol]
    #             price_info["asks"] = data["data"]["asks"]
    #             price_info["bids"] = data["data"]["bids"]

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
        accounts = get_accounts()
        if accounts.get('status') == 'ok':
            spot_account = list(filter(lambda x: x["type"] == 'spot', accounts.get("data")))
            self.ACCOUNT_ID = spot_account[0].get('id')
            my_account_info = get_balance(self.ACCOUNT_ID)
            symbols = [self.BALANCE_USDT, self.BALANCE_BTC, self.BALANCE_HT]
            if my_account_info.get('status') == 'ok':
                data = from_dict(my_account_info, "data", "list")
                for symbol in symbols:
                    symbol_infos = list(filter(lambda x: x["currency"] == symbol, data))
                    symbol_info = self.accountInfo[symbol]
                    symbol_info["available"] = float(symbol_infos[0]["balance"])
                    symbol_info["freezed"] = float(symbol_infos[1]["balance"])
                    symbol_info["total"] = symbol_info["available"] + symbol_info["freezed"]
                    print(symbol.upper(), symbol_info["total"], "available", symbol_info["available"],
                          "freezed", symbol_info["freezed"])
            else:
                print("getAccountInfo Failed!")
                exit()
        else:
            print("getAccounts Failed!")
            exit()

    @classmethod
    def get_line_close(cls, data):
        return data.get('close')

    @classmethod
    def get_klines(cls, symbol, period, size):
        result = get_kline(symbol, period, size)
        if result.get('status') == 'ok':
            return list(map(cls.get_line_close, result.get('data')))
        else:
            cls.get_klines(symbol, period, size)
