
import math, time
from .logging import logger

def check_account_bal(client, amt):
    try:
        result = client.AccountApi.get_account('USDT')
        if result['code'] != '0':
            return
        bal = float(result['data'][0]['details'][0]['availBal']) if len(result['data'][0]['details']) > 0 else 0
        if bal >= amt:
            return
        diff = math.ceil(client.maintain + amt - bal)
        logger.warning(f"[{client.user}] earn-withdraw {diff} USDT")
        result = client.EarnApi.redempt('USDT', diff)
        if result['code'] != '0':
            return
        time.sleep(2)
        result = client.FundingApi.funds_transfer('USDT', diff, 6, 18)
        if result['code'] != '0':
            result = client.FundingApi.funds_transfer('USDT', diff, 6, 18)
        logger.warning(f"[{client.user}] funds_transfer {result['code'] == '0'}")
    except Exception as e:
        logger.warning(f"[{client.user}] check_account_bal err {e}")

def earn_account_bal(client):
    try:
        logger.warning(f"[{client.user}] earn_account_bal")
        result = client.AccountApi.get_account('USDT')
        if result['code'] != '0':
            return
        bal = float(result['data'][0]['details'][0]['availBal'])
        if bal <= client.maintain:
            return
        diff = math.ceil(bal - client.maintain)
        client.FundingApi.funds_transfer('USDT', diff, 18, 6)
        result = client.FundingApi.get_balances('USDT')
        bal = float(result['data'][0]['availBal'])
        if bal == 0:
            return
        logger.warning(f"[{client.user}] earn-purchase {bal} USDT")
        result = client.EarnApi.purchase('USDT', bal)
        logger.warning(f"[{client.user}] earn-purchase {result['code'] == '0'}")
    except Exception as e:
        logger.warning(f"[{client.user}] earn_account_bal err {e}")
