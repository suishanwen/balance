import api.okex_sdk_v3.account_api as account
import api.okex_sdk_v3.ett_api as ett
import api.okex_sdk_v3.futures_api as future
import api.okex_sdk_v3.lever_api as lever
import api.okex_sdk_v3.spot_api as spot
import api.okex_sdk_v3.swap_api as swap
import json


if __name__ == '__main__':

    api_key = ''
    seceret_key = ''
    passphrase = ''

    # account api test
    # param use_server_time's value is False if is True will use server timestamp
    # accountAPI = account.AccountAPI(api_key, seceret_key, passphrase, True)
    # result = accountAPI.get_currencies()
    # result = accountAPI.get_wallet()
    # result = accountAPI.get_currency('btc')
    # result = accountAPI.get_currency('btc')
    # result = accountAPI.get_coin_fee('btc')
    # result = accountAPI.get_coin_fee('btc')
    # result = accountAPI.get_coins_withdraw_record()
    # result = accountAPI.get_coin_withdraw_record('BTC')
    # result = accountAPI.get_ledger_record_v3()
    # result = accountAPI.get_top_up_address('BTC')
    # result = accountAPI.get_top_up_address('BTC')
    # result = accountAPI.get_top_up_records()
    # result = accountAPI.get_top_up_record('BTC')

    # spot api test
    spotAPI = spot.SpotAPI(api_key, seceret_key, passphrase, True)
    # result = spotAPI.get_account_info()
    # result = spotAPI.get_coin_account_info('BTC')
    # result = spotAPI.get_ledger_record('BTC', limit=1)
    # result = spotAPI.take_order('limit', 'sell', 'BTC-USDT', 2, price='3')

    # take orders
    # params = [
    #   {"client_oid":"20180728","instrument_id":"btc-usdt","side":"sell","type":"market"," size ":"0.001"," notional ":"10001","margin_trading ":"1"},
    #   {"client_oid":"20180728","instrument_id":"btc-usdt","side":"sell","type":"limit"," size ":"0.001","notional":"10002","margin_trading ":"1"}
    # ]
    # result = spotAPI.take_orders(params)

    # result = spotAPI.revoke_order(2229535858593792, 'BTC-USDT')
    # revoke orders
    # params = [{'instrument_id': 'btc-usdt', 'orders_ids':[2233702496112640, 2233702479204352]}]
    # result = spotAPI.revoke_orders(params)
    # result = spotAPI.get_orders_list('all', 'Btc-usdT', limit=100)
    # result = spotAPI.get_order_info(2233702496112640, 'btc-usdt')
    # result = spotAPI.get_orders_pending(limit='10', froms='', to='')
    # result = spotAPI.get_fills('2234969640833024', 'btc-usdt', '', '', '')
    # result = spotAPI.get_coin_info()
    # result = spotAPI.get_depth('LTC-USDT')
    # result = spotAPI.get_ticker()
    # result = spotAPI.get_specific_ticker('LTC-USDT')
    # result = spotAPI.get_deal('LTC-USDT', 1, 3, 10)
    # result = spotAPI.get_kline('LTC-USDT', '2018-09-12T07:59:45.977Z', '2018-09-13T07:59:45.977Z', 60)
    #
    # future api test
    futureAPI = future.FutureAPI(api_key, seceret_key, passphrase, True)
    # result = futureAPI.get_position()
    # result = futureAPI.get_coin_account('btc')
    # result = futureAPI.get_leverage('btc')
    # result = futureAPI.set_leverage(symbol='BTC', instrument_id='BCH-USD-181026', direction=1, leverage=10)
    # result = futureAPI.take_order()

    # take orders
    # orders = []
    # order1 = {"client_oid": "f379a96206fa4b778e1554c6dc969687", "type": "2", "price": "1800.0", "size": "1", "match_price": "0"}
    # order2 = {"client_oid": "f379a96206fa4b778e1554c6dc969687", "type": "2", "price": "1800.0", "size": "1", "match_price": "0"}
    # orders.append(order1)
    # orders.append(order2)
    # orders_data = json.dumps(orders)
    # result = futureAPI.take_orders('BCH-USD-181019', orders_data=orders_data, leverage=10)

    # result = futureAPI.get_ledger('btc')
    # result = futureAPI.get_products()
    # result = futureAPI.get_depth('BTC-USD-181019', 1)
    # result = futureAPI.get_ticker()
    # result = futureAPI.get_specific_ticker('ETC-USD-181026')
    # result = futureAPI.get_specific_ticker('ETC-USD-181026')
    # result = futureAPI.get_trades('ETC-USD-181026', 1, 3, 10)
    # result = futureAPI.get_kline('ETC-USD-181026','2018-10-14T03:48:04.081Z', '2018-10-15T03:48:04.081Z')
    # result = futureAPI.get_index('EOS-USD-181019')
    # result = futureAPI.get_products()
    # result = futureAPI.take_order("ccbce5bb7f7344288f32585cd3adf357", 'BCH-USD-181019','2','10000.1','1','0','10')
    # result = futureAPI.take_order("ccbce5bb7f7344288f32585cd3adf351",'BCH-USD-181019',2,10000.1,1,0,10)
    # result = futureAPI.get_trades('BCH-USD-181019')
    # result = futureAPI.get_rate()
    # result = futureAPI.get_estimated_price('BTC-USD-181019')
    # result = futureAPI.get_holds('BTC-USD-181019')
    # result = futureAPI.get_limit('BTC-USD-181019')
    # result = futureAPI.get_liquidation('BTC-USD-181019', 0)
    # result = futureAPI.get_holds_amount('BCH-USD-181019')
    # result = futureAPI.get_mark_price('BCH-USD-181019')

    # level api test
    # levelAPI = lever.LeverAPI(api_key, seceret_key, passphrase, True)
    # result = levelAPI.get_account_info()
    # result = levelAPI.get_specific_account('btc-usdt')
    # result = levelAPI.get_ledger_record('btc-usdt', '1', '4', '2')
    # result = levelAPI.get_config_info()
    # result = levelAPI.get_specific_config_info('btc-usdt')
    # result = levelAPI.get_borrow_coin(0, 1, 2, 1)
    # result = levelAPI.take_order()

    # take orders
    # params = [
    #   {"client_oid":"20180728","instrument_id":"btc-usdt","side":"sell","type":"market"," size ":"0.001"," notional ":"10001","margin_trading ":"1"},
    #   {"client_oid":"20180728","instrument_id":"btc-usdt","side":"sell","type":"limit"," size ":"0.001","notional":"10002","margin_trading ":"1"}
    # ]
    # result = levelAPI.take_orders(params)

    # result = levelAPI.revoke_order()

    # revoke orders
    # params = [
    #   {"instrument_id":"btc-usdt","order_ids":[23464,23465]},
    #   {"instrument_id":"ltc-usdt","order_ids":[243464,234465]}
    # ]
    # result = levelAPI.revoke_orders(params)

    # result = levelAPI.get_order_list('open', '', '', 100, 'ltc-usdt')
    # result = levelAPI.get_order_info('2244927451729920', 'ltc-usdt')
    # result = levelAPI.get_order_pending('', '', '', '')
    # result = levelAPI.get_fills(2245642842378240, 'ltc-usdt', '', '', 100)

    # ett api test
    ettAPI = ett.EttAPI(api_key, seceret_key, passphrase, True)
    # result = ettAPI.get_accounts()
    # result = ettAPI.take_order()
    # result = ettAPI.revoke_order()
    # result = ettAPI.get_order_list()
    # result = ettAPI.get_specific_order()
    # result = ettAPI.get_account('usdt')
    # result = ettAPI.get_ledger('usdt')
    # result = ettAPI.get_constituents('ok06ett')
    # result = ettAPI.get_define_price('ok06ett')

    # swap api test
    # swapAPI = swap.SwapAPI(api_key, seceret_key, passphrase, True)
    # result = swapAPI.get_accounts()
    # result = swapAPI.get_position()
    # result = swapAPI.get_coin_account('BTC-USD-SWAP')
    # result = swapAPI.get_settings('BTC-USD-SWAP')
    # result = swapAPI.set_leverage('BTC-USD-SWAP', 10, 1)
    # result = swapAPI.get_ledger('BTC-USD-SWAP', '0', '2', '5')
    # result = swapAPI.take_order('BTC-USD-SWAP', '1', '1', '3', '', '1')
    # result = swapAPI.take_orders([
    #         {"client_oid": "", "price": "5","size": "2","type": "1","match_price": "0"},
    #         {"client_oid": "","price": "2","size": "3","type": "2","match_price": "1"}
    #     ],'BTC-USD-SWAP')
    # result = swapAPI.revoke_order('64-5e-4761f8af8-0', 'BTC-USD-SWAP')
    # result = swapAPI.revoke_orders(["64-5e-476280dcd-0", "64-5e-47629d453-0"], 'BTC-USD-SWAP')
    # result = swapAPI.get_order_list('2', 'BTC-USD-SWAP', '', '', '')
    # result = swapAPI.get_order_info('BTC-USD-SWAP', '64-5e-47629855f-0')
    # result = swapAPI.get_fills('4-6e-475ffb3f2-0', 'BTC-USD-SWAP', '', '', '')
    # result = swapAPI.get_instruments()
    # result = swapAPI.get_depth('BTC-USD-SWAP', '2')
    # result = swapAPI.get_ticker()
    # result = swapAPI.get_specific_ticker('BTC-USD-SWAP')
    # result = swapAPI.get_trades('BTC-USD-SWAP', '', '', '10')
    # result = swapAPI.get_kline('BTC-USD-SWAP', '60', '', '')
    # result = swapAPI.get_index('BTC-USD-SWAP')
    # result = swapAPI.get_rate()
    # result = swapAPI.get_holds('BTC-USD-SWAP')
    # result = swapAPI.get_limit('BTC-USD-SWAP')
    # result = swapAPI.get_liquidation('BTC-USD-SWAP', '1', '', '', '')
    # result = swapAPI.get_holds_amount('BTC-USD-SWAP')
    # result = swapAPI.get_funding_time('BTC-USD-SWAP')
    # result = swapAPI.get_mark_price('BTC-USD-SWAP')
    # result = swapAPI.get_historical_funding_rate('BTC-USD-SWAP')

    # print(json.dumps(result))
