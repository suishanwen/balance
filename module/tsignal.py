import copy
import json
import os
import signal
import sys

import gevent
from gevent.signal import signal as gevent_signal
from trader.app.bootstrap import start
from module.CfEnv import get_marker_user_path
from module.Logger import logger


def set_user_signal(mclient, clients):
    gevent_signal(signal.SIGUSR1, create_signal_handler(mclient, clients))


def create_signal_handler(mclient, clients):
    def signal_handler(sig, frame):
        logger.warning(f"signal_handler {sig}")
        market_config = mclient.config
        if sig == signal.SIGUSR1:
            market_config.read(get_marker_user_path())
            op = market_config.get("signal", "op")
            user = market_config.get("signal", "user")
            logger.warning(f"signal_handler op={op}, user={user}")
            if op == "restart":
                user_clients = list(filter(lambda client: client.user == user, clients))
                if len(user_clients) > 0:
                    for user_client in user_clients:
                        user_client.stop = True
                        clients.remove(user_client)
                        user_client = copy.deepcopy(user_client)
                        clients.append(user_client)
                        gevent.spawn(start, user_client, )
                else:
                    logger.warning("***system restart***")
                    python = sys.executable
                    os.execl(python, python, *sys.argv)
            elif op == "set_symbols":
                mclient.symbols = json.loads(market_config.get("trade", "symbol"))

    logger.warning("create_signal_handler succeed!")
    return signal_handler
