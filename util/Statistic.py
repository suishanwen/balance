import re
from util.MyUtil import from_time_stamp
from api.OrderInfo import MyOrderInfo
from module.Logger import logger


def analyze_log():
    yy_mm_dd = str(from_time_stamp())[0:10]
    order_list = []
    try:
        with open(r'log.txt') as f:
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
        order_list = order_list[::-1]
    except FileNotFoundError:
        logger.info("LogNotFound!")
    return order_list


def generate_report(client, order_list):
    symbol = client.SYMBOL_T
    # report_content = "<html>\n<body>\n<div>"
    # report_content += "\n<h2>收益统计 {}</h2>".format(str(from_time_stamp())[0:10])
    # 交易币种
    order_list_symbol = list(filter(lambda x: True if x.symbol == symbol else False, order_list))
    # 总交易次数
    # trx_count_total = len(order_list_symbol)
    # 策略交易次数
    trx_count_valid = 0
    # 策略交易次数（买）
    trx_count_valid_buy = 0
    # 策略交易次数（卖）
    trx_count_valid_sell = 0
    # 反转触发次数
    trx_count_reverse = 0
    # 插针触发次数
    trx_count_needle = 0
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
    # quantity_change = 0
    # 持仓增减均价
    quantity_change_price = 0
    # 理论收益
    reward_weight_usdt = 0
    # 吃单费率
    fee_rate = 0.002
    # 点卡消耗
    # points_consume = 0
    # 交易单
    order_sheet = ""
    for order in order_list_symbol:
        order_sheet += "\n<p>" + order.__str__() + "</p>"
        if order.canceled == 0:
            trx_count_valid += 1
            if order.orderType.find("buy") != -1:
                trx_count_valid_buy += 1
                trx_quantity_buy += order.totalAmount
            else:
                trx_count_valid_sell += 1
                trx_quantity_sell += order.totalAmount
            if order.trigger == "reverse":
                trx_count_reverse += 1
            elif order.trigger == "needle":
                trx_count_needle += 1
            trx_usdt_total += abs(order.transaction)
            trx_quantity_total += order.totalAmount
            usdt_change += order.transaction
            reward_weight_usdt += order.count
        else:
            trx_count_canceled += 1
    if trx_quantity_total != 0:
        trx_price_avg = trx_usdt_total / trx_quantity_total
    quantity_change = trx_quantity_buy - trx_quantity_sell
    if quantity_change != 0:
        quantity_change_price = abs(usdt_change / quantity_change)
        if usdt_change > 0 and quantity_change > 0:
            quantity_change_price = -quantity_change_price
    fees = trx_usdt_total * client.fee
    if quantity_change >= 0:
        change_type = "增"
    else:
        change_type = "减"

    # report_content += "\n<div>"
    # report_content += "\n<h3>%s</h3>" % symbol
    # report_content += "\n<table>"
    # report_content += get_html_tr("总交易次数", trx_count_total)
    # report_content += get_html_tr("部分成交撤单次数", trx_count_canceled)
    # report_content += get_html_tr("策略交易次数", trx_count_valid)
    # report_content += get_html_tr("策略交易次数（买）", trx_count_valid_buy)
    # report_content += get_html_tr("策略交易次数（卖）", trx_count_valid_sell)
    # report_content += get_html_tr("反转触发次数", trx_count_reverse)
    # report_content += get_html_tr("插针触发次数", trx_count_needle)
    # report_content += get_html_tr("总成交金额$", trx_usdt_total)
    # report_content += get_html_tr("总成交数量", trx_quantity_total)
    # report_content += get_html_tr("总成交数量（买）", trx_quantity_buy)
    # report_content += get_html_tr("总成交数量（卖）", trx_quantity_sell)
    # report_content += get_html_tr("总交易均价$", trx_price_avg)
    # report_content += get_html_tr("余额变化$", usdt_change)
    # report_content += get_html_tr("持仓变化", quantity_change)
    # report_content += get_html_tr("{}仓均价$".format(change_type), quantity_change_price)
    # report_content += get_html_tr("理论收益$", reward_weight_usdt)
    # report_content += get_html_tr("点卡消耗", points_consume)
    #
    # report_content += "\n</table>"
    # report_content += "\n</div><br/>"
    # report_content += "\n<h4>交易单</h4>"
    # report_content += "\n<div>" + order_sheet + "\n</div>"
    # report_content += "\n</div>\n</body>\n</html>"
    report_content = f"---------{symbol}---------\n"
    report_content += get_tr("交易次数", trx_count_valid)
    report_content += get_tr("买入次数", trx_count_valid_buy)
    report_content += get_tr("卖出次数", trx_count_valid_sell)
    report_content += get_tr("反转次数", trx_count_reverse)
    report_content += get_tr("插针次数", trx_count_needle)
    report_content += get_tr("成交金额", trx_usdt_total)
    report_content += get_tr("成交数量", trx_quantity_total)
    report_content += get_tr("买入数量", trx_quantity_buy)
    report_content += get_tr("卖出数量", trx_quantity_sell)
    report_content += get_tr("交易均价", trx_price_avg)
    report_content += get_tr("余额变化", usdt_change)
    report_content += get_tr("持仓变化", quantity_change)
    report_content += get_tr("{}仓均价".format(change_type), quantity_change_price)
    report_content += get_tr("净收益额", reward_weight_usdt)
    report_content += get_tr("交易费用", fees)
    return report_content


def get_tr(title, content):
    # byte_size = len(bytes(title, encoding="utf-8"))
    space = "    "
    # for i in range(0, 25 - byte_size):
    #     space += " "
    return f"{title}{space}{round(content, 2)}\n"


def get_html_tr(title, content):
    return "\n<tr>" + \
           "\n<td style='width:200px'>{}</td>".format(title) + \
           "\n<td style='width:100px'>{}</td>".format(round(content, 4))
