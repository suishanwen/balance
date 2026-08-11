
import time
from trader.services.market import get_market_price_info

def get_trigger_info(client, price_t):
    data = get_market_price_info(client.SYMBOL_T)[client.period]["data"]
    if client.preCalc:
        cur_data = data[0]
        if price_t > cur_data[1]:
            cur_data[1] = price_t
        if price_t < cur_data[2]:
            cur_data[2] = price_t
        cur_data[3] = price_t
    high = max(map(lambda x: x[1], data))
    low = min(map(lambda x: x[2], data))
    data2 = list(map(lambda x: x[3], data))
    data1 = data2[0:client.size1]
    sum1 = sum2 = 0
    for i in data1:
        sum1 += i
    for i in data2:
        sum2 += i
    prev = data[1]
    prev_grand = data[2]
    dma = round(sum1 / len(data1) - sum2 / len(data2), client.ACCURACY + 2)
    reverse = (prev[2] == low and prev[3] > prev_grand[3]) or               (prev[1] == high and prev[3] < prev_grand[3])
    hammer = False
    if abs(prev[1] - prev[2]) > 0:
        hammer = abs(prev[0] - prev[3]) / abs(prev[1] - prev[2]) <= 0.4
    pierce = False
    if abs(prev_grand[3] - prev_grand[0]) > 0:
        pierce = abs(prev[3] - prev_grand[3]) / abs(prev_grand[3] - prev_grand[0]) >= 0.5
    data_ex = data[8:client.size2] if client.period == '1s' else data[1:client.size2]
    list_ex = []
    for ex in data_ex:
        list_ex.append(ex[0]); list_ex.append(ex[3])
    high_ex = max(list_ex); low_ex = min(list_ex)
    return dma, reverse and (hammer or pierce), high_ex, low_ex

def get_trigger_no(ma_cding, dma, reverse, client, avg_sell, avg_buy, needle_diff, needle_rate, available):
    if client.buyRate >= 1:
        if client.martin == 1:
            from trader.core.statistics import get_statistics
            amount, transaction, price, avg_price, count = get_statistics(client)
            if transaction == 0:
                return 41
            elif transaction > 0:
                return 40
            elif dma > 0 or available < 0:
                return 42
            elif needle_rate >= 1 and needle_diff >= (avg_sell * (client.ratePB - 1) / 2):
                return 43
        elif dma > 0:
            return 1
        elif reverse and client.buyRate >= 2 / client.percentage:
            return 2
        elif needle_rate >= 1 and needle_diff >= (avg_sell * client.percentage / 100 / 2):
            return 3
        elif client.maOff or ma_cding:
            return 9
    elif client.sellRate >= 1:
        if client.martin == 1:
            from trader.core.statistics import get_statistics
            amount, transaction, price, avg_price, count = get_statistics(client)
            if transaction == 0:
                return -41
            elif transaction < 0:
                return -40
            elif dma < 0 or available < 0:
                return -42
            elif needle_rate >= 1 and needle_diff >= (avg_buy * (client.ratePS - 1) / 2):
                return -43
        elif dma < 0:
            return -1
        elif reverse and client.sellRate >= 2 / client.percentage:
            return -2
        elif needle_rate >= 1 and needle_diff >= (avg_buy * client.percentage / 100 / 2):
            return -3
        elif client.maOff or ma_cding:
            return -9
    return 0

def get_trend(client, avg_buy, avg_sell):
    if client.martin == 1:
        if avg_sell < client.currentBase:
            return 1, avg_sell
        else:
            return -1, avg_buy
    else:
        if client.buyRate >= client.sellRate:
            return 1, avg_sell
        else:
            return -1, avg_buy

def is_ma_cding(client, latest_order):
    ma_cding = True
    if latest_order is not None:
        ma_cding = int(time.time()) - latest_order.get_seconds() >= client.cds * 60
    return ma_cding
