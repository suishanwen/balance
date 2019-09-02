import requests
from module.CfEnv import configBase
from module.Logger import logger

# read config
deal_token = configBase.get("tg_tokens", "deal_token")
daily_report_token = configBase.get("tg_tokens", "report_token")
chat_id = configBase.get("tg_tokens", "chat_id")


def send_telegram(message, is_report=False):
    token = deal_token if not is_report else daily_report_token
    data = {
        "chat_id": chat_id,
        "text": message
    }
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        if requests.post(url, data=data).json()["ok"]:
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"send telegram msg exception:{str(e)}")
        return False
