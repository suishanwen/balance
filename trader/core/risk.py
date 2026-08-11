
import operator
import re

from trader.services.logging import logger
from trader.services.notifier import send_msg
from util.MyUtil import user_killed

_OPS = {'<=': operator.le, '>=': operator.ge, '<': operator.lt, '>': operator.gt, '==': operator.eq}
_COND_RE = re.compile(r'^([<>=!]+)(.+)$')


def _eval_condition(value, condition):
    m = _COND_RE.match(condition)
    if not m:
        return False
    op_func = _OPS.get(m.group(1))
    if not op_func:
        return False
    return op_func(float(value), float(m.group(2)))


def kill_checker(client, buy, sell, symbol):
    wait = False
    if _eval_condition(buy, client.kill) or _eval_condition(buy, client.kill2):
        if client.doNotKill:
            wait = True
        else:
            user_killed(client.user)
            logger.warning(f"[{client.user}] {symbol} killed at buy:{buy},sell:{sell} ")
            send_msg(client, f"{symbol} killed at buy:{buy},sell:{sell} ")
            exit()
    return wait
