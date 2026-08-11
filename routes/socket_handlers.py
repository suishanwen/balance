import subprocess
import threading
from select import poll, POLLIN

import gevent

from flask_socketio import join_room

from . import server_core
from .server_core import (
    MARKET_ECHO, PRICE_TMP,
    LOG_PATH, BG_LOG_PATH, ACCESS_PATH, LOG_ALIVE,
    refresh_market_snapshot,
    market_data_alive, check_market_symbol,
    is_spec_swap_symbol, get_split_swap_symbols,
    is_spec_symbol, get_split_symbols,
)
from module.Logger import logger
from util.ServerUtil import admins, auth_match, get_ms, reload_sids, sids
from util.DataUtil import get_file_key
from util.ActiveUser import keep_user_alive
from util.IM import emit_msg


def _resolve_socket_sid(sid):
    if not sid:
        return None
    if sids.get(sid) is not None:
        return sid
    reload_sids()
    if sids.get(sid) is not None:
        return sid
    for real_sid in sids:
        if auth_match(sid, real_sid):
            return real_sid
    return None


def _get_socket_user(payload):
    if isinstance(payload, dict):
        real_sid = _resolve_socket_sid(payload.get('sid'))
        if real_sid is None:
            logger.warning(f"socket auth failed user:{payload.get('user')}")
            return None
        user = sids[real_sid].get('user')
        request_user = payload.get('user')
        if request_user and request_user != user:
            logger.warning(f"socket user mismatch:{request_user}->{user}")
        return user
    return payload


def _get_socket_symbol(payload, symbol=None):
    if isinstance(payload, dict):
        return payload.get('symbol')
    return symbol


def _echo_market_data(socketio, symbol):
    check_market_symbol(symbol, True)
    logger.info(f"start {symbol} echo thread")
    while market_data_alive(symbol):
        try:
            # 四个字段取自同一份快照，避免跨快照读到不同时刻的价量
            snapshot = refresh_market_snapshot()
            bid = snapshot[symbol]["bid1"]
            ask = snapshot[symbol]["ask1"]
            if is_spec_swap_symbol(symbol):
                symbols = get_split_swap_symbols(symbol)
                ext1 = snapshot[symbols[0]]["ask1"]
                ext2 = snapshot[symbols[1]]["bid1"]
            elif is_spec_symbol(symbol):
                symbols = get_split_symbols(symbol)
                ext1 = snapshot[symbols[0]]["ask1"]
                ext2 = snapshot[symbols[1]]["bid1"]
            else:
                ext1 = snapshot[symbol]["bid1_amt"]
                ext2 = snapshot[symbol]["ask1_amt"]
        except Exception:
            gevent.sleep(0.2)
            continue
        if bid != PRICE_TMP[symbol][0] or ask != PRICE_TMP[symbol][1] or ext1 != PRICE_TMP[symbol][2] or ext2 != \
                PRICE_TMP[symbol][3]:
            socketio.emit(symbol, [bid, ask, ext1, ext2], namespace='/market')
            PRICE_TMP[symbol] = [bid, ask, ext1, ext2]
        gevent.sleep(0.2)
    check_market_symbol(symbol, False)
    logger.info(f"stop {symbol} echo thread")


def _send_log(socketio, file, user):
    cmd = f"tail -f {file}"
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    poller = poll()
    poller.register(popen.stdout, POLLIN)
    logger.info(f"start {user} log thread")
    try:
        while _is_log_alive(_get_user_log_key(user) if file == LOG_PATH else file):
            event = poller.poll(1000)
            for fd, flag in event:
                if flag:
                    line = popen.stdout.readline().strip()
                    if line:
                        data = bytes.decode(line, encoding="utf-8")
                        try:
                            if file == LOG_PATH and (data.find(f"[{user}]") != -1 or user in admins):
                                socketio.emit(f'{user}_log', data, namespace="/log")
                            elif file == BG_LOG_PATH:
                                socketio.emit(f'{user}_bg', data, namespace="/bg")
                            elif file == ACCESS_PATH:
                                socketio.emit(f'{user}_access', data, namespace="/access")
                        except Exception as e:
                            logger.warning(f"send data err:{str(e)}")
    except Exception as e:
        logger.error(f"Error in send_log: {str(e)}")
    finally:
        popen.terminate()
        popen.wait()
    if file == LOG_PATH:
        logger.info(f"stop {user} log thread")
    elif file == BG_LOG_PATH:
        logger.info(f"stop {user} bg thread")
    elif file == ACCESS_PATH:
        logger.info(f"stop {user} access thread")


def _is_log_alive(file):
    fk = get_file_key(file)
    now = get_ms()
    version = LOG_ALIVE[fk] if LOG_ALIVE.get(fk) else 0
    return now - version < 15000


def _redeem_log(file):
    LOG_ALIVE[get_file_key(file)] = get_ms()


def _get_user_log_key(user):
    return f"{user}-{LOG_PATH}"


def register_socket_handlers(socketio):

    @socketio.on('connect', namespace="/")
    @socketio.on('connect', namespace="/market")
    @socketio.on('connect', namespace="/log")
    @socketio.on('connect', namespace="/bg")
    @socketio.on('connect', namespace="/access")
    def connect():
        server_core.LIVE_SOCKET += 1
        logger.info(f"socket connect,LIVE({server_core.LIVE_SOCKET})")

    @socketio.on('disconnect', namespace="/")
    @socketio.on('disconnect', namespace="/market")
    @socketio.on('disconnect', namespace="/log")
    @socketio.on('disconnect', namespace="/bg")
    @socketio.on('disconnect', namespace="/access")
    def disconnect():
        server_core.LIVE_SOCKET -= 1
        logger.info(f"socket disconnect,LIVE({server_core.LIVE_SOCKET})")

    @socketio.on('market', namespace="/market")
    def echo_market(payload, symbol=None):
        user = _get_socket_user(payload)
        symbol = _get_socket_symbol(payload, symbol)
        if not user or not symbol:
            return
        join_room(user)
        emit_msg(socketio, user, symbol)
        if MARKET_ECHO.get(symbol) is None:
            MARKET_ECHO[symbol] = 0
        alive = market_data_alive(symbol)
        MARKET_ECHO[symbol] = get_ms()
        keep_user_alive(user)
        if PRICE_TMP.get(symbol) is None:
            PRICE_TMP[symbol] = [0, 0, 0, 0]
        if not alive:
            threading.Thread(target=_echo_market_data, args=(socketio, symbol,)).start()
        return PRICE_TMP[symbol]

    @socketio.on('log', namespace='/log')
    def echo_log(payload):
        user = _get_socket_user(payload)
        if not user:
            return
        user_log_path = _get_user_log_key(user)
        if not _is_log_alive(user_log_path):
            threading.Thread(target=_send_log, args=(socketio, LOG_PATH, user)).start()
        _redeem_log(user_log_path)

    @socketio.on('bg', namespace='/bg')
    def echo_bg(payload):
        user = _get_socket_user(payload)
        if not user:
            return
        if not _is_log_alive(BG_LOG_PATH):
            logger.info(f"start {user} bg thread")
            threading.Thread(target=_send_log, args=(socketio, BG_LOG_PATH, user)).start()
        _redeem_log(BG_LOG_PATH)

    @socketio.on('access', namespace='/access')
    def echo_access(payload):
        user = _get_socket_user(payload)
        if not user:
            return
        if not _is_log_alive(ACCESS_PATH):
            logger.info(f"start {user} access thread")
            threading.Thread(target=_send_log, args=(socketio, ACCESS_PATH, user)).start()
        _redeem_log(ACCESS_PATH)
