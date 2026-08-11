import configparser
import os

from module.CfEnv import get_path, configBase
from util.MyUtil import safe_get_val
import api.OkexClientV5 as Client

CONFIGS = {}
for root, dirs, files in os.walk(get_path()):
    for file in files:
        if file.find(".ini") > 0:
            config = configparser.ConfigParser()
            config.read(file)
            user = file.split('.')[0]
            # init apikey,secretkey,passphrase
            api_key = safe_get_val(configBase, user, 'API_KEY')
            seceret_key = safe_get_val(configBase, user, 'SECRET_KEY')
            passphrase = safe_get_val(configBase, user, 'PASSPHRASE')
            deal_token = safe_get_val(configBase, user, 'deal_token')
            report_token = safe_get_val(configBase, user, 'report_token')
            chat_id = safe_get_val(configBase, user, 'chat_id')
            email = safe_get_val(configBase, user, 'email')
            enable = safe_get_val(configBase, user, 'enable')
            disabled = safe_get_val(configBase, user, 'disabled')
            if disabled != '1' and enable == '1':
                period = safe_get_val(config, "klines", "period", "1s")
                size1 = int(safe_get_val(config, "klines", "size1", "180"))
                size2 = int(safe_get_val(config, "klines", "size2", "300"))
                method = safe_get_val(config, "klines", "method", "ws")
                client = Client.OkexClient(user, api_key, seceret_key, passphrase, config, deal_token,
                                           report_token, chat_id, email, None, period, size1, size2,method)
                client.file = file
                CONFIGS[user] = {'config': config, 'client': client}