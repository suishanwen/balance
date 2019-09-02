from module.CfEnv import config
import tokens.Token as Token
import api.HuobiProClient as Client
import json
import threading

if __name__ == '__main__':
    symbols = json.loads(config.get("trade", "symbol"))
    if len(symbols) > 1:
        for symbol in symbols:
            threading.Thread(target=Token.__main__, args=(Client.HuobiProClient(), symbol,)).start()
    else:
        Token.__main__(Client.HuobiProClient(), symbols[0])
