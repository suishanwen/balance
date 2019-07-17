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
from util.Logger import logger
from codegen.generator import write

# read config
config = configparser.ConfigParser()

CONFIG_FILE = "ok/config.ini"
LOG_FILE = "ok/log.txt"
RUNNING_LOG_FILE = "ok/nohup.out"

accounts_init = {}
try:
    for _, _, files in os.walk("keys"):
        files.sort()
        for file_name in files:
            write("dec", "keys/" + file_name)
            _config = configparser.ConfigParser()
            _config.read("keys/" + file_name)
            apikey = _config.get("info", "apikey")
            secretkey = _config.get("info", "secretkey")
            passphrase = _config.get("info", "passphrase")
            accounts_init[file_name] = (apikey, secretkey, passphrase)
            write("encode", "keys/" + file_name)
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
    with open(file) as fp:
        return fp.read().replace("\n", "<br/>")


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
cat /dev/null > nohup.out
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
def accounts(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    account_list = []
    for key in accounts_init:
        account_list.append(key)
    yield json.dumps(account_list).encode('utf-8')


@require_auth
def control(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/control.html', 'r', encoding="utf-8") as fp:
        yield fp.read().encode('utf-8')


@require_auth
def transfer(environ, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    params = environ['params']
    _type = params["type"].split("-")
    key_list = []
    if params["account"] == "0":
        for name in accounts_init:
            key_list.append(accounts_init[name])
    else:
        key_list.append(accounts_init[params["account"]])
    success = 0
    for key in key_list:
        success += transfer_one(key, params["symbol"], params["amount"], _type[0], _type[1])
    if success == len(key_list):
        yield "ok".encode('utf-8')
    else:
        yield "总共:{},成功:{}".format(len(key_list), success).encode('utf-8')


def transfer_one(key, symbol, amount, _from, _to):
    account_api = AccountAPI(key[0], key[1], key[2])
    try:
        account_api.coin_transfer(symbol, amount, _from, _to)
        return 1
    except Exception as e:
        logger.error(str(e))
        return 0


if __name__ == '__main__':
    from util.Resty import PathDispatcher
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
    dispatcher.register('GET', '/control', control)
    dispatcher.register('POST', '/accounts', accounts)
    dispatcher.register('POST', '/transfer', transfer)
    # dispatcher.register('POST', '/order', order)
    # dispatcher.register('POST', '/withdraw', withdraw)

    # Launch a basic server
    httpd = make_server('', 7777, dispatcher)
    logger.info('Serving on port 7777...')
    httpd.serve_forever()
