import datetime
import smtplib
import time
import configparser
import json
from email.mime.text import MIMEText
from email.header import Header


def has_attr(_dict, args):
    return args in _dict.keys()


def from_dict(_dict, *args):
    for a in args:
        _dict = _dict[a]
    return _dict


def from_time_stamp(time_stamp):
    return datetime.datetime.fromtimestamp(float(time_stamp))


def send_email(content, _subtype='plain', _subject="bitcoinrobot", sender_no=1):
    senders = ("controlservice2@sina.com", "controlservice@sina.com")
    # 第三方 SMTP 服务
    mail_host = "smtp.sina.com"  # 设置服务器
    mail_user = senders[sender_no]  # 用户名
    mail_pass = "a123456"  # 口令

    sender = senders[sender_no]
    receivers = ['suishanwen@icloud.com']  # 接收邮件，可设置为你的QQ邮箱或者其他邮箱

    message = MIMEText(content, _subtype, 'utf-8')
    message['From'] = Header(senders[sender_no])
    message['To'] = Header("my-email")
    message['Subject'] = Header(_subject)
    try:
        smtp_obj = smtplib.SMTP()
        smtp_obj.connect(mail_host, 25)  # 25 为 SMTP 端口号
        smtp_obj.login(mail_user, mail_pass)
        smtp_obj.sendmail(sender, receivers, message.as_string())
        print("邮件发送成功")
        return True
    except smtplib.SMTPException as err:
        print(err)
        print("Error: 邮件发送失败,{}".format(err))
        if sender_no == 1 and str(err).find("550") != -1:
            send_email(content, _subtype, _subject, 2)
        return False


def write_log(text=""):
    s = open('log.txt').read()
    mm = str(from_time_stamp(int(time.time())))[0:7]
    if s.find(mm) != -1:
        f = open(r'log.txt', 'w')
        f.write(text + "\n" + s)
        f.close()
    else:
        f = open(r'log.txt', 'a')
        f.writelines("\n")
        f.close()
        # write old logs
        old_f = open(str(from_time_stamp(int(time.time()) - 86400 * 10))[0:7] + '.txt', 'w')
        old_f.writelines(open('log.txt').readlines()[::-1])
        # write count
        config = configparser.ConfigParser()
        config.read("config.ini")
        symbols = json.loads(config.get("trade", "symbol"))
        for symbol in symbols:
            cfg_field = symbol + "-stat"
            sum_count = 0
            try:
                sum_count = sum(json.loads(config.get(cfg_field, "count")))
            except Exception as err:
                print(err)
            old_f.writelines(symbol + " [" + str(sum_count) + "]")
        old_f.close()
        f = open(r'log.txt', 'w')
        f.write(text)
        f.close()
