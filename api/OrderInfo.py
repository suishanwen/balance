import time

from util.MyUtil import from_time_stamp


class MyOrderInfo(object):
    def __init__(self, symbol, order_type, price=0, amount=0, base=0):
        self.orderId = ""
        self.symbol = symbol
        self.orderType = order_type
        self.price = price
        self.totalAmount = amount
        self.base = base
        self.totalDealAmount = 0
        self.amount = 0
        self.dealAmount = 0
        self.avgPrice = 0
        self.transaction = 0
        self.count = 0
        self.triggerSeconds = int(time.time())

    def __repr__(self):
        return ' '.join(
            [str(self.orderId), self.symbol, self.orderType,
             str(self.base),
             str(self.price),
             str(self.avgPrice),
             str(self.dealAmount),
             str(self.totalDealAmount),
             str(self.transaction),
             "[" + str(self.count) + "]",
             str(from_time_stamp(int(time.time())))])

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
            self.transaction = round(self.transaction + self.dealAmount * self.avgPrice, 3)
        else:
            self.transaction = round(self.transaction - self.dealAmount * self.avgPrice, 3)

    def get_buy_amount(self, price, accuracy=2):
        return round(self.transaction / price, accuracy)

    def get_unhandled_amount(self, accuracy=2):
        return round(self.totalAmount - self.totalDealAmount, accuracy)
