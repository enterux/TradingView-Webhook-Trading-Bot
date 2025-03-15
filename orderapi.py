import logbot
import json, os, config
from ftxapi import Ftx
from bybitapi import ByBit
from binanceapi import BinanceFutures

subaccount_name = 'SUBACCOUNT_NAME'
leverage = 1.0
risk = 1.0 / 100
api_key = 'API_KEY'
api_secret = 'API_SECRET'


# ================== SET GLOBAL VARIABLES ==================


def global_var(payload):
    global subaccount_name
    global leverage
    global risk
    global api_key
    global api_secret

    subaccount_name = payload['subaccount']

    if subaccount_name == 'Testing':
        leverage = os.environ.get('LEVERAGE_TESTING', config.LEVERAGE_TESTING)
        leverage = float(leverage)

        risk = os.environ.get('RISK_TESTING', config.RISK_TESTING)
        risk = float(risk) / 100

        api_key = os.environ.get('API_KEY_TESTING', config.API_KEY_TESTING)

        api_secret = os.environ.get('API_SECRET_TESTING', config.API_SECRET_TESTING)

    elif subaccount_name == 'MYBYBITACCOUNT':
        leverage = os.environ.get('LEVERAGE_MYBYBITACCOUNT', config.LEVERAGE_MYBYBITACCOUNT)
        leverage = float(leverage)

        risk = os.environ.get('RISK_MYBYBITACCOUNT', config.RISK_MYBYBITACCOUNT)
        risk = float(risk) / 100

        api_key = os.environ.get('API_KEY_MYBYBITACCOUNT', config.API_KEY_MYBYBITACCOUNT)

        api_secret = os.environ.get('API_SECRET_MYBYBITACCOUNT', config.API_SECRET_MYBYBITACCOUNT)

    elif subaccount_name == 'BINANCE':
        leverage = os.environ.get('LEVERAGE_BINANCE', config.LEVERAGE_BINANCE)
        leverage = float(leverage)

        risk = os.environ.get('RISK_BINANCE', config.RISK_BINANCE)
        risk = float(risk) / 100

        api_key = os.environ.get('BINANCE_API_KEY', config.BINANCE_API_KEY)

        api_secret = os.environ.get('BINANCE_API_SECRET', config.BINANCE_API_SECRET)

    elif subaccount_name == 'BINANCE_TESTNET':
        leverage = os.environ.get('LEVERAGE_BINANCE_TESTNET', config.LEVERAGE_BINANCE_TESTNET)
        leverage = float(leverage)

        risk = os.environ.get('RISK_BINANCE_TESTNET', config.RISK_BINANCE_TESTNET)
        risk = float(risk) / 100

        api_key = os.environ.get('BINANCE_TESTNET_API_KEY', config.BINANCE_TESTNET_API_KEY)

        api_secret = os.environ.get('BINANCE_TESTNET_API_SECRET', config.BINANCE_TESTNET_API_SECRET)

    else:
        logbot.logs(">>> Subaccount name not found", True)
        return {
            "success": False,
            "error": "subaccount name not found"
        }
           
    return {
        "success": True
    }


# ================== MAIN ==================


def order(payload: dict):
    #   DEFINE GLOBAL VARIABLE
    glob = global_var(payload)
    if not glob['success']:
        return glob
    
    init_var = {
        'subaccount_name': subaccount_name,
        'leverage': leverage,
        'risk': risk,
        'api_key': api_key,
        'api_secret': api_secret
    }
    exchange = payload['exchange']
    
    #   SET EXCHANGE CLASS
    exchange_api = None
    try:
        if exchange.upper() == 'FTX':
            exchange_api = Ftx(init_var)
        elif exchange.upper() == 'BYBIT':
            exchange_api = ByBit(init_var)
        elif exchange.upper() == 'BINANCE':
            exchange_api = BinanceFutures(init_var)
        elif exchange.upper() == 'BINANCE_TESTNET':
            exchange_api = BinanceFutures(init_var, testnet=True)
    except Exception as e:
        logbot.logs('>>> An exception occurred: {}'.format(e), True)
        return {
            "success": False,
            "error": str(e)
        }

    logbot.logs('>>> Exchange: {}'.format(exchange))
    logbot.logs('>>> Subaccount: {}'.format(subaccount_name))

    #   FIND THE APPROPRIATE TICKER IN DICTIONARY
    ticker = ""
    if exchange.upper() == 'BYBIT':
        ticker = payload['ticker']
    else:
        with open('tickers.json') as json_file:
            tickers = json.load(json_file)
            try:
                ticker = tickers[exchange.lower()][payload['ticker']]
            except Exception as e:
                logbot.logs('>>> An exception occurred: {}'.format(e), True)
                return {
                    "success": False,
                    "error": str(e)
                }
    logbot.logs(">>> Ticker '{}' found".format(ticker))

    #   ALERT MESSAGE CONDITIONS
    if payload['message'] == 'entry':
        logbot.logs(">>> Order message: 'entry'")
        exchange_api.exit_position(ticker)
        orders = exchange_api.entry_position(payload, ticker)
        return orders

    elif payload['message'] == 'exit':
        logbot.logs(">>> Order message: 'exit'")
        exit_res = exchange_api.exit_position(ticker)
        return exit_res

    elif payload['message'][-9:] == 'breakeven':
        logbot.logs(">>> Order message: 'breakeven'")
        breakeven_res = exchange_api.breakeven(payload, ticker)
        return breakeven_res
    
    else:
        logbot.logs(f">>> Order message: '{payload['message']}'")

    return {
        "message": payload['message']
    }