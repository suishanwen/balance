import json
import math
import os
import time
from bisect import bisect_left

from trader.services.logging import logger


class RatioTracker:
    """汇率历史追踪器 - 支持秒级和分钟级双精度，文件持久化"""

    def __init__(self, max_minutes=10080, max_seconds=7200, cache_file=None):
        self.max_minutes = max_minutes
        # 用 list 而非 deque：读多写少，切片与二分需要随机访问
        self.data = []
        self.last_minute = 0
        self.max_seconds = max_seconds
        self.ticks = []
        self.last_second = 0
        self.cache_file = cache_file
        self._save_counter = 0
        if cache_file:
            self._load(cache_file)

    def _load(self, path):
        """从文件加载历史汇率数据"""
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    records = saved.get('minutes', [])
                    tick_records = saved.get('ticks', [])
                else:
                    records = saved
                    tick_records = []
                cutoff_min = int(time.time()) - self.max_minutes * 60
                cutoff_sec = int(time.time()) - self.max_seconds
                for ts, ratio in records:
                    if ts >= cutoff_min:
                        self.data.append((ts, ratio))
                for ts, ratio in tick_records:
                    if ts >= cutoff_sec:
                        self.ticks.append((ts, ratio))
                self._trim()
                if self.data:
                    self.last_minute = self.data[-1][0] // 60
                if self.ticks:
                    self.last_second = self.ticks[-1][0]
                logger.info(f"HF tracker loaded {len(self.data)} min + {len(self.ticks)} tick records from {path}")
        except Exception as e:
            logger.warning(f"HF tracker load failed: {e}")

    def _trim(self):
        """丢弃超出容量上限的最旧记录，只保留最新的 max_minutes / max_seconds 条"""
        if len(self.data) > self.max_minutes:
            del self.data[:len(self.data) - self.max_minutes]
        if len(self.ticks) > self.max_seconds:
            del self.ticks[:len(self.ticks) - self.max_seconds]

    def save(self):
        """持久化汇率数据到文件（分钟+秒级）"""
        if not self.cache_file:
            return
        try:
            with open(self.cache_file, 'w') as f:
                json.dump({
                    'minutes': list(self.data),
                    'ticks': list(self.ticks)
                }, f)
        except Exception as e:
            logger.warning(f"HF tracker save failed: {e}")

    def update(self, ratio):
        """每秒记录tick，每分钟记录分钟级，每 2 分钟自动持久化"""
        now = int(time.time())
        if now > self.last_second:
            self.ticks.append((now, ratio))
            self._trim()
            self.last_second = now
        minute = now // 60
        if minute > self.last_minute:
            self.data.append((now, ratio))
            self._trim()
            self.last_minute = minute
            self._save_counter += 1
            if self._save_counter >= 2:
                self._save_counter = 0
                self.save()

    def get_recent(self, minutes):
        """获取最近 N 分钟的汇率数据"""
        return self.data[-minutes:] if minutes else list(self.data)

    def get_recent_ticks(self, seconds):
        """获取最近 N 秒的秒级tick数据；ticks 按时间升序，二分定位起点避免全量扫描"""
        cutoff = int(time.time()) - seconds
        return self.ticks[bisect_left(self.ticks, (cutoff,)):]

    def get_momentum(self, window=30):
        """
        计算短期动量（最近 window 秒的平均变化率）。
        返回 (direction, speed, volatility)
        """
        recent = self.get_recent_ticks(window)
        if len(recent) < 5:
            return 0, 0, 0
        ratios = [r for _, r in recent]
        first = ratios[0]
        last = ratios[-1]
        direction = last - first
        speed = abs(direction) / len(ratios) if len(ratios) > 0 else 0
        mean = sum(ratios) / len(ratios)
        variance = sum((r - mean) ** 2 for r in ratios) / len(ratios)
        volatility = math.sqrt(variance) if variance > 0 else 0
        return direction, speed, volatility

    def get_micro_atr(self, window=60):
        """计算秒级微ATR（最近 window 秒的平均绝对变化）"""
        recent = self.get_recent_ticks(window)
        if len(recent) < 10:
            return 0
        changes = [abs(recent[i][1] - recent[i - 1][1]) for i in range(1, len(recent))]
        return sum(changes) / len(changes) if changes else 0

    def get_export_data(self, minutes=None, seconds=None):
        """导出数据用于外部分析/策略优化"""
        result = {
            'export_time': int(time.time()),
            'minutes_total': len(self.data),
            'ticks_total': len(self.ticks),
        }
        if minutes:
            result['minutes'] = self.get_recent(minutes)
        else:
            result['minutes'] = list(self.data)
        if seconds:
            result['ticks'] = self.get_recent_ticks(seconds)
        else:
            result['ticks'] = list(self.ticks)
        if len(self.data) > 0:
            all_ratios = [r for _, r in self.data]
            result['stats'] = {
                'min': min(all_ratios),
                'max': max(all_ratios),
                'mean': sum(all_ratios) / len(all_ratios),
                'current': all_ratios[-1],
                'range_pct': (max(all_ratios) - min(all_ratios)) / (sum(all_ratios) / len(all_ratios)) * 100
                    if sum(all_ratios) > 0 else 0,
            }
        return result
