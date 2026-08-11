from module.Logger import logger
from api.OrderInfo import MyOrderInfo


def get_latest_order(symbol, user):
    latest_order = None
    try:
        with open(r'log.txt') as f:
            line = f.readline()
            while line and line.find("canceled") == -1:
                order = MyOrderInfo()
                order.from_log(line)
                if order.symbol == symbol and line.find(f"[{user}]") != -1:
                    latest_order = order
                    break
                line = f.readline()
    except FileNotFoundError:
        logger.info("LogNotFound!")
    return latest_order
