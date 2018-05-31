import sys
import importlib

sys.path.append("/home/balance")
importlib.reload(sys)
import tokens.Token as Token1
import tokens.Token2 as Token2
import api.OkexClient as Client
import configparser

# read config
config = configparser.ConfigParser()
config.read("config.ini")

Token = Token1

symbol = config.get("trade", "symbol")
_type = config.get(symbol, "type")
if _type == 'transaction':
    Token = Token2

if __name__ == '__main__':
    Token.__main__(Client.OkexClient(), symbol)
