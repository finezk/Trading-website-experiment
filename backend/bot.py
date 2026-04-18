import os
import time
from pathlib import Path
import pandas as pd
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

import requests
import json
from datetime import datetime, timezone

# Load Alpaca API Keys from .env (same folder as this script)
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / '.env')
API_KEY = os.getenv("APCA_API_KEY_ID", "YOUR_API_KEY")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY", "YOUR_SECRET_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Set to False if going live
PAPER = True

try:
    trading_client = TradingClient(API_KEY, SECRET_KEY, paper=PAPER)
    data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
except Exception as e:
    trading_client = None
    data_client = None
    print(f"Failed to initialize Alpaca clients: {e}. Please check your .env file.")

# Symbols to check (US Stocks as requested)
SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "SPY"]

def get_historical_data(symbol, days=30):
    if not data_client: return None
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Day,
        start=start_date,
        end=end_date,
        feed=DataFeed.IEX,
    )
    
    try:
        bars = data_client.get_stock_bars(request_params)
        df = bars.df
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def indicator_ensemble(df):
    """
    Applies the "All of them" ensemble strategy:
    Checks EMA Crossover, MACD, and RSI at once.
    """
    close = df['close']
    
    # 1. EMA (Exponential Moving Average)
    ema_fast = EMAIndicator(close, window=12).ema_indicator()
    ema_slow = EMAIndicator(close, window=26).ema_indicator()
    
    # 2. MACD (Moving Average Convergence Divergence)
    macd_obj = MACD(close)
    macd = macd_obj.macd()
    macd_signal = macd_obj.macd_signal()
    
    # 3. RSI (Relative Strength Index)
    rsi = RSIIndicator(close, window=14).rsi()
    
    # Current values
    current_idx = -1
    
    # Ensemble Logic - Bullish
    bullish = (
        ema_fast.iloc[current_idx] > ema_slow.iloc[current_idx] and
        macd.iloc[current_idx] > macd_signal.iloc[current_idx] and
        50 < rsi.iloc[current_idx] < 70 # RSI is bullish but not overbought
    )
    
    # Ensemble Logic - Bearish
    bearish = (
        ema_fast.iloc[current_idx] < ema_slow.iloc[current_idx] and
        macd.iloc[current_idx] < macd_signal.iloc[current_idx] and
        30 < rsi.iloc[current_idx] < 50 # RSI is bearish but not oversold
    )
    
    if bullish:
        return "BUY"
    elif bearish:
        return "SELL"
    else:
        return "HOLD"

def execute_trade(symbol, signal, close_price):
    if not trading_client: return
    
    # 1:3 Risk/Reward Math:
    # Example: Risking 1% of the asset price, target 3% of asset price
    risk_pct = 0.01
    reward_pct = 0.03
    
    qty = 1 # We buy 1 share for paper test brevity
    
    try:
        if signal == "BUY":
            stop_price = round(close_price * (1 - risk_pct), 2)
            limit_price = round(close_price * (1 + reward_pct), 2)
            
            bracket_order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=limit_price),
                stop_loss=StopLossRequest(stop_price=stop_price)
            )
            trading_client.submit_order(order_data=bracket_order)
            print(f"Executing BUY for {symbol} at {close_price} - Stop Loss: {stop_price}, Take Profit: {limit_price}")
            
            # Send Notification
            send_discord_notification(
                "🟢 New Trade Opened",
                f"**Symbol**: {symbol}\n**Type**: BUY\n**Entry Target**: ${close_price}\n**Take Profit**: ${limit_price}\n**Stop Loss**: ${stop_price}",
                color=0x3fb950
            )
            
    except Exception as e:
        print(f"Error executing trade for {symbol}: {e}")

def send_discord_notification(title, message, color=0x58a6ff):
    if not DISCORD_WEBHOOK_URL:
        return
    data = {"embeds": [{"title": title, "description": message, "color": color}]}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except:
        pass

def check_for_fills(last_check_time):
    if not trading_client: return last_check_time
    try:
        from alpaca.trading.requests import GetOrderActivitiesRequest
        from alpaca.trading.enums import ActivityType
        
        req = GetOrderActivitiesRequest(
            activity_types=[ActivityType.FILL],
            date=(last_check_time if last_check_time else None)
        )
        activities = trading_client.get_account_activities(req)
        
        now = datetime.now(timezone.utc)
        
        if activities:
            for act in activities:
                # Only alert for activities that happened after our last check
                if last_check_time and act.transaction_time > last_check_time:
                    # If it's a sell, it means our bracket closed (TP or SL)
                    if act.side.value.upper() == "SELL":
                        color = 0x3fb950 if float(act.price) > float(act.price) else 0xf85149 # we will just use standard blue
                        send_discord_notification(
                            "📉 Position Closed (Filled)",
                            f"**Symbol**: {act.symbol}\n**Type**: SELL / Close\n**Fill Price**: ${act.price}\n**Qty**: {act.qty}",
                            color=0x58a6ff
                        )
                    else:
                        send_discord_notification(
                            "✅ Order Filled",
                            f"**Symbol**: {act.symbol}\n**Type**: BUY / Open\n**Fill Price**: ${act.price}\n**Qty**: {act.qty}",
                            color=0x58a6ff
                        )
        return now
    except Exception as e:
        # Avoid crashing loop if activities fail
        return last_check_time

def update_ui_status():
    if not trading_client: return
    try:
        account = trading_client.get_account()
        status_data = {
            "bot_status": "Running API",
            "paper_balance": float(account.portfolio_value),
            "daily_profit": float(account.equity) - float(account.last_equity) if account.last_equity else 0,
            "win_rate": "Running..." 
        }
        with open('bot_state.json', 'w') as f:
            json.dump(status_data, f)
    except Exception as e:
        pass

def run_bot_cycle():
    """Single execution cycle for Market checking (Used by Serverless Cron)"""
    print("AuraBot checking market conditions...")
    update_ui_status()
    
    # We check fills from the last 5 minutes when running serverless
    from datetime import timedelta
    last_fill_check = datetime.now(timezone.utc) - timedelta(minutes=5)
    check_for_fills(last_fill_check)
    
    for symbol in SYMBOLS:
        df = get_historical_data(symbol)
        if df is not None and len(df) > 30:
            signal = indicator_ensemble(df)
            current_price = df['close'].iloc[-1]
            
            print(f"{symbol} - Price: {current_price:.2f} - Signal: {signal}")
            
            if signal != "HOLD":
                execute_trade(symbol, signal, current_price)

    return {"status": "success", "message": "Cycle complete"}

def run_bot():
    """Local infinite loop execution"""
    print("AuraBot Strategy Engine Started (Ensemble Indicators) - 1:3 RR targeted")
    while True:
        run_bot_cycle()
        print("Sleeping for 60 seconds...")
        time.sleep(60)

if __name__ == "__main__":
    # If run directly as a script
    run_bot()
