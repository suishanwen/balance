import json
import math, gevent
from trader.services.logging import logger, write_log
from trader.services.account import check_account_bal, earn_account_bal
from trader.services.notifier import send_msg
from trader.core.statistics import set_order_count, add_statistics


def order_process(client, order_info):
    if client.IS_FUTURE:
        order_info.set_amount(int(order_info.get_unhandled_amount(client.ACCURACY)))
    else:
        order_info.set_amount(order_info.get_unhandled_amount(client.ACCURACY))
    state = client.trade(order_info)
    if state == 'failed' and client.maintain > 0 and order_info.orderType == client.TRADE_BUY and client.BALANCE_E.upper() == 'USDT':
        if 'SWAP' in order_info.symbol:
            bal = math.ceil(order_info.totalAmount / 5) * 1.01
        else:
            bal = order_info.totalAmount * order_info.price
        logger.warning(f"[{client.user}] order_process failed, check {bal} USDT")
        check_account_bal(client, bal)
        state = client.trade(order_info)
    if order_info.amount < client.MIN_AMOUNT and state == client.FILLED_STATUS:
        # ATR/HF: count 由 fill_atr_order/fill_hf_order 计算后在 runner.py 写 log
        is_deferred = (order_info.trigger.startswith("atr") or order_info.trigger.startswith("hf"))
        if not is_deferred:
            set_order_count(client, order_info)
            write_log(str(order_info))
            add_statistics(client, order_info)
        if client.maintain > 0 and order_info.orderType == client.TRADE_SELL and client.BALANCE_E.upper() == 'USDT':
            earn_account_bal(client)
    elif order_info.totalDealAmount > 0:
        if state == 'canceled' or state == 'partial-canceled' or state == -1:
            write_log(str(order_info))
        order_info.set_price(0)
        order_process(client, order_info)


def order_resolve(client, order_info, available, direction):
    from util.MyUtil import user_killed
    logger.warning(f"order_resolve - order_info:{order_info},available:{available},direction:{direction}")
    after_order = available
    if direction == "net" or direction == "long":
        if order_info.orderType == client.TRADE_BUY:
            after_order += order_info.totalAmount
        else:
            after_order -= order_info.totalAmount
    elif direction == "short":
        if order_info.orderType == client.TRADE_BUY:
            after_order -= order_info.totalAmount
        else:
            after_order += order_info.totalAmount
    if after_order >= client.TRADE_LIMIT or after_order <= client.TRADE_LIMIT2:
        user_killed(client.user)
        logger.warning(
            f"[{client.user}]|order limit exceeded, volume:{available},order:{order_info.totalAmount},limit:[{client.TRADE_LIMIT2},{client.TRADE_LIMIT}]")
        send_msg(client,
                 f"order limit exceeded, volume:{available},order:{order_info.totalAmount},limit:[{client.TRADE_LIMIT2},{client.TRADE_LIMIT}]")
        exit()
    is_open, offset = client.get_contract_offset(order_info.orderType, direction)
    if is_open or available == 0:
        order_info.offset = offset
        order_process(client, order_info)
    else:
        if order_info.totalAmount > available:
            logger.info(f"[{client.user}]|order_resolve direction:{direction} available:{available}")
            diff = order_info.totalAmount - available
            order1 = order_info.replicate()
            order2 = order_info.replicate()
            order1.offset = offset
            order1.totalAmount = available
            order2.offset = client.get_contract_opposite_offset(offset)
            order2.totalAmount = diff
            order2.price = 0
            order_process(client, order1)
            if order1.totalAmount - order1.totalDealAmount < client.MIN_AMOUNT:
                while not order2.totalAmount - order2.totalDealAmount < client.MIN_AMOUNT:
                    order_process(client, order2)
                order_info.totalDealAmount = order1.totalDealAmount + order2.totalDealAmount
                order_info.transaction = order1.transaction + order2.transaction
                order_info.count = order1.count + order2.count
                order_info.price = order_info.avgPrice = round(
                    abs(order_info.transaction / (order1.realAmount + order2.realAmount)), client.ACCURACY)
        else:
            order_info.offset = offset
            order_process(client, order_info)
    for i in range(3):
        try:
            available, direction = client.get_contract_position_info(client.SYMBOL_T)
            break
        except Exception as e:
            logger.warning(f"[{client.user}]|order_resolve error:{e},count:{i + 1}")
            gevent.sleep(0.02)
    logger.info(f"[{client.user}]|order_resolve direction:{direction} available:{available}")
    return available, direction


# ATR bookkeeping kept as a service (contains side effects)
from trader.core.strategies.atr import get_release_index, get_energy_box, get_charged
from trader.core.statistics import cost_fill


def re_init_energy(client):
    import configparser, json
    config_tmp = configparser.ConfigParser()
    config_tmp.read(f"{client.user}.ini")
    symbol = client.SYMBOL_T
    from util.MyUtil import safe_get_val
    client.atr_energy = json.loads(safe_get_val(config_tmp, f"{symbol}-ATR", "energy", "{}"))


def reset_channel(client, available):
    from trader.services.market import start_depth_task
    old_channel = client.channel
    client.channel = 'books' if abs(available) > client.reset_channel else 'books5'
    if client.channel != old_channel:
        logger.warning(f"[{client.user}]{client.SYMBOL_T} channel: {old_channel} -> {client.channel}")
        client.old_channel = old_channel
        client.config.set(client.SYMBOL_T, "channel", str(client.channel))
        start_depth_task(client)


def fill_atr_order(client, order_info, trigger, change, earn, release):
    price = client.currentBase
    deal_amount = int(order_info.totalDealAmount) if trigger > 0 else -int(order_info.totalDealAmount)
    client.atr_position += deal_amount
    client.atr_fee += order_info.fee
    client.atr_change = change
    client.atr_earn += earn
    client.atr_count += 1
    trx = client.amount * client.swapEnlarge
    symbol = client.SYMBOL_T

    # 补充 realAmount（原由 set_order_count 设置，现 ATR 跳过该步骤）
    if order_info.avgPrice != 0:
        order_info.realAmount = abs(round(order_info.transaction / order_info.avgPrice, client.ACCURACY))

    if abs(trigger) == 10:
        if trigger == 10:
            client.atr_buys.append(price)
        else:
            client.atr_sells.append(price)
        # 开仓无损益
        order_info.count = 0
    if abs(trigger) == 11:
        if trigger == 11:
            open_price = client.atr_sells.pop()
        else:
            open_price = client.atr_buys.pop()
        sell = max(order_info.avgPrice, open_price)
        buy = min(order_info.avgPrice, open_price)
        if client.USD_FUTURE:
            energy = trx / buy - trx / sell
        else:
            energy = (sell - buy) * trx
        client.atr_outcome += energy
        # 用实际收益覆盖 set_order_count 的估算值
        order_info.count = round(energy, client.ACCURACY)
        box = get_energy_box(open_price)
        if release != 0:
            release = release if trigger > 0 else -release
            from trader.core.strategies.atr import get_released, get_escaped
            released = get_released(client, box)
            escaped = get_escaped(client, box)
            escaped += min(abs(released), abs(release)) if released * release < 0 else 0
            released += release
            client.atr_release[box] = released
            client.atr_escape[box] = escaped
        charging = client.atr_config["charging"]
        charged = get_charged(client, box)
        charge_index = 1 if trigger > 0 else 0
        release_index = get_release_index(trigger)
        charged[charge_index] += int(energy * charging)
        if release != 0:
            charged[release_index] = 0
        client.atr_energy[box] = charged
        client.atr_win += 1
    client.atr_buys.sort()
    client.atr_buys.reverse()
    client.atr_sells.sort()
    if client.USD_FUTURE:
        buy_amount = sum(map(lambda x: trx / x, client.atr_buys))
        sell_amount = sum(map(lambda x: trx / x, client.atr_sells))
        transaction = (len(client.atr_sells) - len(client.atr_buys)) * trx
    else:
        buy_amount = sum(map(lambda x: trx, client.atr_buys))
        sell_amount = sum(map(lambda x: trx, client.atr_sells))
        transaction = sum(map(lambda x: trx * x, client.atr_sells)) - sum(
            map(lambda x: trx * x, client.atr_buys))
    amount = round(buy_amount - sell_amount, client.ACCURACY)
    avg_price = abs(round(transaction / (buy_amount - sell_amount), client.ACCURACY)) if amount != 0 else 0
    client.config.set(f"{symbol}-ATR", "position", str(int(client.atr_position)))
    client.config.set(f"{symbol}-ATR", "amount", str(amount))
    client.config.set(f"{symbol}-ATR", "avgprice", str(avg_price))
    client.config.set(f"{symbol}-ATR", "fee", str(round(client.atr_fee, client.ACCURACY)))
    client.config.set(f"{symbol}-ATR", "outcome", str(round(client.atr_outcome, client.ACCURACY)))
    client.config.set(f"{symbol}-ATR", "count", str(client.atr_count))
    client.config.set(f"{symbol}-ATR", "win", str(client.atr_win))
    client.config.set(f"{symbol}-ATR", "change", str(client.atr_change))
    client.config.set(f"{symbol}-ATR", "earn", str(client.atr_earn))
    client.config.set(f"{symbol}-ATR", "buys", str(client.atr_buys))
    client.config.set(f"{symbol}-ATR", "sells", str(client.atr_sells))
    if abs(trigger) == 11:
        client.config.set(f"{symbol}-ATR", "energy", json.dumps(client.atr_energy))
        client.config.set(f"{symbol}-ATR", "release", json.dumps(client.atr_release))
        client.config.set(f"{symbol}-ATR", "escape", json.dumps(client.atr_escape))
    cost_fill(client, earn, price, deal_amount)


def hf_order_process(client, order_info):
    """
    高频汇率套利下单：将 spec symbol（如 ORDI-OKB）拆成两腿现货交易。
    - buy（做多汇率）= 买 ORDI-USDT + 卖 OKB-USDT → 先卖OKB，再买ORDI
    - sell（做空汇率）= 卖 ORDI-USDT + 买 OKB-USDT → 先卖ORDI，再买OKB
    顺序执行：先卖成功再买；余额不足时跳过。
    """
    from market.MarketMonitor import is_spec_symbol, get_split_symbols, is_spec_swap_symbol, get_split_swap_symbols

    symbol = order_info.symbol
    if is_spec_swap_symbol(symbol):
        symbols = get_split_swap_symbols(symbol)
        is_swap = True
    elif is_spec_symbol(symbol):
        symbols = get_split_symbols(symbol)
        is_swap = False
    else:
        # 不是 spec symbol，走普通流程
        order_process(client, order_info)
        return

    side = order_info.orderType  # 'buy' or 'sell'
    amount = order_info.totalAmount
    market_price = order_info.price  # 汇率
    # 使用 user + order_info.cid 作为前缀，包含用户名和触发类型信息
    # 与普通订单路径一致（OkexClientV5 中 clOrdId = f'{self.user}{my_order_info.cid}'）
    cid = f"{client.user}{order_info.cid}"[:20]  # 截取确保加上S/B+随机ID不超过32字符

    # --- 确定要卖出的币及其余额 ---
    if side == 'sell':
        # 做空汇率：卖 symbols[0]（A币），买 symbols[1]（B币）
        sell_coin = symbols[0].split('-')[0].lower()  # e.g. 'ordi'
        sell_amount = amount  # 卖 A 的数量 = sz
    else:
        # 做多汇率：卖 symbols[1]（B币），买 symbols[0]（A币）
        sell_coin = symbols[1].split('-')[0].lower()  # e.g. 'okb'
        from decimal import Decimal
        sell_amount = float(Decimal(str(amount)) * Decimal(str(market_price)))

    # --- 检查卖出币的余额是否充足 ---
    try:
        result = client.AccountApi.get_account(sell_coin.upper())
        if result.get('code') == '0' and len(result['data'][0].get('details', [])) > 0:
            coin_bal = float(result['data'][0]['details'][0].get('availBal', 0))
        else:
            coin_bal = client.get_coin_num(sell_coin)
        if coin_bal < sell_amount:
            logger.warning(f"[{client.user}]|HF skip: {sell_coin} balance {coin_bal} < need {sell_amount}, wait for next")
            return
    except Exception as e:
        logger.warning(f"[{client.user}]|HF balance check error: {e}, proceeding anyway")

    logger.info(f'[{client.user}]|--- HF order: {side} {symbol} amt={amount} ratio={market_price} cid={cid} -> {symbols} ---')

    try:
        result = client.TradeApi.hf_sequential_swap(
            client.user, side, amount, cid, symbols, market_price, is_swap
        )
        if result is not None and result.get('code') == '0':
            sell_resp = result.get('sell')
            buy_resp = result.get('buy')

            # --- 从两腿响应中提取实际成交价格 ---
            sell_avg_px = 0
            sell_fill_sz = 0
            buy_avg_px = 0
            buy_fill_sz = 0
            sell_fee = 0
            buy_fee = 0

            if sell_resp and client.TradeApi.resp_data(sell_resp):
                sd = sell_resp['data'][0]
                sell_avg_px = float(sd.get('avgPx', 0))
                sell_fill_sz = float(sd.get('accFillSz', 0))
                sell_fee = abs(float(sd.get('fee', 0)))
            if buy_resp and client.TradeApi.resp_data(buy_resp):
                bd = buy_resp['data'][0]
                buy_avg_px = float(bd.get('avgPx', 0))
                buy_fill_sz = float(bd.get('accFillSz', 0))
                buy_fee = abs(float(bd.get('fee', 0)))

            # 计算实际汇率 = A价格 / B价格
            if side == 'sell':
                # 卖A买B → A的sell价 / B的buy价
                actual_ratio = sell_avg_px / buy_avg_px if buy_avg_px > 0 else market_price
            else:
                # 买A卖B → A的buy价 / B的sell价
                actual_ratio = buy_avg_px / sell_avg_px if sell_avg_px > 0 else market_price

            total_fee = sell_fee + buy_fee

            order_info.set_deal_amount(amount)
            order_info.set_avg_price(round(actual_ratio, client.ACCURACY))
            order_info.reset_total_deal_amount(amount)
            order_info.set_fee(total_fee)
            # 设置 orderId 带 [user] 前缀，确保 /log 接口能按用户过滤到 HF 记录
            order_info.set_order_id(f'[{client.user}]HF_{cid}')
            if side == client.TRADE_SELL:
                order_info.set_transaction("plus", client)
            else:
                order_info.set_transaction("minus", client)

            logger.warning(f"[{client.user}]|HF filled: {symbol} {side} amt={amount} "
                           f"ratio={round(actual_ratio, 6)}(target={market_price}) "
                           f"leg1={sell_avg_px}x{sell_fill_sz} leg2={buy_avg_px}x{buy_fill_sz} fee={round(total_fee, 6)}")
            # write_log 移到 runner.py 中 fill_hf_order 之后调用，确保 count 已被正确计算
        else:
            msg = ''
            if result is not None and result.get('data'):
                msg = result['data'][0].get('sMsg', '') if len(result['data']) > 0 else str(result.get('msg', ''))
            logger.error(f"[{client.user}]|HF order failed: {symbol} {side} {amount} {msg}")
    except Exception as e:
        logger.error(f"[{client.user}]|HF order exception: {e}")


def fill_hf_order(client, order_info, trigger):
    """
    高频汇率套利成交后的簿记：
    记录 buys/sells 列表，计算收益（USDT 计价），持久化到 config。
    使用 order_info.avgPrice 作为实际成交汇率（由 hf_order_process 从两腿成交价计算得出）。
    """
    from market.MarketMonitor import marketConfig, safe_get_val as mc_get, \
        is_spec_symbol, get_split_symbols, is_spec_swap_symbol, get_split_swap_symbols

    symbol = client.SYMBOL_T
    # 使用实际成交汇率，而不是 client.currentBase（目标价格）
    actual_ratio = order_info.avgPrice

    # 获取 token B 的 USDT 价格用于收益计算
    if is_spec_swap_symbol(symbol):
        comp = get_split_swap_symbols(symbol)
    elif is_spec_symbol(symbol):
        comp = get_split_symbols(symbol)
    else:
        comp = [symbol]
    b_usdt_price = 1.0
    if len(comp) >= 2:
        try:
            b_usdt_price = float(mc_get(marketConfig, comp[1], "bid1", 1))
        except Exception:
            b_usdt_price = 1.0

    # 更新持仓计数
    deal_amount = order_info.totalDealAmount
    if trigger > 0:
        client.hf_position += deal_amount
    else:
        client.hf_position -= deal_amount
    client.hf_fee += order_info.fee
    client.hf_count += 1

    if abs(trigger) == 20:
        # 开仓 — 记录实际成交汇率和实际手续费
        if trigger == 20:
            client.hf_buys.append([actual_ratio, order_info.fee])
        else:
            client.hf_sells.append([actual_ratio, order_info.fee])

    if abs(trigger) == 21:
        if trigger == 21:
            entry = client.hf_sells.pop()
        else:
            entry = client.hf_buys.pop()
        if isinstance(entry, (list, tuple)):
            open_price, open_fee = entry[0], entry[1]
        else:
            open_price, open_fee = entry, 0
        close_fee = order_info.fee
        total_round_trip_fee = open_fee + close_fee
        ratio_diff = abs(actual_ratio - open_price)
        gross = ratio_diff * deal_amount * b_usdt_price
        net = gross - total_round_trip_fee

        if net < 0:
            # 滑点导致亏损 — 以实际成交价重新入队，拒绝录入亏损
            if trigger > 0:
                client.hf_position -= deal_amount
            else:
                client.hf_position += deal_amount
            new_entry = [actual_ratio, close_fee]
            if trigger == 21:
                client.hf_sells.append(new_entry)
            else:
                client.hf_buys.append(new_entry)
            order_info.count = 0
            logger.warning(f"[{client.user}]{symbol}|HF LOSS PREVENTED: net={round(net, 4)} "
                           f"open={open_price} close={actual_ratio} fee={round(total_round_trip_fee, 4)}, "
                           f"re-enqueued at {actual_ratio}")
        else:
            client.hf_outcome += net
            if net > 0:
                client.hf_win += 1
            order_info.count = round(net, 4)
            logger.warning(f"[{client.user}]{symbol}|HF close: open={open_price} close={order_info.avgPrice} "
                           f"diff={round(ratio_diff, 6)} amt={deal_amount} b_usdt={b_usdt_price} "
                           f"gross={round(gross, 4)} open_fee={round(open_fee, 4)} close_fee={round(close_fee, 4)} "
                           f"net={round(net, 4)} total_P&L={round(client.hf_outcome, 4)}")

    # 排序保持一致（按 price 排序，兼容 [price, fee] 格式）
    client.hf_buys.sort(key=lambda e: e[0] if isinstance(e, list) else e)
    client.hf_buys.reverse()
    client.hf_sells.sort(key=lambda e: e[0] if isinstance(e, list) else e)

    # 持久化
    section = f"{symbol}-HF"
    if not client.config.has_section(section):
        client.config.add_section(section)
    client.config.set(section, "position", str(int(client.hf_position)))
    client.config.set(section, "fee", str(round(client.hf_fee, client.ACCURACY)))
    client.config.set(section, "outcome", str(round(client.hf_outcome, client.ACCURACY)))
    client.config.set(section, "count", str(client.hf_count))
    client.config.set(section, "win", str(client.hf_win))
    client.config.set(section, "buys", str(client.hf_buys))
    client.config.set(section, "sells", str(client.hf_sells))
