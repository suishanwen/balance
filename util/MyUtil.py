import datetime
import smtplib
from email.mime.text import MIMEText
from email.header import Header


def hasattr(dict, args):
    return args in dict.keys()


def fromDict(dict, *args):
    for a in args:
        dict = dict[a]
    return dict


def fromTimeStamp(timeStamp):
    return datetime.datetime.fromtimestamp(float(timeStamp))


def sendEmail(content):
    # 第三方 SMTP 服务
    mail_host = "smtp.sina.com"  # 设置服务器
    mail_user = "controlservice@sina.com"  # 用户名
    mail_pass = "a123456"  # 口令

    sender = 'controlservice@sina.com'
    receivers = ['suishanwen@icloud.com']  # 接收邮件，可设置为你的QQ邮箱或者其他邮箱

    message = MIMEText(content, 'plain', 'utf-8')
    message['From'] = Header("controlservice@sina.com")
    message['To'] = Header("my-email")
    message['Subject'] = Header('我的爬虫通知')
    try:
        smtpObj = smtplib.SMTP()
        smtpObj.connect(mail_host, 25)  # 25 为 SMTP 端口号
        smtpObj.login(mail_user, mail_pass)
        smtpObj.sendmail(sender, receivers, message.as_string())
        print("邮件发送成功")
    except smtplib.SMTPException as err:
        print(err)
        print("Error: 邮件发送失败")
