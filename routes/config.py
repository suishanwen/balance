import configparser
import json
import os
import time

from flask import Blueprint, request
from module.Logger import logger

from .server_core import (
    FISHNET_PATH, FISHNET_PATH2, HF_DEFAULT_CONFIG, HF_DEFAULT_CONFIG_STR,
    get_config, get_symbol, get_all_symbol, get_stat_symbols,
    is_spec_symbol, is_spec_swap_symbol,
    parse_boolish, normalize_config_value, safe_float,
)
from util.ServerUtil import (
    get_config_text, get_user, require_auth,
    safe_get_val, safe_set_val, write_config, write_config_text, write_keys,
)
from util.DataUtil import safe_get

config_bp = Blueprint('config', __name__)


@config_bp.route('/getConfig', methods=['post'])
@require_auth('r')
def get_config_data():
    user = get_user()
    return get_config_text(f"ok/{user}.ini")


@config_bp.route('/getMultiConfig', methods=['post'])
@require_auth('r')
def get_multi_config_data():
    user = get_user()
    symbols = get_all_symbol()
    stat_symbols = get_stat_symbols()
    config = get_config(user)
    configs = {}
    configs['trade'] = {
        'symbol': symbols,
        'symbolCount': len(symbols),
    }
    configs['notify'] = {
        'type': safe_get_val(config, 'notify', 'type', 'telegram'),
    }
    configs['stat'] = {
        'symbol': stat_symbols,
        'symbolCount': len(stat_symbols),
    }
    for symbol in symbols:
        atr = bool(int(safe_get_val(config, f'{symbol}', 'atr', '0')))
        hf = bool(int(safe_get_val(config, f'{symbol}', 'hf', '0')))
        martin = int(safe_get_val(config, symbol, 'martin', '0'))
        configs[symbol] = {
            'amount': safe_get_val(config, symbol, 'amount', '0'),
            'mode': safe_get_val(config, symbol, 'mode', 'amount'),
            'transaction': safe_get_val(config, symbol, 'transaction', '1'),
            'enlarge': safe_get_val(config, symbol, 'enlarge', '10'),
            'currentbase': safe_get_val(config, symbol, 'currentbase', '0'),
            'percentage': safe_get_val(config, symbol, 'percentage', '3'),
            'earncoin': safe_get_val(config, symbol, 'earncoin', '0'),
            'fee': safe_get_val(config, symbol, 'fee', '0.0003'),
            'pricepatch': safe_get_val(config, symbol, 'pricepatch', '0'),
            'timeout': safe_get_val(config, symbol, 'timeout', '9999'),
            'maoff': parse_boolish(safe_get_val(config, symbol, 'maoff', '0')),
            'precalc': parse_boolish(safe_get_val(config, symbol, 'precalc', '1'), True),
            'kill': safe_get_val(config, symbol, 'kill', ''),
            'kill2': safe_get_val(config, symbol, 'kill2', ''),
            'donotkill': safe_get_val(config, symbol, 'donotkill', '0'),
            'limit': safe_get_val(config, symbol, 'limit', '0'),
            'limit2': safe_get_val(config, symbol, 'limit2', '-10000'),
            'martin': str(martin),
            'cost': safe_get_val(config, symbol, 'cost', '0'),
            'costfill': safe_get_val(config, symbol, 'costfill', '0'),
            'experiment': safe_get_val(config, symbol, 'experiment', '0'),
            'channel': safe_get_val(config, symbol, 'channel', 'bbo-tbt'),
            'resetchannel': safe_get_val(config, symbol, 'resetchannel', '10000'),
            'atr': str(int(atr)),
            'hf': str(int(hf)),
        }
        configs['klines'] = {
            'period': safe_get_val(config, 'klines', 'period', '1s'),
            'size1': safe_get_val(config, 'klines', 'size1', '180'),
            'size2': safe_get_val(config, 'klines', 'size2', '300'),
            'cooldowns': safe_get_val(config, 'klines', 'cooldowns', '15'),
            'mpower': safe_get_val(config, 'klines', 'mpower', '1.3'),
            'superpower': safe_get_val(config, 'klines', 'superpower', '5'),
            'maintain': safe_get_val(config, 'klines', 'maintain', '500'),
        }
        if atr:
            atr_config = json.loads(safe_get_val(config, f'{symbol}-ATR', 'config', '{}'))
            configs[f'{symbol}-ATR'] = {
                'mode': safe_get(atr_config, 'mode', 3),
                'pct': float(safe_get(atr_config, 'pct', 0.02)),
                'size': int(safe_get(atr_config, 'size', 30)),
                'trigger': float(safe_get(atr_config, 'trigger', 1)),
                'win': float(safe_get(atr_config, 'win', 0.5)),
                'profitVsFee': int(safe_get(atr_config, 'profitVsFee', '37')),
                'gapPct': float(safe_get(atr_config, 'gapPct', 1)),
                'charging': int(safe_get(atr_config, 'charging', '0')),
                'buyLimit': int(safe_get(atr_config, 'buyLimit', '99')),
                'sellLimit': int(safe_get(atr_config, 'sellLimit', '99')),
                'oracle': safe_get(atr_config, 'oracle', '!=0'),
                'pass': bool(safe_get(atr_config, 'pass', False)),
                'mode1': safe_get(atr_config, 'mode1', ''),
                'mode2': safe_get(atr_config, 'mode2', ''),
                'buys': json.loads(safe_get_val(config, f'{symbol}-ATR', 'buys', '[]')),
                'sells': json.loads(safe_get_val(config, f'{symbol}-ATR', 'sells', '[]')),
                'position': int(float(safe_get_val(config, f'{symbol}-ATR', 'position', '0'))),
                'avgprice': safe_get_val(config, f'{symbol}-ATR', 'avgprice', '0'),
                'fee': safe_get_val(config, f'{symbol}-ATR', 'fee', '0'),
                'outcome': safe_get_val(config, f'{symbol}-ATR', 'outcome', '0'),
                'count': safe_get_val(config, f'{symbol}-ATR', 'count', '0'),
                'winCount': safe_get_val(config, f'{symbol}-ATR', 'win', '0'),
                'earn': safe_get_val(config, f'{symbol}-ATR', 'earn', '0'),
            }
        if hf:
            hf_config = json.loads(safe_get_val(config, f'{symbol}-HF', 'config', HF_DEFAULT_CONFIG_STR))
            configs[f'{symbol}-HF'] = {
                'lookback': int(safe_get(hf_config, 'lookback', HF_DEFAULT_CONFIG['lookback'])),
                'profitVsFee': float(safe_get(hf_config, 'profitVsFee', HF_DEFAULT_CONFIG['profitVsFee'])),
                'gapPct': float(safe_get(hf_config, 'gapPct', HF_DEFAULT_CONFIG['gapPct'])),
                'trigger': float(safe_get(hf_config, 'trigger', HF_DEFAULT_CONFIG['trigger'])),
                'win': float(safe_get(hf_config, 'win', HF_DEFAULT_CONFIG['win'])),
                'buyLimit': int(safe_get(hf_config, 'buyLimit', HF_DEFAULT_CONFIG['buyLimit'])),
                'sellLimit': int(safe_get(hf_config, 'sellLimit', HF_DEFAULT_CONFIG['sellLimit'])),
                'qLow': float(safe_get(hf_config, 'qLow', HF_DEFAULT_CONFIG['qLow'])),
                'qHigh': float(safe_get(hf_config, 'qHigh', HF_DEFAULT_CONFIG['qHigh'])),
                'pass': bool(safe_get(hf_config, 'pass', HF_DEFAULT_CONFIG['pass'])),
                'minRangePct': float(safe_get(hf_config, 'minRangePct', HF_DEFAULT_CONFIG['minRangePct'])),
                'lookbackMax': int(safe_get(hf_config, 'lookbackMax', HF_DEFAULT_CONFIG['lookbackMax'])),
                'buys': json.loads(safe_get_val(config, f'{symbol}-HF', 'buys', '[]')),
                'sells': json.loads(safe_get_val(config, f'{symbol}-HF', 'sells', '[]')),
                'position': int(float(safe_get_val(config, f'{symbol}-HF', 'position', '0'))),
                'fee': float(safe_get_val(config, f'{symbol}-HF', 'fee', '0')),
                'outcome': float(safe_get_val(config, f'{symbol}-HF', 'outcome', '0')),
                'count': int(float(safe_get_val(config, f'{symbol}-HF', 'count', '0'))),
                'winCount': int(float(safe_get_val(config, f'{symbol}-HF', 'win', '0'))),
            }
        if martin == 1:
            stat_key = f'{symbol}-stat'
            configs[stat_key] = {
                'amount': safe_get_val(config, stat_key, 'amount', '0'),
                'transaction': safe_get_val(config, stat_key, 'transaction', '0'),
                'avgprice': safe_get_val(config, stat_key, 'avgprice', '0'),
                'count': safe_get_val(config, stat_key, 'count', '[]'),
            }
    return configs


def _check_config_change(config_check):
    user = get_user()
    config_old = get_config_text(f"ok/{user}.ini")
    return config_check == config_old


@config_bp.route('/saveConfig', methods=['post'])
@require_auth('w')
def save_config():
    data = json.loads(request.data)
    user = get_user()
    if not _check_config_change(data.get('configCheck')):
        return "2"
    write_config_text(f"ok/{user}.ini", data['config'])
    logger.warning(f"{user} save_config")
    return "1"


@config_bp.route('/multiSaveConfig', methods=['post'])
@require_auth('w')
def multi_save_config():
    data = json.loads(request.data)
    user = get_user()
    config = get_config(user)
    configs = data.get('configs')
    for section in configs:
        if "-ATR" in section:
            atr_config = json.loads(config.get(section, 'config'))
            for option in configs.get(section):
                atr_config[option] = configs.get(section).get(option)
            safe_set_val(config, section, 'config', json.dumps(atr_config))
        elif "-HF" in section:
            hf_config_str = safe_get_val(config, section, 'config', HF_DEFAULT_CONFIG_STR)
            hf_config = json.loads(hf_config_str)
            for option in configs.get(section):
                hf_config[option] = configs.get(section).get(option)
            safe_set_val(config, section, 'config', json.dumps(hf_config))
        else:
            for option in configs.get(section):
                val = normalize_config_value(option, configs.get(section).get(option))
                safe_set_val(config, section, option, val)
    for section in configs:
        if "-ATR" not in section and "-HF" not in section and "-stat" not in section and section != 'klines':
            hf_flag = int(safe_get_val(config, section, 'hf', '0'))
            atr_flag = int(safe_get_val(config, section, 'atr', '0'))
            martin_flag = int(safe_get_val(config, section, 'martin', '0'))
            active = sum([hf_flag, atr_flag, martin_flag])
            if active > 1:
                return json.dumps({"code": "3", "msg": f"{section}: 策略冲突，同一币种只能启用 K线/马丁/ATR/高频 中的一个"})
            limit = safe_float(safe_get_val(config, section, 'limit', '0'))
            limit2 = safe_float(safe_get_val(config, section, 'limit2', '-10000'))
            if limit is not None and limit2 is not None and limit2 > limit:
                return json.dumps({"code": "4", "msg": f"{section}: 持仓下限必须小于或等于持仓上限"})
        elif "-HF" in section:
            hf_config = json.loads(safe_get_val(config, section, 'config', HF_DEFAULT_CONFIG_STR))
            q_low = safe_float(hf_config.get('qLow'))
            q_high = safe_float(hf_config.get('qHigh'))
            if q_low is not None and q_high is not None and q_low >= q_high:
                return json.dumps({"code": "4", "msg": f"{section}: 下界分位数必须小于上界分位数"})
    write_config(f"ok/{user}.ini", config)
    logger.warning(f"{user} multiSaveConfig: {configs}")
    return "1"


@config_bp.route('/addSymbol', methods=['post'])
@require_auth('w')
def add_symbol():
    data = json.loads(request.data)
    user = get_user()
    symbol = data.get('symbol', '').strip()
    if not symbol:
        return "0"
    config = get_config(user)
    symbols = json.loads(safe_get_val(config, 'trade', 'symbol', '[]'))
    if symbol in symbols:
        return "2"
    symbols.append(symbol)
    safe_set_val(config, 'trade', 'symbol', json.dumps(symbols))
    defaults = data.get('defaults', {})
    for k, v in defaults.items():
        safe_set_val(config, symbol, k, str(v))
    if is_spec_symbol(symbol) or is_spec_swap_symbol(symbol):
        safe_set_val(config, symbol, 'hf', '1')
        hf_section = f"{symbol}-HF"
        hf_default = HF_DEFAULT_CONFIG_STR
        if not config.has_section(hf_section):
            config.add_section(hf_section)
        safe_set_val(config, hf_section, 'config', hf_default)
        safe_set_val(config, hf_section, 'position', '0')
        safe_set_val(config, hf_section, 'fee', '0')
        safe_set_val(config, hf_section, 'outcome', '0')
        safe_set_val(config, hf_section, 'count', '0')
        safe_set_val(config, hf_section, 'win', '0')
        safe_set_val(config, hf_section, 'buys', '[]')
        safe_set_val(config, hf_section, 'sells', '[]')
        logger.warning(f"{user} addSymbol: {symbol} (auto HF config)")
    hf_flag = int(safe_get_val(config, symbol, 'hf', '0'))
    atr_flag = int(safe_get_val(config, symbol, 'atr', '0'))
    martin_flag = int(safe_get_val(config, symbol, 'martin', '0'))
    active_count = sum([hf_flag, atr_flag, martin_flag])
    if active_count > 1:
        logger.warning(f"{user} addSymbol: {symbol} has conflicting strategies (hf={hf_flag},atr={atr_flag},martin={martin_flag})")
        return json.dumps({"code": "3", "msg": "策略冲突：同一币种只能启用 K线/马丁/ATR/高频 中的一个"})
    write_config(f"ok/{user}.ini", config)
    logger.warning(f"{user} addSymbol: {symbol}")
    return "1"


@config_bp.route('/hf-defaults', methods=['get', 'post'])
@require_auth('r')
def hf_defaults():
    return json.dumps(HF_DEFAULT_CONFIG)


@config_bp.route('/hf-data', methods=['post'])
@require_auth('r')
def hf_data():
    data = json.loads(request.data) if request.data else {}
    user = get_user()
    symbol = data.get('symbol', '')
    minutes = data.get('minutes')
    seconds = data.get('seconds')
    all_minutes = []
    all_ticks = []
    live = False
    try:
        from trader.app.runner import get_hf_client
        hf_client = get_hf_client(user, symbol)
        if hf_client and hasattr(hf_client, '_hf_tracker'):
            tracker = hf_client._hf_tracker
            all_minutes = list(tracker.data)
            all_ticks = list(tracker.ticks)
            live = True
    except Exception:
        pass
    if not live:
        cache_file = f"{user}_{symbol}_hf_ratio.json"
        if not os.path.exists(cache_file):
            cache_file = f"ok/{user}_{symbol}_hf_ratio.json"
        if not os.path.exists(cache_file):
            return json.dumps({"error": f"no HF data for {symbol}", "file": cache_file})
        try:
            with open(cache_file, 'r') as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                all_minutes = saved.get('minutes', [])
                all_ticks = saved.get('ticks', [])
            else:
                all_minutes = saved
                all_ticks = []
        except Exception as e:
            return json.dumps({"error": str(e)})
    try:
        result = {
            'symbol': symbol, 'user': user,
            'export_time': int(time.time()),
            'minutes_total': len(all_minutes), 'ticks_total': len(all_ticks),
            'live': live,
        }
        if minutes:
            result['minutes'] = all_minutes[-int(minutes):]
        else:
            result['minutes'] = all_minutes
        if seconds:
            cutoff = int(time.time()) - int(seconds)
            result['ticks'] = [(ts, r) for ts, r in all_ticks if ts >= cutoff]
        else:
            result['ticks'] = all_ticks
        if len(all_minutes) > 0:
            all_ratios = [r for _, r in all_minutes]
            mean_r = sum(all_ratios) / len(all_ratios)
            result['stats'] = {
                'min': min(all_ratios), 'max': max(all_ratios),
                'mean': mean_r, 'current': all_ratios[-1],
                'range_pct': (max(all_ratios) - min(all_ratios)) / mean_r * 100 if mean_r > 0 else 0,
            }
        config = get_config(user)
        hf_section = f"{symbol}-HF"
        result['hf_status'] = {
            'position': safe_get_val(config, hf_section, 'position', '0'),
            'fee': safe_get_val(config, hf_section, 'fee', '0'),
            'outcome': safe_get_val(config, hf_section, 'outcome', '0'),
            'count': safe_get_val(config, hf_section, 'count', '0'),
            'win': safe_get_val(config, hf_section, 'win', '0'),
            'buys': safe_get_val(config, hf_section, 'buys', '[]'),
            'sells': safe_get_val(config, hf_section, 'sells', '[]'),
        }
        hf_config_str = safe_get_val(config, hf_section, 'config', HF_DEFAULT_CONFIG_STR)
        result['hf_config'] = json.loads(hf_config_str)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@config_bp.route('/removeSymbol', methods=['post'])
@require_auth('w')
def remove_symbol():
    data = json.loads(request.data)
    user = get_user()
    symbol = data.get('symbol', '').strip()
    if not symbol:
        return "0"
    config = get_config(user)
    symbols = json.loads(safe_get_val(config, 'trade', 'symbol', '[]'))
    if symbol not in symbols:
        return "0"
    symbols.remove(symbol)
    safe_set_val(config, 'trade', 'symbol', json.dumps(symbols))
    write_config(f"ok/{user}.ini", config)
    logger.warning(f"{user} removeSymbol: {symbol}")
    return "1"


@config_bp.route('/trial', methods=['post'])
@require_auth('w')
def trial():
    data = json.loads(request.data)
    user = get_user()
    config = get_config(user)
    symbol = get_symbol()
    if data.get('amount'):
        config.set(symbol, 'amount', data['amount'])
    if data.get('percentage'):
        config.set(symbol, 'percentage', data['percentage'])
    if data.get('limit'):
        config.set(symbol, 'limit', data['limit'])
    write_config(f"ok/{user}.ini", config)
    return "1"


@config_bp.route('/key', methods=['post'])
@require_auth('w')
def key():
    data = json.loads(request.data)
    user = get_user()
    field_mapping = {
        'apiKey': 'API_KEY',
        'secretKey': 'SECRET_KEY',
        'passPhrase': 'PASSPHRASE',
        'dealToken': 'deal_token',
        'reportToken': 'report_token',
        'chatId': 'chat_id',
        'email': 'email',
        'disabled': 'disabled',
    }
    values = {config_key: data[field] for field, config_key in field_mapping.items() if data.get(field)}
    write_keys(user, values)
    return '1'


@config_bp.route('/fishnet', methods=['post'])
@require_auth('w')
def fishnet():
    data = json.loads(request.data)
    user = get_user()
    config = configparser.ConfigParser()
    config.read(FISHNET_PATH)
    logger.warning(f"{user} fishnet data:{data}")
    data.get('start') and config.set(user, 'start', str(data['start']))
    data.get('stop') and config.set(user, 'stop', str(data['stop']))
    data.get('gap') and config.set(user, 'gap', str(data['gap']))
    data.get('fish') and config.set(user, 'fish', str(data['fish']))
    data.get('amount') is not None and config.set(user, 'amount', str(data['amount']))
    data.get('enable') is not None and config.set(user, 'enable', str(data['enable']))
    write_config(FISHNET_PATH, config)
    return "1"


@config_bp.route('/getFishnet', methods=['post'])
@require_auth('r')
def get_fishnet():
    user = get_user()
    config = configparser.ConfigParser()
    config.read(FISHNET_PATH)
    start = stop = gap = fish = amount = enable = 0
    try:
        start = float(config.get(user, 'start'))
        stop = float(config.get(user, 'stop'))
        gap = float(config.get(user, 'gap'))
        fish = float(config.get(user, 'fish'))
        amount = int(config.get(user, 'amount'))
        enable = int(config.get(user, 'enable'))
    except Exception as e:
        logger.warning(f"get_fishnet {e}")
    return {'start': start, 'stop': stop, 'gap': gap, 'fish': fish, 'amount': amount, 'enable': enable}


@config_bp.route('/fishnet2', methods=['post'])
@require_auth('w')
def fishnet2():
    data = json.loads(request.data)['data']
    user = get_user()
    config = configparser.ConfigParser()
    config.read(FISHNET_PATH2)
    safe_set_val(config, user, 'amt', data['amt'])
    safe_set_val(config, user, 'base', data['base'])
    safe_set_val(config, user, 'pct', data['pct'])
    safe_set_val(config, user, 'enable', data['enable'])
    write_config(FISHNET_PATH2, config)
    return "1"


@config_bp.route('/getFishnet2', methods=['post'])
@require_auth('r')
def get_fishnet2():
    user = get_user()
    config = configparser.ConfigParser()
    config.read(FISHNET_PATH2)
    amt = base = pct = enable = 0
    try:
        amt = float(safe_get_val(config, user, 'amt', '0'))
        base = float(safe_get_val(config, user, 'base', '0'))
        pct = float(safe_get_val(config, user, 'pct', '0'))
        enable = int(safe_get_val(config, user, 'enable', '0'))
    except Exception as e:
        logger.warning(f"get_fishnet2 {e}")
    return {'amt': amt, 'base': base, 'pct': pct, 'enable': enable}
