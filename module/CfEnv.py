import configparser
import os
from pathlib import Path

from codegen.generator import decrypt_f, encrypt_f, exclusive_file_lock

START_PATH = str(Path(os.getcwd()))
PROJECT_PATH = str(Path(os.getcwd()).parent)

MARKET_PATH = f"{PROJECT_PATH}/market.ini"
KEY_PATH = f"{PROJECT_PATH}/key.ini"
SUB_KEY_PATH = f"{PROJECT_PATH}/keys"


OK_PATH = f"{PROJECT_PATH}/ok"
HB_PATH = f"{PROJECT_PATH}/huobi"

OK_LOG_PATH = f"{PROJECT_PATH}/ok/log.txt"
HB_LOG_PATH = f"{PROJECT_PATH}/huobi/log.txt"


def get_marker_user_path():
    return f"{get_path()}/market.ini"


def get_path():
    return OK_PATH if START_PATH == OK_PATH else HB_PATH


def get_log_path():
    return OK_LOG_PATH if START_PATH == OK_PATH else HB_LOG_PATH


with exclusive_file_lock(KEY_PATH):
    decrypt_f(KEY_PATH)
    try:
        configBase = configparser.ConfigParser()
        configBase.read(KEY_PATH)
    finally:
        encrypt_f(KEY_PATH)


class TradeType:
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    SWAP = "SWAP"
