#!/usr/bin/env python

import asyncio
import websockets
import json
import requests
import dateutil.parser as dp
import hmac
import base64
import zlib


def get_server_time():
    url = "http://www.okex.com/api/general/v3/time"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()['iso']
    else:
        return ""


def server_timestamp():
    server_time = get_server_time()
    parsed_t = dp.parse(server_time)
    timestamp = parsed_t.timestamp()
    return timestamp


def login_params(timestamp, api_key, passphrase, secret_key):
    message = timestamp + 'GET' + '/users/self/verify'
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    sign = base64.b64encode(d)

    login_param = {"op": "login", "args": [api_key, passphrase, timestamp, sign.decode("utf-8")]}
    login_str = json.dumps(login_param)
    return login_str


def inflate(data):
    decompress = zlib.decompressobj(
        -zlib.MAX_WBITS  # see above
    )
    inflated = decompress.decompress(data)
    inflated += decompress.flush()
    return inflated


# subscribe channel without login
#
# swap/ticker // 行情数据频道
# swap/candle60s // 1分钟k线数据频道
# swap/candle180s // 3分钟k线数据频道
# swap/candle300s // 5分钟k线数据频道
# swap/candle900s // 15分钟k线数据频道
# swap/candle1800s // 30分钟k线数据频道
# swap/candle3600s // 1小时k线数据频道
# swap/candle7200s // 2小时k线数据频道
# swap/candle14400s // 4小时k线数据频道
# swap/candle21600 // 6小时k线数据频道
# swap/candle43200s // 12小时k线数据频道
# swap/candle86400s // 1day k线数据频道
# swap/candle604800s // 1week k线数据频道
# swap/trade // 交易信息频道
# swap/funding_rate//资金费率频道
# swap/price_range//限价范围频道
# swap/depth //深度数据频道，首次200档，后续增量
# swap/depth5 //深度数据频道，每次返回前5档
# swap/mark_price// 标记价格频道
async def subscribe_without_login(url, channels):
    async with websockets.connect(url) as websocket:
        sub_param = {"op": "subscribe", "args": channels}
        sub_str = json.dumps(sub_param)
        await  websocket.send(sub_str)
        print("send: {}".format(sub_str))

        print("receive:")
        res = await websocket.recv()
        res = inflate(res)
        print("{}".format(res))

        res = await websocket.recv()
        res = inflate(res)
        print("{}".format(res))


# unsubscribe channels
async def unsubscribe_without_login(url, channels):
    async with websockets.connect(url) as websocket:
        sub_param = {"op": "unsubscribe", "args": channels}
        sub_str = json.dumps(sub_param)
        await  websocket.send(sub_str)
        print("send: {}".format(sub_str))

        res = await websocket.recv()
        res = inflate(res)
        print("{}".format(res))


api_key = ''
seceret_key = ''
passphrase = ''
url = 'wss://real.okex.com:10442/ws/v3'
# asyncio.get_event_loop().run_until_complete(login(url, api_key, passphrase, seceret_key))
channels = ["swap/ticker:BTC-USD-SWAP"]
# asyncio.get_event_loop().run_until_complete(subscribe(url, api_key, passphrase, seceret_key, channels))
# asyncio.get_event_loop().run_until_complete(unsubscribe(url, api_key, passphrase, seceret_key, channels))
asyncio.get_event_loop().run_until_complete(subscribe_without_login(url, channels))
# asyncio.get_event_loop().run_until_complete(unsubscribe_without_login(url, channels))
