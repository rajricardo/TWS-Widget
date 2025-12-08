#!/usr/bin/env python3
"""
TWS Bridge Script - Connects to Interactive Brokers TWS/IB Gateway and handles trading operations
This script attempts to use ib_insync first, then falls back to ibapi
"""

import sys
import json
import time
import traceback
from datetime import datetime

# Global IB connection
ib = None
using_ib_insync = False

def log(message):
    """Log to stderr"""
    print(message, file=sys.stderr, flush=True)

def send_response(response, request_id=None):
    """Send JSON response to stdout"""
    if request_id is not None:
        response['requestId'] = request_id
    print(json.dumps(response), flush=True)
    log(f"Sent response: {json.dumps(response)}")

def init_ib_insync(host, port, client_id):
    """Initialize connection using ib_insync"""
    global ib, using_ib_insync
    try:
        from ib_insync import IB, Contract, Order
        
        ib = IB()
        log(f"Attempting to connect to {host}:{port} with client ID {client_id}...")
        
        ib.connect(host, port, clientId=client_id, timeout=10)
        
        if ib.isConnected():
            using_ib_insync = True
            log("Successfully connected using ib_insync")
            send_response({"success": True, "message": "Connected to TWS"})
            return True
        else:
            log("Failed to connect with ib_insync")
            return False
            
    except ImportError:
        log("ib_insync not installed")
        return False
    except Exception as e:
        log(f"Error with ib_insync: {str(e)}")
        return False

def init_ibapi(host, port, client_id):
    """Initialize connection using ibapi"""
    global ib, using_ib_insync
    try:
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper
        from ibapi.contract import Contract
        from ibapi.order import Order
        import threading
        
        class IBApp(EWrapper, EClient):
            def __init__(self):
                EClient.__init__(self, self)
                self.connected = False
                self.next_order_id = None
                self.positions = []
                self.account_value = 0.0
                self.daily_pnl = 0.0
                self.realized_pnl = 0.0
                self.unrealized_pnl = 0.0
                self.request_complete = False
                self.price = 0.0
                self.price_received = False

            def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
                log(f"Error {errorCode}: {errorString}")

            def connectAck(self):
                log("Connection acknowledged")
                self.connected = True

            def nextValidId(self, orderId):
                self.next_order_id = orderId
                if not self.connected:
                    self.connected = True
                    log(f"Successfully connected using ibapi (Next order ID: {orderId})")

            def position(self, account, contract, position, avgCost):
                self.positions.append({
                    'account': account,
                    'symbol': contract.symbol if hasattr(contract, 'symbol') else '',
                    'position': position,
                    'avgCost': avgCost
                })

            def positionEnd(self):
                self.request_complete = True

            def accountSummary(self, reqId, account, tag, value, currency):
                if tag == 'NetLiquidation':
                    self.account_value = float(value)
                elif tag == 'DailyPnL':
                    self.daily_pnl = float(value)
                elif tag == 'RealizedPnL':
                    self.realized_pnl = float(value)
                elif tag == 'UnrealizedPnL':
                    self.unrealized_pnl = float(value)

            def accountSummaryEnd(self, reqId):
                self.request_complete = True

            def tickPrice(self, reqId, tickType, price, attrib):
                if tickType == 4 and price > 0:
                    self.price = price
                    self.price_received = True
                    log(f"Received price for reqId {reqId}: {price}")
        
        ib = IBApp()
        log(f"Attempting to connect to {host}:{port} with client ID {client_id}...")
        
        ib.connect(host, int(port), int(client_id))
        
        # Start the socket in a thread
        api_thread = threading.Thread(target=ib.run, daemon=True)
        api_thread.start()
        
        # Wait for connection
        timeout = 10
        start_time = time.time()
        while not ib.connected:
            if time.time() - start_time > timeout:
                log("Connection timeout")
                return False
            time.sleep(0.1)
        
        using_ib_insync = False
        send_response({"success": True, "message": "Connected to TWS"})
        return True
            
    except ImportError as e:
        log(f"ibapi not installed: {str(e)}")
        return False
    except Exception as e:
        log(f"Error with ibapi: {str(e)}")
        return False

def connect(host, port, client_id):
    """Connect to TWS/IB Gateway"""
    # Try ib_insync first
    if not init_ib_insync(host, port, client_id):
        # Fall back to ibapi
        if not init_ibapi(host, port, client_id):
            send_response({"success": False, "message": "Failed to connect. Ensure TWS/Gateway is running."})
            return False
    return True

def place_order_ib_insync(action, ticker, quantity, expiry, strike, option_type, stop_loss_pct='--', take_profit_pct='--'):
    """Place order using ib_insync with optional bracket orders for SL/TP"""
    try:
        from ib_insync import Contract, Order, Trade
        
        log(f"=== Starting order placement ===")
        log(f"SL/TP received: stop_loss_pct={stop_loss_pct}, take_profit_pct={take_profit_pct}")
        
        # Create option contract
        contract = Contract()
        contract.symbol = ticker
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = expiry
        contract.strike = strike
        contract.right = option_type  # 'C' or 'P'
        contract.multiplier = '100'
        
        # Qualify the contract
        ib.qualifyContracts(contract)
        log(f"Contract qualified: {contract}")
        
        # Create market order
        order = Order()
        order.action = action
        order.orderType = 'MKT'
        order.totalQuantity = quantity
        order.tif = 'DAY'  # Explicitly set Time in Force to prevent preset conflicts
        
        # Place the parent order
        trade = ib.placeOrder(contract, order)
        log(f"Parent order placed: {trade}")
        
        # Wait for the order to fill
        timeout = 30  # 30 seconds timeout
        start_time = time.time()
        while not trade.isDone():
            ib.sleep(0.5)
            if time.time() - start_time > timeout:
                log("Timeout waiting for order to fill")
                return {
                    "success": False,
                    "message": "Order placement timeout - check TWS for order status"
                }
        
        # Check if order was filled
        if trade.orderStatus.status != 'Filled':
            log(f"Order not filled. Status: {trade.orderStatus.status}")
            return {
                "success": False,
                "message": f"Order not filled. Status: {trade.orderStatus.status}"
            }
        
        # Get the fill price - try multiple methods
        fill_price = None
        log(f"Trade status: {trade.orderStatus}")
        log(f"Trade fills: {trade.fills}")
        
        # Method 1: Check fills list
        if trade.fills and len(trade.fills) > 0:
            # Calculate average fill price from fills
            total_quantity = 0
            total_value = 0
            for fill in trade.fills:
                fill_qty = fill.execution.shares
                fill_px = fill.execution.price
                total_quantity += fill_qty
                total_value += fill_qty * fill_px
                log(f"Fill: {fill_qty} @ ${fill_px}")
            
            if total_quantity > 0:
                fill_price = total_value / total_quantity
                log(f"Calculated fill price from fills: ${fill_price:.2f}")
        
        # Method 2: Use avgFillPrice from order status
        if fill_price is None or fill_price == 0:
            fill_price = trade.orderStatus.avgFillPrice
            log(f"Using avgFillPrice from orderStatus: ${fill_price}")
        
        # Validate fill price
        if fill_price is None or fill_price <= 0:
            log(f"ERROR: Invalid fill price: {fill_price}")
            return {
                "success": False,
                "message": f"Could not determine fill price. Order may have filled at ${fill_price}"
            }
        
        log(f"Final fill price: ${fill_price:.2f}")
        
        # Helper function to round price to valid tick size (0.05 for options under $3, 0.10 for $3+)
        def round_to_tick(price):
            if price < 3:
                tick_size = 0.05
            else:
                tick_size = 0.10
            return round(price / tick_size) * tick_size
        
        # Check if we need to place bracket orders
        has_stop_loss = stop_loss_pct != '--' and stop_loss_pct != '' and stop_loss_pct is not None
        has_take_profit = take_profit_pct != '--' and take_profit_pct != '' and take_profit_pct is not None
        
        log(f"Bracket order check: has_stop_loss={has_stop_loss}, has_take_profit={has_take_profit}")
        
        bracket_messages = []
        
        if has_stop_loss or has_take_profit:
            log(f"Placing bracket orders with OCA group - SL: {stop_loss_pct}, TP: {take_profit_pct}")
            
            # Create unique OCA group name for this bracket
            import time as time_module
            oca_group = f"Bracket_{int(time_module.time() * 1000)}"
            log(f"Created OCA group: {oca_group}")
            
            # Prepare bracket orders
            sl_order = None
            tp_order = None
            
            # Calculate and create stop loss order
            if has_stop_loss:
                try:
                    sl_pct = float(stop_loss_pct)
                    stop_price_raw = fill_price * (1 - sl_pct / 100)
                    stop_price = round_to_tick(stop_price_raw)
                    log(f"Stop Loss calculation: {sl_pct}% of ${fill_price:.2f} = ${stop_price_raw:.3f} -> rounded to ${stop_price:.2f}")
                    
                    # Create stop loss order
                    sl_order = Order()
                    sl_order.action = 'SELL' if action == 'BUY' else 'BUY'
                    sl_order.orderType = 'STP'
                    sl_order.totalQuantity = quantity
                    sl_order.auxPrice = stop_price
                    sl_order.transmit = not has_take_profit  # Only transmit if there's no TP order
                    sl_order.outsideRth = True
                    
                    # OCA settings for bracket (link with TP if both exist)
                    if has_take_profit:
                        sl_order.ocaGroup = oca_group
                        sl_order.ocaType = 1  # Cancel all remaining orders in group when one fills
                    
                    bracket_messages.append(f"Stop Loss at ${stop_price:.2f}")
                except ValueError as ve:
                    log(f"ValueError with stop loss percentage: {stop_loss_pct} - {ve}")
                except Exception as e:
                    log(f"Error preparing stop loss order: {str(e)}")
            
            # Calculate and create take profit order
            if has_take_profit:
                try:
                    tp_pct = float(take_profit_pct)
                    limit_price_raw = fill_price * (1 + tp_pct / 100)
                    limit_price = round_to_tick(limit_price_raw)
                    log(f"Take Profit calculation: {tp_pct}% of ${fill_price:.2f} = ${limit_price_raw:.3f} -> rounded to ${limit_price:.2f}")
                    
                    # Create take profit order
                    tp_order = Order()
                    tp_order.action = 'SELL' if action == 'BUY' else 'BUY'
                    tp_order.orderType = 'LMT'
                    tp_order.totalQuantity = quantity
                    tp_order.lmtPrice = limit_price
                    tp_order.transmit = True  # Always transmit the last order
                    tp_order.outsideRth = True
                    
                    # OCA settings for bracket (link with SL if both exist)
                    if has_stop_loss:
                        tp_order.ocaGroup = oca_group
                        tp_order.ocaType = 1  # Cancel all remaining orders in group when one fills
                    
                    bracket_messages.append(f"Take Profit at ${limit_price:.2f}")
                except ValueError as ve:
                    log(f"ValueError with take profit percentage: {take_profit_pct} - {ve}")
                except Exception as e:
                    log(f"Error preparing take profit order: {str(e)}")
            
            # Submit bracket orders
            if sl_order:
                log(f"Submitting stop loss order with OCA group: {sl_order.ocaGroup if hasattr(sl_order, 'ocaGroup') and sl_order.ocaGroup else 'None'}")
                sl_trade = ib.placeOrder(contract, sl_order)
                ib.sleep(0.5)
                log(f"Stop loss order placed: {sl_trade}")
            
            if tp_order:
                log(f"Submitting take profit order with OCA group: {tp_order.ocaGroup if hasattr(tp_order, 'ocaGroup') and tp_order.ocaGroup else 'None'}")
                tp_trade = ib.placeOrder(contract, tp_order)
                ib.sleep(0.5)
                log(f"Take profit order placed: {tp_trade}")
            
            if has_stop_loss and has_take_profit:
                log(f"Bracket orders linked via OCA group '{oca_group}' - one-cancels-all enabled")
        else:
            log("No bracket orders to place (both SL/TP are '--')")
        
        # Build success message
        base_message = f"{action} order filled: {quantity} {ticker} {expiry} {strike}{option_type} @ ${fill_price:.2f}"
        if bracket_messages:
            base_message += " with " + ", ".join(bracket_messages)
        
        log(f"=== Order placement complete: {base_message} ===")
        
        return {
            "success": True,
            "message": base_message
        }
        
    except Exception as e:
        log(f"Error placing order: {str(e)}\\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to place order: {str(e)}"}

def place_order_ibapi(action, ticker, quantity, expiry, strike, option_type, stop_loss_pct='--', take_profit_pct='--'):
    """Place order using ibapi with optional bracket orders for SL/TP"""
    try:
        from ibapi.contract import Contract
        from ibapi.order import Order
        
        # Create option contract
        contract = Contract()
        contract.symbol = ticker
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = expiry
        contract.strike = strike
        contract.right = option_type
        contract.multiplier = '100'
        
        # Create market order
        order = Order()
        order.action = action
        order.orderType = 'MKT'
        order.totalQuantity = quantity
        
        # Place the order
        if ib.next_order_id is None:
            return {"success": False, "message": "Not ready to place orders"}
        
        parent_order_id = ib.next_order_id
        ib.placeOrder(parent_order_id, contract, order)
        ib.next_order_id += 1
        
        time.sleep(2)  # Wait for order execution
        
        # Note: ibapi implementation is simplified and doesn't wait for fill
        # In production, you'd need to implement fill detection callbacks
        base_message = f"{action} order placed for {quantity} {ticker} {expiry} {strike}{option_type} contracts"
        
        # Check if we need to place bracket orders
        has_stop_loss = stop_loss_pct != '--' and stop_loss_pct != '' and stop_loss_pct is not None
        has_take_profit = take_profit_pct != '--' and take_profit_pct != '' and take_profit_pct is not None
        
        if has_stop_loss or has_take_profit:
            base_message += " (Note: Bracket orders with ibapi require manual fill price monitoring)"
        
        return {
            "success": True,
            "message": base_message
        }
        
    except Exception as e:
        log(f"Error placing order: {str(e)}\\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to place order: {str(e)}"}

def get_positions_ib_insync():
    """Get positions using ib_insync"""
    try:
        log("Requesting positions from ib_insync...")
        
        # Get portfolio items (more detailed than positions)
        portfolio_items = ib.portfolio()
        log(f"Got {len(portfolio_items)} portfolio items from TWS")
        position_list = []
        
        for item in portfolio_items:
            try:
                log(f"Processing portfolio item: {item}")
                
                # Get values from portfolio item
                market_value = float(item.marketValue)
                unrealized_pnl = float(item.unrealizedPNL)
                realized_pnl = float(item.realizedPNL) if hasattr(item, 'realizedPNL') else 0
                
                # Daily P&L is typically realized + unrealized for the day
                daily_pnl = unrealized_pnl  # For now, use unrealized as daily P&L
                
                # Fix avgCost for options: divide by 100 to show per-share cost
                avg_cost = float(item.averageCost)
                if item.contract.secType == 'OPT':
                    avg_cost = avg_cost / 100
                    log(f"Option position detected, adjusted avgCost from {item.averageCost} to {avg_cost}")
                
                position_data = {
                    'symbol': f"{item.contract.symbol} {item.contract.lastTradeDateOrContractMonth} {item.contract.strike}{item.contract.right}",
                    'position': float(item.position),
                    'avgCost': avg_cost,
                    'marketValue': market_value,
                    'unrealizedPNL': unrealized_pnl,
                    'dailyPNL': daily_pnl
                }
                log(f"Position data: {position_data}")
                position_list.append(position_data)
            except Exception as e:
                log(f"Error processing portfolio item: {str(e)}\n{traceback.format_exc()}")
                continue
        
        # If no portfolio items, fall back to positions
        if len(position_list) == 0:
            log("No portfolio items found, falling back to positions...")
            positions = ib.positions()
            log(f"Got {len(positions)} positions from TWS")
            
            for position in positions:
                try:
                    log(f"Processing position: {position}")
                    market_value = position.position * position.avgCost
                    unrealized_pnl = 0
                    
                    if hasattr(position, 'unrealizedPNL'):
                        unrealized_pnl = position.unrealizedPNL
                    
                    avg_cost = float(position.avgCost)
                    if position.contract.secType == 'OPT':
                        avg_cost = avg_cost / 100
                        log(f"Option position detected, adjusted avgCost from {position.avgCost} to {avg_cost}")
                    
                    position_data = {
                        'symbol': f"{position.contract.symbol} {position.contract.lastTradeDateOrContractMonth} {position.contract.strike}{position.contract.right}",
                        'position': float(position.position),
                        'avgCost': avg_cost,
                        'marketValue': float(market_value),
                        'unrealizedPNL': float(unrealized_pnl),
                        'dailyPNL': float(unrealized_pnl)  # Use unrealized as daily P&L
                    }
                    log(f"Position data: {position_data}")
                    position_list.append(position_data)
                except Exception as e:
                    log(f"Error processing position: {str(e)}\n{traceback.format_exc()}")
                    continue
        
        log(f"Returning {len(position_list)} positions")
        return {"success": True, "positions": position_list}
        
    except Exception as e:
        log(f"Error getting positions: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get positions: {str(e)}", "positions": []}

def get_positions_ibapi():
    """Get positions using ibapi"""
    try:
        log("Requesting positions from ibapi...")
        ib.positions = []
        ib.request_complete = False
        ib.reqPositions()
        
        # Wait for response
        timeout = 5
        start_time = time.time()
        while not ib.request_complete:
            if time.time() - start_time > timeout:
                log("Timeout waiting for positions")
                break
            time.sleep(0.1)
        
        log(f"Got {len(ib.positions)} positions from TWS")
        position_list = []
        for pos in ib.positions:
            try:
                position_data = {
                    'symbol': pos['symbol'],
                    'position': float(pos['position']),
                    'avgCost': float(pos['avgCost']),
                    'marketValue': float(pos['position'] * pos['avgCost']),
                    'unrealizedPNL': 0,  # Not easily available in ibapi
                    'dailyPNL': 0  # Not easily available in ibapi
                }
                log(f"Position data: {position_data}")
                position_list.append(position_data)
            except Exception as e:
                log(f"Error processing position: {str(e)}")
                continue
        
        log(f"Returning {len(position_list)} positions")
        return {"success": True, "positions": position_list}
        
    except Exception as e:
        log(f"Error getting positions: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get positions: {str(e)}", "positions": []}

def get_balance_ib_insync():
    """Get account balance using ib_insync"""
    try:
        log("Requesting account values from ib_insync...")
        account_values = ib.accountValues()
        log(f"Got {len(account_values)} account values from TWS")
        net_liquidation = 0
        
        for item in account_values:
            #log(f"Account value: tag={item.tag}, value={item.value}, currency={item.currency}")
            if item.tag == 'LookAheadAvailableFunds' and item.currency == 'USD':
                net_liquidation = float(item.value)
                log(f"Found NetLiquidation: {net_liquidation}")
                break
        
        if net_liquidation == 0:
            log("Warning: NetLiquidation not found or is 0")
        
        return {"success": True, "balance": net_liquidation}
        
    except Exception as e:
        log(f"Error getting balance: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get balance: {str(e)}", "balance": 0}

def get_balance_ibapi():
    """Get account balance using ibapi"""
    try:
        log("Requesting account summary from ibapi...")
        ib.account_value = 0.0
        ib.request_complete = False
        ib.reqAccountSummary(1, 'All', 'NetLiquidation')

        # Wait for response
        timeout = 5
        start_time = time.time()
        while not ib.request_complete:
            if time.time() - start_time > timeout:
                log("Timeout waiting for account summary")
                break
            time.sleep(0.1)

        ib.cancelAccountSummary(1)

        #log(f"Account value: {ib.account_value}")
        if ib.account_value == 0:
            log("Warning: Account value is 0")

        return {"success": True, "balance": ib.account_value}

    except Exception as e:
        log(f"Error getting balance: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get balance: {str(e)}", "balance": 0}

def get_ticker_price_ib_insync(ticker):
    """Get ticker price using ib_insync"""
    try:
        from ib_insync import Stock

        log(f"Requesting ticker price for {ticker} from ib_insync...")
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)

        ticker_data = ib.reqMktData(contract, '', False, False)
        ib.sleep(2)

        price = ticker_data.marketPrice()
        if price and price > 0:
            log(f"Got price for {ticker}: {price}")
            return {"success": True, "price": float(price)}

        if ticker_data.last and ticker_data.last > 0:
            log(f"Got last price for {ticker}: {ticker_data.last}")
            return {"success": True, "price": float(ticker_data.last)}

        if ticker_data.close and ticker_data.close > 0:
            log(f"Got close price for {ticker}: {ticker_data.close}")
            return {"success": True, "price": float(ticker_data.close)}

        log(f"No valid price found for {ticker}")
        return {"success": False, "message": f"No price data available for {ticker}", "price": 0}

    except Exception as e:
        log(f"Error getting ticker price: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get ticker price: {str(e)}", "price": 0}

def get_ticker_price_ibapi(ticker):
    """Get ticker price using ibapi"""
    try:
        from ibapi.contract import Contract

        log(f"Requesting ticker price for {ticker} from ibapi...")

        contract = Contract()
        contract.symbol = ticker
        contract.secType = 'STK'
        contract.exchange = 'SMART'
        contract.currency = 'USD'

        req_id = 9001
        ib.price = 0.0
        ib.price_received = False

        ib.reqMktData(req_id, contract, '', False, False, [])

        timeout = 5
        start_time = time.time()
        while not ib.price_received:
            if time.time() - start_time > timeout:
                log("Timeout waiting for price")
                break
            time.sleep(0.1)

        ib.cancelMktData(req_id)

        if ib.price > 0:
            log(f"Got price for {ticker}: {ib.price}")
            return {"success": True, "price": float(ib.price)}
        else:
            log(f"No valid price found for {ticker}")
            return {"success": False, "message": f"No price data available for {ticker}", "price": 0}

    except Exception as e:
        log(f"Error getting ticker price: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get ticker price: {str(e)}", "price": 0}

def get_daily_pnl_ib_insync():
    """Get account daily P&L using ib_insync"""
    try:
        log("Requesting account daily P&L from ib_insync...")
        account_values = ib.accountValues()
        daily_pnl = 0
        realized_pnl = 0
        unrealized_pnl = 0
        
        for item in account_values:
            #log(f"Account value: tag={item.tag}, value={item.value}, currency={item.currency}")
            if item.currency == 'USD' or item.currency == 'BASE':
                if item.tag == 'DailyPnL':
                    daily_pnl = float(item.value)
                    log(f"Found DailyPnL: {daily_pnl}")
                elif item.tag == 'RealizedPnL':
                    realized_pnl = float(item.value)
                    log(f"Found RealizedPnL: {realized_pnl}")
                elif item.tag == 'UnrealizedPnL':
                    unrealized_pnl = float(item.value)
                    log(f"Found UnrealizedPnL: {unrealized_pnl}")
        
        # If DailyPnL is not available, calculate it from realized + unrealized
        if daily_pnl == 0 and (realized_pnl != 0 or unrealized_pnl != 0):
            daily_pnl = realized_pnl + unrealized_pnl
            log(f"Calculated DailyPnL from Realized + Unrealized: {daily_pnl}")
        
        return {"success": True, "dailyPnL": daily_pnl}
        
    except Exception as e:
        log(f"Error getting daily P&L: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get daily P&L: {str(e)}", "dailyPnL": 0}

def get_daily_pnl_ibapi():
    """Get account daily P&L using ibapi"""
    try:
        log("Requesting daily P&L from ibapi...")
        ib.daily_pnl = 0.0
        ib.realized_pnl = 0.0
        ib.unrealized_pnl = 0.0
        ib.request_complete = False
        ib.reqAccountSummary(2, 'All', 'DailyPnL,RealizedPnL,UnrealizedPnL')
        
        # Wait for response
        timeout = 5
        start_time = time.time()
        while not ib.request_complete:
            if time.time() - start_time > timeout:
                log("Timeout waiting for daily P&L")
                break
            time.sleep(0.1)
        
        ib.cancelAccountSummary(2)
        
        # Calculate total if DailyPnL not available
        daily_pnl = ib.daily_pnl if hasattr(ib, 'daily_pnl') and ib.daily_pnl != 0 else (ib.realized_pnl + ib.unrealized_pnl)
        
        log(f"Daily P&L: {daily_pnl}")
        return {"success": True, "dailyPnL": daily_pnl}
        
    except Exception as e:
        log(f"Error getting daily P&L: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to get daily P&L: {str(e)}", "dailyPnL": 0}

def close_position_ib_insync(symbol, position):
    """Close position using ib_insync"""
    try:
        from ib_insync import Order, Contract
        
        # Find the position
        positions = ib.positions()
        target_position = None
        
        for pos in positions:
            pos_symbol = f"{pos.contract.symbol} {pos.contract.lastTradeDateOrContractMonth} {pos.contract.strike}{pos.contract.right}"
            if pos_symbol == symbol:
                target_position = pos
                break
        
        if not target_position:
            return {"success": False, "message": "Position not found"}
        
        # Reconstruct the contract with exchange='SMART' to avoid "Missing order exchange" error
        contract = Contract()
        contract.symbol = target_position.contract.symbol
        contract.secType = target_position.contract.secType
        contract.exchange = 'SMART'  # Ensure exchange is set to SMART
        contract.currency = target_position.contract.currency
        contract.lastTradeDateOrContractMonth = target_position.contract.lastTradeDateOrContractMonth
        contract.strike = target_position.contract.strike
        contract.right = target_position.contract.right
        contract.multiplier = target_position.contract.multiplier
        
        log(f"Reconstructed contract: {contract}")
        
        # Qualify the contract to ensure it's valid
        ib.qualifyContracts(contract)
        
        # Create closing order
        action = 'SELL' if position > 0 else 'BUY'
        order = Order()
        order.action = action
        order.orderType = 'MKT'
        order.totalQuantity = abs(position)
        
        log(f"Placing closing order: action={action}, quantity={abs(position)}")
        
        # Place the order
        trade = ib.placeOrder(contract, order)
        ib.sleep(1)
        
        return {"success": True, "message": f"Position closed for {symbol}"}
        
    except Exception as e:
        log(f"Error closing position: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to close position: {str(e)}"}

def close_position_ibapi(symbol, position):
    """Close position using ibapi"""
    # This is simplified for ibapi - in production, you'd need to reconstruct the contract
    return {"success": False, "message": "Close position not fully implemented for ibapi"}

def close_all_positions_ib_insync():
    """Close all positions using ib_insync"""
    try:
        from ib_insync import Order, Contract
        
        log("Fetching all positions to close...")
        positions = ib.positions()
        
        if not positions or len(positions) == 0:
            return {"success": True, "message": "No positions to close"}
        
        closed_count = 0
        failed_count = 0
        
        for pos in positions:
            try:
                # Skip if position is 0
                if pos.position == 0:
                    continue
                
                # Reconstruct the contract with exchange='SMART'
                contract = Contract()
                contract.symbol = pos.contract.symbol
                contract.secType = pos.contract.secType
                contract.exchange = 'SMART'
                contract.currency = pos.contract.currency
                contract.lastTradeDateOrContractMonth = pos.contract.lastTradeDateOrContractMonth
                contract.strike = pos.contract.strike
                contract.right = pos.contract.right
                contract.multiplier = pos.contract.multiplier
                
                log(f"Reconstructed contract: {contract}")
                
                # Qualify the contract
                ib.qualifyContracts(contract)
                
                # Create closing order
                action = 'SELL' if pos.position > 0 else 'BUY'
                order = Order()
                order.action = action
                order.orderType = 'MKT'
                order.totalQuantity = abs(pos.position)
                
                pos_symbol = f"{pos.contract.symbol} {pos.contract.lastTradeDateOrContractMonth} {pos.contract.strike}{pos.contract.right}"
                log(f"Closing position: {pos_symbol}, action={action}, quantity={abs(pos.position)}")
                
                # Place the order
                trade = ib.placeOrder(contract, order)
                ib.sleep(0.5)
                
                closed_count += 1
            except Exception as e:
                log(f"Error closing position {pos.contract.symbol}: {str(e)}")
                failed_count += 1
                continue
        
        if failed_count == 0:
            return {"success": True, "message": f"Successfully closed {closed_count} positions"}
        else:
            return {"success": True, "message": f"Closed {closed_count} positions, {failed_count} failed"}
        
    except Exception as e:
        log(f"Error closing all positions: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Failed to close all positions: {str(e)}"}

def close_all_positions_ibapi():
    """Close all positions using ibapi"""
    # This is simplified for ibapi - in production, you'd need full implementation
    return {"success": False, "message": "Close all positions not fully implemented for ibapi"}

def handle_command(command):
    """Handle incoming command"""
    global ib
    
    cmd_type = command.get('type')
    request_id = command.get('requestId')
    
    log(f"Handling command: {cmd_type} with requestId: {request_id}")
    
    try:
        if cmd_type == 'place_order':
            data = command.get('data', {})
            log(f"Placing order: {data}")
            
            # Extract SL/TP parameters
            stop_loss = data.get('stopLoss', '--')
            take_profit = data.get('takeProfit', '--')
            
            if using_ib_insync:
                result = place_order_ib_insync(
                    data['action'], data['ticker'], data['quantity'],
                    data['expiry'], data['strike'], data['optionType'],
                    stop_loss, take_profit
                )
            else:
                result = place_order_ibapi(
                    data['action'], data['ticker'], data['quantity'],
                    data['expiry'], data['strike'], data['optionType'],
                    stop_loss, take_profit
                )
            send_response(result, request_id)
            
        elif cmd_type == 'get_positions':
            log("Getting positions...")
            if using_ib_insync:
                result = get_positions_ib_insync()
            else:
                result = get_positions_ibapi()
            log(f"Positions result: {result}")
            send_response(result, request_id)
            
        elif cmd_type == 'get_balance':
            log("Getting balance...")
            if using_ib_insync:
                result = get_balance_ib_insync()
            else:
                result = get_balance_ibapi()
            log(f"Balance result: {result}")
            send_response(result, request_id)
            
        elif cmd_type == 'close_position':
            data = command.get('data', {})
            log(f"Closing position: {data}")
            if using_ib_insync:
                result = close_position_ib_insync(data['symbol'], data['position'])
            else:
                result = close_position_ibapi(data['symbol'], data['position'])
            send_response(result, request_id)
            
        elif cmd_type == 'get_daily_pnl':
            log("Getting daily P&L...")
            if using_ib_insync:
                result = get_daily_pnl_ib_insync()
            else:
                result = get_daily_pnl_ibapi()
            log(f"Daily P&L result: {result}")
            send_response(result, request_id)
            
        elif cmd_type == 'close_all_positions':
            log("Closing all positions...")
            if using_ib_insync:
                result = close_all_positions_ib_insync()
            else:
                result = close_all_positions_ibapi()
            log(f"Close all positions result: {result}")
            send_response(result, request_id)

        elif cmd_type == 'get_ticker_price':
            data = command.get('data', {})
            ticker = data.get('ticker', '')
            log(f"Getting ticker price for {ticker}...")
            if using_ib_insync:
                result = get_ticker_price_ib_insync(ticker)
            else:
                result = get_ticker_price_ibapi(ticker)
            log(f"Ticker price result: {result}")
            send_response(result, request_id)

        else:
            log(f"Unknown command: {cmd_type}")
            send_response({"success": False, "message": f"Unknown command: {cmd_type}"}, request_id)
            
    except Exception as e:
        log(f"Error handling command {cmd_type}: {str(e)}\n{traceback.format_exc()}")
        send_response({"success": False, "message": f"Error: {str(e)}"}, request_id)

def main():
    if len(sys.argv) != 4:
        log("Usage: tws_bridge.py <host> <port> <client_id>")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    client_id = int(sys.argv[3])
    
    # Connect to TWS
    if not connect(host, port, client_id):
        sys.exit(1)
    
    log("Bridge ready, waiting for commands...")
    
    # Command loop
    try:
        while True:
            if using_ib_insync:
                ib.sleep(0.1)
            else:
                time.sleep(0.1)
            
            # Read commands from stdin
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                
                command = json.loads(line.strip())
                handle_command(command)
                
            except json.JSONDecodeError:
                continue
            except Exception as e:
                log(f"Error processing command: {str(e)}\n{traceback.format_exc()}")
                continue
                
    except KeyboardInterrupt:
        log("Shutting down...")
    finally:
        if ib:
            try:
                if using_ib_insync:
                    ib.disconnect()
                else:
                    ib.disconnect()
            except:
                pass

if __name__ == "__main__":
    main()
