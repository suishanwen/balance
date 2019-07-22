import configparser
import smtplib
import requests
from email.mime.text import MIMEText
from email.header import Header
from util.Logger import logger

# read config
config = configparser.ConfigParser()
config.read("config.ini")
receivers = [config.get("trade", "email")]

token = "905510819:AAHENewu_2fH78tM_aDYXRwaTqCRWhZm9Ck"


def get_chat_id():
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    resp = requests.post(url).json()
    chat_id = resp["result"][0]["message"]["chat"]["id"]
    return chat_id


def send_tg(message):
    chat_id = get_chat_id()
    send_message(message, chat_id)


def send_message(message, chat_id):
    data = {
        "chat_id": chat_id,
        "text": message
    }
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    print(requests.post(url, data=data).json()["ok"])

def notice(order_info):
    order_type = "买入" if order_info.orderType == "buy" else "卖出"
    coin = order_info.symbol.split("_")[0]
    currency = order_info.symbol.split("_")[1]
    message = f"{order_type} {coin} {order_info.totalDealAmount}个，" \
              f"均价 {order_info.avgPrice} {currency},类型 {order_info.trigger}"
    send_tg(message)


def send_email(content, _subtype='plain', _subject="bitcoinrobot"):
    # 第三方 SMTP 服务
    send_tg(content)
    """
    mail_host = "smtp.gmail.com"  # 设置服务器
    mail_user = "controlservice9@gmail.com"  # 用户名
    mail_pass = "pupso7-waXtuz-qitceh"  # 口令

    message = MIMEText(content, _subtype, 'utf-8')
    message['From'] = Header(mail_user)
    message['To'] = Header(",".join(receivers))
    message['Subject'] = Header(_subject)
    try:
        server = smtplib.SMTP_SSL(mail_host, 465)
        server.ehlo()
        server.login(mail_user, mail_pass)
        server.sendmail(mail_user, receivers, message.as_string())
        server.close()
        logger.info("邮件发送成功")
        return True
    except smtplib.SMTPException as err:
        logger.error("Error: 邮件发送失败,{}".format(err))
        return False
    """
