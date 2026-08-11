import datetime
import hashlib
import json
import os
import time

import orjson
import pytz

file_key = {}

TAIL_CHUNK_SIZE = 64 * 1024


def _split_tail_segment(raw):
    """产出该段内的行（自新到旧），\r\n 与单独 \r 均按行终止符处理，行尾统一为 \n"""
    if raw.endswith(b'\r'):
        raw = raw[:-1]
    return [part.decode('utf-8') + '\n' for part in reversed(raw.split(b'\r'))]


def iter_lines_backward(file, chunk_size=TAIL_CHUNK_SIZE):
    """从文件尾部按块回读并逐行产出，避免逐行反向读取的高额单行开销"""
    with open(file, 'rb') as f:
        pos = f.seek(0, os.SEEK_END)
        if pos == 0:
            return
        tail = b''
        end_trimmed = False
        while pos > 0:
            step = min(chunk_size, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + tail
            if not end_trimmed:
                end_trimmed = True
                # 文件末尾的换行符不构成额外空行
                if buf.endswith(b'\n'):
                    buf = buf[:-1]
            parts = buf.split(b'\n')
            # 首段可能被块边界截断，留到下一块拼接后再产出
            tail = parts[0]
            for part in reversed(parts[1:]):
                yield from _split_tail_segment(part)
        yield from _split_tail_segment(tail)


ORDER_PROPS = ['instId', 'ordId', 'clOrdId', 'cTime', 'uTime', 'px', 'avgPx', 'side', 'sz', 'accFillSz', 'fee',
               'feeCcy', 'state']


def get_log(user, file):
    with open(file, encoding="utf-8") as f:
        lines = []
        while len(lines) < 1000:
            line = f.readline()
            if not line:
                break
            if line.find(f"[{user}]") != -1:
                lines.append(line)
    return "<br/>".join(lines)


def get_all(file):
    with open(file, encoding="utf-8") as f:
        lines = []
        while True:
            line = f.readline()
            if not line:
                break
            lines.append(json.loads(line))
    return lines


def get_log_b(file):
    lines = []
    key_error = False
    for line in iter_lines_backward(file):
        if "failed with KeyError" in line:
            key_error = True
        if key_error:
            if "Traceback" in line:
                key_error = False
                lines.append("*keyError*")
        elif line.strip():
            lines.append(line)
        if len(lines) >= 1000:
            break
    return "<br/>".join(lines)


def get_last_line(file):
    for line in iter_lines_backward(file):
        return line
    return ''


def get_last_lines(file, offset):
    orders = []
    for line in iter_lines_backward(file):
        if len(line.strip()) == 0:
            break
        order = orjson.loads(line)
        orders.append(order)
        if int(order[4]) < offset:
            break
    return orders


def sha256(content=None):
    if content is None:
        return ''
    sha256gen = hashlib.sha256()
    sha256gen.update(content.encode())
    return sha256gen.hexdigest()


def get_file_key(file):
    if file_key.get(file) is None:
        file_key[file] = sha256(file)
    return file_key.get(file)


def from_time_stamp(seconds=0):
    if seconds == 0:
        seconds = int(time.time())
    return datetime.datetime.fromtimestamp(seconds, pytz.timezone('Asia/Shanghai')).strftime(
        '%Y-%m-%d %H:%M:%S')


def get_year_month_day(seconds=0):
    if seconds == 0:
        seconds = int(time.time())
    return datetime.datetime.fromtimestamp(seconds, pytz.timezone('Asia/Shanghai')).strftime(
        '%Y-%m-%d')


def get_today_ts():
    today = datetime.date.today()
    return int(time.mktime(today.timetuple())) * 1000


def safe_get(obj, key, default):
    return obj[key] if obj.get(key) is not None else default


def copy_obj(data):
    obj = {}
    for prop in ORDER_PROPS:
        obj[prop] = data[prop]
    return obj


def order_to_log(data):
    obj = []
    for prop in ORDER_PROPS:
        obj.append(from_time_stamp(int(int(data['uTime']) / 1000)) if prop == 'instId' else data[prop])
    return json.dumps(obj)


def log_to_order(symbol, data):
    data = orjson.loads(data)
    obj = {'instId': symbol}
    for i in range(1, len(ORDER_PROPS)):
        obj[ORDER_PROPS[i]] = data[i]
    return obj


def is_result_data(result):
    return result is not None and result.get('code') == "0" and result.get('data') and len(result.get('data')) > 0
