#!/usr/bin/env python3
"""
TWS Bridge Script - Connects to Interactive Brokers TWS/IB Gateway using ib_insync
"""

import sys
import json
import time
import traceback
from datetime import datetime

# Fix for Python 3.14+ event loop compatibility
import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    # No event loop exists, create one
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from ib_insync import IB, Contract, Order, Trade, Stock

# Global IB connection
ib = None

def log(message):
    """Log to stderr"""
    print(message, file=sys.stderr, flush=True)

def send_response(response, request_id=None):
    """Send JSON response to stdout"""
    if request_id is not None:
        response['requestId'] = request_id
    print(json.dumps(response), flush=True)
    log(f"Sent response: {json.dumps(response)}")

def connect(host, port, client_id):
    """Connect to TWS/IB Gateway using ib_insync"""
    global ib
    try:
        ib = IB()
        log(f"Attempting to connect to {host}:{port} with client ID {client_id}...")
        
        ib.connect(host, port, clientId=client_id, timeout=10)
        
        if ib.isConnected():
            log("Successfully connected using ib_insync")
            send_response({"success": True, "message": "Connected to TWS"})
            return True
        else:
            log("Failed to connect")
            send_response({"success": False, "message": "Failed to connect. Ensure TWS/Gateway is running."})
            return False
            
    except ImportError:
        log("ib_insync not installed - please run: pip install ib-insync")
        send_response({"success": False, "message": "ib_insync not installed"})
        return False
    except Exception as e:
        log(f"Error connecting: {str(e)}")
        send_response({"success": False, "message": f"Connection error: {str(e)}"})
        return False
def is_market_open():
    """Check if US options market is currently open"""
    from datetime import datetime
    import pytz
    
    # Get current time in US/Eastern timezone
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    
    # Check if it's a weekday (Monday=0, Sunday=6)
    if now.weekday() > 4:  # Saturday or Sunday
        return False, "Market is closed (weekend)"
    
    # Market hours: 9:30 AM - 4:00 PM ET
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    if now < market_open:
        return False, f"Market is closed (opens at 9:30 AM ET, currently {now.strftime('%I:%M %p ET')})"
    elif now >= market_close:
        return False, f"Market is closed (closed at 4:00 PM ET, currently {now.strftime('%I:%M %p ET')})"
    
    return True, "Market is open"




def place_order(action, ticker, quantity, expiry, strike, option_type, stop_loss_pct='--', take_profit_pct='--'):
    """Place order with optional bracket orders for SL/TP"""
    try:
        log(f"=== Starting order placement ===")
        log(f"SL/TP received: stop_loss_pct={stop_loss_pct}, take_profit_pct={take_profit_pct}")
        
        # Check if market is open before placing order
        is_open, message = is_market_open()
        if not is_open:
            log(f"Order rejected: {message}")
            return {"success": False, "message": message}
        
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
        order.tif = 'GTC'  # Explicitly set Time in Force to prevent preset conflicts
        
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
                    sl_order.transmit = True #not has_take_profit  # Only transmit if there's no TP order
                    sl_order.outsideRth = True
                    sl_order.eTradeOnly = False  # Allow order to be transmitted
                    sl_order.firmQuoteOnly = False  # Don't wait for firm quote
                    
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
                    tp_order.eTradeOnly = False  # Allow order to be transmitted
                    tp_order.firmQuoteOnly = False  # Don't wait for firm quote
                    
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



def get_positions():
    """Get positions"""
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



def get_balance():
    """Get account balance"""
    try:
        log("Requesting account values from ib_insync...")
        account_values = ib.accountValues()
        log(f"Got {len(account_values)} account values from TWS")
        net_liquidation = 0
        
        for item in account_values:
            log(f"Account value: tag={item.tag}, value={item.value}, currency={item.currency}")
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



def get_ticker_price(ticker):
    """Get ticker price"""
    try:
        log(f"Requesting ticker price for {ticker}...")
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

def validate_ticker(ticker):
    """Validate if ticker is valid and supports options trading"""
    try:
        log(f"Validating ticker: {ticker}...")
        
        # Create stock contract
        stock_contract = Stock(ticker, 'SMART', 'USD')
        qualified = ib.qualifyContracts(stock_contract)
        
        if not qualified or len(qualified) == 0:
            log(f"Ticker {ticker} not found or invalid")
            return {"success": False, "message": f"Invalid ticker symbol: {ticker}"}
        
        log(f"Stock contract qualified: {qualified[0]}")
        
        # Try to get option chain to verify options trading is available
        # Request option chain for the stock
        from ib_insync import Option
        from datetime import datetime, timedelta
        
        # Get a future date for option expiry (e.g., 30 days from now)
        future_date = (datetime.now() + timedelta(days=30)).strftime('%Y%m%d')
        
        # Try to request option chain details
        chains = ib.reqSecDefOptParams(stock_contract.symbol, '', stock_contract.secType, stock_contract.conId)
        ib.sleep(1)
        
        if not chains or len(chains) == 0:
            log(f"No options chain found for {ticker}")
            return {"success": False, "message": f"{ticker} does not support options trading"}
        
        log(f"Options trading verified for {ticker}")
        return {"success": True, "message": f"{ticker} is valid and supports options trading"}
        
    except Exception as e:
        log(f"Error validating ticker: {str(e)}\n{traceback.format_exc()}")
        return {"success": False, "message": f"Invalid or unsupported ticker: {ticker}"}




def get_daily_pnl():
    """Get account daily P&L"""
    try:
        log("Requesting account daily P&L from ib_insync...")
        account_values = ib.accountValues()
        daily_pnl = 0
        realized_pnl = 0
        unrealized_pnl = 0
        
        for item in account_values:
            log(f"Account value: tag={item.tag}, value={item.value}, currency={item.currency}")
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



def close_position(symbol, position):
    """Close position"""
    try:
        
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



def close_all_positions():
    """Close all positions"""
    try:
        log("=== Starting close all positions ===")
        
        # Check if market is open before closing positions
        is_open, message = is_market_open()
        if not is_open:
            log(f"Close all positions rejected: {message}")
            return {"success": False, "message": message}
        
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
            
            result = place_order(
                data['action'], data['ticker'], data['quantity'],
                data['expiry'], data['strike'], data['optionType'],
                stop_loss, take_profit
            )
            send_response(result, request_id)
            
        elif cmd_type == 'get_positions':
            log("Getting positions...")
            result = get_positions()
            log(f"Positions result: {result}")
            send_response(result, request_id)
            
        elif cmd_type == 'get_balance':
            log("Getting balance...")
            result = get_balance()
            log(f"Balance result: {result}")
            send_response(result, request_id)
            
        elif cmd_type == 'close_position':
            data = command.get('data', {})
            log(f"Closing position: {data}")
            result = close_position(data['symbol'], data['position'])
            send_response(result, request_id)
            
        elif cmd_type == 'get_daily_pnl':
            log("Getting daily P&L...")
            result = get_daily_pnl()
            log(f"Daily P&L result: {result}")
            send_response(result, request_id)
            
        elif cmd_type == 'close_all_positions':
            log("Closing all positions...")
            result = close_all_positions()
            log(f"Close all positions result: {result}")
            send_response(result, request_id)

        elif cmd_type == 'get_ticker_price':
            data = command.get('data', {})
            ticker = data.get('ticker', '')
            log(f"Getting ticker price for {ticker}...")
            result = get_ticker_price(ticker)
            log(f"Ticker price result: {result}")
            send_response(result, request_id)

        elif cmd_type == 'validate_ticker':
            data = command.get('data', {})
            ticker = data.get('ticker', '')
            log(f"Validating ticker {ticker}...")
            result = validate_ticker(ticker)
            log(f"Validation result: {result}")
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
            ib.sleep(0.1)
            
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
                ib.disconnect()
            except:
                pass

if __name__ == "__main__":
    main()
