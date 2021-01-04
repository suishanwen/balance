import configparser
from module.CfEnv import config
from util.MailUtil import send_email
from util.TelegramUtil import send_telegram
from module.Logger import logger
try:
    notify_type = config.get("notify", "type")
except (configparser.NoOptionError, configparser.NoSectionError):
    notify_type = "telegram"

MSG_TYPE_DEAL = 1
MSG_TYPE_REPORT = 2


def send_msg(message, msg_type=MSG_TYPE_DEAL):
    logger.info("send statistic message")
    if notify_type == "telegram":
        return send_telegram(message, msg_type == MSG_TYPE_REPORT)
    else:
        return send_email(message)
