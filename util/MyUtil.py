import configparser
import datetime
import time

import pytz

from codegen.generator import decrypt_f, encrypt_f, exclusive_file_lock
from module.CfEnv import get_log_path, KEY_PATH

log_path = get_log_path()


def has_attr(_dict, args):
    return args in _dict.keys()


def from_dict(_dict, *args):
    for a in args:
        _dict = _dict[a]
    return _dict


def from_time_stamp(seconds=0):
    # remark: int(time.time()) 不能放到参数默认值，否则会初始化为常量
    if seconds == 0:
        seconds = int(time.time())
    return datetime.datetime.fromtimestamp(seconds, pytz.timezone('Asia/Shanghai')).strftime(
        '%Y-%m-%d %H:%M:%S')


def get_ms():
    t = time.time()
    return int(round(t * 1000))


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
        safe_set_val(config, section, option, val)


def write_config(file, config):
    with open(file, "w") as fp:
        config.write(fp)


def get_day_bj():
    return int(datetime.datetime.fromtimestamp(int(time.time()), pytz.timezone('Asia/Shanghai')).strftime('%d'))


def write_log(text=""):
    try:
        with open(log_path) as f:
            s = f.read()
    except FileNotFoundError:
        s = ""
    mm = str(from_time_stamp())[0:7]
    if s == "" or s.find(mm) != -1:
        with open(log_path, 'w') as f:
            f.write(text + "\n" + s)
    else:
        with open(log_path, 'a') as f:
            f.writelines("\n")
        # write old logs
        with open(str(from_time_stamp(int(time.time()) - 86400 * 10))[0:7] + '.txt', 'w') as old_f:
            with open(log_path) as f:
                old_f.writelines(f.readlines()[::-1])
        with open(log_path, 'w') as f:
            f.write(text)


def user_killed(user):
    with exclusive_file_lock(KEY_PATH):
        decrypt_f(KEY_PATH)
        try:
            config = configparser.ConfigParser()
            config.read(KEY_PATH)
            config.set(user, 'enable', "0")
            with open(KEY_PATH, "w") as fp:
                config.write(fp)
        finally:
            encrypt_f(KEY_PATH)
