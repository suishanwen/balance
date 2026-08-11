from api.okex_sdk_v5.client import Client
from api.okex_sdk_v5.consts import GET, SAVINGS_BALANCE, PURCHASE_REDEMPT, POST


class EarnAPI(Client):

    def __init__(self, api_key, api_secret_key, passphrase, use_server_time=False, flag='0'):
        Client.__init__(self, api_key, api_secret_key, passphrase, use_server_time, flag)

    def offers(self, ccy=''):
        params = {}
        if ccy:
            params['ccy'] = ccy

        return self._request_with_params(GET, SAVINGS_BALANCE, params)

    def purchase(self, ccy, amt):
        params = {'ccy': ccy, 'amt': amt, 'side': 'purchase', 'rate': '0.01'}
        return self._request_with_params(POST, PURCHASE_REDEMPT, params)

    def redempt(self, ccy, amt):
        params = {'ccy': ccy, 'amt': amt, 'side': 'redempt', 'rate': '0.01'}
        return self._request_with_params(POST, PURCHASE_REDEMPT, params)
