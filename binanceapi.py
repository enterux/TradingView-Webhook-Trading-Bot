# filepath: c:\Work\Trading\Binance\TradingView-Webhook-Trading-Bot\src\binanceapi.py
import logbot
from binance.client import Client
from binance.enums import *

class BinanceFutures:
    def __init__(self, var: dict, testnet=False):
        self.api_key = var['api_key']
        self.api_secret = var['api_secret']
        self.leverage = var['leverage']
        self.risk = var['risk']
        self.client = Client(self.api_key, self.api_secret)
        if testnet:
            self.client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
        self.client.futures_change_leverage(symbol='BTCUSDT', leverage=self.leverage)

    # =============== SIGN, POST AND REQUEST ===============

    def _try_request(self, method: str, **kwargs):
        try:
            if method == 'get_wallet_balance':
                req = self.client.futures_account_balance()
            elif method == 'my_position':
                req = self.client.futures_position_information(symbol=kwargs.get('symbol'))
            elif method == 'place_order':
                req = self.client.futures_create_order(
                    symbol=kwargs.get('symbol'),
                    side=kwargs.get('side'),
                    type=kwargs.get('order_type'),
                    quantity=kwargs.get('qty'),
                    price=kwargs.get('price', None),
                    stopPrice=kwargs.get('stop_price', None),
                    timeInForce=kwargs.get('time_in_force'),
                    reduceOnly=kwargs.get('reduce_only'),
                    closePosition=kwargs.get('close_position')
                )
            elif method == 'cancel_all_orders':
                req = self.client.futures_cancel_all_open_orders(symbol=kwargs.get('symbol'))
        except Exception as e:
            logbot.logs('>>> /!\ An exception occurred: {}'.format(e), True)
            return {
                "success": False,
                "error": str(e)
            }
        if 'code' in req and req['code'] != 200:
            logbot.logs('>>> /!\ {}'.format(req['msg']), True)
            return {
                "success": False,
                "error": req['msg']
            }
        else:
            req['success'] = True
        return req

    # ================== UTILITY FUNCTIONS ==================

    def _rounded_size(self, size, qty_step):
        step_size = round(float(size) / qty_step) * qty_step
        if isinstance(qty_step, float):
            decimal = len(str(qty_step).split('.')[1])
            return round(step_size, decimal)
        return step_size

    # ================== ORDER FUNCTIONS ==================

    def entry_position(self, payload: dict, ticker):
        #   PLACE ORDER
        orders = []

        side = SIDE_BUY
        close_sl_tp_side = SIDE_SELL
        stop_loss = payload['long SL']
        take_profit = payload['long TP']

        if payload['action'] == 'sell':
            side = SIDE_SELL
            close_sl_tp_side = SIDE_BUY
            stop_loss = payload['short SL']
            take_profit = payload['short TP']

        r = self._try_request('get_wallet_balance')
        if not r['success']:
            return r
        free_collateral = float(next(item for item in r['result'] if item['asset'] == 'USDT')['balance'])
        logbot.logs('>>> Found free collateral: {}'.format(free_collateral))
        size = (free_collateral * self.risk) / abs(payload['price'] - stop_loss)
        if (size / (free_collateral / payload['price'])) > self.leverage:
            return {
                "success": False,
                "error": "leverage is higher than maximum limit you set"
            }

        size = self._rounded_size(size, 0.001)  # Binance Futures uses 0.001 as the minimum lot size

        logbot.logs(f">>> SIZE: {size}, SIDE: {side}, PRICE: {payload['price']}, SL: {stop_loss}, TP: {take_profit}")

        # 1/ place order with stop loss
        order_type = ORDER_TYPE_MARKET if 'type' not in payload.keys() else payload['type'].upper()
        if order_type not in [ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT]:
            return {
                "success": False,
                "error": f"order type '{order_type}' is unknown"
            }
        exe_price = None if order_type == ORDER_TYPE_MARKET else payload['price']
        r = self._try_request('place_order',
                              symbol=ticker,
                              side=side,
                              order_type=order_type,
                              qty=size,
                              price=exe_price,
                              stop_price=stop_loss,
                              time_in_force=TIME_IN_FORCE_GTC,
                              reduce_only=False,
                              close_position=False)
        if not r['success']:
            r['orders'] = orders
            return r
        orders.append(r['result'])
        logbot.logs(f">>> Order {order_type} posted with success")

        # 2/ place the take profit only if it is not None or 0
        if take_profit:
            r = self._try_request('place_order',
                                  symbol=ticker,
                                  side=close_sl_tp_side,
                                  order_type=ORDER_TYPE_LIMIT,
                                  qty=size,
                                  price=take_profit,
                                  time_in_force=TIME_IN_FORCE_GTC,
                                  reduce_only=True,
                                  close_position=False)
            if not r['success']:
                r['orders'] = orders
                return r
            orders.append(r['result'])
            logbot.logs(">>> Take profit posted with success")

        # 3/ (optional) place multiples take profits
        i = 1
        while True:
            tp = 'tp' + str(i) + ' Mult'
            if tp in payload.keys():
                dist = abs(payload['price'] - stop_loss) * payload[tp]
                mid_take_profit = (payload['price'] + dist) if side == SIDE_BUY else (payload['price'] - dist)
                mid_size = size * (payload['tp Close'] / 100)
                mid_size = self._rounded_size(mid_size, 0.001)
                r = self._try_request('place_order',
                                      symbol=ticker,
                                      side=close_sl_tp_side,
                                      order_type=ORDER_TYPE_LIMIT,
                                      qty=mid_size,
                                      price=mid_take_profit,
                                      time_in_force=TIME_IN_FORCE_GTC,
                                      reduce_only=True,
                                      close_position=False)
                if not r['success']:
                    r['orders'] = orders
                    return r
                orders.append(r['result'])
                logbot.logs(f">>> Take profit {i} posted with success at price {mid_take_profit} with size {mid_size}")
            else:
                break
            i += 1

        return {
            "success": True,
            "orders": orders
        }

    def exit_position(self, ticker):
        #   CLOSE POSITION IF ONE IS ONGOING
        r = self._try_request('my_position', symbol=ticker)
        if not r['success']:
            return r
        logbot.logs(">>> Retrieve positions")

        for position in r['result']:
            open_size = float(position['positionAmt'])
            if open_size != 0:
                open_side = SIDE_BUY if open_size > 0 else SIDE_SELL
                close_side = SIDE_SELL if open_side == SIDE_BUY else SIDE_BUY

                r = self._try_request('place_order',
                                      symbol=ticker,
                                      side=close_side,
                                      order_type=ORDER_TYPE_MARKET,
                                      qty=abs(open_size),
                                      price=None,
                                      time_in_force=TIME_IN_FORCE_GTC,
                                      reduce_only=True,
                                      close_position=False)

                if not r['success']:
                    return r
                logbot.logs(">>> Close ongoing position with success")

                break

        #   DELETE ALL OPEN AND CONDITIONAL ORDERS REMAINING
        r = self._try_request('cancel_all_orders', symbol=ticker)
        if not r['success']:
            return r
        logbot.logs(">>> Deleted all open and conditional orders remaining with success")

        return {
            "success": True
        }

    def breakeven(self, payload: dict, ticker):
        #   SET STOP LOSS TO BREAKEVEN
        r = self._try_request('my_position', symbol=ticker)
        if not r['success']:
            return r
        logbot.logs(">>> Retrieve positions")

        orders = []

        for position in r['result']:
            open_size = float(position['positionAmt'])
            if open_size != 0:
                open_side = SIDE_BUY if open_size > 0 else SIDE_SELL
                breakeven_price = payload['long Breakeven'] if open_side == SIDE_BUY else payload['short Breakeven']

                # place market stop loss at breakeven
                r = self._try_request('place_order',
                                      symbol=ticker,
                                      side=open_side,
                                      order_type=ORDER_TYPE_STOP_MARKET,
                                      qty=abs(open_size),
                                      stop_price=breakeven_price,
                                      time_in_force=TIME_IN_FORCE_GTC,
                                      reduce_only=True,
                                      close_position=False)
                if not r['success']:
                    return r
                orders.append(r['result'])
                logbot.logs(f">>> Breakeven stop loss posted with success at price {breakeven_price}")

        return {
            "success": True,
            "orders": orders
        }