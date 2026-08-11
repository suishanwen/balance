import requests

from module.Logger import logger


def send_telegram(client, message, is_report=False):
    token = client.deal_token if not is_report else client.report_token
    data = {
        "chat_id": client.chat_id,
        "text": message
    }
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        if requests.post(url, data=data, timeout=(3, 5)).json()["ok"]:
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"send telegram msg exception:{str(e)}")
        return False
