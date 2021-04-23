#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
@author: chris
@contact: heningyu21@gmail.com
@software: PyCharm
@file: HuobiContractAPI.py
@time: 2019/11/25
"""
import math
from util.HuobiUtils import *
from module.CfEnv import TRADE_LIMIT, TRADE_LEVEL
from module.Logger import logger
from module.CfEnv import config

order_symbol = {}
global_type = "next_quarter"
global_symbol = "NQ"


class Security(object):

    def __init__(self):
        self.last = ""
        self.volume = 0
        config.read("config.ini")
        try:
            self.last = config.get("security", "last")
            self.volume = int(config.get("security", "count"))
        except Exception as e:
            if str(e).find("No section") > -1:
                config.add_section("security")
            self.reset()
        finally:
            logger.info(f"CURRENT CONTRACT TRADE COUNT:{self.volume}")

    def reset(self):
        date_indicator = str(datetime.date.today())
        self.volume = 0
        self.last = date_indicator
        config.set("security", "count", "0")
        config.set("security", "last", str(date_indicator))
        with open("config.ini", "w") as fp:
            config.write(fp)

    def set(self, volume):
        date_indicator = str(datetime.date.today())
        if date_indicator != self.last:
            self.reset()
        self.volume += volume
        config.set("security", "count", str(self.volume))
        with open("config.ini", "w") as fp:
            config.write(fp)

    def open(self, volume):
        self.set(volume)

    def close(self, volume):
        self.set(-volume)

    def get_volume(self):
        return self.volume


security = Security()


class ContractInfo(object):

    def __init__(self):
        self.contract_code = None

    def get_contract_code(self, symbol):
        if not self.contract_code:
            self.fill_contract_code(symbol)
        return self.contract_code

    # 获取合约信息
    def get_contract_info(self, symbol='', contract_type=global_type, contract_code=''):
        """
        参数名称         参数类型  必填    描述
        symbol          string  false   "BTC","ETH"...
        contract_type   string  false   合约类型: this_week:当周 next_week:下周 next_quarter:季度
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
            if global_type == item["contract_type"]:
                self.contract_code = item["contract_code"]
                break


contract_info = ContractInfo()


def get_contract_symbol(symbol):
    return f"{symbol.split('_')[0].upper()}_{global_symbol}"


def get_currency_name(symbol):
    return symbol.split("_")[0].upper()


def get_full_url(path):
    return f"{CONTRACT_URL}{path}"


def get_kline(symbol, period, size=150):
    """
    :param symbol
    :param period: 可选值：{1min, 5min, 15min, 30min, 60min, 1day, 1mon, 1week, 1year }
    :param size: 可选值： [1,2000]
    :return:
    """

    params = {'symbol': get_contract_symbol(symbol),
              'period': period,
              'size': size}
    result = http_get_request(
        get_full_url("/market/history/kline"),
        params)

    result["data"] = sorted(result["data"], key=lambda item: item["id"], reverse=True)
    return result


# 获取marketdepth
def get_depth(symbol, _type='step0'):
    """
    :param symbol
    :param _type: 可选值：{ percent10, step0, step1, step2, step3, step4, step5 }
    :return:
    """
    params = {'symbol': get_contract_symbol(symbol),
              'type': _type}
    result = http_get_request(
        get_full_url("/market/depth"),
        params)
    # if result.get("tick") is not None and result.get("tick").get("asks") is not None:
    #     result["tick"]["asks"] = list(map(lambda x: [x[0], x[1] * 10 / x[0]], result["tick"]["asks"]))
    #     result["tick"]["bids"] = list(map(lambda x: [x[0], x[1] * 10 / x[0]], result["tick"]["bids"]))
    return result


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


def get_accounts():
    """
    :return:
    """
    path = "/v1/account/accounts"
    params = {}
    return api_key_get(params, path)


# 获取当前账户资产
def get_balance(acct_id=None):
    """
    :param acct_id
    :return:
    """

    if not acct_id:
        accounts = get_accounts()
        acct_id = accounts['data'][0]['id']

    url = "/v1/account/accounts/{0}/balance".format(acct_id)
    params = {"account-id": acct_id}
    return api_key_get(params, url)


# 获取用户持仓信息
def get_contract_position_info(symbol='EOS'):
    """
    :param symbol: "BTC","ETH"...如果缺省，默认返回所有品种
    :return:
    """

    params = {}
    if symbol:
        params["symbol"] = symbol.split("_")[0].upper()

    request_path = '/api/v1/contract_position_info'
    data = api_key_post(params, request_path, CONTRACT_URL)
    volume = data["data"][0]["available"]
    direction = data["data"][0]["direction"]
    return volume, direction


# 创建并执行订单
def send_order(acct_id, amount, symbol, _type, price=0, offset="close"):
    """
    :param acct_id:
    :param amount:
    :param symbol:
    :param _type: 可选值 {buy-market：市价买, sell-market：市价卖, buy-limit：限价买, sell-limit：限价卖}
    :param price:
    :param offset:
    :return:
    """
    # 合约下单
    order_price_type = "limit"
    direction = _type.split("-")[0]
    contract_code = contract_info.get_contract_code(symbol)
    contract_symbol = symbol.split("_")[0].upper()
    contract_type = global_type
    # sell_offset = "open" if price > 4 else "close"
    # buy_offset = "close" if price > 4 else "open"
    # offset = sell_offset if direction == "sell" else buy_offset
    lever_rate = TRADE_LEVEL

    def send_contract_order(symbol, contract_type, contract_code,
                            client_order_id, price, volume, direction, offset,
                            lever_rate, order_price_type):
        """
        :symbol: "BTC","ETH"..
        :contract_type: "this_week", "next_week", "next_quarter"
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

    # amount = math.ceil(amount * price / 10)
    amount = math.ceil(amount)
    if math.ceil(security.get_volume()) <= TRADE_LIMIT:
        result = send_contract_order(contract_symbol, contract_type, contract_code, "", price, amount,
                                     direction,
                                     offset,
                                     lever_rate,
                                     order_price_type)
        logger.info(result)
        order_symbol[str(result["data"]["order_id"])] = contract_symbol
        if "ok" == result["status"]:
            if direction == "buy":
                security.open(amount)
            else:
                security.close(amount)
        # order_ts[result["data"]["order_id"]] = result["ts"]
        return {"data": str(result["data"]["order_id"]), "status": result["status"]}
    else:
        from module.Notification import send_msg
        send_msg("amount:{} volume:{} limit:{}".format(amount, security.get_volume(), TRADE_LIMIT))
        exit()
    return {"data": [], "status": "ok"}


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

    return result
    # if order_id in result["successes"]:
    #     return {"data": order_id, "_type": "contract"}
    # else:
    #     return {
    #         "status": "error",
    #         "err-code": "order-orderstate-error",
    #         "err-msg": "订单状态错误",
    #         "order-state": -1
    #     }


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
    data = result["data"][0]
    data["amount"] = data["volume"]
    data["price"] = data["trade_avg_price"]
    data["id"] = str(data["order_id"])
    data["field-amount"] = data["trade_volume"]
    data["field-cash-amount"] = data["trade_turnover"]
    data["state"] = status_map[str(data["status"])]
    return {
        "data": data, "status": result["status"]
    }


# 查询当前委托、历史委托
def orders_list(symbol, states, types=None, size=None, start_date=None, end_date=None, _from=None, direct=None):
    """

    :param symbol:
    :param states: 可选值 {pre-submitted 准备提交, submitted 已提交, partial-filled 部分成交,
     partial-canceled 部分成交撤销, filled 完全成交, canceled 已撤销}
    :param types: 可选值 {buy-market：市价买, sell-market：市价卖, buy-limit：限价买, sell-limit：限价卖}
    :param start_date:
    :param end_date:
    :param _from:
    :param direct: 可选值{prev 向前，next 向后}
    :param size:
    :return:
    """

    # 获取合约历史委托
    def get_contract_history_orders(symbol, trade_type, type, status, create_date,
                                    page_index=None, page_size=None):
        """
        参数名称     是否必须  类型     描述	    取值范围
        symbol      true	    string  品种代码  "BTC","ETH"...
        trade_type  true	    int     交易类型  0:全部,1:买入开多,2: 卖出开空,3: 买入平空,4: 卖出平多,5: 卖出强平,6: 买入强平,7:交割平多,8: 交割平空
        type        true	    int     类型     1:所有订单、2：结束汏订单
        status      true	    int     订单状态  0:全部,3:未成交, 4: 部分成交,5: 部分成交已撤单,6: 全部成交,7:已撤单
        create_date true	    int     日期     7，90（7天或者90天）
        page_index  false   int     页码，不填默认第1页
        page_size   false   int     不填默认20，不得多于50
        """

        params = {"symbol": symbol,
                  "trade_type": trade_type,
                  "type": type,
                  "status": status,
                  "create_date": create_date}
        if page_index:
            params["page_index"] = page_index
        if page_size:
            params["page_size"] = page_size

        request_path = '/api/v1/contract_hisorders'
        return api_key_post(params, request_path, CONTRACT_URL)

    result = get_contract_history_orders(get_currency_name(symbol), 0, 1, 0, 7)

    reponse = ""
    if "ok" == result["status"]:
        response = result["data"]["orders"]
        for order in response:
            order["amount"] = order["volume"]
            order["field-amount"] = order["trade_volume"]
            order["field-cash-amount"] = order["trade_turnover"]
            order["state"] = status_map[str(order["status"])]
            order["id"] = str(order["order_id"])
    return {"data": response, "status": result["status"]}


# 查询当前成交、历史成交
def orders_matchresults(symbol, types=None, size=None, start_date=None, end_date=None, _from=None, direct=None):
    """

    :param symbol:
    :param types: 可选值 {buy-market：市价买, sell-market：市价卖, buy-limit：限价买, sell-limit：限价卖}
    :param start_date:
    :param end_date:
    :param _from:
    :param direct: 可选值{prev 向前，next 向后}
    :param size:
    :return:
    """
    params = {'symbol': get_contract_symbol(symbol), "trade_type": 0, "create_data": 7}

    request_path = 'api/v1/contract_matchresults'
    result = api_key_post(params, request_path, CONTRACT_URL)
    response = result["data"]["trades"]
    for order in response:
        order["filled-amount"] = order["trade_volume"]
        order["price"] = order["trade_price"]
        order["id"] = str(order["order_id"])
    return {"data": response}


if __name__ == "__main__":
    data = get_depth("eos_usdt")
