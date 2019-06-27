# -*- coding: utf-8 -*-
# encoding: utf-8

import configparser
import time
import datetime
import gevent
import zlib
import json
import api.okex_sdk_v3.spot_api as spot
from util.MyUtil import from_time_stamp
from util.Logger import logger
from websocket import create_connection
from codegen.generator import write

write("dec", '../key.ini')
# read config
configBase = configparser.ConfigParser()
config = configparser.ConfigParser()
configBase.read("../key.ini")
config.read("config.ini")
write("enc", '../key.ini')

# init apikey,secretkey,passphrase
api_key = configBase.get("okex-v3", "API_KEY")
seceret_key = configBase.get("okex-v3", "SECRET_KEY")
passphrase = configBase.get("okex-v3", "PASSPHRASE")

# currentAPIV3
spotAPI = spot.SpotAPI(api_key, seceret_key, passphrase, True)

granularityDict = {
    "1min": 60,
    "3min": 180,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "2hour": 7200,
    "4hour": 14400,
    "6hour": 21600,
    "12hour": 43200,
    "1day": 86400,
    "1week": 604800,
}


class OkexClient(object):
    BALANCE_USD = "usdt"
    BALANCE_T = ""

    SYMBOL_T = ""

    TRADE_BUY = "buy"
    TRADE_SELL = "sell"

    FILLED_STATUS = 'filled'
    CANCELLED_STATUS = 'cancelled'

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
    kill = 0
    maOff = False
    kline_data = []
    depth_data = {"asks": [], "bids": []}

    ws = None
    ping = False
    pong = False
    socketData = None

    # global variable
    accountInfo = {BALANCE_USD: {"total": 0, "available": 0, "freezed": 0}}

    priceInfo = {"version": 0, SYMBOL_T: {"asks": [], "bids": []}}

    def get_coin_num(self, symbol):
        return self.accountInfo[symbol]["available"]

    @classmethod
    def make_order(cls, my_order_info):
        logger.info('-----------------------------------------spot order----------------------------------------------')
        result = {}
        try:
            result = spotAPI.take_order(my_order_info.orderType, my_order_info.symbol, 2, my_order_info.price,
                                        my_order_info.amount)
        except Exception as e:
            logger.error("***trade:%s" % e)
        if result is not None and result.get('result'):
            logger.info(
                "Order {} {} {} {} {} {}".format(result['order_id'], my_order_info.symbol, my_order_info.orderType,
                                                 my_order_info.price, my_order_info.amount,
                                                 from_time_stamp()))
            return result['order_id']
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
            order_result = spotAPI.get_order_info(my_order_info.orderId, my_order_info.symbol)
        except Exception as e:
            logger.error("***orderinfo:%s" % e)
        if order_result is not None and order_result.get('order_id') == my_order_info.orderId:
            order = order_result
            order_id = order["order_id"]
            status = order["status"]
            filled_size = float(order["filled_size"])
            if filled_size > 0:
                my_order_info.set_deal_amount(filled_size)
                my_order_info.set_avg_price(float(order["filled_notional"]) / filled_size)
            if status == self.CANCELLED_STATUS:
                logger.info("order {} canceled".format(order_id))
            elif status == 'open':
                if wait_count == self.TRADE_WAIT_COUNT:
                    logger.info("timeout no deal")
                else:
                    logger.info("no deal")
            elif status == 'part_filled':
                if wait_count == self.TRADE_WAIT_COUNT:
                    logger.info("timeout part deal {}".format(my_order_info.dealAmount))
                else:
                    logger.info("part deal {}".format(my_order_info.dealAmount))
            elif status == self.FILLED_STATUS:
                logger.info("order {} filled".format(order_id))
            elif status == 'canceling':
                logger.info("order {} canceling".format(order_id))
            elif status == 'ordering':
                logger.info("order {} ordering".format(order_id))
            return status
        else:
            logger.warning("order {} checkOrderStatus failed,try again.".format(order_id))
            return self.check_order_status(my_order_info, wait_count)

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

    # def get_coin_price(self, symbol):
    #     data = {}
    #     try:
    #         data = spotAPI.get_depth(symbol)
    #     except Exception as e:
    #         logger.error("***depth:%s" % e)
    #     price_info = self.priceInfo[symbol]
    #     if data is not None and data.get("asks") is not None:
    #         price_info["asks"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["asks"]))
    #         price_info["bids"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["bids"]))
    #     else:
    #         self.get_coin_price(symbol)

    def ws_connect(self):
        if self.ws is None or not self.ws.connected:
            try:
                self.ws = create_connection("wss://real.okex.com:10442/ws/v3", timeout=5)
                logger.info('websocket connected!')
                pair = self.SYMBOL_T.upper().replace("_", "-")
                sub_param = {"op": "subscribe", "args": ["spot/depth:{}".format(pair)]}
                sub_str = json.dumps(sub_param)
                self.ws.send(sub_str)
                result = self.inflate(self.ws.recv())
                logger.info("{} subscribe:{}".format(pair, result))
            except Exception as e:
                logger.error('\nconnect ws error[{}],retry...'.format(e))
                time.sleep(2)
                self.ws_connect()

    @classmethod
    def inflate(cls, data):
        decompress = zlib.decompressobj(
            -zlib.MAX_WBITS  # see above
        )
        inflated = decompress.decompress(data)
        inflated += decompress.flush()
        return inflated

    @classmethod
    def socket_recv(cls, client):
        client.recvException = False
        try:
            client.socketData = (cls.inflate(client.ws.recv())).decode(encoding="utf-8")
        except Exception as e:
            logger.error('recv Exception:[{}]'.format(e))

    def get_coin_price(self, symbol):
        self.ws_connect()
        self.socketData = None
        gevent.spawn(self.socket_recv, self).join(15)
        if not self.socketData:
            self.ping = True
            self.pong = False
            t = 0
            while not self.pong and t < 3:
                try:
                    self.ws.send("ping")
                    logger.info("[{}]ping.........".format(symbol))
                    gevent.spawn(self.socket_recv, self).join(3)
                except Exception as e:
                    logger.info("[{}]ping exception，{}".format(symbol, e))
                if self.socketData:
                    self.pong = True
                    logger.info("[{}]pong!!!!!!!!!".format(symbol))
                t += 1
        if self.ping:
            self.ping = False
            if not self.pong:
                logger.warning("[{}]no pong in 5s,reconnect!".format(symbol))
                self.ws.close()
                self.get_coin_price(symbol)
            return
        res = None
        try:
            res = json.loads(self.socketData)
        except Exception as e:
            logger.error("{} : {}".format(self.socketData, e))
        if res and res.get("data") is not None:
            data = res.get("data")[0]
            logger.info("priceInfo:action-{}".format(res.get("action")))
            if res.get("action") == "partial":
                self.depth_data = data
            elif res.get("action") == "update":
                self.depth_data["asks"][0:len(data["asks"])] = data["asks"]
                self.depth_data["bids"][0:len(data["bids"])] = data["bids"]
            price_info = self.priceInfo[symbol]
            price_info["asks"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["asks"][0:10]))
            price_info["bids"] = list(map(lambda x: list(map(lambda d: float(d), x)), data["bids"][0:10]))
            logger.info("priceInfo:{}".format(price_info))

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
        logger.info('-----------------------------------spot account info--------------------------------------------')
        try:
            accounts = [self.BALANCE_USD.upper(), self.BALANCE_T.upper()]
            for symbol in accounts:
                t_account = spotAPI.get_coin_account_info(symbol)
                if t_account.get('currency') == symbol:
                    logger.info("%s:balance %s available %s frozen %s" % (symbol, t_account["balance"],
                                                                          t_account["available"],
                                                                          t_account["frozen"]))
                else:
                    logger.warning("getAccountInfo Fail,Try again!")
                    self.get_account_info()
        except Exception as err:
            logger.error(err)
            self.get_account_info()

    @classmethod
    def get_line_data(cls, data):
        return [float(data[1]), float(data[2]), float(data[3]), float(data[4]), float(data[5]), data[0]]

    # (开,高,低,收,交易量)
    def get_klines(self, symbol, period, size):
        result = {}
        granularity = granularityDict[period]
        end_s = int("%0.0f" % datetime.datetime.utcnow().timestamp())
        start_s = end_s - granularity * size
        start = datetime.datetime.fromtimestamp(start_s).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end = datetime.datetime.fromtimestamp(end_s).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        try:
            result = spotAPI.get_kline(symbol, start, end, granularity)
        except Exception as e:
            logger.error("***klines:%s" % e)
        is_list = isinstance(result, list)
        if is_list and len(result) == size:
            self.kline_data = list(map(self.get_line_data, result))
        if len(self.kline_data) == 0:
            logger.error("***klines retry...")
            return self.get_klines(symbol, period, size)
        elif is_list and len(result) == size - 1 and self.kline_data[0][5] != end:
            first = json.loads(json.dumps(result[0]))
            first[0] = end
            first[1] = first[4]
            first[2] = first[4]
            first[3] = first[4]
            first[5] = "0"
            result.insert(0, first)
            self.kline_data = list(map(self.get_line_data, result))
        elif is_list and len(result) != size and len(result) != size - 1:
            logger.warning("***klines not refresh,{}".format(result))
        return self.kline_data
