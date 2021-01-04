import json
import time
import hashlib
import hmac
import urllib.parse
import requests
from api.Result import Result
from module.CfEnv import configBase

API_KEY = configBase.get("binance", "API_KEY")
SECRET_KEY = configBase.get("binance", "SECRET_KEY")

BASE_URL = "https://api.binance.com"

headers = {
    "Accept": "application/json",
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/39.0.2171.71 Safari/537.36',
    "X-MBX-APIKEY": API_KEY
}


def common_response(response):
    try:
        if response.status_code == 200:
            return Result(200, "ok", response.json())
        else:
            data = json.loads(response.text)
            return Result(response.status_code, data.get('msg'), data)
    except Exception as e:
        return Result(response.status_code, str(e))


def http_get_request(url, params, add_to_headers=None):
    if add_to_headers:
        headers.update(add_to_headers)
    sorted_params = sorted(params.items(), key=lambda d: d[0], reverse=False)
    query_params = urllib.parse.urlencode(sorted_params)
    response = requests.get(url, query_params, headers=headers, timeout=5)
    return common_response(response)


def http_post_request(url, params, add_to_headers=None):
    if add_to_headers:
        headers.update(add_to_headers)
    sorted_params = sorted(params.items(), key=lambda d: d[0], reverse=False)
    query_params = urllib.parse.urlencode(sorted_params)
    response = requests.post(url, query_params, headers=headers, timeout=10)
    return common_response(response)


def http_delete_request(url, params, add_to_headers=None):
    if add_to_headers:
        headers.update(add_to_headers)
    sorted_params = sorted(params.items(), key=lambda d: d[0], reverse=False)
    query_params = urllib.parse.urlencode(sorted_params)
    response = requests.delete(url + "?" + query_params, headers=headers, timeout=10)
    return common_response(response)


def api_key_http(params, request_path, method):
    # timestamp = round(datetime.utcnow().timestamp() * 1000)
    timestamp = int(time.time() * 1000)
    params.update(
        {'timestamp': timestamp})
    params['signature'] = create_sign(params, SECRET_KEY)
    url = BASE_URL + request_path
    method = method.upper()
    if method == "GET":
        return http_get_request(url, params)
    elif method == "POST":
        return http_post_request(url, params)
    elif method == "DELETE":
        return http_delete_request(url, params)


def create_sign(params, secret_key):
    sorted_params = sorted(params.items(), key=lambda d: d[0], reverse=False)
    encode_params = urllib.parse.urlencode(sorted_params).encode(encoding='UTF8')
    secret_key = secret_key.encode(encoding='UTF8')
    m = hmac.new(secret_key, encode_params, digestmod=hashlib.sha256)
    return m.hexdigest()
