
import json
from util.MyUtil import get_day_bj
from trader.services.config import re_init_cost_fill
def get_statistics(client):
    cfg_field = client.SYMBOL_T + "-stat"
    amount = transaction = price = avg_price = 0
    count = []
    try:
        amount = float(client.config.get(cfg_field, "amount"))
        transaction = float(client.config.get(cfg_field, "transaction"))
        price = float(client.config.get(cfg_field, "price"))
        avg_price = float(client.config.get(cfg_field, "avgprice"))
        count = json.loads(client.config.get(cfg_field, "count"))
    except Exception as err:
        if str(err).find("No section") > -1:
            client.config.add_section(cfg_field)
            client.config.set(cfg_field, "amount", str(amount))
            client.config.set(cfg_field, "transaction", str(transaction))
            client.config.set(cfg_field, "price", str(price))
            client.config.set(cfg_field, "avgprice", str(avg_price))
            client.config.set(cfg_field, "count", json.dumps(count))
    return amount, transaction, price, avg_price, count

def new_statistics(client, order_info):
    amount, transaction, price, avg_price, count = get_statistics(client)
    if order_info.orderType == client.TRADE_BUY:
        new_amount = round(amount + order_info.realAmount, client.ACCURACY)
    else:
        new_amount = round(amount - order_info.realAmount, client.ACCURACY)
    new_transaction = round(transaction + order_info.transaction, client.ACCURACY)
    return amount, transaction, price, avg_price, new_amount, new_transaction, count

def set_order_count(client, order_info):
    order_info.realAmount = abs(round(order_info.transaction / order_info.avgPrice, client.ACCURACY))
    amount, transaction, price, avg_price, new_amount, new_transaction, count = new_statistics(client, order_info)
    order_info.count = round((new_transaction + new_amount * order_info.avgPrice) - (
            transaction + amount * price) - abs(order_info.transaction) * client.fee, client.ACCURACY)

def add_statistics(client, order_info):
    cfg_field = order_info.symbol + "-stat"
    amount, transaction, price, avg_price, new_amount, new_transaction, count = new_statistics(client, order_info)
    day = get_day_bj()
    if day == len(count):
        count[day - 1] = round(count[day - 1] + order_info.count, client.ACCURACY)
    elif day > len(count):
        for i in range(day - len(count) - 1):
            count.append(0)
        count.append(order_info.count)
    elif day < len(count):
        count = [order_info.count]
    if client.martin == 1 and ((new_transaction - order_info.earn * 10 == 0) or abs(new_amount) < client.MIN_AMOUNT):
        client.config.set(cfg_field, "transaction", str(0))
        client.config.set(cfg_field, "amount", str(0))
        client.config.set(cfg_field, "price", str(0))
        client.config.set(cfg_field, "avgprice", str(0))
    else:
        client.config.set(cfg_field, "transaction", str(new_transaction))
        client.config.set(cfg_field, "amount", str(new_amount))
        client.config.set(cfg_field, "price", str(order_info.avgPrice))
        client.config.set(cfg_field, "avgprice", str(round(abs(new_transaction / new_amount), client.ACCURACY)))
    client.config.set(cfg_field, "count", str(json.dumps(count)))

# The following two keep original logic though they touch config file via re_init_cost_fill
def cost_fill(client, earn, price=0, deal_amount=0):
    if earn == 0:
        return
    if client.cost > 0 or client.experiment:
        re_init_cost_fill(client)
        new_cost_fill = int(client.costFill - earn) if not client.experiment else int(client.costFill + deal_amount)
        if client.experiment and new_cost_fill != 0:
            new_cost = (client.cost * client.costFill + deal_amount * price) / new_cost_fill
        else:
            new_cost = client.cost
        client.costFill = new_cost_fill
        client.cost = abs(new_cost)
        client.config.set(client.SYMBOL_T, "costfill", str(client.costFill))
        client.config.set(client.SYMBOL_T, "costfilled", str(client.costFilled + earn))
        client.config.set(client.SYMBOL_T, "cost", str(client.cost))

def get_earn(client, open_price, diff):
    earn = diff / open_price * client.amount
    re_init_cost_fill(client)
    if abs(client.costFill) >= client.experiment * client.amount and (
            (client.cost < open_price and client.costFill < 0) or (
            client.cost > open_price and client.costFill > 0 and client.experiment == 0)):
        earn = earn * client.cost / (client.cost - open_price)
        earn = earn if abs(earn) <= abs(client.costFill) else client.costFill
        earn = client.amount / 2 * abs(earn) / earn if abs(earn) >= client.amount / 2 else earn
    return earn
