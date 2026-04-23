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
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, CryptoBarsRequest
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
    crypto_data_client = CryptoHistoricalDataClient()  # No keys needed for crypto data
except Exception as e:
    trading_client = None
    data_client = None
    crypto_data_client = None
    print(f"Failed to initialize Alpaca clients: {e}. Please check your .env file.")

# Symbols to check
STOCK_SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "SPY"]
CRYPTO_SYMBOLS = ["BTC/USD", "ETH/USD"]
SYMBOLS = STOCK_SYMBOLS  # Keep for backward compatibility

# Crypto position tracking for manual stop-loss / take-profit
CRYPTO_RISK_PCT = 0.01   # 1% stop loss
CRYPTO_REWARD_PCT = 0.03  # 3% take profit
CRYPTO_NOTIONAL = 50      # $50 per crypto trade

def is_crypto(symbol):
    """Returns True if the symbol is a crypto pair (contains '/')."""
    return '/' in symbol


def get_historical_data(symbols, days=30):
    """Fetch historical bars for STOCK symbols."""
    if not data_client: return None
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    request_params = StockBarsRequest(
        symbol_or_symbols=symbols,
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
        print(f"Error fetching stock data: {e}")
        return None


def get_crypto_historical_data(symbols, days=60):
    """Fetch historical bars for CRYPTO symbols via the dedicated Crypto API."""
    if not crypto_data_client: return None
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    request_params = CryptoBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start_date,
        end=end_date,
    )
    
    try:
        bars = crypto_data_client.get_crypto_bars(request_params)
        df = bars.df
        return df
    except Exception as e:
        print(f"Error fetching crypto data: {e}")
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
    """Execute a trade. Stocks use bracket orders; crypto uses simple market orders."""
    if not trading_client: return
    
    risk_pct = 0.01
    reward_pct = 0.03
    
    try:
        if signal == "BUY":
            stop_price = round(close_price * (1 - risk_pct), 2)
            limit_price = round(close_price * (1 + reward_pct), 2)
            
            if is_crypto(symbol):
                # Crypto: No bracket orders allowed — use simple market order
                order = MarketOrderRequest(
                    symbol=symbol,
                    notional=CRYPTO_NOTIONAL,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC,
                )
                trading_client.submit_order(order_data=order)
                print(f"Executing CRYPTO BUY for {symbol} (${CRYPTO_NOTIONAL}) at {close_price}")
                
                send_discord_notification(
                    "🟢 Crypto Trade Opened",
                    f"**Symbol**: {symbol}\n**Type**: BUY\n**Amount**: ${CRYPTO_NOTIONAL}\n**Entry Price**: ${close_price:.2f}\n**Target TP**: ${limit_price:.2f} (+3%)\n**Target SL**: ${stop_price:.2f} (-1%)",
                    color=0xf7931a
                )
            else:
                # Stocks: Use bracket order with built-in SL/TP
                bracket_order = MarketOrderRequest(
                    symbol=symbol,
                    qty=1,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=limit_price),
                    stop_loss=StopLossRequest(stop_price=stop_price)
                )
                trading_client.submit_order(order_data=bracket_order)
                print(f"Executing BUY for {symbol} at {close_price} - Stop Loss: {stop_price}, Take Profit: {limit_price}")
                
                send_discord_notification(
                    "🟢 New Trade Opened",
                    f"**Symbol**: {symbol}\n**Type**: BUY\n**Entry Target**: ${close_price}\n**Take Profit**: ${limit_price}\n**Stop Loss**: ${stop_price}",
                    color=0x3fb950
                )
            
    except Exception as e:
        print(f"Error executing trade for {symbol}: {e}")

def send_discord_notification(title, message, color=0x58a6ff):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        print("Discord webhook skipped: DISCORD_WEBHOOK_URL not set")
        return
    data = {"embeds": [{"title": title, "description": message, "color": color}]}
    try:
        resp = requests.post(webhook_url, json=data, timeout=5)
        print(f"Discord notification sent: {resp.status_code}")
    except Exception as e:
        print(f"Discord notification failed: {e}")

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
                if last_check_time and act.transaction_time > last_check_time:
                    if act.side.value.upper() == "SELL":
                        color = 0x3fb950 if float(act.price) > float(act.price) else 0xf85149
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
        return last_check_time

def check_crypto_positions():
    """Manually check crypto positions for stop-loss / take-profit exits.
    Alpaca doesn't support bracket orders for crypto, so we monitor ourselves."""
    if not trading_client: return
    try:
        positions = trading_client.get_all_positions()
        for pos in positions:
            if not is_crypto(pos.symbol):
                continue
            
            entry = float(pos.avg_entry_price)
            current = float(pos.current_price)
            pnl_pct = (current - entry) / entry
            
            # Take Profit at +3%
            if pnl_pct >= CRYPTO_REWARD_PCT:
                order = MarketOrderRequest(
                    symbol=pos.symbol,
                    qty=float(pos.qty),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                )
                trading_client.submit_order(order_data=order)
                pnl = float(pos.unrealized_pl)
                send_discord_notification(
                    "🎯 Crypto Take Profit Hit!",
                    f"**Symbol**: {pos.symbol}\n**Entry**: ${entry:.2f}\n**Exit**: ${current:.2f}\n**P/L**: ${pnl:+.2f} ({pnl_pct*100:+.1f}%)",
                    color=0x3fb950
                )
                print(f"CRYPTO TP HIT: {pos.symbol} at ${current:.2f} ({pnl_pct*100:+.1f}%)")
            
            # Stop Loss at -1%
            elif pnl_pct <= -CRYPTO_RISK_PCT:
                order = MarketOrderRequest(
                    symbol=pos.symbol,
                    qty=float(pos.qty),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                )
                trading_client.submit_order(order_data=order)
                pnl = float(pos.unrealized_pl)
                send_discord_notification(
                    "🛑 Crypto Stop Loss Hit",
                    f"**Symbol**: {pos.symbol}\n**Entry**: ${entry:.2f}\n**Exit**: ${current:.2f}\n**P/L**: ${pnl:+.2f} ({pnl_pct*100:+.1f}%)",
                    color=0xf85149
                )
                print(f"CRYPTO SL HIT: {pos.symbol} at ${current:.2f} ({pnl_pct*100:+.1f}%)")
            else:
                print(f"CRYPTO HOLD: {pos.symbol} entry=${entry:.2f} now=${current:.2f} ({pnl_pct*100:+.1f}%)")
    except Exception as e:
        print(f"Error checking crypto positions: {e}")


def run_bot_cycle():
    """Single execution cycle for Market checking (Used by Serverless Cron)"""
    print("AuraBot checking market conditions...")
    
    from datetime import timedelta
    last_fill_check = datetime.now(timezone.utc) - timedelta(minutes=5)
    check_for_fills(last_fill_check)
    
    # ── Check crypto positions for manual SL/TP exits ──
    check_crypto_positions()
    
    # ── STOCKS: Bulk fetch all stock symbols ──
    all_bars = get_historical_data(STOCK_SYMBOLS)
    if all_bars is not None:
        for symbol in STOCK_SYMBOLS:
            if symbol in all_bars.index.get_level_values(0):
                df = all_bars.loc[symbol]
                if df is not None and len(df) > 30:
                    signal = indicator_ensemble(df)
                    current_price = df['close'].iloc[-1]
                    print(f"{symbol} - Price: {current_price:.2f} - Signal: {signal}")
                    if signal != "HOLD":
                        execute_trade(symbol, signal, current_price)
    
    # ── CRYPTO: Bulk fetch all crypto symbols ──
    crypto_bars = get_crypto_historical_data(CRYPTO_SYMBOLS)
    if crypto_bars is not None:
        for symbol in CRYPTO_SYMBOLS:
            if symbol in crypto_bars.index.get_level_values(0):
                df = crypto_bars.loc[symbol]
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
