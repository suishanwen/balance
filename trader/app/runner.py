import os, time, math, gevent, traceback
import api.OrderInfo as OrderInfo
from trader.services.logging import logger, write_log
from trader.services.notifier import send_msg, push_msg, push_reload
from trader.services.market import get_market_price_info
from util.LogUtil import get_latest_order
from util.MyUtil import get_ms
from trader.services.config import init_config, init_symbol, check_timer_task
from trader.core.risk import kill_checker
from trader.core.pricing import get_next_buy_sell_info, modify_val_by_price
from trader.core.strategies.common import get_trigger_info, get_trend, get_trigger_no
from trader.core.strategies.atr import get_atr_trigger, get_release_index, get_energy_box, get_charged
from trader.core.strategies.high_frequency import get_hf_trigger
from trader.services.execution import order_process, order_resolve, fill_atr_order, fill_hf_order, hf_order_process, re_init_energy, reset_channel
from trader.core.statistics import get_statistics, cost_fill, get_earn, add_statistics

# HF 客户端注册表：供 /hf-data 端点读取活跃 tracker 的实时数据
_hf_clients = {}  # key: (user, symbol), value: client


def get_hf_client(user, symbol):
    """获取正在运行的 HF 客户端（用于读取实时 tick 数据）"""
    return _hf_clients.get((user, symbol))


def run_loop(client):
    client.stop = False
    symbol = client.SYMBOL_T
    init_config(client)
    init_symbol(client)
    is_atr = client.atr == 1
    is_hf = client.hf == 1
    sleep = 0.02 if is_atr or is_hf else 0.99
    client.get_account_info()
    available = 0
    direction = ""
    if client.IS_FUTURE and not is_hf:
        available, direction = client.get_contract_position_info(symbol)
        logger.info(f"[{client.user}]{symbol} available: {available}, direction: {direction}")
    latest_order = get_latest_order(symbol, client.user)
    ma_cding = False
    counter = 0
    trigger = 0
    dma = 0
    next_base = 0
    next_buy_amount = 0
    next_buy_p = 0
    next_sell_amount = 0
    next_sell_p = 0
    time.sleep(1)
    next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
    trend = trend_tmp = None
    trend_change = False
    if is_hf:
        buy = avg_buy = sell = avg_sell = 0
        buy_amount = sell_amount = client.amount * 10
    else:
        buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, 1)
    ms = get_ms()
    open_price = None
    change = earn = release = 0
    try:
        logger.warning(f"[{client.user}] {symbol} {client.type} TRADING START! PID: {os.getpid()}")
        if is_hf:
            logger.warning(f"[{client.user}] {symbol} HF strategy ACTIVE, config={client.hf_config}")
            _hf_clients[(client.user, symbol)] = client
        while True:
            if client.stop:
                logger.warning(f"[{client.user}] {symbol} STOP!")
                _hf_clients.pop((client.user, symbol), None)
                return
            if counter % 4 == 0 and not is_hf:
                wait = kill_checker(client, buy, sell, symbol)
                if wait:
                    logger.info(
                        f"[{client.user}]{symbol}| buy:{buy}, sell:{sell}, wait:{client.kill} or {client.kill2}")
                    buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, 1)
                    gevent.sleep(1)
                    continue
            if client.maintain > 0 and not is_hf and client.sellRate < client.buyRate and (trend_change or counter % 10 == 0):
                from trader.services.account import check_account_bal
                check_account_bal(client, math.ceil(next_buy_amount / 5))
            if counter % 200 == 0:
                if check_timer_task(client, latest_order) and client.atr != 1:
                    next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
                counter = 0
            if is_hf:
                # HF 模式：spec symbol 的汇率从 marketConfig 读取（由 set_t1_t2 实时更新）
                from market.MarketMonitor import get_bid1_ask1, \
                    get_split_symbols, get_split_swap_symbols, is_spec_swap_symbol, \
                    get_market_price_info as mm_get_info, get_depth as mm_refresh
                _bid1, _ask1 = get_bid1_ask1(symbol)
                bid1 = float(_bid1)
                ask1 = float(_ask1)
                if bid1 == 0 or ask1 == 0:
                    if counter % 100 == 0:
                        logger.warning(f"[{client.user}]{symbol}|HF 等待行情数据... bid1={bid1} ask1={ask1}")
                    gevent.sleep(0.1)
                    counter += 1
                    continue
                # 检测组件币种深度是否过期（>30秒无更新则强制刷新）
                comp_syms = get_split_swap_symbols(symbol) if is_spec_swap_symbol(symbol) else get_split_symbols(symbol)
                now_ms = get_ms()
                for cs in comp_syms:
                    cs_depth = mm_get_info(cs).get("depth", {})
                    cs_ver = cs_depth.get("version", 0)
                    if cs_ver > 0 and now_ms - cs_ver > 30000:
                        if counter % 50 == 0:
                            logger.warning(f"[{client.user}]{symbol}|HF {cs} depth stale ({(now_ms - cs_ver) // 1000}s), refreshing")
                        try:
                            import copy
                            _rc = copy.copy(client)
                            _rc.SYMBOL_T = cs
                            mm_refresh(_rc, emergency=True)
                        except Exception as e:
                            logger.warning(f"HF depth refresh {cs} error: {e}")
                buy = avg_buy = bid1
                sell = avg_sell = ask1
                buy_amount = sell_amount = client.amount * 10  # 足量
                next_buy_amount = next_sell_amount = client.amount
                trigger, next_buy_p, next_sell_p, ma, open_price = get_hf_trigger(client, avg_buy, avg_sell)
                earn = 0
                if trigger != 0:
                    logger.warning(f"[{client.user}]{symbol}|HF TRIGGER={trigger} target={next_buy_p}/{next_sell_p} "
                                   f"bid={buy} ask={sell} pos={client.hf_position} "
                                   f"buys={client.hf_buys} sells={client.hf_sells}")
            if not is_hf:
                depth_data = get_market_price_info(symbol)["depth"]
                max_depth = min(len(depth_data['asks']), len(depth_data['bids']))
                for i in range(max_depth):
                    buy, avg_buy, buy_amount, sell, avg_sell, sell_amount = client.get_price_info(symbol, i + 1)
                    if client.atr != 1:
                        next_buy_amount, next_buy_p, next_sell_amount, next_sell_p = modify_val_by_price(
                            avg_buy, avg_sell, next_buy, next_buy_val, next_sell, next_sell_val, client)
                        trend, price_t = get_trend(client, avg_buy, avg_sell)
                        dma, reverse, high_ex, low_ex = get_trigger_info(client, price_t)
                        needle_diff = (low_ex - avg_sell) if trend > 0 else (avg_buy - high_ex)
                        needle_rate = 0 if high_ex - low_ex == 0 else round(needle_diff / (high_ex - low_ex),
                                                                            client.ACCURACY)
                        trigger = get_trigger_no(ma_cding, dma, reverse, client, avg_sell, avg_buy, needle_diff,
                                                 needle_rate, available)
                        if client.martin == 1 and trigger != 0:
                            earn = 0;
                            open_price = None
                            if next_sell_p > client.earnCoin or next_buy_p > client.earnCoin:
                                amount, transaction, price, avg_price, count = get_statistics(client)
                                if trigger == -40:
                                    open_price = avg_price
                                    earn = (amount - next_sell_amount * 10 / next_sell_p) * avg_price / 10
                                    if client.cost > next_sell_p and client.costFill > 0:
                                        earn = int(earn * client.cost / (client.cost - next_sell_p))
                                        earn = earn if abs(earn) <= abs(client.costFill) else client.costFill
                                        next_sell_amount += int(earn)
                                if trigger == 40:
                                    open_price = avg_price
                                    earn = (next_buy_amount * 10 / next_buy - abs(amount)) * avg_price / 10
                                    if client.cost > next_buy_p and client.costFill > 0:
                                        earn = int(earn * client.cost / (client.cost - next_buy_p))
                                        earn = earn if abs(earn) <= abs(client.costFill) else client.costFill
                                        next_buy_amount -= int(earn)
                    else:
                        next_buy_amount = next_sell_amount = client.amount
                        trigger, next_buy_p, next_sell_p, ma, open_price = get_atr_trigger(client, avg_buy, avg_sell)
                        change = client.atr_change;
                        earn = 0;
                        release = 0
                        if trigger == -10:
                            px = buy
                            diff = px * client.fee * client.atr_config['profitVsFee']
                            if ma > client.earnCoin and client.USD_FUTURE:
                                earn = math.floor(get_earn(client, px, diff))
                            next_sell_amount += earn
                        if trigger == -11:
                            px = buy
                            diff = px - open_price
                            if ma > client.earnCoin and client.USD_FUTURE:
                                earn = get_earn(client, open_price, diff)
                                change_t = math.floor(earn * 100) + change
                                change = change_t % 100
                                earn = int((change_t - change) / 100)
                            next_sell_amount += earn
                        if abs(trigger) == 11 and open_price:
                            px = sell if trigger == 11 else buy
                            if get_energy_box(px) != get_energy_box(open_price):
                                re_init_energy(client)
                                release_index = get_release_index(trigger)
                                release_energy = get_charged(client, get_energy_box(open_price))[release_index]
                                if client.USD_FUTURE:
                                    release = int(px * release_energy * client.swapEnlarge)
                                else:
                                    release = int(release_energy / px / client.swapEnlarge)
                            if trigger == 11:
                                next_buy_amount += release
                            elif trigger == -11:
                                next_sell_amount += release
                    if (trigger > 0 and sell_amount >= next_buy_amount) or (trigger < 0 and buy_amount >= next_sell_amount):
                        logger.info(f"[{client.user}] trigger[{trigger}]: depth combine lv {i + 1}")
                        break
                    if trigger == 0:
                        break
            order_info = None
            if trigger > 0 and sell_amount >= next_buy_amount:
                next_base = next_buy_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_BUY,
                                                   round(sell + client.pricePatch, client.ACCURACY),
                                                   next_buy_amount, next_base, trigger, open_price, earn)
            elif trigger < 0 and buy_amount >= next_sell_amount:
                next_base = next_sell_p
                order_info = OrderInfo.MyOrderInfo(symbol, client.TRADE_SELL,
                                                   round(buy - client.pricePatch, client.ACCURACY),
                                                   next_sell_amount, next_base, trigger, open_price, earn)
            if order_info is not None:
                if is_hf:
                    hf_order_process(client, order_info)
                elif client.IS_FUTURE:
                    available, direction = order_resolve(client, order_info, available, direction)
                else:
                    order_process(client, order_info)
                if order_info.totalAmount - order_info.totalDealAmount < client.MIN_AMOUNT:
                    client.currentBase = round(order_info.avgPrice,
                                               client.ACCURACY) if client.martin == 1 or is_atr else round(next_base,
                                                                                                           client.ACCURACY)
                    if is_hf:
                        fill_hf_order(client, order_info, trigger)
                        write_log(str(order_info))
                    elif is_atr:
                        fill_atr_order(client, order_info, trigger, change, earn, release)
                        add_statistics(client, order_info)
                        write_log(str(order_info))
                    else:
                        if client.martin == 1:
                            cost_fill(client, earn)
                            amount, transaction, price, avg_price, count = get_statistics(client)
                            reset_channel(client, transaction / 10)
                        client.config.set(symbol, "currentBase", str(client.currentBase))
                        next_buy, next_buy_val, next_sell, next_sell_val = get_next_buy_sell_info(client)
                        latest_order = get_latest_order(symbol, client.user)
                    with open(f"{client.user}.ini", "w") as fp:
                        client.config.write(fp)
                    deal_msg = order_info.tl_msg(client)
                    send_msg(client, deal_msg);
                    push_msg(client.user, deal_msg);
                    push_reload(client.user, symbol)
                    counter = -1
            if client.sellRate >= client.buyRate:
                diff = f"(+{round(next_sell_p - buy, client.ACCURACY)})" if client.ACCURACY <= 4 else ""
                tail = f"[{next_sell_p},{next_sell_amount}]:[{buy},{buy_amount}]{diff}"
                info = f"↑({client.sellRate}):{tail}"
            else:
                diff = f"({round(next_buy_p - sell, client.ACCURACY)})" if client.ACCURACY <= 4 else ""
                tail = f"[{next_buy_p},{next_buy_amount}]:[{sell},{sell_amount}]{diff}"
                info = f"↓({client.buyRate}):{tail}"
            t_ms = get_ms()
            counter += 1
            if t_ms - ms >= 980:
                if is_hf:
                    bs = "BID" if client.buyRate > 0 else "ASK"
                    pos_info = f"P:{client.hf_position} B:{len(client.hf_buys)} S:{len(client.hf_sells)}"
                    tick_info = ""
                    if hasattr(client, '_hf_tracker'):
                        tick_info = f" D:{len(client._hf_tracker.data)}m/{len(client._hf_tracker.ticks)}t"
                    logger.info(f"[{client.user}]{symbol}|{client.hf_info} {pos_info}{tick_info} {bs}{tail}")
                elif client.atr != 1:
                    rdma = round(dma, client.ACCURACY)
                    logger.info(f"[{client.user}]{symbol}|B:{client.currentBase} M:{rdma} {info}")
                else:
                    bs = "BID" if client.buyRate > 0 else "ASK"
                    logger.info(f"[{client.user}]{symbol}|{client.atr_info} {bs}{tail}")
                ms = t_ms
            else:
                gevent.sleep(sleep)
            trend_tmp, trend_change = (trend, (trend_tmp is not None and trend_tmp != trend))
            if client.martin == 1 and counter % 20 == 0:
                logger.info(f"[{client.user}]{symbol}|-------------->{client.profit}<--------------")
    except Exception as e:
        logger.error(f"[{client.user}] [unhandled exception]{e}:{traceback.format_exc()}")
        send_msg(client, f"{symbol}:unhandled exception:{traceback.format_exc()}")
        exit()
