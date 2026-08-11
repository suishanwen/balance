from module.Logger import logger
from util.MailUtil import send_email
from util.TelegramUtil import send_telegram

MSG_TYPE_DEAL = 1
MSG_TYPE_REPORT = 2


def send_msg(client, message, msg_type=MSG_TYPE_DEAL):
    logger.info(f"[{client.user}] send message")
    if client.notify_type == "telegram":
        return send_telegram(client, message, msg_type == MSG_TYPE_REPORT)
    else:
        return send_email(client, message)
