#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

# 添加项目路径以支持导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool.eth_token_balance import EthTokenBalanceChecker

# Plasma 链配置
CHAIN_NAME = "plasma"
ECO_ADDRESS = os.environ.get("XPL_ECO_ADDRESS", "")
PRE_ADDRESS = os.environ.get("XPL_PRE_ADDRESS", "")

# 可改：输出文件名（同目录）
OUTPUT_FILE = os.environ.get("XPL_MONITOR_OUT", os.path.join(
    os.path.dirname(__file__), "..", "xpl_monitor_log.txt"
))
TIMEOUT = float(os.environ.get("XPL_MONITOR_TIMEOUT", "30"))


def fetch_balances() -> Dict[str, Any]:
    """获取 ECO 和 PRE 地址的 XPL 余额"""
    if not ECO_ADDRESS or not PRE_ADDRESS:
        raise RuntimeError("XPL_ECO_ADDRESS 或 XPL_PRE_ADDRESS 未配置")
    checker = EthTokenBalanceChecker(CHAIN_NAME, timeout=int(TIMEOUT))

    # 查询 ECO 地址余额
    eco_balance = checker.get_native_balance(ECO_ADDRESS)

    # 查询 PRE 地址余额
    pre_balance = checker.get_native_balance(PRE_ADDRESS)

    return {
        "eco_address": ECO_ADDRESS,
        "eco_balance": str(eco_balance),
        "pre_address": PRE_ADDRESS,
        "pre_balance": str(pre_balance),
        "chain": CHAIN_NAME
    }


def append_line(payload: Dict[str, Any]) -> None:
    """追加记录到文件"""
    ts = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    payload['ts'] = ts
    # 压缩 JSON，避免换行；保留中文
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    line = f"{compact}\n"
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def monitor() -> int:
    """监控并记录 XPL 余额"""
    try:
        data = fetch_balances()
        append_line(data)

        # 打印到控制台
        print(f"[{data['ts']}] ECO: {data['eco_balance']} XPL | PRE: {data['pre_balance']} XPL")

        return 0
    except Exception as e:
        # 出错也记录一行，便于排查
        ts = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        err_data = {"error": str(e).replace('"', "'")}
        err_data['ts'] = ts
        compact = json.dumps(err_data, ensure_ascii=False, separators=(",", ":"))
        line = f"{compact}\n"
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(line)

        print(f"[{ts}] 错误: {e}", file=sys.stderr)
        return 1
