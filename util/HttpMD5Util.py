#!/usr/bin/python
# -*- coding: utf-8 -*-
# 用于进行http请求，以及MD5加密，生成签名的工具类

import http.client
import urllib
import json
import hashlib
import ssl
import configparser
from util.Socks5 import open_socks

# read config
configBase = configparser.ConfigParser()
configBase.read("../key.ini")
context = ssl._create_unverified_context()
# local socks5 proxy
OPEN_SOCKS = configBase.get("okex", "socks")
if OPEN_SOCKS == "1":
    open_socks()


def build_my_sign(params, secretKey):
    sign = ''
    for key in sorted(params.keys()):
        sign += key + '=' + str(params[key]) + '&'
    data = sign + 'secret_key=' + secretKey
    return hashlib.md5(data.encode("utf8")).hexdigest().upper()


def http_get(url, resource, params=''):
    inside_exception = True
    while inside_exception:
        try:
            conn = http.client.HTTPSConnection(url, timeout=10, context=context)
            conn.request("GET", resource + '?' + params)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            inside_exception = False
        except Exception as err:
            print(err)
    return json.loads(data)


def http_post(url, resource, params):
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
    }
    inside_exception = True
    while inside_exception:
        try:
            conn = http.client.HTTPSConnection(url, timeout=10, context=context)
            temp_params = urllib.parse.urlencode(params)
            conn.request("POST", resource, temp_params, headers)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            params.clear()
            conn.close()
            inside_exception = False
        except Exception as err:
            print(err)
    return json.loads(data)
