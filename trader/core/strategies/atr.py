import math

from trader.services.market import get_market_price_info
from trader.services.logging import logger
from trader.services.notifier import send_msg


def get_atr_auto_mode(atr_config, ma):
    buy_mode = sell_mode = False
    if atr_config.get("mode1") is not None:
        buy_mode = eval(f"{ma}{atr_config.get('mode1')}")
    if atr_config.get("mode2") is not None:
        sell_mode = eval(f"{ma}{atr_config.get('mode2')}")
    if atr_config.get("mode3") is not None:
        exp = atr_config.get('mode3')
        if isinstance(exp, list) and len(exp) == 2:
            buy_sell_mode = eval(f"{ma}{exp[0]}") and eval(f"{ma}{exp[1]}")
            buy_mode = buy_mode or buy_sell_mode
            sell_mode = sell_mode or buy_sell_mode
    return buy_mode, sell_mode


def get_atr_trigger(client, buy, sell):
    atr_config = client.atr_config
    pct = atr_config["pct"] / 100
    gap = atr_config["gapPct"] / 100
    profit = atr_config["profitVsFee"]
    atr_pass = atr_config["pass"]
    atr_buys = client.atr_buys
    atr_sells = client.atr_sells
    buy_mode = client.atr_buy_mode
    sell_mode = client.atr_sell_mode
    data = get_market_price_info(client.SYMBOL_T)[client.period]["data"]
    atr_arr = []
    for i in range(atr_config['size']):
        if client.period == '1s':
            sub_data = data[i * 10:(i + 1) * 10]
            high = max(list(map(lambda x: x[1], sub_data)))
            low = min(list(map(lambda x: x[2], sub_data)))
        else:
            high = data[i][1]
            low = data[i][2]
        atr_arr.append(high - low)
    ma = (sum(list(map(lambda x: x[3], data))) + buy + sell) / (len(data) + 2)
    if client.period != '1s':
        last_close = data[0][3]
        cur_max = max(last_close, buy, sell)
        cur_min = min(last_close, buy, sell)
        atr_arr.append(cur_max - cur_min)
        atr_arr.remove(min(atr_arr))
    atr = sum(atr_arr) / len(atr_arr)
    atr_threshold = max(atr, ma * pct)
    next_sell = round(ma + atr_threshold * atr_config['trigger'], client.ACCURACY)
    sell_win = round(next_sell - atr_threshold * atr_config['win'], client.ACCURACY)
    next_buy = round(ma - atr_threshold * atr_config['trigger'], client.ACCURACY)
    buy_win = round(next_buy + atr_threshold * atr_config['win'], client.ACCURACY)
    if client.atr_auto_mode:
        buy_mode, sell_mode = get_atr_auto_mode(atr_config, ma)
    client.atr_info = f"MA:{round(ma, client.ACCURACY)} ATR:{round(atr, client.ACCURACY)}"
    last_buy = atr_buys[len(atr_buys) - 1] if len(atr_buys) > 0 else None
    last_sell = atr_sells[len(atr_sells) - 1] if len(atr_sells) > 0 else None
    client.buyRate = client.sellRate = 0
    oracles = []
    if buy_mode:
        buy_point = 99999
        if len(atr_buys) > 0:
            next_sell_p = max(last_buy / (1 - client.fee * profit), buy_win)
            oracles.append(
                {"trigger": -11, "exp": f"{buy}>={next_sell_p}", "ext": last_buy, "distance": abs(buy - next_sell_p),
                 "p": next_sell_p})
            buy_point = last_buy * (1 - gap)
        if len(atr_buys) < atr_config['buyLimit']:
            next_buy_p = min(next_buy, buy_point - 2 * atr_threshold * atr_config['trigger'])
            oracles.append(
                {"trigger": 10, "exp": f"{sell}<={next_buy_p}", "ext": None, "distance": abs(sell - next_buy_p),
                 "p": next_buy_p})
    if sell_mode:
        sell_point = -99999
        if len(atr_sells) > 0:
            next_buy_p = min(last_sell / (1 + client.fee * profit), sell_win)
            oracles.append(
                {"trigger": 11, "exp": f"{sell}<={next_buy_p}", "ext": last_sell, "distance": abs(sell - next_buy_p),
                 "p": next_buy_p})
            sell_point = last_sell * (1 + gap)
        if len(atr_sells) < atr_config['sellLimit']:
            next_sell_p = max(next_sell, sell_point + 2 * atr_threshold * atr_config['trigger'])
            oracles.append(
                {"trigger": -10, "exp": f"{buy}>={next_sell_p}", "ext": None, "distance": abs(buy - next_sell_p),
                 "p": next_sell_p})
    if len(oracles) == 0:
        logger.warning(f"[{client.user}] atr not applicable, exit")
        send_msg(client, f"[{client.user}] atr not applicable, exit")
        exit()
    # 10 L+, -10 S+  -11 L-, 11 S-
    if client.atr_config.get("oracle") is not None:
        oracles = list(
            filter(lambda x: eval(f"{x['trigger']}{atr_config.get('oracle')} or {abs(x['trigger']) == 11} "), oracles))
    trigger = 0
    result = None
    if atr == atr_threshold or atr_pass:
        for oracle in oracles:
            if eval(oracle["exp"]):
                result = oracle
                trigger = oracle["trigger"]
                break
    if not result:
        oracles = sorted(oracles, key=lambda x: x['distance'])
        result = oracles[0]
    if result["trigger"] > 0:
        client.buyRate = 1
    else:
        client.sellRate = 1
    return trigger, round(result["p"], 4), round(result["p"], 4), ma, result["ext"]


def get_energy_box(x) -> str:
    if x <= 0:
        return "0"
    v = x
    # 选择步长
    if v < 1:
        step = 0.05
    elif v < 10:
        step = 0.5
    elif v < 100:
        step = 5
    elif v < 1000:
        step = 50
    else:
        # 每 10 倍范围步长 ×10
        mag = 10 ** (math.floor(math.log10(v)) - 2)
        step = 5 * mag

    # 向下取整
    res = math.floor(v / step) * step

    # 格式化字符串：整数不带小数，其他保留一位
    if abs(res - round(res)) < 1e-9:
        return str(int(res))
    else:
        return f"{res:.2f}".rstrip('0').rstrip('.')

def get_charge_index(trigger):
    return 1 if trigger > 0 else 0


def get_release_index(trigger):
    return 0 if trigger > 0 else 1


def get_charged(client, box):
    return client.atr_energy.get(box) if client.atr_energy.get(box) is not None else [0, 0]


def get_released(client, box):
    return client.atr_release.get(box) if client.atr_release.get(box) is not None else 0


def get_escaped(client, box):
    return client.atr_escape.get(box) if client.atr_escape.get(box) is not None else 0
