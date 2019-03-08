import time
import re
import json
import configparser
from util.MyUtil import from_time_stamp, send_email
from api.OrderInfo import MyOrderInfo

# read config
config = configparser.ConfigParser()
config.read("config.ini")


def analyze_log():
    yy_mm_dd = str(from_time_stamp(int(time.time())))[0:10]
    order_list = []
    f = open(r'log.txt')
    line = f.readline()
    while line and (line.find(yy_mm_dd) != -1 or line.find("canceled") != -1):
        search_canceled = re.search("order ([0-9]+) canceled", line)
        if search_canceled:
            order_id_canceled = search_canceled.group(1)
            for order in order_list:
                if order.orderId == order_id_canceled:
                    order.canceled = 1
        else:
            order = MyOrderInfo()
            order.from_log(line)
            order_list.append(order)
        line = f.readline()
    f.close()
    order_list = order_list[::-1]
    return order_list


def generate_email(order_list):
    symbols = json.loads(config.get("trade", "symbol"))
    email_content = "<html>\n<body>\n<div>"
    email_content += "\n<h2>收益统计 {}</h2>".format(str(from_time_stamp(int(time.time())))[0:10])
    # 交易币种
    for symbol in symbols:
        order_list_symbol = list(filter(lambda x: True if x.symbol == symbol else False, order_list))
        # 总交易次数
        trx_count_total = len(order_list_symbol)
        # 策略交易次数
        trx_count_valid = 0
        # 策略交易次数（买）
        trx_count_valid_buy = 0
        # 策略交易次数（卖）
        trx_count_valid_sell = 0
        # 部分成交撤单次数
        trx_count_canceled = 0
        # 总成交金额
        trx_usdt_total = 0
        # 总成交数量
        trx_quantity_total = 0
        # 总成交数量（买）
        trx_quantity_buy = 0
        # 总成交数量（卖）
        trx_quantity_sell = 0
        # 总交易均价
        trx_price_avg = 0
        # 余额变化
        usdt_change = 0
        # 持仓变化
        quantity_change = 0
        # 持仓增减均价
        quantity_change_price = 0
        # 理论收益
        reward_weight_usdt = 0
        # 吃单费率
        fee_rate = 0.0015
        # 点卡消耗
        points_consume = 0
        # 交易单
        order_sheet = ""
        for order in order_list_symbol:
            order_sheet += "\n<p>" + order.__str__() + "</p>"
            if order.canceled == 0:
                trx_count_valid += 1
                if order.orderType == "buy":
                    trx_count_valid_buy += 1
                    trx_quantity_buy += order.totalAmount
                else:
                    trx_count_valid_sell += 1
                    trx_quantity_sell += order.totalAmount
                trx_usdt_total += abs(order.transaction)
                trx_quantity_total += order.totalAmount
                usdt_change += order.transaction
                reward_weight_usdt += order.count
            else:
                trx_count_canceled += 1
        trx_price_avg = trx_usdt_total / trx_quantity_total
        quantity_change = trx_quantity_buy - trx_quantity_sell
        quantity_change_price = abs(usdt_change / quantity_change)
        points_consume = trx_usdt_total * fee_rate
        if quantity_change >= 0:
            change_type = "增"
        else:
            change_type = "减"
        email_content += "\n<div>"
        email_content += "\n<h3>%s</h3>" % symbol
        email_content += "\n<table>"
        email_content += get_tr("总交易次数", trx_count_total)
        email_content += get_tr("部分成交撤单次数", trx_count_canceled)
        email_content += get_tr("策略交易次数", trx_count_valid)
        email_content += get_tr("策略交易次数（买）", trx_count_valid_buy)
        email_content += get_tr("策略交易次数（卖）", trx_count_valid_sell)
        email_content += get_tr("总成交金额$", trx_usdt_total)
        email_content += get_tr("总成交数量", trx_quantity_total)
        email_content += get_tr("总成交数量（买）", trx_quantity_buy)
        email_content += get_tr("总成交数量（卖）", trx_quantity_sell)
        email_content += get_tr("总交易均价$", trx_price_avg)
        email_content += get_tr("余额变化$", usdt_change)
        email_content += get_tr("持仓变化", quantity_change)
        email_content += get_tr("{}仓均价$".format(change_type), quantity_change_price)
        email_content += get_tr("理论收益$", reward_weight_usdt)
        email_content += get_tr("点卡消耗", points_consume)
        email_content += "\n</table>"
        email_content += "\n</div><br/>"
        email_content += "\n<h4>交易单</h4>"
        email_content += "\n<div>" + order_sheet + "\n</div>"
    email_content += "\n</div>\n</body>\n</html>"
    return email_content


def get_tr(title, content):
    return "\n<tr>" + \
           "\n<td style='width:200px'>{}</td>".format(title) + \
           "\n<td style='width:100px'>{}</td>".format(round(content, 4))
