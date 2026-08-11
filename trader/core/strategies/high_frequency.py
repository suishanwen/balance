"""
高频汇率套利策略 - Cross Pair High Frequency Arbitrage

策略原理：
两个币之间的汇率在一个区间内来回波动（如 ORDI-OKB），
记录汇率的历史波动，识别高低点，在低点买入A卖出B、高点卖出A买入B，来回倒腾套利。

实际操作：
- 交易对 ORDI-OKB 时，实际拆成两笔交易：
  - 买入方向：买 ORDI-USDT + 卖 OKB-USDT（做多汇率）
  - 卖出方向：卖 ORDI-USDT + 买 OKB-USDT（做空汇率）

融入现有 ATR 体系，复用 atr 配置和 runner 逻辑。

优化：
- 秒级汇率追踪（RatioTracker 支持秒/分钟双精度）
- 动量检测（短期趋势方向和速度）
- 波动率自适应触发（实时 ATR 调节开仓阈值）
- 数据导出接口（get_export_data）
"""

import time
import operator
import re

from trader.services.logging import logger
from trader.core.strategies.ratio_tracker import RatioTracker


# HF 策略默认配置 — 唯一权威定义，config.py / server.py 均引用此处
HF_DEFAULT_CONFIG = {
    "lookback": 120,       # 回看窗口（分钟）
    "profitVsFee": 1.5,    # 利润/手续费倍数（一轮2腿费用，实际门槛=fee*此值*2）
    "gapPct": 0.8,         # 加仓间距 %
    "trigger": 0.3,        # 触发位置（0~1）越小越容易触发
    "win": 0.3,            # 止盈回撤（0~1）越大越快止盈
    "buyLimit": 99,        # 最大做多层数
    "sellLimit": 99,       # 最大做空层数
    "qLow": 0.15,          # 下界分位数
    "qHigh": 0.85,         # 上界分位数
    "pass": False,          # 数据不足仍交易
    "minRangePct": 0.003,  # 最小区间百分比（0.3%），防止平盘时完全停滞
    "lookbackMax": 0,      # 自适应最大回看窗口，0=lookback*3
}

_OPS = {
    '>=': operator.ge, '<=': operator.le,
    '>': operator.gt, '<': operator.lt,
    '==': operator.eq, '!=': operator.ne,
}
_ORACLE_RE = re.compile(r'^([><=!]{1,2})\s*(-?\d+(?:\.\d+)?)$')


def _oracle_check(oracle):
    return _OPS[oracle['op']](oracle['actual'], oracle['target'])


def _oracle_match(trigger, oracle_str):
    m = _ORACLE_RE.match(str(oracle_str).strip())
    if not m:
        return True
    op_str, val_str = m.groups()
    op_fn = _OPS.get(op_str)
    if not op_fn:
        return True
    return op_fn(trigger, float(val_str))


def _hf_price(entry):
    return entry[0] if isinstance(entry, (list, tuple)) else entry



def detect_range(ratios, quantile_low=0.15, quantile_high=0.85):
    """
    根据历史汇率数据检测波动区间。
    用分位数而非简单最大最小值，避免极端值干扰。

    Args:
        ratios: 汇率列表
        quantile_low: 低分位数（默认15%）
        quantile_high: 高分位数（默认85%）

    Returns:
        (low, high, mid): 区间低点、高点、中位
    """
    if len(ratios) < 20:
        return None, None, None
    sorted_r = sorted(ratios)
    n = len(sorted_r)
    low = sorted_r[int(n * quantile_low)]
    high = sorted_r[int(n * quantile_high)]
    mid = sorted_r[n // 2]
    return low, high, mid


def get_hf_trigger(client, buy, sell):
    """
    高频汇率套利触发器（兼容 ATR 接口，可直接在 runner.py 中替换 get_atr_trigger）。

    利用 is_spec_symbol 的交易对（如 ORDI-OKB），
    它的 depth bid1/ask1 已经由 MarketMonitor 的 set_t1_t2 合成好了。

    优化点：
    - 平仓优先：有仓位时，只要达到最小利润就平仓（覆盖 fee * profitVsFee 即可）
    - 开仓更灵敏：trigger 控制在区间内的偏离比例，不再叠加额外的 spread*factor 偏移
    - 动量过滤更温和：只在极端速度时跳过，避免 micro_atr=0 时误杀
    - 秒级 tick 驱动，保证数据鲜活

    Args:
        client: 客户端对象（需要 hf_config 配置）
        buy: 当前买一价（bid1，即卖出汇率的成交价）
        sell: 当前卖一价（ask1，即买入汇率的成交价）

    Returns:
        (trigger, next_buy_p, next_sell_p, ma, open_price):
            trigger: 20=买入(做多), -20=卖出(做空), -21=平多, 21=平空, 0=无操作
            next_buy_p / next_sell_p: 目标价格
            ma: 汇率中位数
            open_price: 开仓价格
    """
    hf_config = client.hf_config
    symbol = client.SYMBOL_T

    # --- 初始化追踪器 ---
    if not hasattr(client, '_hf_tracker'):
        cache_file = f"{client.user}_{client.SYMBOL_T}_hf_ratio.json"
        client._hf_tracker = RatioTracker(cache_file=cache_file)
        logger.warning(f"[{client.user}]{client.SYMBOL_T}|HF tracker initialized, cache={cache_file}")

    tracker = client._hf_tracker
    mid_ratio = (buy + sell) / 2
    tracker.update(mid_ratio)

    # --- 配置参数 ---
    lookback = hf_config.get("lookback", HF_DEFAULT_CONFIG["lookback"])
    profit_vs_fee = float(hf_config.get("profitVsFee", HF_DEFAULT_CONFIG["profitVsFee"]))
    gap_pct = hf_config.get("gapPct", HF_DEFAULT_CONFIG["gapPct"]) / 100
    buy_limit = hf_config.get("buyLimit", HF_DEFAULT_CONFIG["buyLimit"])
    sell_limit = hf_config.get("sellLimit", HF_DEFAULT_CONFIG["sellLimit"])
    q_low = hf_config.get("qLow", HF_DEFAULT_CONFIG["qLow"])
    q_high = hf_config.get("qHigh", HF_DEFAULT_CONFIG["qHigh"])
    hf_pass = hf_config.get("pass", HF_DEFAULT_CONFIG["pass"])
    trigger_factor = float(hf_config.get("trigger", HF_DEFAULT_CONFIG["trigger"]))
    win_factor = float(hf_config.get("win", HF_DEFAULT_CONFIG["win"]))
    min_range_pct = float(hf_config.get("minRangePct", HF_DEFAULT_CONFIG["minRangePct"]))
    lookback_max_cfg = int(hf_config.get("lookbackMax", HF_DEFAULT_CONFIG["lookbackMax"]))
    lookback_max = lookback_max_cfg if lookback_max_cfg > 0 else lookback * 3

    hf_buys = client.hf_buys
    hf_sells = client.hf_sells

    # --- 计算汇率波动区间（融合分钟+秒级数据，提高精度） ---
    recent = tracker.get_recent(lookback)
    ratios = [r[1] for r in recent]
    # 融合最近5分钟的秒级tick数据，让区间检测更敏感
    recent_ticks = tracker.get_recent_ticks(300)
    tick_ratios = [r[1] for r in recent_ticks]
    combined_ratios = ratios + tick_ratios
    if len(combined_ratios) > 0:
        combined_ratios.append(mid_ratio)
    range_low, range_high, ma = detect_range(combined_ratios, q_low, q_high)

    # --- 秒级动量和微ATR ---
    momentum_dir, momentum_speed, momentum_vol = tracker.get_momentum(30)
    micro_atr = tracker.get_micro_atr(60)

    # 数据不足
    if range_low is None:
        ma = mid_ratio
        if not hf_pass:
            client.hf_info = f"HF:数据积累中({len(combined_ratios)}/20) tick={len(tracker.ticks)}"
            client.buyRate = client.sellRate = 0
            return 0, mid_ratio, mid_ratio, ma, None
        range_low = mid_ratio * 0.995
        range_high = mid_ratio * 1.005

    spread = range_high - range_low

    # --- 最小区间保底：防止平盘时 spread 缩到 0 导致永不交易 ---
    min_range = ma * min_range_pct
    if spread < min_range:
        spread = min_range
        range_low = ma - spread / 2
        range_high = ma + spread / 2

    # --- 获取组件币种 USDT 价格（用于费用计算和平仓阈值） ---
    from market.MarketMonitor import marketConfig as _mc, safe_get_val as _mc_get, \
        is_spec_swap_symbol as _is_spec_swap, get_split_swap_symbols as _get_swap_syms, \
        is_spec_symbol as _is_spec, get_split_symbols as _get_syms
    _comp = _get_swap_syms(symbol) if _is_spec_swap(symbol) else _get_syms(symbol) if _is_spec(symbol) else [symbol]
    _b_usdt_px = 1.0
    if len(_comp) >= 2:
        try:
            _b_usdt_px = float(_mc_get(_mc, _comp[1], "bid1", 1))
        except Exception:
            _b_usdt_px = 1.0
    _deal_amt = max(client.amount, 0.01)

    # --- 估算实际手续费率 ---
    # 优先从最近一次开仓的实际手续费(USDT)反推真实费率
    # 如果没有历史数据，则使用 client.fee
    actual_fee_rate = client.fee
    _recent_fee_entries = hf_buys + hf_sells
    if len(_recent_fee_entries) > 0:
        _last_entry = _recent_fee_entries[-1]
        if isinstance(_last_entry, (list, tuple)) and len(_last_entry) > 1 and _last_entry[1] > 0:
            _last_open_fee = _last_entry[1]  # USDT fee for 2 legs (open)
            # 估算 A 币 USDT 价格
            _a_comp = _comp[0] if len(_comp) >= 1 else symbol
            try:
                _a_px = float(_mc_get(_mc, _a_comp, "bid1", 0))
            except Exception:
                _a_px = 0
            if _a_px > 0 and _deal_amt > 0:
                # 2 legs notional: sell A + buy B ≈ 2 * amount * A_price
                _est_notional = 2 * _deal_amt * _a_px
                actual_fee_rate = _last_open_fee / _est_notional if _est_notional > 0 else client.fee
                actual_fee_rate = max(actual_fee_rate, client.fee)  # 不低于配置值

    # --- 最小可盈利价差检查 ---
    # HF 一次完整交易：开仓1次（A+B两腿）+ 平仓1次（A+B两腿）= 2次交易手续费
    # actual_fee_rate 是单次交易手续费率（已包含两腿），所以乘 2
    min_profit_pct = actual_fee_rate * profit_vs_fee * 2
    min_spread = ma * min_profit_pct
    if spread < min_spread:
        # --- 自适应回看窗口：被阻塞时尝试扩大窗口寻找更大波动 ---
        now_ts = int(time.time())
        if not hasattr(client, '_hf_blocked_since'):
            client._hf_blocked_since = now_ts
        blocked_sec = now_ts - client._hf_blocked_since
        # 被阻塞超过60秒，尝试扩大回看窗口
        if blocked_sec > 60 and lookback < lookback_max:
            # 按阻塞时间逐步扩大：每被阻塞1分钟额外加50%原始窗口
            expand_factor = 1 + min(blocked_sec / 60, (lookback_max / lookback - 1))
            expanded_lookback = min(int(lookback * expand_factor), lookback_max)
            if expanded_lookback > lookback:
                expanded_recent = tracker.get_recent(expanded_lookback)
                expanded_ratios = [r[1] for r in expanded_recent] + tick_ratios + [mid_ratio]
                e_low, e_high, e_ma = detect_range(expanded_ratios, q_low, q_high)
                if e_low is not None:
                    e_spread = max(e_high - e_low, min_range)
                    if e_spread >= min_spread:
                        # 扩大窗口成功找到足够波动
                        range_low, range_high, ma = e_low, e_high, e_ma
                        spread = e_spread
                        if not hasattr(client, '_hf_last_expand_log') or now_ts - client._hf_last_expand_log > 300:
                            logger.info(f"[{client.user}]{symbol}|HF 自适应扩窗 {lookback}->{expanded_lookback}min "
                                        f"spread={round(e_spread, 6)}({round(e_spread/e_ma*100, 3)}%)")
                            client._hf_last_expand_log = now_ts
                        client._hf_blocked_since = now_ts  # 重置阻塞计时
        # 扩窗后仍然不够
        if spread < min_spread:
            spread_pct = round(spread / ma * 100, 4) if ma > 0 else 0
            min_pct = round(min_profit_pct * 100, 4)
            client.hf_info = f"HF:价差不足 {spread_pct}%<{min_pct}% fee={round(actual_fee_rate, 6)} blk={blocked_sec}s"
            # 节流日志：每5分钟输出一次警告
            if not hasattr(client, '_hf_last_barrier_log') or now_ts - client._hf_last_barrier_log > 300:
                logger.warning(f"[{client.user}]{symbol}|HF 价差阻塞: spread={round(spread, 6)}({spread_pct}%) "
                               f"< min={round(min_spread, 6)}({min_pct}%) fee={round(actual_fee_rate, 6)} "
                               f"pvf={profit_vs_fee} lookback={lookback} data={len(ratios)}min blocked={blocked_sec}s")
                client._hf_last_barrier_log = now_ts
            client.buyRate = client.sellRate = 0
            return 0, mid_ratio, mid_ratio, ma, None
        # 通过了检查，重置阻塞计时
        if hasattr(client, '_hf_blocked_since'):
            del client._hf_blocked_since
    else:
        # 未阻塞，重置计时
        if hasattr(client, '_hf_blocked_since'):
            del client._hf_blocked_since

    # --- 计算开仓价格和平仓价格 ---
    # trigger_factor 表示从 MA 偏离 spread 的比例才开仓
    # 例如 trigger=0.5 → MA ± spread*0.25 处开仓
    half_trigger = spread * trigger_factor / 2
    open_buy_price = round(ma - half_trigger, client.ACCURACY)     # 做多开仓价（低点买入）
    open_sell_price = round(ma + half_trigger, client.ACCURACY)    # 做空开仓价（高点卖出）

    # win_factor 表示从开仓价回到 MA 的比例时平仓
    # 例如 win=0.3 → 开仓后回撤 spread*0.15 就平仓（回归 MA 方向）
    half_win = spread * win_factor / 2
    close_buy_price = round(open_buy_price + half_win, client.ACCURACY)    # 做多平仓价（向 MA 回归）
    close_sell_price = round(open_sell_price - half_win, client.ACCURACY)  # 做空平仓价（向 MA 回归）

    # 动量指示器字符
    m_arrow = '↑' if momentum_dir > 0 else '↓' if momentum_dir < 0 else '→'

    micro_atr_str = f" μATR:{round(micro_atr, client.ACCURACY)}" if micro_atr > 0 else ""
    client.hf_info = f"HF R:{round(range_low, client.ACCURACY)}-{round(range_high, client.ACCURACY)} MA:{round(ma, client.ACCURACY)} S:{round(spread, client.ACCURACY)} T:{round(open_buy_price, client.ACCURACY)}/{round(open_sell_price, client.ACCURACY)} {m_arrow}{micro_atr_str}"

    # --- 构建候选信号 ---
    # 优先级：平仓 > 开仓（保护利润优先）
    close_oracles = []
    open_oracles = []


    # ===== 平多仓信号：汇率上涨到止盈价 =====
    if len(hf_buys) > 0:
        last_buy_entry = hf_buys[-1]
        last_buy = _hf_price(last_buy_entry)
        open_fee_val = last_buy_entry[1] if isinstance(last_buy_entry, (list, tuple)) and len(last_buy_entry) > 1 else 0
        slippage_buffer = last_buy * 0.001
        if open_fee_val > 0 and _b_usdt_px > 0:
            est_round_trip_fee = open_fee_val * 2 * 1.5
            min_ratio_diff = est_round_trip_fee / (_deal_amt * _b_usdt_px)
            min_close_price = last_buy + min_ratio_diff + slippage_buffer
        else:
            min_close_price = last_buy * (1 + client.fee * 2 * 2.0) + slippage_buffer
        target_close = max(min_close_price, close_buy_price)
        close_oracles.append({
            "trigger": -11, "exp": f"{buy}>={target_close}",
            "actual": buy, "op": ">=", "target": target_close,
            "ext": last_buy, "distance": abs(buy - target_close), "p": target_close
        })

    # ===== 平空仓信号：汇率下跌到止盈价 =====
    if len(hf_sells) > 0:
        last_sell_entry = hf_sells[-1]
        last_sell = _hf_price(last_sell_entry)
        open_fee_val = last_sell_entry[1] if isinstance(last_sell_entry, (list, tuple)) and len(last_sell_entry) > 1 else 0
        slippage_buffer = last_sell * 0.001
        if open_fee_val > 0 and _b_usdt_px > 0:
            est_round_trip_fee = open_fee_val * 2 * 1.5
            min_ratio_diff = est_round_trip_fee / (_deal_amt * _b_usdt_px)
            max_close_price = last_sell - min_ratio_diff - slippage_buffer
        else:
            max_close_price = last_sell * (1 - client.fee * 2 * 2.0) - slippage_buffer
        target_close = min(max_close_price, close_sell_price)
        close_oracles.append({
            "trigger": 11, "exp": f"{sell}<={target_close}",
            "actual": sell, "op": "<=", "target": target_close,
            "ext": last_sell, "distance": abs(sell - target_close), "p": target_close
        })

    # ===== 开多仓信号：汇率下跌到区间低点 =====
    if len(hf_buys) < buy_limit:
        target_open = open_buy_price
        # 如果已有多仓，新开仓需要间距 gap_pct
        if len(hf_buys) > 0:
            gap_price = _hf_price(hf_buys[-1]) * (1 - gap_pct)
            target_open = min(target_open, gap_price)
        open_oracles.append({
            "trigger": 10, "exp": f"{sell}<={target_open}",
            "actual": sell, "op": "<=", "target": target_open,
            "ext": None, "distance": abs(sell - target_open), "p": target_open
        })

    # ===== 开空仓信号：汇率上涨到区间高点 =====
    if len(hf_sells) < sell_limit:
        target_open = open_sell_price
        # 如果已有空仓，新开仓需要间距 gap_pct
        if len(hf_sells) > 0:
            gap_price = _hf_price(hf_sells[-1]) * (1 + gap_pct)
            target_open = max(target_open, gap_price)
        open_oracles.append({
            "trigger": -10, "exp": f"{buy}>={target_open}",
            "actual": buy, "op": ">=", "target": target_open,
            "ext": None, "distance": abs(buy - target_open), "p": target_open
        })

    # --- 合并信号列表（平仓优先） ---
    oracles = close_oracles + open_oracles

    if len(oracles) == 0:
        client.hf_info += " | NO_ORACLE"
        client.buyRate = client.sellRate = 0
        return 0, mid_ratio, mid_ratio, ma, None

    # --- oracle 过滤 ---
    if hf_config.get("oracle") is not None:
        oracles = list(filter(
            lambda x: _oracle_match(x['trigger'], hf_config.get('oracle')) or abs(x['trigger']) == 11,
            oracles
        ))
        if len(oracles) == 0:
            client.buyRate = client.sellRate = 0
            return 0, mid_ratio, mid_ratio, ma, None

    # --- 选择触发信号（平仓优先） ---
    trigger = 0
    result = None

    # 先检查平仓信号是否满足条件
    for oracle in close_oracles:
        if oracle in oracles and _oracle_check(oracle):
            result = oracle
            trigger = oracle["trigger"]
            break

    # 再检查开仓信号
    if trigger == 0:
        for oracle in open_oracles:
            if oracle in oracles and _oracle_check(oracle):
                result = oracle
                trigger = oracle["trigger"]
                break

    # 没有触发的信号，取距离最近的（用于显示下一个触发目标）
    if not result:
        oracles = sorted(oracles, key=lambda x: x['distance'])
        result = oracles[0]

    if result["trigger"] > 0:
        client.buyRate = 1
    else:
        client.sellRate = 1

    # HF 用 20/-20/21/-21 以区分 ATR 的 10/-10/11/-11
    if trigger != 0:
        trigger = trigger + 10 if trigger > 0 else trigger - 10

    return trigger, round(result["p"], client.ACCURACY), round(result["p"], client.ACCURACY), ma, result["ext"]


def get_hf_export_data(client, minutes=None, seconds=None):
    """导出HF策略数据（供外部分析/策略优化）"""
    if not hasattr(client, '_hf_tracker'):
        return {"error": "tracker not initialized"}
    tracker = client._hf_tracker
    data = tracker.get_export_data(minutes, seconds)
    # 附加策略状态
    data['symbol'] = client.SYMBOL_T
    data['user'] = client.user
    data['hf_config'] = client.hf_config
    data['hf_buys'] = client.hf_buys
    data['hf_sells'] = client.hf_sells
    data['hf_position'] = client.hf_position
    data['hf_outcome'] = client.hf_outcome
    data['hf_count'] = client.hf_count
    data['hf_win'] = client.hf_win
    data['hf_fee'] = client.hf_fee
    # 动量快照
    momentum_dir, momentum_speed, momentum_vol = tracker.get_momentum(30)
    micro_atr = tracker.get_micro_atr(60)
    data['momentum'] = {
        'direction': momentum_dir,
        'speed': momentum_speed,
        'volatility': momentum_vol,
        'micro_atr': micro_atr,
    }
    return data
