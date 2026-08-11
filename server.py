import gzip
import logging
import os
import threading

import gevent
from engineio.payload import Payload
from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO

from routes.server_core import coin
from task import start_job
from routes.backtest import backtest_bp
from routes.config import config_bp
from routes.history import history_bp
from routes.trading import trading_bp
from routes.socket_handlers import register_socket_handlers
from routes.fish_job import do_job
from module.Logger import logger

logger.setLevel(logging.WARNING)
# OKEx REST 是阻塞调用，经 hub 线程池卸载执行，默认 10 个槽位不足以容纳
# 一次页面刷新（/history + /orders + /count）同时发出的请求，超出部分会排队
gevent.get_hub().threadpool.maxsize = 32
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
CORS(app, supports_credentials=True)
Payload.max_decode_packets = 5000
socketio = SocketIO(app, cors_allowed_origins='*', logger=False, engineio_logger=False,
                    ping_timeout=5, ping_interval=5, async_handlers=True, async_mode="gevent")

app.register_blueprint(backtest_bp)
app.register_blueprint(config_bp)
app.register_blueprint(history_bp)
app.register_blueprint(trading_bp)
register_socket_handlers(socketio)

_GZIP_MIN_SIZE = 1024


@app.after_request
def compress_month_history_response(response):
    accept_encoding = request.headers.get('Accept-Encoding', '')
    if (request.path != '/month-history'
            or 'gzip' not in accept_encoding.lower()
            or response.direct_passthrough
            or response.status_code < 200
            or response.status_code >= 300
            or 'Content-Encoding' in response.headers):
        return response
    body = response.get_data()
    if len(body) < _GZIP_MIN_SIZE:
        return response
    response.set_data(gzip.compress(body, 9))
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(response.get_data())
    response.headers.add('Vary', 'Accept-Encoding')
    return response


@app.route('/test', methods=['get'])
def test():
    return "1"


if __name__ == '__main__':
    threading.Thread(target=do_job, args=(coin,)).start()
    threading.Thread(target=start_job, args=()).start()
    socketio.run(app, host='0.0.0.0', port=5555, debug=False, log_output=False)
