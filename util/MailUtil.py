import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from module.Logger import logger


def send_email(client, content, _subtype='plain', _subject="bitcoinrobot"):
    mail_host = os.environ.get("SMTP_HOST", "")
    mail_user = os.environ.get("SMTP_USER", "")
    mail_pass = os.environ.get("SMTP_PASSWORD", "")
    if not mail_host or not mail_user or not mail_pass:
        logger.warning("MailUtil#send_email SMTP 未配置")
        return False
    receivers = [client.email]
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
        logger.info("MailUtil#send_email 邮件发送成功")
        return True
    except smtplib.SMTPException as err:
        logger.error("MailUtil#send_email 邮件发送失败 err:%s", err)
        return False
