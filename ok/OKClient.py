import sys
import importlib

sys.path.append("/home/balance")
importlib.reload(sys)
import tokens.Token as Token
import api.OkexClient as Client
import configparser
import json
import threading

# read config
config = configparser.ConfigParser()
config.read("config.ini")

if __name__ == '__main__':
    symbols = json.loads(config.get("trade", "symbol"))
    for symbol in symbols:
        threading.Thread(target=Token.__main__, args=(Client.OkexClient(), symbol,)).start()
