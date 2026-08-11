import copy
import json
import os

import gevent

from trader.app.bootstrap import start
from market.MarketMonitor import start_kline_task, start_depth_task, start_market_task, depth_task_symbols
from module.tsignal import set_user_signal
from util.MyUtil import safe_get_val, safe_set_val, write_config

if __name__ == '__main__':
    from module.CfEnv import configBase, get_marker_user_path
    from module.ClientReader import CONFIGS

    tasks = []
    market_user = os.environ.get("MARTIN_MARKET_USER", "")
    if not market_user or market_user not in CONFIGS:
        raise RuntimeError("MARTIN_MARKET_USER 未配置或对应账户未启用")
    market_entry = CONFIGS.pop(market_user)
    market_client = market_entry['client']
    market_config = market_entry['config']
    clients = []
    for user in CONFIGS:
        config = CONFIGS[user]['config']
        client = CONFIGS[user]['client']
        enable = safe_get_val(configBase, user, 'enable')
        disabled = safe_get_val(configBase, user, 'disabled')
        symbols = json.loads(safe_get_val(config, "trade", "symbol", '["LTC-USD-SWAP"]'))
        if disabled != '1' and enable == '1':
            for symbol in symbols:
                _client = copy.copy(client)
                _client.set_symbol(symbol,config)
                start_depth_task(_client)
                start_kline_task(_client)
                main_task = gevent.spawn(start, _client, )
                tasks.append(main_task)
                clients.append(_client)
    safe_set_val(market_config, 'trade', 'ignore', json.dumps(depth_task_symbols))
    safe_set_val(market_config, 'signal', 'pid', str(os.getpid()))
    safe_set_val(market_config, 'signal', 'update', str(0))
    write_config(get_marker_user_path(), market_config)
    monitor_task = gevent.spawn(start_market_task, market_client, )
    tasks.append(monitor_task)
    set_user_signal(market_client, clients)
    # 启动K线、深度线程
    gevent.joinall(tasks)
