#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date    : 2019-07-27
# @Author  : sw
# @github  : https://github.com/suishanwen

from util.BinanceUtil import BASE_URL, http_get_request, api_key_http

# 1分钟限制访问总权重数1200，超出将被封2分钟-3天


'''
Market API
'''


# 获取服务器时间 权重：1
def server_time():
    params = {}
    url = BASE_URL + '/api/v1/time'
    return http_get_request(url, params)


# 获取KLine 权重: 1
def get_kline(symbol, interval, limit=10):
    """
    :param symbol
    :param interval: 可选值：{1m, 3m, 5m, 15m,30m,1h,2h,4h,6h,8h,12h,1d,3d,1w,1M}
    :param limit: 可选值： [1,1000]
    :return:
    """
    params = {'symbol': symbol.replace("_", "").upper(),
              'interval': interval,
              'limit': limit}

    url = BASE_URL + '/api/v1/klines'
    return http_get_request(url, params)


# 获取marketdepth 权重：通过参数判定
def get_depth(symbol, limit='10'):
    """
    :param symbol
    :param limit: 可选值：{ 权重1： 5, 10, 20, 50, 100  权重5：500 权重10：1000}
    :return:
    """
    params = {'symbol': symbol.replace("_", "").upper(),
              'limit': limit}

    url = BASE_URL + '/api/v1/depth'
    return http_get_request(url, params)


'''
Trade/Account API
'''


# 获取账户信息 权重：5
def get_accounts():
    """
    :return:
    """
    path = "/api/v3/account"
    params = {}
    return api_key_http(params, path, method="GET")


# 创建并执行订单 权重：1
def send_order(symbol, side, price, quantity):
    """
    :param symbol
    :param side: buy/sell
    :param quantity
    :param price
    :return:
    """
    params = {"symbol": symbol.replace("_", "").upper(),
              "side": side,
              "type": "limit",
              "timeInForce": "FOK",
              "price": price,
              "quantity": quantity}
    if price:
        params["price"] = price

    path = '/api/v3/order'
    return api_key_http(params, path, method="POST")


# 撤销订单 权重：1
def cancel_order(symbol, order_id):
    """
    :param symbol
    :param order_id
    :return:
    """
    params = {
        "symbol": symbol.replace("_", "").upper(),
        "orderId": order_id
    }
    path = "/api/v3/order"
    return api_key_http(params, path, method="DELETE")


# 查询某个订单 权重：1
def order_info(symbol, order_id):
    """
    :param symbol
    :param order_id
    :return:
    """
    params = {"symbol": symbol.replace("_", "").upper(),
              "orderId": order_id}
    path = "/api/v3/order"
    return api_key_http(params, path, method="GET")


if __name__ == '__main__':
    print(server_time().__dict__)
