import re
import time

from util.MyUtil import from_time_stamp
from module.CfEnv import TRADE_TYPE, TradeType


class MyOrderInfo(object):
    def __init__(self, symbol="", order_type="", price=0, amount=0, base=0, trigger=0):
        self.orderId = ""
        self.symbol = symbol
        self.orderType = order_type
        self.price = price
        self.offset = "close"
        self.totalAmount = amount
        self.base = base
        self.totalDealAmount = 0
        self.amount = 0
        self.dealAmount = 0
        self.avgPrice = 0
        self.transaction = 0
        self.count = 0
        self.trigger = self.get_trigger(trigger)
        self.timestamp = from_time_stamp()
        self.canceled = 0

    def replicate(self):
        order_info = MyOrderInfo(self.symbol, self.orderType, self.price, self.amount, self.base)
        order_info.trigger = self.trigger
        return order_info

    def __repr__(self):
        data = [str(self.orderId), self.symbol, self.orderType,
                str(self.base),
                str(self.price),
                str(self.avgPrice),
                str(self.dealAmount),
                str(self.totalDealAmount),
                str(self.transaction),
                "[" + str(self.count) + "]",
                str(self.timestamp),
                str(self.trigger)]
        if self.canceled == 1:
            data.append('[已撤销]')
        return ' '.join(data)

    def tl_msg(self, client):
        if TRADE_TYPE != TradeType.SPOT:
            unit = "张"
        else:
            unit = "个"
        order_type = "买入" if self.orderType == client.TRADE_BUY else "卖出"
        if self.symbol.find("_") == -1:
            coin = self.symbol.replace(client.BALANCE_E, "")
            currency = client.BALANCE_E
        else:
            coin = self.symbol.split("_")[0]
            currency = self.symbol.split("_")[1]
        message = f"[{self.trigger.upper()[0:1]}] {order_type} {coin} {self.totalDealAmount}{unit}，均价 {self.avgPrice}\n" \
                  f"总成交额 {round(self.transaction, 2)} {currency}，收益 {self.count}"
        return message

    @classmethod
    def get_trigger(cls, trigger):
        if abs(trigger) == 1:
            return "dma"
        elif abs(trigger) == 2:
            return "reverse"
        elif abs(trigger) == 3:
            return "needle"
        elif abs(trigger) == 9:
            return "percent"
        return ""

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

    def reset_total_deal_amount(self, deal_amount):
        self.totalDealAmount += deal_amount

    def set_transaction(self, trans_type):
        if trans_type == 'plus':
            if TRADE_TYPE == TradeType.SPOT:
                self.transaction = round(self.transaction + self.dealAmount * self.avgPrice, 3)
            else:
                self.transaction = self.transaction + self.dealAmount * 10
        else:
            if TRADE_TYPE == TradeType.SPOT:
                self.transaction = round(self.transaction - self.dealAmount * self.avgPrice, 3)
            else:
                self.transaction = self.transaction - self.dealAmount * 10

    def get_buy_amount(self, price, accuracy=2):
        return round(self.transaction / price, accuracy)

    def get_unhandled_amount(self, accuracy=2):
        return round(self.totalAmount - self.totalDealAmount, accuracy)

    def from_log(self, line):
        match_obj = re.match("(.*) (.*) (.*) (.*) (.*) (.*) (.*) (.*) (.*) (.*) (.* .*) (.*)", line, re.M | re.I)
        if match_obj:
            self.orderId = match_obj.group(1)
            self.symbol = match_obj.group(2)
            self.orderType = match_obj.group(3)
            self.base = float(match_obj.group(4))
            self.price = float(match_obj.group(5))
            self.avgPrice = float(match_obj.group(6))
            self.dealAmount = float(match_obj.group(7))
            self.totalAmount = float(match_obj.group(8))
            self.totalDealAmount = float(match_obj.group(8))
            self.amount = float(match_obj.group(8))
            self.transaction = float(match_obj.group(9))
            self.count = float(re.search("[0-9]+(.[0-9]+)?", match_obj.group(10)).group())
            self.timestamp = match_obj.group(11)
            self.trigger = match_obj.group(12)

    def get_seconds(self):
        return int(time.mktime(time.strptime(self.timestamp, '%Y-%m-%d %H:%M:%S')))
