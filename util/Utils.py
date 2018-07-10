#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date    : 2017-12-20 15:40:03
# @Author  : KlausQiu
# @QQ      : 375235513
# @github  : https://github.com/KlausQIU

import base64
import datetime
import hashlib
import hmac
import json
import urllib
import urllib.parse
import urllib.request
import requests
from ecdsa import SigningKey
from hashlib import sha256
import configparser

# read config
configBase = configparser.ConfigParser()
configBase.read("../key.ini")

# 此处填写APIKEY
# init apikey,secretkey,url
ACCESS_KEY = configBase.get("huobipro", "access_key")
SECRET_KEY = configBase.get("huobipro", "secret_key")

# Need to replace with the actual value generated from below command
# openssl ecparam -name secp256k1 -genkey -noout -out secp256k1-key.pem
PRIVATE_KEY = '''-----BEGIN EC PRIVATE KEY-----
    MHQCAQEEIGsZdYPWE/j9v3PyQuTP7XEJM5AmX02FCCHeIscumc9PoAcGBSuBBAAK
oUQDQgAEH1WA/nxcZIXvRRIucEJ2viijhd7oEbzNqYJz/5gBF7381i8CPuKv06XH
5eHglrcOW3V9r/6YByBIXn/sUd/4hw==
    -----END EC PRIVATE KEY-----'''

# API request URL
MARKET_URL = "https://api.huobi.pro"
TRADE_URL = "https://api.huobi.pro"

# Can first request to call get_accounts()to find the target acct_id,later can just specify the actual acc_id in the api call
ACCOUNT_ID = None


# 'Timestamp': '2017-06-02T06:13:49'

def http_get_request(url, params, add_to_headers=None):
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36',
    }
    if add_to_headers:
        headers.update(add_to_headers)
    postdata = urllib.parse.urlencode(params)
    response = requests.get(url, postdata, headers=headers, timeout=5)
    try:

        if response.status_code == 200:
            return response.json()
        else:
            return
    except BaseException as e:
        print("httpGet failed, detail is:%s,%s" % (response.text, e))
        return


def http_post_request(url, params, add_to_headers=None):
    headers = {
        "Accept": "application/json",
        'Content-Type': 'application/json'
    }
    if add_to_headers:
        headers.update(add_to_headers)
    postdata = json.dumps(params)
    response = requests.post(url, postdata, headers=headers, timeout=10)
    try:

        if response.status_code == 200:
            return response.json()
        else:
            return
    except BaseException as e:
        print("httpPost failed, detail is:%s,%s" % (response.text, e))
        return


def api_key_get(params, request_path):
    method = 'GET'
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    params.update({'AccessKeyId': ACCESS_KEY,
                   'SignatureMethod': 'HmacSHA256',
                   'SignatureVersion': '2',
                   'Timestamp': timestamp})

    host_url = TRADE_URL
    host_name = urllib.parse.urlparse(host_url).hostname
    host_name = host_name.lower()
    signature = createSign(params, method, host_name, request_path, SECRET_KEY)
    params['Signature'] = signature
    params['PrivateSignature'] = createPrivateSignature(signature, PRIVATE_KEY)
    url = host_url + request_path
    return http_get_request(url, params)


def api_key_post(params, request_path):
    method = 'POST'
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    params_to_sign = {'AccessKeyId': ACCESS_KEY,
                      'SignatureMethod': 'HmacSHA256',
                      'SignatureVersion': '2',
                      'Timestamp': timestamp}

    host_url = TRADE_URL
    host_name = urllib.parse.urlparse(host_url).hostname
    host_name = host_name.lower()
    signature = createSign(params_to_sign, method, host_name, request_path, SECRET_KEY)
    params_to_sign['Signature'] = signature
    params_to_sign['PrivateSignature'] = createPrivateSignature(signature, PRIVATE_KEY)
    url = host_url + request_path + '?' + urllib.parse.urlencode(params_to_sign)
    return http_post_request(url, params)


def createSign(pParams, method, host_url, request_path, secret_key):
    sorted_params = sorted(pParams.items(), key=lambda d: d[0], reverse=False)
    encode_params = urllib.parse.urlencode(sorted_params)
    payload = [method, host_url, request_path, encode_params]
    payload = '\n'.join(payload)
    payload = payload.encode(encoding='UTF8')
    secret_key = secret_key.encode(encoding='UTF8')

    digest = hmac.new(secret_key, payload, digestmod=hashlib.sha256).digest()
    signature = base64.b64encode(digest)
    signature = signature.decode()
    return signature


def createPrivateSignature(signature, private_key):
    signingKey = SigningKey.from_pem(private_key, hashfunc=sha256)
    privateSignature = signingKey.sign(signature.encode(encoding='UTF8'))
    return base64.b64encode(privateSignature)