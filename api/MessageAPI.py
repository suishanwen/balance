import requests

from module.Logger import logger


class MessageAPI:

    def __init__(self, deal_token, report_token, chat_id):
        self.deal_token = deal_token
        self.report_token = report_token
        self.chat_id = chat_id

    def send(self, message, is_report=False):
        token = self.deal_token if not is_report else self.report_token

        data = {
            "chat_id": self.chat_id,
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
