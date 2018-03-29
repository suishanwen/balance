#!/usr/bin/python
# -*- coding: utf-8 -*-
# 用于进行http请求，以及MD5加密，生成签名的工具类

import http.client
import urllib
import json
import hashlib
import ssl

context = ssl._create_unverified_context()


def buildMySign(params, secretKey):
    sign = ''
    for key in sorted(params.keys()):
        sign += key + '=' + str(params[key]) + '&'
    data = sign + 'secret_key=' + secretKey
    return hashlib.md5(data.encode("utf8")).hexdigest().upper()


def httpGet(url, resource, params=''):
    insideException = True
    while insideException:
        try:
            conn = http.client.HTTPSConnection(url, timeout=10, context=context)
            conn.request("GET", resource + '?' + params)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            insideException = False
        except Exception as err:
            print(err)
    return json.loads(data)


def httpPost(url, resource, params):
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
    }
    insideException = True
    while insideException:
        try:
            conn = http.client.HTTPSConnection(url, timeout=10, context=context)
            temp_params = urllib.parse.urlencode(params)
            conn.request("POST", resource, temp_params, headers)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            params.clear()
            conn.close()
            insideException = False
        except Exception as err:
            print(err)
    return json.loads(data)
