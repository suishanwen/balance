from module.CfEnv import config, configBase
import tokens.Token as Token
import api.OkexClientV3 as Client
import json
import threading

# init apikey,secretkey,passphrase
api_key = configBase.get("okex-v3", "API_KEY")
seceret_key = configBase.get("okex-v3", "SECRET_KEY")
passphrase = configBase.get("okex-v3", "PASSPHRASE")

if __name__ == '__main__':
    symbols = json.loads(config.get("trade", "symbol"))
    if len(symbols) > 1:
        for symbol in symbols:
            threading.Thread(target=Token.__main__,
                             args=(Client.OkexClient(api_key, seceret_key, passphrase), symbol,)).start()
    else:
        Token.__main__(Client.OkexClient(api_key, seceret_key, passphrase), symbols[0])
