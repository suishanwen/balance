import math
from util.FibUtil import find_closest_fib_position


def get_next_buy_sell_info(client):
    client.ratePB = client.ratePS = client.rateP
    if client.martin == 1:
        from .statistics import get_statistics
        amount, transaction, price, avg_price, count = get_statistics(client)
        atn = abs(transaction)
        btn = client.amount * 10
        multiple = atn / btn
        client.power = max(find_closest_fib_position(multiple) - 1, 0)
        client.ratePB = client.ratePS = client.rateP = 1 + (client.percentage * 0.01) * pow(client.mpower, client.power)
        cr = 1
        if transaction < 0:
            client.ratePB = 1 + (client.percentage * 0.01) * pow(client.mpower, client.power)
            client.ratePS = (avg_price * (1 + (client.percentage * cr * 0.01))) / client.currentBase
        elif transaction > 0:
            client.ratePB = client.currentBase / (avg_price / (1 + (client.percentage * cr * 0.01)))
            client.ratePS = 1 + (client.percentage * 0.01) * pow(client.mpower, client.power)
    client.buyRate = client.sellRate = 1
    _next_buy_price = round(client.currentBase / pow(client.ratePB, client.buyRate), client.ACCURACY)
    _next_sell_price = round(client.currentBase * pow(client.ratePS, client.sellRate), client.ACCURACY)
    if client.mode == "transaction":
        next_buy_val = client.transaction * client.buyRate
        if client.currentBase < client.earnCoin or client.martin == 1:
            next_sell_val = client.transaction * client.sellRate
        else:
            next_sell_val = client.transaction * client.sellRate * client.ratePS
    else:
        next_buy_val = client.amount * client.buyRate
        if client.IS_SPOT:
            if client.currentBase < client.earnCoin:
                next_buy_val = round(
                    client.amount * client.buyRate + client.amount * (client.ratePB - 1) * (
                            1 + client.buyRate) * client.buyRate / 2, 2)
        else:
            if client.currentBase > client.earnCoin and client.martin != 1:
                next_buy_val = round(
                    client.amount * client.buyRate - client.amount * (client.ratePB - 1) * (
                            1 + client.buyRate) * client.buyRate / 2, 2)
        next_sell_val = client.amount * client.sellRate
    return _next_buy_price, next_buy_val, _next_sell_price, next_sell_val


def modify_trans_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_transaction, _next_sell, _next_sell_transaction,
                          client):
    buy_rate = math.log(client.currentBase / _avg_sell, client.ratePB)
    if client.percentage >= 1:
        buy_rate = round(math.floor(buy_rate / 0.1) * 0.1, 1)
    else:
        buy_rate = math.floor(buy_rate)
    client.buyRate = buy_rate
    buy_transaction_rate = _next_buy_transaction / client.transaction
    if buy_rate > 1 and buy_rate > buy_transaction_rate:
        _next_buy = round(client.currentBase / pow(client.ratePB, buy_rate), client.ACCURACY)
        if client.currentBase < client.earnCoin:
            _next_buy_transaction = client.transaction * buy_rate
        else:
            _next_buy_transaction = round(client.transaction * buy_rate - client.transaction * (client.ratePB - 1) *
                                          buy_rate * (buy_rate - 1) / 2, client.ACCURACY)
    sell_rate = math.log(_avg_buy / client.currentBase, client.ratePS)
    if client.percentage >= 1:
        sell_rate = round(math.floor(sell_rate / 0.1) * 0.1, 1)
    else:
        sell_rate = math.floor(sell_rate)
    client.sellRate = sell_rate
    sell_transaction_rate = _next_sell_transaction / client.transaction
    if sell_rate > 1 and sell_rate > sell_transaction_rate:
        _next_sell = round(client.currentBase * pow(client.ratePS, sell_rate), client.ACCURACY)
        if client.currentBase < client.earnCoin:
            _next_sell_transaction = client.transaction * sell_rate
        else:
            _next_sell_transaction = round(client.transaction * sell_rate + client.transaction * (client.ratePS - 1) * (
                    1 + sell_rate) * sell_rate / 2, client.ACCURACY)
    return _next_buy_transaction, _next_buy, _next_sell_transaction, _next_sell


def modify_amt_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_amount, _next_sell, _next_sell_amount, client):
    buy_rate = math.log(client.currentBase / _avg_sell, client.ratePB)
    client.buyRate = buy_rate = round(math.floor(buy_rate / 0.1) * 0.1, 1)
    buy_amount_rate = _next_buy_amount / client.amount
    if buy_rate > 1 and buy_rate > buy_amount_rate:
        _next_buy = round(client.currentBase / pow(client.ratePB, buy_rate), client.ACCURACY)
        _next_buy_amount = client.amount * buy_rate
        if client.IS_SPOT:
            if client.currentBase < client.earnCoin:
                _next_buy_amount = round(client.amount * buy_rate + client.amount * (client.ratePB - 1) * (
                        1 + buy_rate) * buy_rate / 2, client.ACCURACY)
        else:
            if client.currentBase > client.earnCoin:
                _next_buy_amount = round(client.amount * buy_rate - client.amount * (client.ratePB - 1) * (
                        1 + buy_rate) * buy_rate / 2, client.ACCURACY)
    sell_rate = math.log(_avg_buy / client.currentBase, client.ratePS)
    client.sellRate = sell_rate = round(math.floor(sell_rate / 0.1) * 0.1, 1)
    sell_amount_rate = _next_sell_amount / client.amount
    if sell_rate > 1 and sell_rate > sell_amount_rate:
        _next_sell = round(client.currentBase * pow(client.ratePS, sell_rate), client.ACCURACY)
        if client.currentBase < client.earnCoin and client.IS_SPOT:
            _next_sell_amount = round(client.amount * sell_rate - client.amount * (client.ratePS - 1) *
                                      sell_rate * (sell_rate - 1) / 2, client.ACCURACY)
        else:
            _next_sell_amount = client.amount * sell_rate
    if client.martin == 1:
        from .statistics import get_statistics
        amount, transaction, price, avg_price, count = get_statistics(client)
        if client.IS_FUTURE:
            client.profit = None
            k = 1 + client.percentage * (1 - 1 / pow(max(client.ratePB, client.ratePS), int(client.percentage * 100)))
            if amount > 0:
                if avg_price != 0:
                    loss = abs(avg_price - _next_buy) * amount
                    client.profit = round((_avg_sell - avg_price) * abs(transaction) / 100)
                    rate = max(client.ratePB - 1, (price / _next_buy - 1) / 3)
                    amt_relocate = amount * _next_buy if abs(transaction) / 10 >= client.amount * 2 else 0
                    _next_buy_amount = int(k * max((loss / rate - amt_relocate) / 10, client.amount))
                    if _next_buy_amount > 10 * client.amount:
                        _next_buy_amount = min(_next_buy_amount, int(client.superpower * abs(transaction / 10)))
                _next_sell_amount = math.ceil(abs(transaction) / 10)
            elif amount < 0:
                if avg_price != 0:
                    loss = abs(_next_sell - avg_price) * abs(amount)
                    client.profit = round((avg_price - _avg_buy) * abs(transaction) / 100)
                    rate = max(client.ratePS - 1, (_next_sell / price - 1) / 3)
                    amt_relocate = abs(amount) * _next_sell if abs(transaction) / 10 >= client.amount * 2 else 0
                    _next_sell_amount = int(k * max((loss / rate - amt_relocate) / 10, client.amount))
                    if _next_sell_amount > 10 * client.amount:
                        _next_sell_amount = min(_next_sell_amount, int(client.superpower * abs(transaction / 10)))
                _next_buy_amount = math.ceil(abs(transaction) / 10)
            else:
                _next_buy_amount = int(_next_buy_amount)
                _next_sell_amount = int(_next_sell_amount)
        else:
            if avg_price != 0:
                _next_buy_amount = round(
                    amount * (round(avg_price - _next_buy, client.ACCURACY)) * pow(client.ratePB, client.power) / (
                            client.ratePB - 1) / _next_buy,
                    client.ACCURACY)
            _next_sell_amount = amount
    return _next_buy_amount, _next_buy, _next_sell_amount, _next_sell


def modify_val_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_val, _next_sell, _next_sell_val, client):
    if client.mode == "transaction":
        next_buy_trans_p, next_buy_p, next_sell_trans_p, next_sell_p = modify_trans_by_price(_avg_buy, _avg_sell,
                                                                                             _next_buy, _next_buy_val,
                                                                                             _next_sell, _next_sell_val,
                                                                                             client)
        next_buy_amount = round(next_buy_trans_p / _avg_sell, client.ACCURACY)
        next_sell_amount = round(next_sell_trans_p / _avg_buy, client.ACCURACY)
        return next_buy_amount, next_buy_p, next_sell_amount, next_sell_p
    else:
        return modify_amt_by_price(_avg_buy, _avg_sell, _next_buy, _next_buy_val, _next_sell, _next_sell_val, client)
