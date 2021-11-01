# -*- coding: utf-8 -*-
# encoding: utf-8
import time
import api.okex_sdk_v5.Market_api as MarketApi
import api.okex_sdk_v5.Trade_api as TradeApi
import api.okex_sdk_v5.Account_api as AccountApi
from module.Logger import logger
from util.MyUtil import from_time_stamp
from module.CfEnv import TRADE_TYPE, TradeType


class OkexClient(object):

    def __init__(self, api_key, seceret_key, passphrase):
        self.IS_SPOT = TRADE_TYPE == TradeType.SPOT
        self.TradeApi = TradeApi.TradeAPI(api_key, seceret_key, passphrase)
        self.MarketApi = MarketApi.MarketAPI(api_key, seceret_key, passphrase)
        self.AccountApi = AccountApi.AccountAPI(api_key, seceret_key, passphrase)

    BALANCE_T = ""
    BALANCE_E = ""

    SYMBOL_T = ""

    TRADE_BUY = "buy"
    TRADE_SELL = "sell"
    FILLED_STATUS = 'filled'
    CANCELLED_STATUS = 'canceled'

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
    timeout = 6
    fee = 0.002
    kill = 0
    maOff = False
    kline_data = []

    ws = None
    ping = False
    pong = False
    socketData = None

    # global variable
    accountInfo = {BALANCE_E: {"total": 0, "available": 0, "freezed": 0}}

    priceInfo = {"version": 0, SYMBOL_T: {"asks": [], "bids": []}}

    def get_coin_num(self, symbol):
        return self.accountInfo[symbol]["available"]

    def make_order(self, my_order_info):
        logger.info('-----------------------------------------make order----------------------------------------------')
        result = {}
        try:
            result = self.TradeApi.place_order(my_order_info.symbol, "cross", my_order_info.orderType, "fok",
                                               my_order_info.amount, my_order_info.offset, my_order_info.price)
        except Exception as e:
            logger.error("***trade:%s" % e)
        if result is not None and result.get('code') == "0" and result.get('data'):
            logger.info(
                "Order {} {} {} {} {} {}".format(result['data'][0]['ordId'], my_order_info.symbol,
                                                 my_order_info.orderType,
                                                 my_order_info.price, my_order_info.amount,
                                                 from_time_stamp()))
            return result['data'][0]['ordId']
        else:
            logger.error(
                "order failed！{} {} {} {} {}".format(my_order_info.symbol, my_order_info.orderType, my_order_info.price,
                                                     my_order_info.amount,
                                                     round(my_order_info.price * my_order_info.amount, 3)))
            return -1

    def check_order_status(self, my_order_info, wait_count=0):
        order_id = my_order_info.orderId
        order_result = {}
        try:
            logger.info("check order status {}".format(wait_count))
            order_result = self.TradeApi.get_orders(my_order_info.symbol, my_order_info.orderId)
        except Exception as e:
            logger.error("***orderinfo:%s" % e)
        if order_result is not None and order_result.get('code') == "0" and order_result.get('data'):
            order = order_result['data'][0]
            order_id = order["ordId"]
            status = order["state"]
            filled_size = float(order["accFillSz"])
            if filled_size > 0:
                my_order_info.set_deal_amount(filled_size)
                my_order_info.set_avg_price(float(order["avgPx"]))
            if status == self.CANCELLED_STATUS:
                logger.info("order {} canceled".format(order_id))
            elif status == 'live':
                if wait_count == self.TRADE_WAIT_COUNT:
                    logger.info("timeout no deal")
                else:
                    logger.info("no deal")
            elif status == 'partially_filled':
                if wait_count == self.TRADE_WAIT_COUNT:
                    logger.info("timeout part deal {}".format(my_order_info.dealAmount))
                else:
                    logger.info("part deal {}".format(my_order_info.dealAmount))
            elif status == self.FILLED_STATUS:
                logger.info("order {} filled".format(order_id))
            return status
        else:
            logger.warning("order {} checkOrderStatus failed,try again.".format(order_id))
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
            while status != self.FILLED_STATUS and status != self.CANCELLED_STATUS:
                wait_count += 1
                status = self.check_order_status(my_order_info, wait_count)
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
            return "failed"

    def get_coin_price(self, symbol):
        data = {}
        try:
            data = self.MarketApi.get_orderbook(symbol, '10')
            data = data['data'][0]
        except Exception as e:
            logger.error("***depth:%s" % e)
        price_info = self.priceInfo[symbol]
        if data is not None and data.get("asks") is not None:
            price_info["asks"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["asks"]))
            price_info["bids"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["bids"]))
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
        logger.info('-----------------------------------account info--------------------------------------------')

    @classmethod
    def get_line_data(cls, data):
        return [float(data[1]), float(data[2]), float(data[3]), float(data[4]), float(data[5]), data[0]]

    # (开,高,低,收,交易量)
    def get_klines(self, symbol, period, size):
        result = {}
        try:
            result = self.MarketApi.get_history_candlesticks(symbol, period, size)
        except Exception as e:
            logger.error("***klines:%s" % e)
            time.sleep(0.2)
        if result["code"] == "0":
            data = result["data"]
            is_list = isinstance(data, list)
            if is_list and len(data) == size:
                self.kline_data = list(map(self.get_line_data, data))
            if len(self.kline_data) == 0:
                logger.error("***klines retry...")
                self.get_klines(symbol, period, size)
            elif is_list and len(data) != size and len(data) != size - 1:
                logger.warning("***klines not refresh,{}".format(data))
        else:
            logger.error("***klines:%s" % result["msg"])

    # 获取用户持仓信息
    def get_contract_position_info(self, symbol):
        data = self.AccountApi.get_positions("FUTURES", symbol)
        volume = data["data"][0]["pos"]
        direction = data["data"][0]["posSide"]
        return abs(int(volume)), direction

    def get_contract_offset(self, order_type, direction):
        if direction == "short" and order_type == self.TRADE_SELL:
            return True, direction
        elif direction == "long" and order_type == self.TRADE_BUY:
            return True, direction
        else:
            return False, direction

    def get_contract_opposite_offset(self, offset):
        if offset == "long":
            return "short"
        else:
            return "long"
