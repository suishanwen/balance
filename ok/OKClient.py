import time
from util.MyUtil import from_time_stamp, send_email
from util.Statistic import generate_email, analyze_log

send_email(generate_email(analyze_log()), "html", "收益统计[bitcoinrobot]")
