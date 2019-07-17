import configparser
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from util.Logger import logger

# read config
config = configparser.ConfigParser()
config.read("config.ini")
receivers = [config.get("trade", "email")]


def send_email(content, _subtype='plain', _subject="bitcoinrobot"):
    # 第三方 SMTP 服务
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
