import re
import time

from util.MyUtil import from_time_stamp


class MyOrderInfo(object):
    def __init__(self, symbol="", order_type="", price=0, amount=0, base=0, trigger=0, trigger_ext=None, earn=0):
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
        self.realAmount = 0
        self.avgPrice = 0
        self.transaction = 0
        self.count = 0
        self.trigger = self.get_trigger(
            trigger) if trigger_ext is None else f"{self.get_trigger(trigger)}_{trigger_ext}"
        self.cid = self.get_trigger_cid(trigger) + symbol.replace("-", "")
        self.timestamp = from_time_stamp()
        self.canceled = 0
        self.fee = 0
        self.earn = earn

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
        if client.IS_FUTURE:
            unit = "张"
            self.totalDealAmount = int(self.totalDealAmount)
        else:
            unit = "个"
        order_type = "买入" if self.orderType == client.TRADE_BUY else "卖出"
        if self.symbol.find("_") != -1:
            coin = self.symbol.split("_")[0]
            currency = self.symbol.split("_")[1]
        elif self.symbol.find("-") != -1:
            coin = self.symbol.split("-")[0]
            currency = self.symbol.split("-")[1]
        else:
            coin = self.symbol.replace(client.BALANCE_E, "")
            currency = client.BALANCE_E
        _type = self.trigger.upper()[0:1]
        dynamic_msg = f"总成交额 {round(self.transaction, 2)} {currency.upper()}"
        if self.trigger.find("mt") != -1:
            if self.trigger == "mt_long_open" or self.trigger == "mt_long_apnd":
                _type = "TL+"
            elif self.trigger.find("mt_long_napnd") != -1:
                _type = "TLN+"
            elif self.trigger.find("mt_long_clos") != -1:
                _type = "TL-"
                dynamic_msg = f"开仓均价 {self.trigger.split('mt_long_clos_')[1] if 'mt_long_clos_' in self.trigger else ''}"
            elif self.trigger == "mt_short_open" or self.trigger == "mt_short_apnd":
                _type = "TS+"
            elif self.trigger.find("mt_short_napnd") != -1:
                _type = "TSN+"
            elif self.trigger.find("mt_short_clos") != -1:
                _type = "TS-"
                dynamic_msg = f"开仓均价 {self.trigger.split('mt_short_clos_')[1] if 'mt_short_clos_' in self.trigger else ''}"
        elif self.trigger.find("atr") != -1:
            if self.trigger == "atr_long_open":
                _type = "AL+"
            elif self.trigger.find("atr_long_clos") != -1:
                _type = "AL-"
                dynamic_msg = f"开仓价格 {self.trigger.split('atr_long_clos_')[1]}"
            elif self.trigger == "atr_short_open":
                _type = "AS+"
            elif self.trigger.find("atr_short_clos") != -1:
                _type = "AS-"
                dynamic_msg = f"开仓价格 {self.trigger.split('atr_short_clos_')[1]}"
        elif self.trigger.find("hf") != -1:
            if self.trigger == "hf_long_open":
                _type = "HF+"
            elif self.trigger.find("hf_long_clos") != -1:
                _type = "HF-"
                dynamic_msg = f"开仓汇率 {self.trigger.split('hf_long_clos_')[1]}"
            elif self.trigger == "hf_short_open":
                _type = "HF↓+"
            elif self.trigger.find("hf_short_clos") != -1:
                _type = "HF↓-"
                dynamic_msg = f"开仓汇率 {self.trigger.split('hf_short_clos_')[1]}"
        message = f"[{_type}] {order_type} {coin} {self.totalDealAmount}{unit}，均价 {self.avgPrice}\n" \
                  f"{dynamic_msg}，收益 {round(self.count, 2)}"
        return message

    @classmethod
    def get_trigger(cls, trigger):
        if trigger == 41:
            return "mt_long_open"
        elif trigger == 42:
            return "mt_long_apnd"
        elif trigger == 43:
            return "mt_long_napnd"
        elif trigger == 40:
            return "mt_short_clos"
        elif trigger == -41:
            return "mt_short_open"
        elif trigger == -42:
            return "mt_short_apnd"
        elif trigger == -43:
            return "mt_short_napnd"
        elif trigger == -40:
            return "mt_long_clos"
        elif abs(trigger) == 1:
            return "dma"
        elif abs(trigger) == 2:
            return "reverse"
        elif abs(trigger) == 3:
            return "needle"
        elif abs(trigger) == 9:
            return "percent"
        elif trigger == 10:
            return "atr_long_open"
        elif trigger == -11:
            return "atr_long_clos"
        elif trigger == -10:
            return "atr_short_open"
        elif trigger == 11:
            return "atr_short_clos"
        elif trigger == 20:
            return "hf_long_open"
        elif trigger == -21:
            return "hf_long_clos"
        elif trigger == -20:
            return "hf_short_open"
        elif trigger == 21:
            return "hf_short_clos"
        return ""

    @classmethod
    def get_trigger_cid(cls, trigger):
        if trigger == 41:
            return "MTLOPEN"
        elif trigger == 42 or trigger == 43:
            return "MTLAPND"
        elif trigger == 40:
            return "MTSCLOS"
        elif trigger == -41:
            return "MTSOPEN"
        elif trigger == -42 or trigger == -43:
            return "MTSAPND"
        elif trigger == -40:
            return "MTLCLOS"
        elif abs(trigger) == 1:
            return "MA"
        elif abs(trigger) == 2:
            return "MA"
        elif abs(trigger) == 3:
            return "MA"
        elif abs(trigger) == 9:
            return "MA"
        elif trigger == 10:
            return "ATRLONGOPEN"
        elif trigger == -11:
            return "ATRLONGCLOS"
        elif trigger == -10:
            return "ATRSHORTOPEN"
        elif trigger == 11:
            return "ATRSHORTCLOS"
        elif trigger == 20:
            return "HFLONGOPEN"
        elif trigger == -21:
            return "HFLONGCLOS"
        elif trigger == -20:
            return "HFSHORTOPEN"
        elif trigger == 21:
            return "HFSHORTCLOS"
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

    def set_transaction(self, trans_type, client):
        if trans_type == 'plus':
            if client.IS_FUTURE:
                if client.USDT_FUTURE and client.atr == 1:
                    self.transaction = self.transaction + self.dealAmount * client.swapEnlarge * self.avgPrice
                else:
                    self.transaction = self.transaction + self.dealAmount * 10
            else:
                self.transaction = round(self.transaction + self.dealAmount * self.avgPrice, 3)

        else:
            if client.IS_FUTURE:
                if client.USDT_FUTURE and client.atr == 1:
                    self.transaction = self.transaction - self.dealAmount * client.swapEnlarge * self.avgPrice
                else:
                    self.transaction = self.transaction - self.dealAmount * 10
            else:
                self.transaction = round(self.transaction - self.dealAmount * self.avgPrice, 3)

    def set_fee(self, fee):
        self.fee = fee

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
            self.count = float(re.search("-?[0-9]+(.[0-9]+)?", match_obj.group(10)).group())
            self.timestamp = match_obj.group(11)
            self.trigger = match_obj.group(12)

    def get_seconds(self):
        return int(time.mktime(time.strptime(self.timestamp, '%Y-%m-%d %H:%M:%S')))
