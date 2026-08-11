import json
import os
import threading

PATH = os.environ.get("MARTIN_MESSAGE_PATH", "msgs")
_emit_lock = threading.Lock()


def push_reload(user, symbol=None):
    push_msg(user, 'reload', symbol)


def push_refresh(user):
    push_msg(user, 'refresh')


def push_msg(user, msg, symbol=None):
    data = {"u": user, "m": msg}
    if symbol:
        data["s"] = symbol
    with _emit_lock:
        with open(PATH, 'a') as f:
            f.write(json.dumps(data, ensure_ascii=False) + "@")


def _parse_queued_chunk(chunk):
    chunk = chunk.strip()
    if not chunk:
        return None
    try:
        o = json.loads(chunk)
        u, m = o.get("u"), o.get("m")
        if u is None or m is None:
            return None
        return u, m, o.get("s")
    except (json.JSONDecodeError, TypeError):
        pass
    if "|" in chunk:
        u, m = chunk.split("|", 1)
        return u, m, None
    return None


def _expand_related_symbols(symbol):
    if not symbol:
        return set()
    parts = symbol.split('-')
    related = {symbol}
    if len(parts) == 3 and parts[2] == 'SWAP' and parts[1] not in ('USD', 'USDT'):
        related.add(f"{parts[0]}-USDT-SWAP")
        related.add(f"{parts[1]}-USDT-SWAP")
    elif len(parts) == 2 and parts[1] not in ('BTC', 'ETH', 'USDT'):
        related.add(f"{parts[0]}-USDT")
        related.add(f"{parts[1]}-USDT")
    return related


def _is_related_symbol(message_symbol, target_symbol):
    if not message_symbol or not target_symbol:
        return True
    return bool(_expand_related_symbols(message_symbol) & _expand_related_symbols(target_symbol))


def _collapse_queued_messages(parsed_list):
    """单次 flush 内合并重复通知，避免更新或重启时连续触发多个气泡"""
    users_with_reload = set()
    for u, m, s in parsed_list:
        if m == 'reload' and not s:
            users_with_reload.add(u)
    seen_reload = set()
    seen_refresh = set()
    out = []
    for u, m, s in parsed_list:
        if m == 'reload':
            reload_key = (u, s)
            if reload_key in seen_reload:
                continue
            seen_reload.add(reload_key)
            out.append((u, m, s))
        elif m == 'refresh':
            if u in users_with_reload:
                continue
            if u in seen_refresh:
                continue
            seen_refresh.add(u)
            out.append((u, m, s))
        else:
            out.append((u, m, s))
    final = []
    for item in out:
        if final and final[-1] == item:
            continue
        final.append(item)
    return final


def _write_queued_messages(parsed_list):
    values = []
    for u, m, s in parsed_list:
        data = {"u": u, "m": m}
        if s:
            data["s"] = s
        values.append(json.dumps(data, ensure_ascii=False))
    text = "@".join(values)
    with open(PATH, 'w') as f:
        f.write(f"{text}@" if text else "")


def _should_emit_to_target(user, symbol, target_user, target_symbol):
    return user == target_user and _is_related_symbol(symbol, target_symbol)


def emit_msg(socketio, target_user, target_symbol=None):
    with _emit_lock:
        with open(PATH, 'r') as f:
            msgs = f.read()
        if msgs:
            parsed_list = []
            for raw in msgs.split("@"):
                parsed = _parse_queued_chunk(raw)
                if parsed:
                    parsed_list.append(parsed)
            remaining = []
            for user, m, symbol in _collapse_queued_messages(parsed_list):
                if not _should_emit_to_target(user, symbol, target_user, target_symbol):
                    remaining.append((user, m, symbol))
                    continue
                socketio.emit(user, m, namespace='/market', room=user)
            _write_queued_messages(remaining)
