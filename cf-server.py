import subprocess
import uuid
import configparser
import json
from util.Logger import logger

# read config
config = configparser.ConfigParser()


def read_config():
    config.read("ok/config.ini")


def write_config():
    with open("ok/config.ini", "w") as fp:
        config.write(fp)


def get_log():
    with open('ok/log.txt') as fp:
        return fp.read().replace("\n", "<br/>")


def get_option_val(section, option):
    val = None
    try:
        val = config.get(section, option)
    except configparser.NoSectionError or configparser.NoOptionError as e:
        logger.error(str(e))
    return val


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


def cfg(environ, start_response):
    auth_code_in = environ['HTTP_COOKIE'][environ['HTTP_COOKIE'].index("code=") + 5:len(environ['HTTP_COOKIE'])]
    with open(r'auth', 'r') as f:
        auth_code = f.read()
        start_response('200 OK', [('Content-type', 'text/html')])
        if auth_code == auth_code_in:
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
                options = config.options("{}-stat".format(symbol))
                for option in options:
                    val = get_option_val("{}-stat".format(symbol), option)
                    build_html += "<div>{} = {}</div>".format(option, val)
                build_html += "</div><hr/>"
            with open('app/config.html', 'r', encoding="utf-8") as fp:
                yield fp.read().replace("#tbd", build_html).encode('utf-8')
        else:
            with open('app/info.html', 'r', encoding="utf-8") as fp:
                yield fp.read().format(code="406 Forbidden", msg="授权码验证失败,点击重试！").encode('utf-8')


def generate_auth():
    with open(r'auth', 'w') as f:
        auth_code = str(uuid.uuid1()).split("-")[0]
        f.write(auth_code)
        return auth_code


def modify_val(environ, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    params = environ['params']
    read_config()
    section = params.get('section')
    option = params.get('option')
    val = params.get('val')
    if section and option:
        config.set(section, option, val)
        write_config()
    yield "ok".encode('utf-8')


def restart(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    cmd = """echo '----- pull code -----'
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


def shutdown(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    cmd = """ps -ef | grep OKClient.py | grep -v grep | awk '{print $2}' | xargs kill -9
"""
    subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    yield "ok".encode('utf-8')


def log(_, start_response):
    start_response('200 OK', [('Content-type', 'text/html')])
    with open('app/log.html', 'r', encoding="utf-8") as fp:
        yield fp.read().format(text=get_log()).encode('utf-8')


if __name__ == '__main__':
    from util.Resty import PathDispatcher
    from wsgiref.simple_server import make_server

    # Create the dispatcher and register functions
    dispatcher = PathDispatcher()
    dispatcher.register('GET', '/', hello)
    dispatcher.register('GET', '/auth', auth)
    dispatcher.register('GET', '/cfg', cfg)
    dispatcher.register('GET', '/modify', modify_val)
    dispatcher.register('GET', '/restart', restart)
    dispatcher.register('GET', '/shutdown', shutdown)
    dispatcher.register('GET', '/log', log)

    # Launch a basic server
    httpd = make_server('', 7777, dispatcher)
    logger.info('Serving on port 7777...')
    httpd.serve_forever()
