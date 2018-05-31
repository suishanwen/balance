import sys
import importlib

sys.path.append("/home/balance")
importlib.reload(sys)
import tokens.Token as Token1
import tokens.Token2 as Token2
import api.HuobiProClient as Client
import configparser
import json
import threading

# read config
config = configparser.ConfigParser()
config.read("config.ini")

if __name__ == '__main__':
    symbols = json.loads(config.get("trade", "symbol"))
    for symbol in symbols:
        _type = config.get(symbol, "type")
        if _type == 'transaction':
            threading.Thread(target=Token2.__main__, args=(Client.HuobiProClient(), symbol,)).start()
        else:
            threading.Thread(target=Token1.__main__, args=(Client.HuobiProClient(), symbol,)).start()
