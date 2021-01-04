#!/usr/bin/python
# -*- coding: utf-8 -*-
# 用于访问OKCOIN 现货REST API
from util.HttpMD5Util import build_my_sign, http_get, http_post


class OkexSpot:

    def __init__(self, url, apikey, secretkey):
        self.__url = url
        self.__apikey = apikey
        self.__secretkey = secretkey

    # 获取OKCOIN现货行情信息
    def ticker(self, symbol=''):
        ticker_resource = "/api/v1/ticker.do"
        params = ''
        if symbol:
            params = 'symbol=%(symbol)s' % {'symbol': symbol}
        return http_get(self.__url, ticker_resource, params)

    # 获取OKCOIN现货市场深度信息
    def depth(self, symbol='', size=10):
        depth_resource = "/api/v1/depth.do"
        params = ''
        if symbol:
            params = 'symbol=%(symbol)s&size=%(size)d' % {'symbol': symbol, 'size': size}
        return http_get(self.__url, depth_resource, params)

    # 获取OKCOIN现货历史交易信息
    def trades(self, symbol=''):
        trades_resource = "/api/v1/trades.do"
        params = ''
        if symbol:
            params = 'symbol=%(symbol)s' % {'symbol': symbol}
        return http_get(self.__url, trades_resource, params)

    # 获取OKCOIN现货历史交易信息
    def klines(self, symbol='', _type='15min', size=''):
        trades_resource = "/api/v1/kline.do"
        params = 'symbol=%(symbol)s&type=%(type)s&size=%(size)d&rnd=%(size)s' % {'symbol': symbol, 'type': _type,
                                                                                 'size': size}
        return http_get(self.__url, trades_resource, params)

    # 获取用户现货账户信息
    def userinfo(self):
        userinfo_resource = "/api/v1/userinfo.do"
        params = {
            'api_key': self.__apikey
        }
        # params['api_key'] = self.__apikey
        params['sign'] = build_my_sign(params, self.__secretkey)
        return http_post(self.__url, userinfo_resource, params)

    # 现货交易
    def trade(self, symbol, trade_type, price='', amount=''):
        trade_resource = "/api/v1/trade.do"
        params = {
            'api_key': self.__apikey,
            'symbol': symbol,
            'type': trade_type
        }
        if price:
            params['price'] = price
        if amount:
            params['amount'] = amount

        params['sign'] = build_my_sign(params, self.__secretkey)
        return http_post(self.__url, trade_resource, params)

    # 现货批量下单
    def batch_trade(self, symbol, trade_type, orders_data):
        batch_trade_resource = "/api/v1/batch_trade.do"
        params = {
            'api_key': self.__apikey,
            'symbol': symbol,
            'type': trade_type,
            'orders_data': orders_data
        }
        params['sign'] = build_my_sign(params, self.__secretkey)
        return http_post(self.__url, batch_trade_resource, params)

    # 现货取消订单
    def cancel_order(self, symbol, order_id):
        cancel_order_resource = "/api/v1/cancel_order.do"
        params = {
            'api_key': self.__apikey,
            'symbol': symbol,
            'order_id': order_id
        }
        params['sign'] = build_my_sign(params, self.__secretkey)
        return http_post(self.__url, cancel_order_resource, params)

    # 现货订单信息查询
    def orderinfo(self, symbol, order_id):
        order_info_resource = "/api/v1/order_info.do"
        params = {
            'api_key': self.__apikey,
            'symbol': symbol,
            'order_id': order_id
        }
        params['sign'] = build_my_sign(params, self.__secretkey)
        return http_post(self.__url, order_info_resource, params)

    # 现货批量订单信息查询
    def ordersinfo(self, symbol, order_id, trade_type):
        orders_info_resource = "/api/v1/orders_info.do"
        params = {
            'api_key': self.__apikey,
            'symbol': symbol,
            'order_id': order_id,
            'type': trade_type
        }
        params['sign'] = build_my_sign(params, self.__secretkey)
        return http_post(self.__url, orders_info_resource, params)

    # 现货获得历史订单信息
    def order_history(self, symbol, status, current_page, page_length):
        order_history_resource = "/api/v1/order_history.do"
        params = {
            'api_key': self.__apikey,
            'symbol': symbol,
            'status': status,
            'current_page': current_page,
            'page_length': page_length
        }
        params['sign'] = build_my_sign(params, self.__secretkey)
        return http_post(self.__url, order_history_resource, params)
