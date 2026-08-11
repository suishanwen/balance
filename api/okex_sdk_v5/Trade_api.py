import time
import uuid
from decimal import Decimal

import gevent

from module.Logger import logger
from .client import Client
from .consts import *

TAG = 'f924a8c6cc6fBCDE'
OPEN = "OPEN"
CLOSE = "CLOS"
MANUAL = "MANUAL"
FISH = "FISH"


def get_swap_enlarge(symbol):
    if symbol == 'ORDI-USDT-SWAP':
        return Decimal(0.1)
    elif symbol == 'XPL-USDT-SWAP':
        return Decimal(10)
    elif symbol == 'OKB-USDT-SWAP':
        return Decimal(0.01)
    return Decimal(1)


class TradeAPI(Client):

    def __init__(self, api_key, api_secret_key, passphrase, use_server_time=False, flag='0'):
        Client.__init__(self, api_key, api_secret_key, passphrase, use_server_time, flag)

    @classmethod
    def get_random_id(cls):
        return str(uuid.uuid1()).split("-")[0] + str(time.time()).split(".")[1]

    @classmethod
    def resp_data(cls, resp):
        return resp is not None and resp.get('code') == "0" and len(resp['data']) > 0

    @classmethod
    def resp_filled(cls, resp):
        return cls.resp_data(resp) and resp['data'][0]['state'] == 'filled'

    @classmethod
    def req_timeout(cls, resp):
        return resp is not None and (resp.get('code') == "50004" or resp.get('code') == "50013")

    @classmethod
    def not_exist(cls, resp):
        return resp is not None and resp.get('code') == "51603"

    # Place Order
    def place_order(self, user, instId, tdMode, side, ordType, sz, posSide='', px='', cid=''):
        params = {'instId': instId, 'tdMode': tdMode, 'side': side, 'ordType': ordType, 'sz': sz, 'ccy': '',
                  'clOrdId': f"{cid}{self.get_random_id()}".upper()[0:32], 'tag': TAG, 'posSide': posSide, 'px': px,
                  'reduceOnly': '',
                  'tgtCcy': ''}
        # return self._request_with_params(POST, PLACR_ORDER, params, timeout=(15, 15))
        return self.safe_make_order(user, params)

    # Place Order
    def place_instant_order(self, user, instId, tdMode, side, sz, posSide='', cid=''):
        params = {'instId': instId, 'tdMode': tdMode, 'side': side, 'ordType': 'market', 'sz': sz, 'ccy': '',
                  'clOrdId': cid, 'tag': TAG, 'posSide': posSide, 'px': '',
                  'reduceOnly': '',
                  'tgtCcy': ''}
        # return self._request_with_params(POST, PLACR_ORDER, params, timeout=(15, 15))
        return self.safe_make_order(user, params)

    # Place Multiple Orders
    def place_orders_tt(self, user, instId, tdMode, side, ordType, sz, posSide='', px='',
                        pft=1, adjust=False, cost=0, cid=''):
        # 统一 Decimal
        px = Decimal(str(px))
        pft = Decimal(str(pft))
        sz = Decimal(str(sz))
        cost = Decimal(str(cost))

        rev_side = 'buy' if side == 'sell' else 'sell'

        # diff 计算
        if 'USD-SWAP' in instId and "fish" not in cid:
            diff = pft * px * px / (sz * Decimal(10))
        elif 'USDT-SWAP' in instId and "fish" not in cid:
            diff = px * pft * Decimal('0.01')
        else:
            diff = pft

        # 计算收益 earn
        earn = diff / px * sz * Decimal('0.996')
        if cost > px:
            earn = int((earn * cost / (cost - px)).to_integral_value())
        else:
            earn = int(earn.to_integral_value())

        # 调整仓位
        ord_sz = int(sz + earn) if adjust and not 'USDT-SWAP' in instId and side == 'sell' else int(sz)
        rev_sz = int(sz + earn) if adjust and not 'USDT-SWAP' in instId and rev_side == 'sell' else int(sz)

        rnd = self.get_random_id()

        # ---- 第1单：开仓 ----
        param1 = {
            'instId': instId, 'tdMode': tdMode, 'side': side, 'ordType': ordType,
            'sz': ord_sz, 'ccy': '',
            'clOrdId': f"{cid}{OPEN}{rnd}".upper()[0:32],
            'tag': TAG, 'posSide': posSide, 'px': '', 'reduceOnly': '', 'tgtCcy': ''
        }

        order1 = self.safe_make_order(user, param1)
        if not self.resp_data(order1):
            logger.warning(f"[{user}]|place_orders_tt order1 failed:{order1}")
            return order1

        # 获取成交均价
        try:
            avg_price = Decimal(str(order1['data'][0]['avgPx']))
        except Exception:
            avg_price = px

        # ---- 第2单：反向平仓 ----
        rev_px = avg_price + diff if rev_side == 'sell' else avg_price - diff
        # 不做 round，保持完整精度
        rev_px_str = format(rev_px.normalize(), 'f')

        param2 = {
            'instId': instId,
            'tdMode': tdMode,
            'side': rev_side,
            'ordType': 'limit',
            'sz': rev_sz,
            'ccy': '',
            'clOrdId': f"{cid}{CLOSE}{rnd}".upper()[0:32],
            'tag': TAG,
            'posSide': posSide,
            'px': rev_px_str,  # Decimal 直接转字符串
            'reduceOnly': '',
            'tgtCcy': ''
        }

        order2 = None
        for i in range(4):
            order2 = self.safe_make_order(user, param2)
            if self.resp_data(order2):
                break
            logger.warning(f"[{user}]|place_orders_tt order2 failed:{order2}-> {rev_px_str}, retry...({i + 1})")
            gevent.sleep(0.1)

        if self.resp_data(order2):
            logger.info(f"[{user}]rev {rev_px} {rev_side} {rev_sz}")  # 日志直接输出完整价格
        else:
            logger.warning(f"[{user}]rev {rev_px} {rev_side} {rev_sz} failed!")

        return order2

    # Place Multiple Orders
    def batch_swap(self, side, sz, cid, symbols):
        param1 = {'instId': symbols[0], 'tdMode': 'cross', 'side': side, 'ordType': 'market', 'sz': sz, 'ccy': '',
                  'clOrdId': f"{cid}{self.get_random_id()}".upper()[0:32], 'tag': TAG, 'posSide': '', 'px': '',
                  'reduceOnly': '', 'tgtCcy': ''}
        rev_sz = int(sz / 10) if 'BTC' in symbols[1] or 'ETH' in symbols[1] else sz
        param2 = {'instId': symbols[1], 'tdMode': 'cross', 'side': 'buy' if side == 'sell' else 'sell',
                  'ordType': 'market',
                  'sz': rev_sz, 'ccy': '', 'clOrdId': f"{cid}{self.get_random_id()}".upper()[0:32], 'tag': TAG,
                  'posSide': '', 'px': '', 'reduceOnly': '',
                  'tgtCcy': ''}
        return self._request_with_params(POST, BATCH_ORDERS, [param1, param2], timeout=(15, 15))

    def batch_swap2(self, user, side, sz, cid, symbols):
        if side == 'sell':
            param = {'instId': symbols[0], 'tdMode': 'cash', 'side': 'sell', 'ordType': 'market', 'sz': sz, 'ccy': '',
                     'clOrdId': f"{cid}{self.get_random_id()}".upper()[0:32], 'tag': TAG, 'posSide': '', 'px': '',
                     'reduceOnly': '', 'tgtCcy': 'base_ccy'}
            resp = self.safe_make_order(user, param)
            if self.resp_data(resp):
                sz = float(resp['data'][0]['accFillSz']) * float(resp['data'][0]['avgPx']) + float(
                    resp['data'][0]['fee'])
                param = {'instId': symbols[1], 'tdMode': 'cash', 'side': 'buy',
                         'ordType': 'market', 'sz': sz, 'ccy': '',
                         'clOrdId': f"{cid}{self.get_random_id()}".upper()[0:32], 'tag': TAG, 'posSide': '', 'px': '',
                         'reduceOnly': '', 'tgtCcy': 'quote_ccy'}
                resp = self.safe_make_order(user, param)
        else:
            param = {'instId': symbols[1], 'tdMode': 'cash', 'side': 'sell',
                     'ordType': 'market', 'sz': sz, 'ccy': '',
                     'clOrdId': f"{cid}{self.get_random_id()}".upper()[0:32], 'tag': TAG, 'posSide': '', 'px': '',
                     'reduceOnly': '', 'tgtCcy': 'base_ccy'}
            resp = self.safe_make_order(user, param)
            if self.resp_data(resp):
                sz = float(resp['data'][0]['accFillSz']) * float(resp['data'][0]['avgPx']) + float(
                    resp['data'][0]['fee'])
                param = {'instId': symbols[0], 'tdMode': 'cash', 'side': 'buy',
                         'ordType': 'market', 'sz': sz, 'ccy': '',
                         'clOrdId': f"{cid}{self.get_random_id()}".upper()[0:32], 'tag': TAG, 'posSide': '', 'px': '',
                         'reduceOnly': '', 'tgtCcy': 'quote_ccy'}
                resp = self.safe_make_order(user, param)
        return resp

    def hf_sequential_swap(self, user, side, sz, cid, symbols, r12, swap=False):
        """
        高频顺序互换（先卖后买，确保卖成功再买）：
        - side='sell' -> 卖 symbols[0]，用所得 USDT 买 symbols[1]
        - side='buy'  -> 卖 symbols[1]，用所得 USDT 买 symbols[0]
        返回 dict: {'sell': sell_resp, 'buy': buy_resp, 'code': '0'/'‑1'}
        """
        if swap:
            tdMode = 'cross'
            tgtCcy_sell = ''
            tgtCcy_buy = ''
        else:
            tdMode = 'cash'
            tgtCcy_sell = 'base_ccy'
            tgtCcy_buy = 'quote_ccy'

        from decimal import Decimal, ROUND_DOWN, getcontext
        getcontext().prec = 28
        q1 = Decimal(str(sz))
        r12d = Decimal(str(r12))

        if side == 'sell':
            # 卖 symbols[0]，买 symbols[1]
            sell_inst = symbols[0]
            buy_inst = symbols[1]
            sell_sz = sz
        else:
            # 卖 symbols[1]，买 symbols[0]
            sell_inst = symbols[1]
            buy_inst = symbols[0]
            if swap:
                q1e = get_swap_enlarge(symbols[0])
                q2e = get_swap_enlarge(symbols[1])
                sell_sz = int((q1 * q1e * r12d / q2e).quantize(Decimal('1'), rounding=ROUND_DOWN))
            else:
                sell_sz = float((q1 * r12d).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))

        # --- 第一步：卖出 ---
        sell_param = {
            'instId': sell_inst, 'tdMode': tdMode, 'side': 'sell', 'ordType': 'market',
            'sz': sell_sz, 'ccy': '',
            'clOrdId': f"{cid}S{self.get_random_id()}".upper()[:32], 'tag': TAG,
            'posSide': '', 'px': '', 'reduceOnly': '', 'tgtCcy': tgtCcy_sell
        }
        logger.info(f"[{user}]|HF seq sell: {sell_inst} sz={sell_sz}")
        sell_resp = self.safe_make_order(user, sell_param)

        if not self.resp_data(sell_resp):
            logger.error(f"[{user}]|HF seq sell failed: {sell_resp}")
            return {'code': '-1', 'data': [], 'msg': 'sell leg failed'}

        # --- 第二步：用卖出所得买入 ---
        sell_data = sell_resp['data'][0]
        if swap:
            # 合约：直接用计算好的数量
            if side == 'sell':
                q2e = get_swap_enlarge(symbols[1])
                q1e = get_swap_enlarge(symbols[0])
                buy_sz = int((q1 * q1e * r12d / q2e).quantize(Decimal('1'), rounding=ROUND_DOWN))
            else:
                buy_sz = sz
        else:
            # 现货：用卖出所得的 USDT 去买
            proceeds = float(sell_data.get('accFillSz', 0)) * float(sell_data.get('avgPx', 0))
            fee = abs(float(sell_data.get('fee', 0)))
            usdt_available = proceeds - fee
            buy_sz = round(usdt_available, 2)  # USDT 精度
            logger.info(f"[{user}]|HF seq sell done, proceeds={proceeds:.4f} fee={fee:.4f} -> buy {buy_inst} with {buy_sz} USDT")

        buy_param = {
            'instId': buy_inst, 'tdMode': tdMode, 'side': 'buy', 'ordType': 'market',
            'sz': buy_sz, 'ccy': '',
            'clOrdId': f"{cid}B{self.get_random_id()}".upper()[:32], 'tag': TAG,
            'posSide': '', 'px': '', 'reduceOnly': '', 'tgtCcy': tgtCcy_buy
        }
        logger.info(f"[{user}]|HF seq buy: {buy_inst} sz={buy_sz}")
        buy_resp = self.safe_make_order(user, buy_param)

        if not self.resp_data(buy_resp):
            logger.error(f"[{user}]|HF seq buy failed: {buy_resp} (sell already done!)")

        return {
            'code': '0',
            'data': buy_resp.get('data', []) if buy_resp else [],
            'sell': sell_resp,
            'buy': buy_resp,
        }

    def m_batch_swap2(self, user, side, sz, cid, symbols, r12, swap=False, fee_bps=10, slip_bps=5):
        from decimal import Decimal, getcontext, ROUND_DOWN
        getcontext().prec = 28

        """
        批量现货互换（两腿同批提交；字段保持原样）：
        - symbols[0] = inst1, symbols[1] = inst2（同一计价货币）
        - r12 = px1 / px2（只知道价格比）
        - 约束：无论买还是卖 inst1，inst1 的下单数量 == 传入 sz
        - 手续费与滑点都用乘法因子：
            买入端：价格 × (1 + slip) 且 数量需覆盖 (1 + fee)
            卖出端：价格 × (1 - slip) 且 卖出所得打折 (1 - fee)
          这才是“用价格换算”的正确方式
        """

        # ---- 参数转 Decimal ----
        q1 = Decimal(str(sz))  # inst1 下单数量（固定为入参）
        r12d = Decimal(str(r12))
        if r12d <= 0:
            raise ValueError("r12 must be > 0")

        f = Decimal(str(fee_bps)) / Decimal('10000')  # 手续费率
        s = Decimal(str(slip_bps)) / Decimal('10000')  # 滑点率

        # 保护：避免分母为 0
        one = Decimal('1')
        buy_num = (one + f) * (one + s)  # 买入端放大因子
        sell_denom = (one - f) * (one - s)  # 卖出端折价因子
        if sell_denom <= 0:
            raise ValueError("fee_bps/slip_bps too large, (1 - fee)*(1 - slip) <= 0")

        # === 正确的价格换算公式（用 r = p1/p2 抵消绝对价）===
        # 1) 卖 inst1、买 inst2（side == 'sell'）：
        #    inst2_buy_qty = q1 * r12 * [ 卖出端(1-f)(1-s) / 买入端(1+f)(1+s) ]
        # 2) 买 inst1、卖 inst2（side != 'sell'）：
        #    inst2_sell_qty = q1 * r12 * [ 买入端(1+f)(1+s) / 卖出端(1-f)(1-s) ]
        if side == 'sell':


            # 第二腿：买 inst2 的“基币数量”（base_ccy）
            if swap:
                q1e = get_swap_enlarge(symbols[0])
                q2e = get_swap_enlarge(symbols[1])
                inst2_buy_qty = int(
                    (q1 * q1e * r12d * sell_denom / buy_num / q2e).quantize(Decimal('0.00000001'),
                                                                            rounding=ROUND_DOWN))
                tgtCcy = ''
                tdMode = 'cross'
            else:
                inst2_buy_qty = float((q1 * r12d * sell_denom / buy_num).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
                tgtCcy = 'base_ccy'
                tdMode = 'cash'
            # 第一腿：卖 inst1 == symbols[0]，数量固定为 q1
            p1 = {'instId': symbols[0], 'tdMode': tdMode, 'side': 'sell', 'ordType': 'market', 'sz': sz, 'ccy': '',
                  'clOrdId': f"{cid}{self.get_random_id()}".upper()[:32], 'tag': TAG, 'posSide': '', 'px': '',
                  'reduceOnly': '', 'tgtCcy': tgtCcy}
            p2 = {'instId': symbols[1], 'tdMode': tdMode, 'side': 'buy', 'ordType': 'market',
                  'sz': inst2_buy_qty, 'ccy': '',
                  'clOrdId': f"{cid}{self.get_random_id()}".upper()[:32], 'tag': TAG, 'posSide': '', 'px': '',
                  'reduceOnly': '', 'tgtCcy': tgtCcy}

        else:
            # 第一腿：卖 inst2（为买 inst1 筹资）
            if swap:
                q1e = get_swap_enlarge(symbols[0])
                q2e = get_swap_enlarge(symbols[1])
                inst2_sell_qty = int(
                    (q1 * q1e * r12d * buy_num / sell_denom / q2e).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
                tgtCcy = ''
                tdMode = 'cross'
            else:
                inst2_sell_qty = float((q1 * r12d * buy_num / sell_denom).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN))
                tgtCcy = 'base_ccy'
                tdMode = 'cash'
            p1 = {'instId': symbols[1], 'tdMode': tdMode, 'side': 'sell', 'ordType': 'market',
                  'sz': inst2_sell_qty, 'ccy': '',
                  'clOrdId': f"{cid}{self.get_random_id()}".upper()[:32], 'tag': TAG, 'posSide': '', 'px': '',
                  'reduceOnly': '', 'tgtCcy': tgtCcy}

            # 第二腿：买 inst1，数量固定为 q1（入参 sz）
            p2 = {'instId': symbols[0], 'tdMode': tdMode, 'side': 'buy', 'ordType': 'market', 'sz': sz, 'ccy': '',
                  'clOrdId': f"{cid}{self.get_random_id()}".upper()[:32], 'tag': TAG, 'posSide': '', 'px': '',
                  'reduceOnly': '', 'tgtCcy': tgtCcy}

        # 批量一次提交（字段完全不变）
        return self._request_with_params(POST, BATCH_ORDERS, [p1, p2], timeout=(15, 15))

    def safe_make_order(self, user, param):
        cl_ord_id = param['clOrdId'] if param['clOrdId'] != '' else self.get_random_id()
        param['clOrdId'] = cl_ord_id
        param['tag'] = TAG
        resp = None
        exp = False
        try:
            logger.info(f"[{user}]|safe_make_order,param: {param}")
            resp = self._request_with_params(POST, PLACR_ORDER, param, timeout=(15, 15))
            if not self.resp_data(resp):
                logger.warning(f"[{user}]|safe_make_order,resp: {resp}")
        except TimeoutError as e:
            logger.warning(f"[{user}]|order timeout: {e}")
            exp = True
        except Exception as e:
            logger.warning(f"[{user}]|order exp: {e}")
            exp = True
        check = 60 if exp or self.req_timeout(resp) else 30
        resp = self.check_order(user, param['instId'], cl_ord_id, check)
        return resp

    def check_order(self, user, inst_id, cl_ord_id, check=1):
        resp = None
        for i in range(check):
            try:
                resp = self.get_orders(inst_id, '', cl_ord_id)
            except Exception as e:
                logger.warning(f"[{user}]|safe_make_order,check({i + 1}) exp: {e}")
            if self.resp_data(resp):
                return resp
            if self.not_exist(resp):
                logger.warning(f"[{user}]|safe_make_order,check({i + 1}) order not exist: {resp}")
                return resp
            logger.warning(f"[{user}]|safe_make_order,check({i + 1}) retry: {resp}")
        return resp

    # Place Multiple Orders
    def place_multiple_orders_tt(self, user, instId, tdMode, side, ordType, sz, posSide='', px='', pft=1,
                                 adjust=False, cost=0, cid=''):
        # 转 Decimal
        px = Decimal(str(px))
        pft = Decimal(str(pft))
        sz = Decimal(str(sz))
        cost = Decimal(str(cost))

        rnd = self.get_random_id()

        # 计算 diff
        if 'USD-SWAP' in instId:
            diff = pft * px * px / (sz * Decimal(10))
        elif 'USDT-SWAP' in instId:
            diff = px * pft * Decimal('0.01')
        else:
            diff = pft

        rev_side = 'buy' if side == 'sell' else 'sell'

        # 计算反向价格 rev_px，不 round
        rev_px = px + diff if side == 'buy' else px - diff

        # 计算收益 earn
        earn = diff / rev_px * sz * Decimal('0.998')
        if cost > rev_px:
            earn = int((earn * cost / (cost - rev_px)).to_integral_value())
        else:
            earn = int(earn.to_integral_value())

        # 调整仓位
        ord_sz = int(sz + earn) if adjust and not 'USDT-SWAP' in instId and side == 'sell' else int(sz)
        rev_sz = int(sz + earn) if adjust and not 'USDT-SWAP' in instId and rev_side == 'sell' else int(sz)

        # 第一笔订单参数
        param1 = {
            'instId': instId,
            'tdMode': tdMode,
            'side': side,
            'ordType': ordType,
            'sz': ord_sz,
            'ccy': '',
            'clOrdId': f'{cid}{OPEN}{rnd}'.upper()[0:32],
            'tag': TAG,
            'posSide': posSide,
            'px': format(px.normalize(), 'f'),  # 不用科学计数法
            'reduceOnly': '',
            'tgtCcy': ''
        }

        # 第二笔订单参数
        param2 = {
            'instId': instId,
            'tdMode': tdMode,
            'side': rev_side,
            'ordType': ordType,
            'sz': rev_sz,
            'ccy': '',
            'clOrdId': f'{cid}{CLOSE}{rnd}'.upper()[0:32],
            'tag': TAG,
            'posSide': posSide,
            'px': format(rev_px.normalize(), 'f'),  # 不用科学计数法
            'reduceOnly': '',
            'tgtCcy': ''
        }

        # 日志直接打印完整 Decimal
        logger.warning(f"[{user}] - [{px} {side} {ord_sz}, {rev_px} {rev_side} {rev_sz}]")

        return self._request_with_params(POST, BATCH_ORDERS, [param1, param2], timeout=(15, 15))

    # Place Multiple Orders
    def place_multiple_orders(self, orders_data):
        return self._request_with_params(POST, BATCH_ORDERS, orders_data, timeout=(15, 15))

    # Cancel Order
    def cancel_order(self, instId, ordId='', clOrdId=''):
        params = {'instId': instId, 'ordId': ordId, 'clOrdId': clOrdId}
        return self._request_with_params(POST, CANAEL_ORDER, params)

    # Cancel Multiple Orders
    def cancel_multiple_orders(self, orders_data):
        return self._request_with_params(POST, CANAEL_BATCH_ORDERS, orders_data)

    # Amend Order
    def amend_order(self, instId, cxlOnFail='', ordId='', clOrdId='', reqId='', newSz='', newPx=''):
        params = {'instId': instId, 'cxlOnFailc': cxlOnFail, 'ordId': ordId, 'clOrdId': clOrdId, 'reqId': reqId,
                  'newSz': newSz,
                  'newPx': newPx}
        return self._request_with_params(POST, AMEND_ORDER, params)

    # Amend Multiple Orders
    def amend_multiple_orders(self, orders_data):
        return self._request_with_params(POST, AMEND_BATCH_ORDER, orders_data)

    # Close Positions
    def close_positions(self, instId, mgnMode, posSide='', ccy=''):
        params = {'instId': instId, 'mgnMode': mgnMode, 'posSide': posSide, 'ccy': ccy}
        return self._request_with_params(POST, CLOSE_POSITION, params)

    # Get Order Details
    def get_orders(self, instId, ordId='', clOrdId=''):
        params = {'instId': instId, 'ordId': ordId, 'clOrdId': clOrdId}
        return self._request_with_params(GET, ORDER_INFO, params)

    # Get Order List
    def get_order_list(self, instType='', uly='', instId='', ordType='', state='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordType': ordType, 'state': state,
                  'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_PENDING, params)

    # Get Order History (last 7 days）
    def get_orders_history(self, instType, uly='', instId='', ordType='', state='', after='', before='', begin='',
                           end='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordType': ordType, 'state': state,
                  'after': after, 'before': before, 'begin': begin, 'end': end, 'limit': limit}
        return self._request_with_params(GET, ORDERS_HISTORY, params)

    # Get Order History (last 3 months)
    def orders_history_archive(self, instType, uly='', instId='', ordType='', state='', after='', before='', begin='',
                               end='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordType': ordType, 'state': state,
                  'after': after, 'before': before, 'begin': begin, 'end': end, 'limit': limit}
        return self._request_with_params(GET, ORDERS_HISTORY_ARCHIVE, params)

    # Get Transaction Details
    def get_fills(self, instType='', uly='', instId='', ordId='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordId': ordId, 'after': after, 'before': before,
                  'limit': limit}
        return self._request_with_params(GET, ORDER_FILLS, params)

    # Place Algo Order
    def place_algo_order(self, instId, tdMode, side, ordType, sz, ccy='', posSide='', reduceOnly='', tpTriggerPx='',
                         tpOrdPx='', slTriggerPx='', slOrdPx='', triggerPx='', orderPx='', tgtCcy='', pxVar='',
                         pxSpread='',
                         szLimit='', pxLimit='', timeInterval='', ):
        params = {'instId': instId, 'tdMode': tdMode, 'side': side, 'ordType': ordType, 'sz': sz, 'ccy': ccy,
                  'posSide': posSide, 'reduceOnly': reduceOnly, 'tpTriggerPx': tpTriggerPx, 'tpOrdPx': tpOrdPx,
                  'slTriggerPx': slTriggerPx, 'slOrdPx': slOrdPx, 'triggerPx': triggerPx, 'orderPx': orderPx,
                  'tgtCcy': tgtCcy, 'pxVar': pxVar, 'szLimit': szLimit, 'pxLimit': pxLimit,
                  'timeInterval': timeInterval,
                  'pxSpread': pxSpread}
        return self._request_with_params(POST, PLACE_ALGO_ORDER, params)

    # Cancel Algo Order
    def cancel_algo_order(self, params):
        return self._request_with_params(POST, CANCEL_ALGOS, params)

    # Cancel Advance Algos
    def cancel_advance_algos(self, params):
        return self._request_with_params(POST, Cancel_Advance_Algos, params)

    # Get Algo Order List
    def order_algos_list(self, ordType, algoId='', instType='', instId='', after='', before='', limit=''):
        params = {'ordType': ordType, 'algoId': algoId, 'instType': instType, 'instId': instId, 'after': after,
                  'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_ALGO_OENDING, params)

    # Get Algo Order History
    def order_algos_history(self, ordType, state='', algoId='', instType='', instId='', after='', before='', limit=''):
        params = {'ordType': ordType, 'state': state, 'algoId': algoId, 'instType': instType, 'instId': instId,
                  'after': after, 'before': before, 'limit': limit}
        return self._request_with_params(GET, ORDERS_ALGO_HISTORY, params)

    # Get Transaction Details History
    def get_fills_history(self, instType, uly='', instId='', ordId='', after='', before='', limit=''):
        params = {'instType': instType, 'uly': uly, 'instId': instId, 'ordId': ordId, 'after': after, 'before': before,
                  'limit': limit}
        return self._request_with_params(GET, ORDERS_FILLS_HISTORY, params)
