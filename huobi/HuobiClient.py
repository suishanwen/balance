import os
import sys
import importlib
from pathlib import Path

project_path = str(Path(os.getcwd()).parent)

sys.path.append(project_path)

importlib.reload(sys)
import tokens.Token as Token
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
        threading.Thread(target=Token.__main__, args=(Client.HuobiProClient(), symbol,)).start()
