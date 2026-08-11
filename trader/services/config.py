import configparser, json, time
from .logging import logger
from .notifier import send_msg, MSG_TYPE_REPORT
from util.Statistic import analyze_log, generate_report
from util.MyUtil import safe_get_val, from_time_stamp
from market.MarketMonitor import is_spec_symbol, is_spec_swap_symbol

ATR_TRUSTS = []


def parse_bool_value(raw, default=False):
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in ('1', 'true', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'no', 'off', ''):
        return False
    return default


def init_config(client):
    symbol = client.SYMBOL_T
    config = client.config
    config.read(client.file)
    client.mode = safe_get_val(config, symbol, "mode", "amount")
    client.amount = float(safe_get_val(config, symbol, "amount", "1"))
    client.swapEnlarge = float(safe_get_val(config, symbol, "enlarge", "10"))
    client.transaction = float(safe_get_val(config, symbol, "transaction", "1"))
    client.currentBase = float(safe_get_val(config, symbol, "currentbase", "0"))
    client.percentage = float(safe_get_val(config, symbol, "percentage", "3"))
    client.earnCoin = float(safe_get_val(config, symbol, "earncoin", 0))
    client.maOff = parse_bool_value(safe_get_val(config, symbol, "maoff", '0'))
    client.preCalc = parse_bool_value(safe_get_val(config, symbol, "precalc", '1'), True)
    client.timeout = float(safe_get_val(config, symbol, "timeout", 9999))
    client.fee = float(safe_get_val(config, symbol, "fee", 0.0003))
    client.pricePatch = float(safe_get_val(config, symbol, "pricepatch", 0))
    client.kill = safe_get_val(config, symbol, "kill", "<=0")
    client.kill2 = safe_get_val(config, symbol, "kill2", "<=0")
    client.doNotKill = float(safe_get_val(config, symbol, "donotkill", 0))
    client.cost = float(safe_get_val(config, symbol, "cost", '0'))
    client.costFill = float(safe_get_val(config, symbol, "costfill", '0'))
    client.experiment = int(safe_get_val(config, symbol, "experiment", '0'))
    client.TRADE_LIMIT = int(safe_get_val(config, symbol, "limit", "0"))
    client.TRADE_LIMIT2 = int(safe_get_val(config, symbol, "limit2", "-10000"))
    client.martin = int(safe_get_val(config, symbol, "martin", '0'))
    client.rateP = (100 + client.percentage) * 0.01
    client.cds = int(safe_get_val(config, "klines", "cooldowns", "15"))
    client.mpower = float(safe_get_val(config, "klines", "mpower", '1.3'))
    client.superpower = float(safe_get_val(config, "klines", "superpower", '5'))
    client.maintain = float(safe_get_val(config, "klines", "maintain", '500'))
    client.notify_type = safe_get_val(config, "notify", "type", 'telegram')
    client.hf = int(safe_get_val(config, symbol, "hf", '0'))
    # 提前读取 atr 标志（用于互斥校验，后面会根据条件重新设置）
    _atr_raw = int(safe_get_val(config, symbol, "atr", '0')) if client.IS_FUTURE else 0
    # 自动检测 spec symbol（如 OKB-ORDI, XPL-ORDI-SWAP），强制启用 HF
    if client.hf != 1 and (is_spec_symbol(symbol) or is_spec_swap_symbol(symbol)):
        logger.warning(f"[{client.user}]{symbol} auto-detected as HF spec symbol, forcing hf=1")
        client.hf = 1
    # 策略互斥校验：同一个币种只能启用 K线/马丁/ATR/高频 中的一个
    if client.hf == 1:
        if _atr_raw == 1:
            logger.warning(f"[{client.user}]{symbol} atr=1 conflicts with hf=1, disabling atr")
        if client.martin == 1:
            logger.warning(f"[{client.user}]{symbol} martin=1 conflicts with hf=1, disabling martin")
            client.martin = 0
    elif _atr_raw == 1:
        if client.martin == 1:
            logger.warning(f"[{client.user}]{symbol} martin=1 conflicts with atr=1, disabling martin")
            client.martin = 0
    if client.hf == 1:
        from trader.core.strategies.high_frequency import HF_DEFAULT_CONFIG
        hf_default_str = json.dumps(HF_DEFAULT_CONFIG)
        client.hf_config = json.loads(safe_get_val(config, f"{symbol}-HF", "config", hf_default_str))
        # 补齐缺失的键
        for k, v in HF_DEFAULT_CONFIG.items():
            if client.hf_config.get(k) is None:
                client.hf_config[k] = v
        client.hf_buys = json.loads(safe_get_val(config, f"{symbol}-HF", "buys", "[]"))
        client.hf_sells = json.loads(safe_get_val(config, f"{symbol}-HF", "sells", "[]"))
        # 归一化：旧格式 float → [float, 0]，确保排序不报错
        client.hf_buys = [e if isinstance(e, list) else [e, 0] for e in client.hf_buys]
        client.hf_sells = [e if isinstance(e, list) else [e, 0] for e in client.hf_sells]
        client.hf_position = int(float(safe_get_val(config, f"{symbol}-HF", "position", "0")))
        client.hf_fee = float(safe_get_val(config, f"{symbol}-HF", "fee", "0"))
        client.hf_outcome = float(safe_get_val(config, f"{symbol}-HF", "outcome", "0"))
        client.hf_count = int(float(safe_get_val(config, f"{symbol}-HF", "count", "0")))
        client.hf_win = int(float(safe_get_val(config, f"{symbol}-HF", "win", "0")))
        client.hf_info = ""
    client.atr = int(safe_get_val(config, symbol, "atr", '0')) if client.IS_FUTURE and client.hf != 1 else 0
    if client.atr == 1:
        if client.user not in ATR_TRUSTS:
            logger.warning(f"[{client.user}] atr not applicable, exit")
            send_msg(client, f"[{client.user}] atr not applicable, exit")
            exit()
        client.atr_position = int(safe_get_val(config, f"{symbol}-ATR", "position", "0"))
        client.atr_avg_price = float(safe_get_val(config, f"{symbol}-ATR", "avgprice", "0"))
        client.atr_fee = float(safe_get_val(config, f"{symbol}-ATR", "fee", "0"))
        client.atr_outcome = float(safe_get_val(config, f"{symbol}-ATR", "outcome", "0"))
        client.atr_count = int(safe_get_val(config, f"{symbol}-ATR", "count", "0"))
        client.atr_win = int(safe_get_val(config, f"{symbol}-ATR", "win", "0"))
        client.atr_change = int(safe_get_val(config, f"{symbol}-ATR", "change", "0"))
        client.atr_earn = int(safe_get_val(config, f"{symbol}-ATR", "earn", "0"))
        client.atr_energy = json.loads(safe_get_val(config, f"{symbol}-ATR", "energy", "{}"))
        client.atr_release = json.loads(safe_get_val(config, f"{symbol}-ATR", "release", "{}"))
        client.atr_escape = json.loads(safe_get_val(config, f"{symbol}-ATR", "escape", "{}"))
        client.atr_config = json.loads(safe_get_val(config, f"{symbol}-ATR", "config"))
        if client.atr_config.get("pct") is None:
            client.atr_config["pct"] = 0.02
        if client.atr_config.get("gapPct") is None:
            client.atr_config["gapPct"] = 1
        if client.atr_config.get("pass") is None:
            client.atr_config["pass"] = False
        if client.atr_config.get("charging") is None or client.atr_config.get("charging") == '':
            client.atr_config["charging"] = 0
        if client.atr_config.get("buyLimit") is None or client.atr_config.get("buyLimit") == '':
            client.atr_config["buyLimit"] = 99
        if client.atr_config.get("sellLimit") is None or client.atr_config.get("sellLimit") == '':
            client.atr_config["sellLimit"] = 99
        client.atr_buys = json.loads(safe_get_val(config, f"{symbol}-ATR", "buys", "[]"))
        client.atr_sells = json.loads(safe_get_val(config, f"{symbol}-ATR", "sells", "[]"))
        atr_mode = client.atr_config.get("mode")
        client.atr_buy_mode = atr_mode == 1 or atr_mode == 3
        client.atr_sell_mode = atr_mode == 2 or atr_mode == 3
        client.atr_auto_mode = atr_mode == 4


def init_symbol(client):
    symbol = client.SYMBOL_T
    # HF spec symbol: OKB-ORDI, XPL-OKB, OKB-ORDI-SWAP 等
    if (client.hf == 1 or is_spec_symbol(symbol) or is_spec_swap_symbol(symbol)):
        parts = symbol.split("-")
        if len(parts) >= 2 and parts[1] not in ("BTC", "ETH", "USDT", "USD"):
            client.BALANCE_E = "usdt"
            client.BALANCE_T = parts[0].lower()
            client.BALANCE_T2 = parts[1].lower()
            client.accountInfo[client.BALANCE_T] = {"total": 0, "available": 0, "freezed": 0}
            client.accountInfo[client.BALANCE_T2] = {"total": 0, "available": 0, "freezed": 0}
            client.accountInfo[client.BALANCE_E] = {"total": 0, "available": 0, "freezed": 0}
            return
    if symbol.lower().find("usdt") != -1:
        client.BALANCE_E = "usdt"
    elif symbol.lower().find("usd") != -1:
        client.BALANCE_E = "usd"
    elif symbol.lower().find("3l") != -1 or symbol.lower().find("3s") != -1:
        client.BALANCE_E = "usdt"
    elif symbol.lower().find("eos") != -1 and symbol.lower().find("eth") != -1:
        client.BALANCE_E = "eth"
    elif symbol.lower().find("eos") != -1 and symbol.lower().find("btc") != -1:
        client.BALANCE_E = "btc"
    else:
        parts = symbol.split("_") if "_" in symbol else symbol.split("-")
        client.BALANCE_E = parts[1].lower() if len(parts) > 1 else "usdt"
    client.BALANCE_T = str(symbol).replace("_", "").replace(client.BALANCE_E, "")
    client.accountInfo[client.BALANCE_T] = {"total": 0, "available": 0, "freezed": 0}
    client.accountInfo[client.BALANCE_E] = {"total": 0, "available": 0, "freezed": 0}
    if client.BALANCE_T == "btc":
        client.MIN_AMOUNT = 0.0001
    elif client.BALANCE_T == "eth":
        client.MIN_AMOUNT = 0.001
    elif client.BALANCE_T == "bch":
        client.MIN_AMOUNT = 0.01
    elif symbol == 'EOS-ETH':
        client.MIN_AMOUNT = 0.1
        client.ACCURACY = 6
    elif 'LTC-USD' in symbol:
        client.ACCURACY = 2
    elif symbol == 'EOS-ETH' or symbol == 'EOS-BTC':
        client.MIN_AMOUNT = 0.1
        client.ACCURACY = 7


def set_easy_mode(client, latest_order):
    if latest_order is None or client.martin == 1 or client.atr == 1 or client.hf == 1:
        return False
    timeout = int(time.time()) - latest_order.get_seconds() >= 3600 * client.timeout
    ori_percentage = float(client.config.get(client.SYMBOL_T, "percentage"))
    if (timeout and client.percentage == ori_percentage * 0.5) or (not timeout and client.percentage == ori_percentage):
        return False
    if timeout:
        logger.warning("set easy mode")
        client.percentage = ori_percentage * 0.5
    else:
        logger.warning("set normal mode")
        client.percentage = ori_percentage
    client.rateP = (100 + client.percentage) * 0.01
    client.transaction = client.amount = round(
        float(client.config.get(client.SYMBOL_T, client.mode)) * client.percentage / ori_percentage, client.ACCURACY)
    return True


def check_timer_task(client, latest_order):
    time_stamp = from_time_stamp()
    dd = int(time_stamp[8:10])
    hh = int(time_stamp[11:13])
    mm = int(time_stamp[14:16])
    rebase = False
    if client.emailDay != dd and hh == 23 and mm > 55:
        if send_msg(client, generate_report(client, analyze_log()), MSG_TYPE_REPORT):
            client.emailDay = dd
        rebase = True
    if set_easy_mode(client, latest_order):
        rebase = True
    return rebase


def re_init_cost_fill(client):
    config_tmp = configparser.ConfigParser()
    config_tmp.read(f"{client.user}.ini")
    client.cost = float(safe_get_val(config_tmp, client.SYMBOL_T, "cost", '0'))
    client.costFill = int(safe_get_val(config_tmp, client.SYMBOL_T, "costfill", '0'))
    client.costFilled = int(safe_get_val(config_tmp, client.SYMBOL_T, "costfilled", '0'))
    # sync earns (side effect preserved)
    from util.MyUtil import safe_set_val
    safe_set_val(client.config, "fish", "earn", str(safe_get_val(config_tmp, "fish", "earn", '0')))
    safe_set_val(client.config, "manual", "earn", str(safe_get_val(config_tmp, "manual", "earn", '0')))
