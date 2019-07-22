import os
import sys
import importlib

from pathlib import Path

project_path = str(Path(os.getcwd()).parent)

sys.path.append(project_path)

importlib.reload(sys)
import tokens.Token as Token
import api.OkexClientV3 as Client
import configparser
import json
import threading
from codegen.generator import write

# read config
config = configparser.ConfigParser()
config.read("config.ini")
# read key
write("dec", '../key.ini')
configBase = configparser.ConfigParser()
configBase.read("../key.ini")
write("enc", '../key.ini')

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
