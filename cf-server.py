import functools
import subprocess
import uuid
import configparser
import json
import time
import datetime
import pytz
import os

from api.okex_sdk_v3.account_api import AccountAPI
from api.okex_sdk_v3.spot_api import SpotAPI
from api.Result import Result
from module.Logger import logger
from codegen.generator import decrypt_f, encrypt_f
from file_read_backwards import FileReadBackwards
EOS_LOG_FILE = "../eos-miner/nohup.out"

# read config
config = configparser.ConfigParser()

CONFIG_FILE = "ok/config.ini"
LOG_FILE = "ok/log.txt"
RUNNING_LOG_FILE = "ok/nohup.out"

accounts_init = {}
try:
    for _, _, files in os.walk("keys"):
        files.sort(key=lambda x: int(x.split("-")[0]))
        for file_name in files:
            decrypt_f(f"keys/{file_name}")
            _config = configparser.ConfigParser()
            _config.read("keys/" + file_name)
            apikey = _config.get("info", "apikey")
            secretkey = _config.get("info", "secretkey")
            passphrase = _config.get("info", "passphrase")
            trxpass = _config.get("info", "trxpass")
            accounts_init[file_name] = (apikey, secretkey, passphrase, trxpass)
            encrypt_f(f"keys/{file_name}")
except FileNotFoundError:
    logger.warning("keys not found")


def read_config():
    config.clear()
    config.read(CONFIG_FILE)


def write_config():
    with open(CONFIG_FILE, "w") as fp:
        config.write(fp)


def get_config_text():
    with open(CONFIG_FILE, "r") as fp:
        return fp.read()


def write_config_text(text):
    with open(CONFIG_FILE, "w") as fp:
        fp.write(text)


def get_log(file):
    with FileReadBackwards(file, encoding="utf-8") as frb:
        lines = []
        while len(lines) < 1000:
            line = frb.readline()
            if not line:
                break
            lines.append(line)
    return "<br/>".join(lines)


def get_option_val(section, option):
    val = None
    try:
        val = config.get(section, option)
    except configparser.NoSectionError or configparser.NoOptionError as e:
        logger.error(str(e))
    return val


def generate_auth():
    with open(r'auth', 'w') as f:
        auth_code = str(uuid.uuid1()).split("-")[0]
        f.write(auth_code)
        return auth_code


def auth_fail(_, start_response):
    with open('app/info.html', 'r', encoding="utf-8") as fp:
        logger.warning("授权码验证失败,点击重试")
        start_response('200 OK', [('Content-type', 'text/html')])
        yield fp.read().format(code="406 Forbidden", msg="授权码验证失败,点击重试！").encode('utf-8')


def require_auth(func):
    @functools.wraps(func)
    def wrapper(*args, **kw):
        environ = args[0]
        logger.info("require_auth")
        cookies = environ.get('HTTP_COOKIE')
        if cookies is None:
            return auth_fail(*args)
        index1 = cookies.find("code=") + 5
        index2 = cookies.find(";")
        if index2 < index1:
            index2 = len(cookies)
        auth_code_in = cookies[index1:index2].strip()
        with open(r'auth', 'r') as f:
            auth_code = f.read().strip()
            if auth_code != auth_code_in:
                return auth_fail(*args)
        return func(*args, **kw)

    return wrapper


def hello(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    try:
        with open(r'auth', 'r'):
            with open('app/hello.html', 'r', encoding="utf-8") as fp:
                yield fp.read().encode('utf-8')
    except FileNotFoundError:
        with open('app/info.html', 'r', encoding="utf-8") as fp:
            yield fp.read().format(code=generate_auth(), msg="记住授权码并点击开始验证").encode('utf-8')


def auth(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/auth.html', 'r', encoding="utf-8") as fp:
        yield fp.read().encode('utf-8')


@require_auth
def cfg(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    read_config()
    symbols = get_option_val("trade", "symbol")
    build_html = ""
    for symbol in json.loads(symbols):
        build_html += "<div>"
        build_html += "<div>[{}]</div>".format(symbol)
        options = config.options(symbol)
        for option in options:
            val = get_option_val(symbol, option)
            build_html += "<div id='{}_{}'>{} = <a style='cursor:pointer;' onclick='modify(\"{}\",\"{}\")'>{}" \
                          "</a></div>".format(symbol, option, option, symbol, option, val)
        build_html += "</div>"
        build_html += "<br/>"
        build_html += "<div>"
        build_html += "<div>[{}-stat]</div>".format(symbol)
        try:
            options = config.options("{}-stat".format(symbol))
            for option in options:
                val = get_option_val("{}-stat".format(symbol), option)
                build_html += "<div id='{}_{}'>{} = <a style='cursor:pointer;' onclick='modify(\"{}\",\"{}\")'>{}" \
                              "</a></div>".format(symbol + "-stat", option, option, symbol + "-stat", option, val)
        except Exception as e:
            logger.warning(str(e))
        build_html += "</div><hr/>"
    with open('app/config.html', 'r', encoding="utf-8") as fp:
        yield fp.read().replace("#tbd", build_html).encode('utf-8')


@require_auth
def edit(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/edit.html', 'r', encoding="utf-8") as fp:
        yield fp.read().replace("#config", get_config_text()).encode('utf-8')


@require_auth
def save(environ, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    params = environ['params']
    write_config_text(params.get("data"))
    yield "ok".encode('utf-8')


def calc_avg_price(section):
    transaction = float(get_option_val(section, "transaction"))
    amount = float(get_option_val(section, "amount"))
    if amount != 0:
        avg_price = abs(round(transaction / amount, 4))
        if transaction > 0 and amount > 0:
            avg_price = -avg_price
        config.set(section, "avgprice", str(avg_price))


@require_auth
def modify_val(environ, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    params = environ['params']
    read_config()
    section = params.get('section')
    option = params.get('option')
    val = params.get('val')
    _type = params.get('type')
    if section and option and val:
        if _type == "plus" or _type == "minus":
            old_val = config.get(section, option)
            is_count = section.find("stat") != -1 and option == "count"
            dd = 0
            arr = []
            if is_count:
                dd = int(datetime.datetime.fromtimestamp(int(time.time()), pytz.timezone('Asia/Shanghai')).strftime(
                    '%Y-%m-%d %H:%M:%S')[8:10])
                arr = json.loads(old_val)
                if len(arr) == dd:
                    old_val = arr[dd - 1]
                else:
                    old_val = 0
            if _type == "plus":
                val = round(float(old_val) + float(val), 4)
            elif _type == "minus":
                val = round(float(old_val) - float(val), 4)
            if is_count:
                if len(arr) < dd:
                    diff = dd - len(arr)
                    for i in range(0, diff):
                        arr.append(0)
                elif len(arr) > dd:
                    arr = []
                    for i in range(0, dd):
                        arr.append(0)
                arr[dd - 1] = round(val, 3)
                val = json.dumps(arr)
        config.set(section, option, str(val))
        if section.find("stat") != -1 and (option == "transaction" or option == "amount"):
            calc_avg_price(section)
        write_config()
    yield "ok".encode('utf-8')


@require_auth
def pull(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    cmd = """cd /home/balance
rm -rf tokens/Token.py
git checkout tokens/Token.py
git pull
ps -ef | grep cf-server.py | grep -v grep | awk '{print $2}' | xargs kill -9
cat /dev/null > /home/balance/cfg.out
nohup python3 cf-server.py>/home/balance/cfg.out 2>&1 &"""
    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    yield "ok".encode('utf-8')


@require_auth
def restart(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    cmd = """echo '----- pull code -----'
cd /home/balance
rm -rf tokens/Token.py
git checkout tokens/Token.py
git pull
cd codegen
python3 dec.py
echo '----- kill okclient -----'
ps -ef | grep OKClient.py | grep -v grep | awk '{print $2}' | xargs kill -9
echo '----- start okclient -----'
cd /home/balance/ok
cat /dev/null > nohup.out
nohup python3 OKClient.py>/home/balance/ok/nohup.out 2>&1 &"""
    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    yield "ok".encode('utf-8')


@require_auth
def shutdown(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    cmd = """ps -ef | grep OKClient.py | grep -v grep | awk '{print $2}' | xargs kill -9
"""
    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    yield "ok".encode('utf-8')


@require_auth
def log(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/log.html', 'r', encoding="utf-8") as fp:
        yield fp.read().format(text=get_log(LOG_FILE)).encode('utf-8')


@require_auth
def running_log(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/log.html', 'r', encoding="utf-8") as fp:
        yield fp.read().format(text=get_log(RUNNING_LOG_FILE)).encode('utf-8')

@require_auth
def eos_log(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/log.html', 'r', encoding="utf-8") as fp:
        yield fp.read().format(text=get_log(EOS_LOG_FILE)).encode('utf-8')

@require_auth
def accounts(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    account_list = []
    for name in accounts_init:
        account_list.append(name)
    yield json.dumps(account_list).encode('utf-8')


@require_auth
def control(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/control.html', 'r', encoding="utf-8") as fp:
        yield fp.read().encode('utf-8')


@require_auth
def transfer(environ, start_response):
    start_response('200 OK', [('Content-type', 'application/json')])
    params = environ['params']
    _type = params["type"].split("-")
    account = params["account"]
    symbol = params["symbol"]
    amount = params.get("amount")
    key_list = []
    if account == "0":
        for name in accounts_init:
            key_list.append(accounts_init[name])
    else:
        key_list.append(accounts_init[account])
    success = 0
    msg_list = []
    for key in key_list:
        status, msg = transfer_one(key, symbol, amount, _type[0], _type[1])
        success += status
        msg_list.append(msg)
    if success == len(key_list):
        yield Result(True, "ok").response()
    else:
        yield Result(False, "总共:{},成功:{}\n{}".format(len(key_list), success, '\n'.join(msg_list))).response()


def transfer_one(key, symbol, amount, _from, _to):
    account_api = AccountAPI(key[0], key[1], key[2])
    try:
        if not amount:
            if _from == "6":
                amount = get_account_currency(symbol, key)[0]["available"]
            else:
                amount = get_spot_currency(symbol, key)["available"]
        account_api.coin_transfer(symbol, float(amount), int(_from), int(_to))
        return 1, "ok"
    except Exception as e:
        logger.error(str(e))
        return 0, str(e)


@require_auth
def get_currency(environ, start_response):
    start_response('200 OK', [('Content-type', 'application/json')])
    params = environ['params']
    symbol = params["symbol"]
    key = accounts_init[params["account"]]
    try:
        yield Result(True, "", {"fund": get_account_currency(symbol, key),
                                "coin": get_spot_currency(symbol, key)}).response()
    except Exception as e:
        logger.error(str(e))
        yield Result(False, str(e)).response()


def get_account_currency(symbol, key):
    account_api = AccountAPI(key[0], key[1], key[2])
    return account_api.get_currency(symbol)


def get_spot_currency(symbol, key):
    spot_api = SpotAPI(key[0], key[1], key[2])
    return spot_api.get_coin_account_info(symbol)


@require_auth
def withdraw(environ, start_response):
    start_response('200 OK', [('Content-type', 'application/json')])
    params = environ['params']
    account = params["account"]
    symbol = params["symbol"]
    amount = params.get("amount")
    to_address = params.get("toAddress")
    key_list = []
    if account == "0":
        for name in accounts_init:
            key_list.append(accounts_init[name])
    else:
        key_list.append(accounts_init[account])
    success = 0
    msg_list = []
    for key in key_list:
        status, msg = withdraw_one(key, symbol, amount, to_address)
        success += status
        msg_list.append(msg)
    if success == len(key_list):
        yield Result(True, "ok").response()
    else:
        yield Result(False, "总共:{},成功:{}\n{}".format(len(key_list), success, '\n'.join(msg_list))).response()


def withdraw_one(key, symbol, amount, to_address):
    account_api = AccountAPI(key[0], key[1], key[2])
    try:
        if not amount:
            amount = get_account_currency(symbol, key)[0]["available"]
        account_api.coin_withdraw(symbol, float(amount), 3, to_address, key[3], 0)
        return 1, "ok"
    except Exception as e:
        logger.error(str(e))
        return 0, str(e)


@require_auth
def order(environ, start_response):
    start_response('200 OK', [('Content-type', 'application/json')])
    params = environ['params']
    account = params["account"]
    symbol = params["symbol"]
    order_type = params.get("orderType")
    price = params.get("price")
    amount = params.get("amount")
    key_list = []
    if account == "0":
        for name in accounts_init:
            key_list.append(accounts_init[name])
    else:
        key_list.append(accounts_init[account])
    success = 0
    msg_list = []
    for key in key_list:
        status, msg = order_one(key, order_type, symbol, price, amount)
        success += status
        msg_list.append(msg)
    if success == len(key_list):
        yield Result(True, "ok").response()
    else:
        yield Result(False, "总共:{},成功:{}\n{}".format(len(key_list), success, '\n'.join(msg_list))).response()


def order_one(key, order_type, symbol, price, amount):
    spot_api = SpotAPI(key[0], key[1], key[2])
    try:
        if not amount:
            amount = get_spot_currency(symbol.split("_"[0]), key)["available"]
        result = spot_api.take_order(order_type, symbol, 2, price, amount)
        if result is not None and result.get('result'):
            return 1, result['order_id']
        else:
            return 0, "下单未成功"

    except Exception as e:
        logger.error(str(e))
        return 0, str(e)


if __name__ == '__main__':
    from module.Resty import PathDispatcher
    from wsgiref.simple_server import make_server

    # Create the dispatcher and register functions
    dispatcher = PathDispatcher()
    dispatcher.register('GET', '/', hello)
    dispatcher.register('GET', '/auth', auth)
    dispatcher.register('GET', '/pull', pull)
    dispatcher.register('GET', '/cfg', cfg)
    dispatcher.register('GET', '/edit', edit)
    dispatcher.register('POST', '/save', save)
    dispatcher.register('GET', '/modify', modify_val)
    dispatcher.register('GET', '/restart', restart)
    dispatcher.register('GET', '/shutdown', shutdown)
    dispatcher.register('GET', '/log', log)
    dispatcher.register('GET', '/log-run', running_log)
    dispatcher.register('GET', '/log-eos', eos_log)
    dispatcher.register('GET', '/control', control)
    dispatcher.register('POST', '/accounts', accounts)
    dispatcher.register('POST', '/transfer', transfer)
    dispatcher.register('POST', '/get_currency', get_currency)
    dispatcher.register('POST', '/withdraw', withdraw)
    dispatcher.register('POST', '/order', order)

    # Launch a basic server
    httpd = make_server('', 7777, dispatcher)
    logger.info('Serving on port 7777...')
    httpd.serve_forever()
