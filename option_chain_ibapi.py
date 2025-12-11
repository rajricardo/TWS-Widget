#!/usr/bin/env python3
"""
Option Chain Module - Uses native IBAPI for fetching option chain data
Separate from main tws_bridge.py to avoid conflicts with ib_insync
"""

import sys
import time
import threading
import math
from datetime import datetime
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract, ContractDetails
from ibapi.common import TickerId


class OptionChainApp(EWrapper, EClient):
    """IBAPI application for fetching option chain data"""
    
    def __init__(self):
        EClient.__init__(self, self)
        self.nextValidOrderId = None
        self.contract_details = []
        self.option_data = {}
        self.current_req_id = 1000
        self.pending_requests = set()
        self.data_ready = threading.Event()
        self.stock_price = None
        self.option_params = []
        
    def nextValidId(self, orderId: int):
        """Callback when connection is established"""
        self.nextValidOrderId = orderId
        
    def error(self, reqId: TickerId, errorCode: int, errorString: str):
        """Error callback"""
        if errorCode not in [2104, 2106, 2158]:  # Ignore market data connection messages
            print(f"Error {reqId}: {errorCode} - {errorString}", file=sys.stderr)
    
    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        """Callback for contract details"""
        self.contract_details.append(contractDetails)
    
    def contractDetailsEnd(self, reqId: int):
        """Callback when contract details are complete"""
        if reqId in self.pending_requests:
            self.pending_requests.remove(reqId)
            if len(self.pending_requests) == 0:
                self.data_ready.set()
    
    def securityDefinitionOptionParameter(self, reqId: int, exchange: str,
                                         underlyingConId: int, tradingClass: str,
                                         multiplier: str, expirations: set,
                                         strikes: set):
        """Callback for option parameters"""
        self.option_params.append({
            'exchange': exchange,
            'underlyingConId': underlyingConId,
            'tradingClass': tradingClass,
            'multiplier': multiplier,
            'expirations': sorted(list(expirations)),
            'strikes': sorted(list(strikes))
        })
    
    def securityDefinitionOptionParameterEnd(self, reqId: int):
        """Callback when option parameters are complete"""
        if reqId in self.pending_requests:
            self.pending_requests.remove(reqId)
            if len(self.pending_requests) == 0:
                self.data_ready.set()
    
    def tickPrice(self, reqId: TickerId, tickType: int, price: float, attrib):
        """Callback for price data"""
        if reqId not in self.option_data:
            self.option_data[reqId] = {}
        
        # TickType: 1=Bid, 2=Ask, 4=Last, 6=High, 7=Low, 9=Close
        if tickType == 1:  # Bid
            self.option_data[reqId]['bid'] = price
        elif tickType == 2:  # Ask
            self.option_data[reqId]['ask'] = price
        elif tickType == 4:  # Last
            self.option_data[reqId]['last'] = price
    
    def tickSize(self, reqId: TickerId, tickType: int, size: int):
        """Callback for size data"""
        if reqId not in self.option_data:
            self.option_data[reqId] = {}
        
        # TickType: 0=BidSize, 3=AskSize, 5=LastSize, 8=Volume
        if tickType == 8:  # Volume
            self.option_data[reqId]['volume'] = size
    
    def tickGeneric(self, reqId: TickerId, tickType: int, value: float):
        """Callback for generic tick data"""
        if reqId not in self.option_data:
            self.option_data[reqId] = {}
        
        # TickType: 24=IV, 13=ModelOption (Greeks container)
        if tickType == 24:  # Implied Volatility
            self.option_data[reqId]['iv'] = value
    
    def tickOptionComputation(self, reqId: TickerId, tickType: int, tickAttrib: int,
                             impliedVol: float, delta: float, optPrice: float,
                             pvDividend: float, gamma: float, vega: float,
                             theta: float, undPrice: float):
        """Callback for option computation (Greeks)"""
        if reqId not in self.option_data:
            self.option_data[reqId] = {}
        
        if impliedVol and impliedVol > 0:
            self.option_data[reqId]['iv'] = impliedVol
        if delta and not math.isnan(delta):
            self.option_data[reqId]['delta'] = delta
        if theta and not math.isnan(theta):
            self.option_data[reqId]['theta'] = theta


def get_option_chain_ibapi(ticker, host, port, client_id):
    """
    Fetch option chain for ticker using IBAPI
    Returns: dict with success, message, optionChain, currentPrice
    """
    try:
        print(f"[IBAPI] Fetching option chain for {ticker}...", file=sys.stderr)
        
        # Create app and connect
        app = OptionChainApp()
        app.connect(host, int(port), int(client_id) + 1000)  # Use different client ID
        
        # Start message processing thread
        api_thread = threading.Thread(target=app.run, daemon=True)
        api_thread.start()
        
        # Wait for connection
        time.sleep(1)
        
        # Create stock contract
        stock_contract = Contract()
        stock_contract.symbol = ticker
        stock_contract.secType = "STK"
        stock_contract.exchange = "SMART"
        stock_contract.currency = "USD"
        
        # Request market data for current price
        app.reqMktData(1, stock_contract, "", False, False, [])
        time.sleep(2)  # Wait for price data
        
        # Get current price
        current_price = None
        if 1 in app.option_data:
            current_price = app.option_data[1].get('last') or app.option_data[1].get('bid') or app.option_data[1].get('ask')
        
        if not current_price:
            app.disconnect()
            return {"success": False, "message": f"Could not get price for {ticker}", "optionChain": []}
        
        print(f"[IBAPI] Current price: ${current_price}", file=sys.stderr)
        
        # First, get contract details to obtain the contract ID
        app.data_ready.clear()
        app.contract_details = []
        app.pending_requests.add(99)
        app.reqContractDetails(99, stock_contract)
        
        # Wait for contract details
        if not app.data_ready.wait(10):
            app.disconnect()
            return {"success": False, "message": "Timeout getting contract details", "optionChain": []}
        
        if not app.contract_details:
            app.disconnect()
            return {"success": False, "message": f"Could not find contract for {ticker}", "optionChain": []}
        
        # Get the contract ID
        stock_con_id = app.contract_details[0].contract.conId
        print(f"[IBAPI] Stock contract ID: {stock_con_id}", file=sys.stderr)
        
        # Request option parameters using the proper contract ID
        app.data_ready.clear()
        app.pending_requests.add(100)
        app.option_params = []
        app.reqSecDefOptParams(100, ticker, "", "STK", stock_con_id)
        
        # Wait for option parameters
        if not app.data_ready.wait(10):
            app.disconnect()
            return {"success": False, "message": "Timeout getting option parameters", "optionChain": []}
        
        if not app.option_params:
            app.disconnect()
            return {"success": False, "message": f"{ticker} does not support options", "optionChain": []}
        
        # Get the primary option parameters (usually first one matches ticker trading class)
        primary_params = None
        for params in app.option_params:
            if params['tradingClass'] == ticker:
                primary_params = params
                break
        
        if not primary_params:
            primary_params = app.option_params[0]
        
        expirations = primary_params['expirations']
        all_strikes = primary_params['strikes']
        
        if not expirations:
            app.disconnect()
            return {"success": False, "message": "No expirations found", "optionChain": []}
        
        # Find nearest expiry
        today = datetime.now().strftime('%Y%m%d')
        nearest_expiry = None
        for exp in expirations:
            if exp >= today:
                nearest_expiry = exp
                break
        
        if not nearest_expiry:
            nearest_expiry = expirations[0]
        
        print(f"[IBAPI] Using expiry: {nearest_expiry}", file=sys.stderr)
        
        # Filter strikes centered around current price (6 ITM, 6 OTM)
        strikes_list = sorted(all_strikes)
        closest_idx = min(range(len(strikes_list)), key=lambda i: abs(strikes_list[i] - current_price))
        
        start_idx = max(0, closest_idx - 6)
        end_idx = min(len(strikes_list), closest_idx + 6)
        
        if end_idx - start_idx < 12:
            if start_idx == 0:
                end_idx = min(len(strikes_list), start_idx + 12)
            elif end_idx == len(strikes_list):
                start_idx = max(0, end_idx - 12)
        
        selected_strikes = strikes_list[start_idx:end_idx]
        selected_strikes = sorted(selected_strikes, reverse=True)  # Descending order
        
        print(f"[IBAPI] Selected {len(selected_strikes)} strikes: {selected_strikes}", file=sys.stderr)
        
        # Fetch option data for each strike
        option_chain_data = []
        req_id = 2000
        
        for strike in selected_strikes:
            # Create Call contract
            call_contract = Contract()
            call_contract.symbol = ticker
            call_contract.secType = "OPT"
            call_contract.exchange = "SMART"
            call_contract.currency = "USD"
            call_contract.lastTradeDateOrContractMonth = nearest_expiry
            call_contract.strike = strike
            call_contract.right = "C"
            call_contract.multiplier = "100"
            
            # Create Put contract
            put_contract = Contract()
            put_contract.symbol = ticker
            put_contract.secType = "OPT"
            put_contract.exchange = "SMART"
            put_contract.currency = "USD"
            put_contract.lastTradeDateOrContractMonth = nearest_expiry
            put_contract.strike = strike
            put_contract.right = "P"
            put_contract.multiplier = "100"
            
            # Request market data with Greeks
            call_req_id = req_id
            put_req_id = req_id + 1
            
            app.reqMktData(call_req_id, call_contract, "106", False, False, [])  # 106 = Option Greeks
            app.reqMktData(put_req_id, put_contract, "106", False, False, [])
            
            req_id += 2
        
        # Wait for data to populate
        time.sleep(3)
        
        # Build option chain data
        req_id = 2000
        for strike in selected_strikes:
            call_req_id = req_id
            put_req_id = req_id + 1
            
            call_data = app.option_data.get(call_req_id, {})
            put_data = app.option_data.get(put_req_id, {})
            
            # Helper to safely get values
            def safe_get(d, key, default=0):
                val = d.get(key, default)
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    return default
                return val
            
            # Calculate mid prices
            call_bid = safe_get(call_data, 'bid')
            call_ask = safe_get(call_data, 'ask')
            call_mid = round((call_bid + call_ask) / 2, 2) if call_bid and call_ask else 0
            
            put_bid = safe_get(put_data, 'bid')
            put_ask = safe_get(put_data, 'ask')
            put_mid = round((put_bid + put_ask) / 2, 2) if put_bid and put_ask else 0
            
            expiry_formatted = f"{nearest_expiry[0:4]}-{nearest_expiry[4:6]}-{nearest_expiry[6:8]}"
            
            option_data = {
                'strike': strike,
                'expiry': expiry_formatted,  
                'expiryRaw': nearest_expiry,
                'callMid': call_mid,
                'callIV': round(safe_get(call_data, 'iv') * 100, 2) if safe_get(call_data, 'iv') else 0,
                'callDelta': round(safe_get(call_data, 'delta'), 3),
                'callTheta': round(safe_get(call_data, 'theta'), 3),
                'putMid': put_mid,
                'putIV': round(safe_get(put_data, 'iv') * 100, 2) if safe_get(put_data, 'iv') else 0,
                'putDelta': round(safe_get(put_data, 'delta'), 3),
                'putTheta': round(safe_get(put_data, 'theta'), 3)
            }
            
            option_chain_data.append(option_data)
            req_id += 2
        
        print(f"[IBAPI] Successfully fetched {len(option_chain_data)} strikes", file=sys.stderr)
        
        # Disconnect
        app.disconnect()
        
        return {
            "success": True,
            "message": f"Option chain for {ticker}",
            "optionChain": option_chain_data,
            "currentPrice": round(current_price, 2)
        }
        
    except Exception as e:
        import traceback
        print(f"[IBAPI] Error: {str(e)}\n{traceback.format_exc()}", file=sys.stderr)
        return {"success": False, "message": f"Failed to get option chain: {str(e)}", "optionChain": []}


if __name__ == "__main__":
    # Test code
    if len(sys.argv) >= 5:
        result = get_option_chain_ibapi(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
        print(result)
