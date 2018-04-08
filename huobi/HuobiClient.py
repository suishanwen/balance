import sys
import importlib

sys.path.append("/home/balance")
importlib.reload(sys)
import tokens.Token as Token
import api.HuobiProClient as Client

if __name__ == '__main__':
    Token.__main__(Client.HuobiProClient(), Client.HuobiProClient.SYMBOL_HT)
