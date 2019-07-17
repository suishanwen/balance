import datetime
import time
import configparser
import json
import pytz
from util.Logger import logger

# read config
config = configparser.ConfigParser()
config.read("config.ini")


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


def get_day_bj():
    return int(datetime.datetime.fromtimestamp(int(time.time()), pytz.timezone('Asia/Shanghai')).strftime('%d'))


def write_log(text=""):
    with open('log.txt') as f:
        s = f.read()
    mm = str(from_time_stamp())[0:7]
    if s.find(mm) != -1:
        with open(r'log.txt', 'w') as f:
            f.write(text + "\n" + s)
    else:
        with open(r'log.txt', 'a') as f:
            f.writelines("\n")
        # write old logs
        with open(str(from_time_stamp(int(time.time()) - 86400 * 10))[0:7] + '.txt', 'w') as old_f:
            with open('log.txt') as f:
                old_f.writelines(f.readlines()[::-1])
            # write count
            config.read("config.ini")
            symbols = json.loads(config.get("trade", "symbol"))
            for symbol in symbols:
                cfg_field = symbol + "-stat"
                sum_count = 0
                try:
                    sum_count = sum(json.loads(config.get(cfg_field, "count")))
                except Exception as err:
                    logger.error("Error: write_log,{}".format(err))
                old_f.writelines(symbol + " [" + str(sum_count) + "]")
        with open(r'log.txt', 'w') as f:
            f.write(text)
