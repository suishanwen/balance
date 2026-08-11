# -*- coding: utf-8 -*-
# encoding: utf-8

import gevent

import api.okex_sdk_v5.Account_api as AccountApi
import api.okex_sdk_v5.Market_api as MarketApi
import api.okex_sdk_v5.Trade_api as TradeApi
import api.okex_sdk_v5.Funding_api as FundingApi
import api.okex_sdk_v5.Earn_api as EarnApi
from market.MarketMonitor import set_market_depth, set_market_klines, get_market_price_info
from module.Logger import logger
from util.MyUtil import from_time_stamp, get_ms, safe_get_val


class OkexClient(object):

    def __init__(self, user, api_key, seceret_key, passphrase, config, deal_token, report_token, chat_id, email, symbol,
                 period, size1, size2, method):
        self.user = user
        self.config = config
        self.type = None
        self.IS_FUTURE = True
        self.USDT_FUTURE = True
        self.USD_FUTURE = False
        self.IS_SPOT = not self.IS_FUTURE
        self.TRADE_LEVEL = int(safe_get_val(config, symbol, "level", "20"))
        self.TradeApi = TradeApi.TradeAPI(api_key, seceret_key, passphrase)
        self.MarketApi = MarketApi.MarketAPI(api_key, seceret_key, passphrase)
        self.AccountApi = AccountApi.AccountAPI(api_key, seceret_key, passphrase)
        self.FundingApi = FundingApi.FundingAPI(api_key, seceret_key, passphrase)
        self.EarnApi = EarnApi.EarnAPI(api_key, seceret_key, passphrase)
        self.deal_token = deal_token
        self.report_token = report_token
        self.chat_id = chat_id
        self.email = email
        self.atr = 0
        self.SYMBOL_T = symbol
        self.period = period
        self.size1 = size1
        self.size2 = size2
        self.old_channel = None
        self.channel = safe_get_val(config, symbol, "channel", "bbo-tbt")
        self.reset_channel = int(safe_get_val(config, symbol, "resetchannel", "10000"))
        self.method = method

    def set_symbol(self, symbol, config):
        self.SYMBOL_T = symbol
        from market.MarketMonitor import is_spec_symbol, is_spec_swap_symbol
        if is_spec_symbol(symbol):
            # HF 现货 spec symbol, e.g. OKB-ORDI
            self.type = 'SPOT'
            self.IS_FUTURE = False
            self.USD_FUTURE = False
            self.USDT_FUTURE = False
            self.IS_SPOT = True
        elif is_spec_swap_symbol(symbol):
            # HF 合约 spec symbol, e.g. XPL-ORDI-SWAP
            self.type = 'SWAP'
            self.IS_FUTURE = True
            self.USD_FUTURE = True
            self.USDT_FUTURE = False
            self.IS_SPOT = False
        else:
            self.type = 'SWAP' if "SWAP" in symbol  else 'SPOT'
            self.IS_FUTURE = "SWAP" in symbol
            self.USD_FUTURE = "USD-SWAP" in symbol
            self.USDT_FUTURE = "USDT-SWAP" in symbol
            self.IS_SPOT = not self.IS_FUTURE
        self.channel = safe_get_val(config, symbol, "channel", "bbo-tbt")

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

    user = ''
    period = '1m'
    size1 = 2
    size2 = 5

    # global variable
    accountInfo = {BALANCE_E: {"total": 0, "available": 0, "freezed": 0}}

    def get_coin_num(self, symbol):
        return self.accountInfo[symbol]["available"]

    def make_order(self, my_order_info):
        logger.info(f'[{self.user}]|-------------------------------- make order-------------------------------------')
        result = {}
        if self.IS_FUTURE:
            pos_side = my_order_info.offset
            mode = "cross"
        else:
            pos_side = ''
            mode = 'cash'
        try:
            ordType = "fok"
            result = self.TradeApi.place_order(self.user, my_order_info.symbol, mode, my_order_info.orderType, ordType,
                                               my_order_info.amount, pos_side, my_order_info.price,
                                               f'{self.user}{my_order_info.cid}')
        except Exception as e:
            logger.error(f"{self.user} ***trade:{e}")
        if result is not None and result.get('code') == "0" and result.get('data'):
            logger.info(
                f"[{self.user}]|Order {result['data'][0]['ordId']} {my_order_info.symbol} {my_order_info.orderType} {my_order_info.price} {my_order_info.amount} {from_time_stamp()}")
            return result['data'][0]['ordId'], result
        else:
            msg = ''
            if result is not None and result.get('data'):
                msg = result['data'][0]['sMsg']
            logger.error(
                f"[{self.user}]|order failed！{my_order_info.symbol} {my_order_info.orderType} {my_order_info.price} {my_order_info.amount} {msg}")

            return -1, None

    def check_order_status(self, my_order_info, wait_count=0, order_result=None):
        order_id = my_order_info.orderId
        try:
            logger.info(f"[{self.user}]|check order status {wait_count}")
            if order_result is None or wait_count > 1:
                order_result = self.TradeApi.get_orders(my_order_info.symbol, my_order_info.orderId)
        except Exception as e:
            logger.error("***orderinfo:%s" % e)
        if order_result is not None and order_result.get('code') == "0" and order_result.get('data'):
            order = order_result['data'][0]
            order_id = order["ordId"]
            status = order["state"]
            filled_size = float(order["accFillSz"])
            fee = float(order["fee"])
            if filled_size > 0:
                my_order_info.set_deal_amount(filled_size)
                my_order_info.set_avg_price(float(order["avgPx"]))
            if status == self.CANCELLED_STATUS:
                logger.info(f"[{self.user}]|order {order_id} canceled")
            elif status == 'live':
                if wait_count == self.TRADE_WAIT_COUNT:
                    logger.info(f"[{self.user}]|timeout no deal")
                else:
                    logger.info(f"[{self.user}]|no deal")
            elif status == 'partially_filled':
                if wait_count == self.TRADE_WAIT_COUNT:
                    logger.info(f"[{self.user}]|timeout part deal {my_order_info.dealAmount}")
                else:
                    logger.info(f"[{self.user}]|part deal {my_order_info.dealAmount}")
            elif status == self.FILLED_STATUS:
                logger.info(f"[{self.user}]|order {order_id} filled")
            return status, fee
        else:
            logger.warning(f"order {order_id} checkOrderStatus failed,try again.")
            return self.check_order_status(my_order_info, wait_count, None)

    def trade(self, my_order_info):
        if my_order_info.amount < self.MIN_AMOUNT:
            return self.FILLED_STATUS
        if my_order_info.price == 0:
            my_order_info.set_price(self.get_trade_price(my_order_info.symbol, my_order_info.orderType))
        order_id, order_result = self.make_order(my_order_info)
        if order_id != -1:
            my_order_info.set_order_id(order_id)
            wait_count = 0
            status = 0
            fee = 0
            avg_price_bak = my_order_info.avgPrice
            while status != self.FILLED_STATUS and status != self.CANCELLED_STATUS:
                wait_count += 1
                status, fee = self.check_order_status(my_order_info, wait_count, order_result)
            my_order_info.reset_total_deal_amount(my_order_info.dealAmount)
            if my_order_info.totalDealAmount > 0:
                my_order_info.set_fee(fee)
                if my_order_info.orderType == self.TRADE_SELL:
                    my_order_info.set_transaction("plus", self)
                else:
                    my_order_info.set_transaction("minus", self)
                my_order_info.set_avg_price(round(
                    ((my_order_info.totalDealAmount - my_order_info.dealAmount) * avg_price_bak
                     + my_order_info.dealAmount * my_order_info.avgPrice) / my_order_info.totalDealAmount,
                    self.ACCURACY))
                if self.IS_FUTURE:
                    my_order_info.set_amount(int(my_order_info.get_unhandled_amount(self.ACCURACY)))
                else:
                    my_order_info.set_amount(my_order_info.get_unhandled_amount(self.ACCURACY))
                my_order_info.set_order_id(f'[{self.user}]{order_id}')
            return status
        else:
            return "failed"

    def get_coin_price(self, symbol):
        start = get_ms()
        get_market_price_info(symbol)["depth"]["pending"] += 1
        result = None
        try:
            result = self.MarketApi.get_orderbook(symbol, '20')
        except Exception as e:
            logger.error("***depth:%s" % e)
        get_market_price_info(symbol)["depth"]["pending"] -= 1
        cost = get_ms() - start
        if cost > 5000:
            logger.warning(f"[{self.user}]{symbol}:depth requested,taking too long:{cost} ms")
        if result is not None and result['code'] is not None and len(result['data']) > 0 and len(
                result['data'][0]["asks"]) > 0:
            asks = list(map(lambda x: list(map(lambda d: float(d), x)), result['data'][0]["asks"]))
            bids = list(map(lambda x: list(map(lambda d: float(d), x)), result['data'][0]["bids"]))
            set_market_depth(symbol, asks, bids)
        else:
            gevent.sleep(0.02)
            self.get_coin_price(symbol)

    def get_price_info(self, symbol, size):
        depth = get_market_price_info(symbol)['depth']
        asks = depth['asks']
        bids = depth['bids']
        amount_buy_sum = 0
        trans_buy_sum = 0
        amount_sell_sum = 0
        trans_sell_sum = 0
        for i in range(size):
            amount_buy_sum += bids[i][1]
            trans_buy_sum += bids[i][0] * bids[i][1]
            amount_sell_sum += asks[i][1]
            trans_sell_sum += asks[i][0] * asks[i][1]
        avg_buy = round(trans_buy_sum / amount_buy_sum, self.ACCURACY)
        avg_sell = round(trans_sell_sum / amount_sell_sum, self.ACCURACY)
        if self.IS_FUTURE:
            amount_buy_sum = int(amount_buy_sum)
            amount_sell_sum = int(amount_sell_sum)
        return bids[size - 1][0], avg_buy, amount_buy_sum, asks[size - 1][0], avg_sell, amount_sell_sum

    def get_trade_price(self, symbol, order_type):
        depth = get_market_price_info(symbol)['depth']
        if order_type == self.TRADE_BUY:
            return depth["asks"][0][0]
        else:
            return depth["bids"][0][0]

    def get_account_info(self):
        logger.info(f'{self.user}|--------------------------------- start-----------------------------------------')

    @classmethod
    def get_line_data(cls, data):
        return [float(data[1]), float(data[2]), float(data[3]), float(data[4]), float(data[5]), data[0]]

    # (开,高,低,收,交易量)
    def get_klines(self, symbol, period, size, ts=''):
        start = get_ms()
        get_market_price_info(symbol)[period]["pending"] += 1
        result = None
        try:
            result = self.MarketApi.get_history_candlesticks(symbol, period, 100 if size > 100 else size, ts)
        except Exception as e:
            logger.error("***klines:%s" % e)
        get_market_price_info(symbol)[period]["pending"] -= 1
        cost = get_ms() - start
        if cost > 5000:
            logger.warning(f"[{self.user}]{symbol}:kline requested,taking too long:{cost} ms")
        if result is not None and result['code'] is not None and result["code"] == "0":
            set_market_klines(symbol, period, list(map(self.get_line_data, result["data"])), size)
        else:
            gevent.sleep(2 if period == '1s' else 0.2)
            self.get_klines(symbol, period, size, ts)

    # 获取用户持仓信息
    def get_contract_position_info(self, symbol):
        try:
            data = self.AccountApi.get_positions("", symbol)
            if data is not None and data['data'] is not None and data['code'] == '0':
                if len(data['data']) != 0:
                    volume = data["data"][0]["pos"]
                    direction = data["data"][0]["posSide"]
                    if direction is None or volume is None:
                        raise Exception
                    return int(volume), direction
                else:
                    return 0, "net"
        except Exception:
            logger.info(f"{self.user}|***get_contract_position_info: retry...")
            gevent.sleep(0.02)
            return self.get_contract_position_info(symbol)

    def get_contract_offset(self, order_type, direction):
        if direction == "short" and order_type == self.TRADE_SELL:
            return True, direction
        elif direction == "long" and order_type == self.TRADE_BUY:
            return True, direction
        elif direction == "net":
            return True, direction
        else:
            return False, direction

    def get_contract_opposite_offset(self, offset):
        if offset == "long":
            return "short"
        else:
            return "long"
