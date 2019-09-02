import os
import configparser
from pathlib import Path
from codegen.generator import decrypt_f, encrypt_f

START_PATH = str(Path(os.getcwd()))
PROJECT_PATH = str(Path(os.getcwd()).parent)

KEY_PATH = f"{PROJECT_PATH}/key.ini"
SUB_KEY_PATH = f"{PROJECT_PATH}/keys"

TOKEN_PY_PATH = f"{PROJECT_PATH}/tokens/Token.py"

OK_PATH = f"{PROJECT_PATH}/ok"
OK_CF_PATH = f"{PROJECT_PATH}/ok/config.ini"
OK_LOG_PATH = f"{PROJECT_PATH}/ok/log.txt"

HB_PATH = f"{PROJECT_PATH}/huobi"
HB_CF_PATH = f"{PROJECT_PATH}/huobi/config.ini"
HB_LOG_PATH = f"{PROJECT_PATH}/huobi/log.txt"


def get_cf_path():
    return OK_CF_PATH if START_PATH == OK_PATH else HB_CF_PATH


def get_log_path():
    return OK_LOG_PATH if START_PATH == OK_PATH else HB_LOG_PATH


decrypt_f(KEY_PATH)
configBase = configparser.ConfigParser()
configBase.read(KEY_PATH)
encrypt_f(KEY_PATH)

config = configparser.ConfigParser()
config.read(get_cf_path())
