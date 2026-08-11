import os
import configparser
import threading
import time
from pathlib import Path
import functools

from module.Logger import logger
from flask import request
import json
import uuid
from codegen.generator import decrypt_f, encrypt_f, exclusive_file_lock
from util.DataUtil import get_today_ts
from util.LoginGuard import (
    get_client_ip, get_login_failures,
    is_locked, record_login_failure, reset_login_failures,
)

PROJECT_PATH = str(Path(os.getcwd()))
KEY_PATH = os.environ.get("MARTIN_KEY_PATH", f"{PROJECT_PATH}/key.ini")
AUTH_PATH = os.environ.get("MARTIN_AUTH_PATH", f"{PROJECT_PATH}/auth.ini")
authConfig = configparser.ConfigParser()
authConfig.read(AUTH_PATH)
sids = json.loads(authConfig.get("sids", "data"))
masks = json.loads(authConfig.get("masks", "data"))
users = []
admins = []
keys = {}
apis = {}
_credential_lock = threading.RLock()
SESSION_DAYS = 14


def reload_sids():
    authConfig.read(AUTH_PATH)
    new_sids = json.loads(authConfig.get("sids", "data"))
    new_masks = json.loads(authConfig.get("masks", "data"))
    sids.clear()
    sids.update(new_sids)
    masks.clear()
    masks.update(new_masks)


def invalidate_user_cache(user):
    """清除该用户的密钥与 API 实例缓存，凭证变更后下次调用重新加载"""
    with _credential_lock:
        keys.pop(user, None)
        for cache_key in [k for k in apis if k[0] == user]:
            apis.pop(cache_key)


def get_api(user, type=1):
    with _credential_lock:
        # 复用 API 实例以保住底层 HTTP 连接池，避免每次请求重做 TCP+TLS 握手
        cached = apis.get((user, type))
        if cached is not None:
            return cached
        if not keys.get(user):
            with exclusive_file_lock(KEY_PATH):
                decrypt_f(KEY_PATH)
                try:
                    config_base = configparser.ConfigParser()
                    config_base.read(KEY_PATH)
                    api_key = safe_get_val(config_base, user, "API_KEY", "")
                    seceret_key = safe_get_val(config_base, user, "SECRET_KEY", "")
                    passphrase = safe_get_val(config_base, user, "PASSPHRASE", "")
                    deal_token = safe_get_val(config_base, user, "deal_token", "")
                    report_token = safe_get_val(config_base, user, "report_token", "")
                    chat_id = safe_get_val(config_base, user, "chat_id", "")
                finally:
                    encrypt_f(KEY_PATH)
            key = {'api_key': api_key, 'seceret_key': seceret_key, 'passphrase': passphrase,
                   'deal_token': deal_token, 'report_token': report_token, 'chat_id': chat_id}
            keys[user] = key
        key = keys[user]
        import api.MessageAPI as messageApi
        import api.okex_sdk_v5.Trade_api as tradeApi
        import api.okex_sdk_v5.Account_api as accountApi
        import api.okex_sdk_v5.Market_api as marketApi
        import api.okex_sdk_v5.Funding_api as fundingApi
        import api.okex_sdk_v5.Earn_api as earnApi
        factories = {
            0: lambda: messageApi.MessageAPI(key['deal_token'], key['report_token'], key['chat_id']),
            1: lambda: tradeApi.TradeAPI(key['api_key'], key['seceret_key'], key['passphrase']),
            2: lambda: accountApi.AccountAPI(key['api_key'], key['seceret_key'], key['passphrase']),
            3: lambda: marketApi.MarketAPI(key['api_key'], key['seceret_key'], key['passphrase']),
            7: lambda: fundingApi.FundingAPI(key['api_key'], key['seceret_key'], key['passphrase']),
            8: lambda: earnApi.EarnAPI(key['api_key'], key['seceret_key'], key['passphrase']),
        }
        factory = factories.get(type)
        if factory is None:
            return None
        api = factory()
        apis[(user, type)] = api
        return api


def safe_get_val(config, section, option, default=''):
    try:
        return config.get(section, option)
    except Exception:
        return default


def safe_set_val(config, section, option, val):
    try:
        config.set(section, option, str(val))
    except configparser.NoSectionError:
        config.add_section(section)
        safe_set_val(config, section, option, str(val))


def get_ms():
    t = time.time()
    return int(round(t * 1000))


def write_config(file, config):
    with open(file, "w") as fp:
        config.write(fp)


def get_config_text(file):
    with open(file, "r") as fp:
        return fp.read()


def write_config_text(file, text):
    with open(file, "w") as fp:
        fp.write(text)


def write_keys(user, values):
    """以单次文件事务更新用户凭证，并同步失效关联 API 缓存"""
    if not values:
        return
    with _credential_lock:
        with exclusive_file_lock(KEY_PATH):
            decrypt_f(KEY_PATH)
            try:
                config = configparser.ConfigParser()
                config.read(KEY_PATH)
                if not config.has_section(user):
                    config.add_section(user)
                for key, value in values.items():
                    config.set(user, key, value)
                write_config(KEY_PATH, config)
            finally:
                encrypt_f(KEY_PATH)
        invalidate_user_cache(user)


def write_key(user, key, val):
    write_keys(user, {key: val})


def get_sid():
    sid = json.loads(request.data).get('sid')
    for x in sids:
        if auth_match(sid, x):
            return x
    return sid


def get_user():
    return sids.get(get_sid())['user']


def user_version():
    data = json.loads(request.data)
    sid_info = sids.get(get_sid())
    a = data.get('a')
    p = sid_info['p']
    if a is not None:
        sid_info['p'] = "rw"
    else:
        logger.warning(f"hello {sid_info.get('user')} {sid_info.get('version')}")
    if (sid_info is not None and sid_info.get('version') < get_today_ts()) or (sid_info['p'] != p):
        sid_info['version'] = get_today_ts()
        pop_sid()
        authConfig.set("sids", "data", json.dumps(sids))
        authConfig.set("masks", "data", json.dumps(masks))
        write_config(AUTH_PATH, authConfig)
    return sid_info


def require_auth(p):
    def func_wrapper(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            sid = get_sid()
            if sid is None or sids.get(sid) is None:
                logger.warning(f"@require_auth sid[{sid}] not exist!")
                return '0'
            if sids.get(sid).get('p').find(p) == -1:
                logger.warning(f"@require_auth sid[{p}] not exist!")
                return '0'
            return func(*args, **kw)

        return wrapper

    return func_wrapper


def time_cost(func):
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000
        logger.warning(f"{func.__name__} took {execution_time} ms to execute.")
        return result

    return wrapper


def get_mask_symbol(sid):
    return masks.get(sid)


def set_mask_symbol(sid, symbol):
    if symbol is None:
        if masks.get(sid):
            masks.pop(sid)
    else:
        masks[sid] = symbol
    authConfig.set("masks", "data", json.dumps(masks))
    write_config(AUTH_PATH, authConfig)


def pop_sid(user=None):
    _sid = []
    now = get_ms()
    oneday = 86400000
    for i in sids:
        if now - sids[i]['version'] > oneday * SESSION_DAYS or sids[i]['user'] == user:
            _sid.append(i)
    for sid in _sid:
        logger.warning(f"pop expired sid:{sid}")
        if masks.get(sid):
            masks.pop(sid)
        sids.pop(sid)


def get_random_id():
    return str(uuid.uuid4()).split("-")[0] + str(time.time()).split(".")[1]


def auth_match(auth, pwd):
    tt = int(time.time() / 10)
    return auth == encrypt(pwd, tt) or auth == encrypt(pwd, tt - 1) or auth == encrypt(pwd, tt - 2)


def encrypt(txt, tt):
    import base64
    exps = ["+", "-", "*"]
    seed = str(tt)
    seeds = [int(seed[8]), int(seed[7]), int(seed[6]), int(seed[5]), int(seed[4]), int(seed[3]), int(seed[2]),
             int(seed[1]), int(seed[0])]

    def calc(n1, op, n2):
        if op == "+":
            return n1 + n2
        if op == "-":
            return n1 - n2
        return n1 * n2

    calcs = []
    for i in range(max(len(seeds), len(txt))):
        code = ord(txt[i % len(txt)])
        s = seeds[i % len(seeds)]
        e = exps[i % len(exps)]
        calcs.append(calc(code, e, s))
    fna = ""
    for i in range(1, len(calcs)):
        n1 = calcs[i - 1]
        e = exps[i % len(exps)]
        n2 = calcs[i]
        fna += str(calc(n1, e, n2))
    txt_enc = str(seeds[0]) + str(seeds[3]) + str(seeds[7]) + str(seeds[4]) + str(seeds[8]) + fna + str(
        seeds[2]) + str(seeds[5]) + str(seeds[1]) + str(seeds[6])
    encoded = str(base64.b64encode(txt_enc.encode('UTF-8')), 'UTF-8')
    return encoded


def auth_user():
    data = json.loads(request.data)
    if not data['user'] or not data['auth']:
        return '0'
    user = data['user']
    auth = data['auth']
    ip = get_client_ip()

    logger.warning(f"user:{user},ip:{ip}")

    if user not in users:
        return '0'

    # Check if user or IP is locked
    failures = get_login_failures()
    user_key = f"user_{user}"
    ip_key = f"ip_{ip}"

    if is_locked(user_key, failures):
        remaining_time = int((failures[user_key]['locked_until'] - time.time()) / 60)
        logger.warning(f"{user} is locked! Remaining time: {remaining_time} minutes")
        return '0'

    if is_locked(ip_key, failures):
        remaining_time = int((failures[ip_key]['locked_until'] - time.time()) / 60)
        logger.warning(f"IP {ip} is locked! Remaining time: {remaining_time} minutes")
        return '0'

    authConfig.read(AUTH_PATH)
    try:
        auth_in = authConfig.get(user, "auth")
    except configparser.NoSectionError:
        authConfig.add_section(user)
        auth_in = ''
    if len(auth_in) == 0:
        authConfig.set(user, "auth", auth)
        write_config("auth.ini", authConfig)
    elif not auth_match(auth, auth_in):
        logger.warning(f"{user} auth failed!")
        # Record login failure
        record_login_failure(user, ip)
        return '0'

    # Successful login - reset failure count
    reset_login_failures(user)

    pop_sid(user if user in admins else None)
    _uuid = get_random_id()
    sids[_uuid] = {"user": user, "version": get_ms(), "p": "rw"}
    authConfig.set("sids", "data", json.dumps(sids))
    authConfig.set("masks", "data", json.dumps(masks))
    write_config(AUTH_PATH, authConfig)
    logger.warning(f"{user} login success")
    return _uuid


def get_contract_position_info(user, symbol):
    account_api = get_api(user, 2)
    data = account_api.get_positions("", symbol)
    if data is not None and data['data'] is not None and data['code'] == '0':
        if len(data['data']) != 0:
            volume = data["data"][0]["pos"]
            direction = data["data"][0]["posSide"]
            if direction is None or volume is None:
                raise Exception
            return int(volume), direction
        else:
            return 0, "net"
