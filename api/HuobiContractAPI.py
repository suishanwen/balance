#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
@author: chris
@contact: heningyu21@gmail.com
@software: PyCharm
@file: HuobiContractAPI.py
@time: 2019/11/25
"""
from util.HuobiUtils import *

order_symbol = {}


class ContractInfo(object):

    def __init__(self):
        self.contract_code = None

    def get_contract_code(self, symbol):
        if not self.contract_code:
            self.fill_contract_code(symbol)
        return self.contract_code

    # 获取合约信息
    def get_contract_info(self, symbol='', contract_type='quarter', contract_code=''):
        """
        参数名称         参数类型  必填    描述
        symbol          string  false   "BTC","ETH"...
        contract_type   string  false   合约类型: this_week:当周 next_week:下周 quarter:季度
        contract_code   string  false   BTC181228
        备注：如果contract_code填了值，那就按照contract_code去查询，如果contract_code 没有填值，则按照symbol+contract_type去查询
        """
        params = {}
        if symbol:
            params['symbol'] = symbol.split("_")[0].upper()
        if contract_type:
            params['contract_type'] = contract_type
        if contract_code:
            params['contract_code'] = contract_code

        return http_get_request(get_full_url('/api/v1/contract_contract_info'), params)

    def fill_contract_code(self, symbol):
        symbol = symbol.split("_")[0].upper()
        data = self.get_contract_info(symbol=symbol)
        for item in data["data"]:
            if "quarter" == item["contract_type"]:
                self.contract_code = item["contract_code"]
                break


contract_info = ContractInfo()


def get_contract_symbol(symbol):
    return f"{symbol.split('_')[0].upper()}_CQ"


def get_currency_name(symbol):
    return symbol.split("_")[0].upper()


def get_full_url(path):
    return f"{CONTRACT_URL}{path}"


def get_k_line(symbol, period, size=150):
    """
    :param symbol
    :param period: 可选值：{1min, 5min, 15min, 30min, 60min, 1day, 1mon, 1week, 1year }
    :param size: 可选值： [1,2000]
    :return:
    """

    params = {'symbol': get_contract_symbol(symbol),
              'period': period,
              'size': size}
    return http_get_request(
        get_full_url("/market/history/kline"),
        params)["data"]


# 获取marketdepth
def get_depth(symbol, _type='step0'):
    """
    :param symbol
    :param _type: 可选值：{ percent10, step0, step1, step2, step3, step4, step5 }
    :return:
    """
    params = {'symbol': get_contract_symbol(symbol),
              'type': _type}

    return http_get_request(
        get_full_url("/market/depth"),
        params)["tick"]


# 获取tradedetail
def get_trade(symbol):
    """
    :param symbol
    :return:
    """
    params = {'symbol': get_contract_symbol(symbol)}

    return http_get_request(
        get_full_url('/market/trade'), params)["tick"]


#  获取聚合行情(Ticker)
def get_ticker(symbol):
    """
    :param symbol:
    :return:
    """
    params = {'symbol': get_contract_symbol(symbol)}

    return http_get_request(get_full_url('/market/detail/merged'), params)["tick"]


# def get_accounts():
#     """
#     :return:
#     """
#     path = "/v1/account/accounts"
#     params = {}
#     return api_key_get(params, path)


# 创建并执行订单
def send_order(acct_id, amount, symbol, _type, price=0):
    """
    :param acct_id:
    :param amount:
    :param symbol:
    :param _type: 可选值 {buy-market：市价买, sell-market：市价卖, buy-limit：限价买, sell-limit：限价卖}
    :param price:
    :return:
    """
    # 合约下单
    order_price_type = _type.split("-")[1]
    direction = _type.split("-")[0]
    contract_code = contract_info.get_contract_code(symbol)
    contract_symbol = symbol.split("_")[0].upper()
    contract_type = "quarter"
    offset = "close" if direction == "sell" else "open"
    lever_rate = 1

    def send_contract_order(symbol, contract_type, contract_code,
                            client_order_id, price, volume, direction, offset,
                            lever_rate, order_price_type):
        """
        :symbol: "BTC","ETH"..
        :contract_type: "this_week", "next_week", "quarter"
        :contract_code: "BTC181228"
        :client_order_id: 客户自己填写和维护，这次一定要大于上一次
        :price             必填   价格
        :volume            必填  委托数量（张）
        :direction         必填  "buy" "sell"
        :offset            必填   "open", "close"
        :lever_rate        必填  杠杆倍数
        :order_price_type  必填   "limit"限价， "opponent" 对手价
        备注：如果contract_code填了值，那就按照contract_code去下单，如果contract_code没有填值，则按照symbol+contract_type去下单。
        :
        """

        params = {"price": price,
                  "volume": volume,
                  "direction": direction,
                  "offset": offset,
                  "lever_rate": lever_rate,
                  "order_price_type": order_price_type}
        if symbol:
            params["symbol"] = symbol
        if contract_type:
            params['contract_type'] = contract_type
        if contract_code:
            params['contract_code'] = contract_code
        if client_order_id:
            params['client_order_id'] = client_order_id

        request_path = '/api/v1/contract_order'
        return api_key_post(params, request_path, CONTRACT_URL)

    result = send_contract_order(contract_symbol, contract_type, contract_code, "", price, amount, direction, offset,
                                 lever_rate,
                                 order_price_type)

    order_symbol[result["data"]["order_id"]] = contract_symbol
    # order_ts[result["data"]["order_id"]] = result["ts"]
    return {"data": result["data"]["order_id"]}


# 撤销订单
def cancel_order(order_id):
    """

    :param order_id:
    :return:
    """

    # 撤销订单
    def cancel_contract_order(symbol, order_id='', client_order_id=''):
        """
        参数名称          是否必须 类型     描述
        symbol           true   string  BTC, ETH, ...
        order_id	         false  string  订单ID（ 多个订单ID中间以","分隔,一次最多允许撤消50个订单 ）
        client_order_id  false  string  客户订单ID(多个订单ID中间以","分隔,一次最多允许撤消50个订单)
        备注： order_id 和 client_order_id都可以用来撤单，同时只可以设置其中一种，如果设置了两种，默认以order_id来撤单。
        """

        params = {"symbol": symbol}
        if order_id:
            params["order_id"] = order_id
        if client_order_id:
            params["client_order_id"] = client_order_id

        request_path = '/api/v1/contract_cancel'
        return api_key_post(params, request_path, CONTRACT_URL)

    symbol = order_symbol[order_id]
    result = cancel_contract_order(symbol=symbol, order_id=order_id)

    if order_id in result["successes"]:
        return {"data": order_id}
    else:
        return {
            "status": "error",
            "err-code": "order-orderstate-error",
            "err-msg": "订单状态错误",
            "order-state": -1
        }


status_map = {
    "1": "submitted",
    "2": "submitted",
    "3": "submitted",
    "4": "partial-filled",
    "5": "partial-canceled",
    "6": "filled",
    "7": "canceled",
    "11": "submitted",
}


# 查询某个订单
def order_info(order_id):
    """

    :param order_id:
    :return:
    """

    # 获取合约订单信息
    def get_contract_order_info(symbol, order_id='', client_order_id=''):
        """
        参数名称	        是否必须	类型	    描述
        symbol          true    string  BTC, ETH, ...
        order_id	        false	string	订单ID（ 多个订单ID中间以","分隔,一次最多允许查询20个订单 ）
        client_order_id	false	string	客户订单ID(多个订单ID中间以","分隔,一次最多允许查询20个订单)
        备注：order_id和client_order_id都可以用来查询，同时只可以设置其中一种，如果设置了两种，默认以order_id来查询。
        """

        params = {"symbol": symbol}
        if order_id:
            params["order_id"] = order_id
        if client_order_id:
            params["client_order_id"] = client_order_id

        request_path = '/api/v1/contract_order_info'
        return api_key_post(params, request_path, CONTRACT_URL)

    symbol = order_symbol[order_id]
    result = get_contract_order_info(symbol, order_id)
    data = result["data"]["0"]
    data["amount"] = data["volume"]
    data["price"] = data["price"]
    data["field-amount"] = data["trade_volume"]
    data["field-cash-amount"] = data["trade_turnover"]
    data["state"] = status_map[str(data["status"])]
    return {
        "data": data
    }
