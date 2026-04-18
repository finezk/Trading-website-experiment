import json
import os
from pathlib import Path
from datetime import datetime, timedelta

from flask import Flask, render_template, jsonify
from dotenv import load_dotenv

# Always load .env from the same folder as app.py
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("APCA_API_KEY_ID", "")
SECRET_KEY = os.getenv("APCA_API_SECRET_KEY", "")

SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "SPY"]

app = Flask(__name__)

from werkzeug.exceptions import HTTPException
@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    return f"AuraBot App Error: {type(e).__name__}: {str(e)}", 500

# ── helpers ───────────────────────────────────────────────────

def alpaca_clients():
    """Return (trading_client, data_client) or (None, None) when keys missing."""
    if not API_KEY or not SECRET_KEY:
        return None, None
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import StockHistoricalDataClient
        trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
        data = StockHistoricalDataClient(API_KEY, SECRET_KEY)
        return trading, data
    except Exception as e:
        print(f"Alpaca client error: {e}")
        return None, None


def get_real_prices():
    """Fetch the latest daily close price for each symbol via Alpaca."""
    _, data_client = alpaca_clients()
    if not data_client:
        return {}

    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    end = datetime.utcnow()
    start = end - timedelta(days=5)   # look back a few days to guarantee data

    try:
        from alpaca.data.enums import DataFeed
        req = StockBarsRequest(
            symbol_or_symbols=SYMBOLS,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
        bars = data_client.get_stock_bars(req).df
        # bars is a multi-index df: (symbol, timestamp) → pick last bar per symbol
        prices = {}
        for sym in SYMBOLS:
            try:
                prices[sym] = float(bars.loc[sym]['close'].iloc[-1])
            except Exception:
                pass
        return prices
    except Exception as e:
        print(f"Price fetch error: {e}")
        return {}


def get_real_positions(trading_client):
    """Return open Alpaca positions as a list of dicts."""
    try:
        positions = trading_client.get_all_positions()
        result = []
        for p in positions:
            entry = float(p.avg_entry_price)
            current = float(p.current_price)
            pnl = float(p.unrealized_pl)
            result.append({
                "symbol": p.symbol,
                "type": "BUY" if float(p.qty) > 0 else "SELL",
                "entry": round(entry, 2),
                "exit": round(current, 2),
                "profit": pnl >= 0,
                "pnl": round(pnl, 2),
            })
        return result
    except Exception as e:
        print(f"Position fetch error: {e}")
        return []

# ── routes ────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    # Try live Alpaca account info
    trading_client, _ = alpaca_clients()
    if not trading_client:
        return jsonify({
            "bot_status": "⚠️ Add API keys to .env",
            "paper_balance": 0.0,
            "daily_profit": 0.0,
            "win_rate": "-"
        })

    try:
        account = trading_client.get_account()
        return jsonify({
            "bot_status": "Running",
            "paper_balance": float(account.portfolio_value),
            "daily_profit": float(account.equity) - float(account.last_equity) if account.last_equity else 0.0,
            "win_rate": "Active 🟢"
        })
    except Exception as e:
        return jsonify({
            "bot_status": f"⚠️ API Error",
            "paper_balance": 0.0,
            "daily_profit": 0.0,
            "win_rate": "-"
        })


@app.route('/api/trades')
def get_trades():
    # Try live open positions from Alpaca
    trading_client, _ = alpaca_clients()
    if trading_client:
        positions = get_real_positions(trading_client)
        if positions:
            return jsonify(positions)

    # Try to build a "last signals" table using real prices + mock context
    prices = get_real_prices()
    if prices:
        mock_trades = []
        for i, (sym, price) in enumerate(prices.items()):
            # Show real price as entry; exit is a plausible 1:3 scenario
            sl = round(price * 0.99, 2)
            tp = round(price * 1.03, 2)
            mock_trades.append({
                "id": i + 1,
                "symbol": sym,
                "type": "BUY",
                "entry": price,
                "exit": tp,
                "profit": True,
                "pnl": round(tp - price, 2),
            })
        return jsonify(mock_trades)

    # Full fallback when no API keys present
    return jsonify([{
        "id": 1,
        "symbol": "–",
        "type": "–",
        "entry": "–",
        "exit": "–",
        "profit": None,
        "pnl": 0,
    }])


@app.route('/api/prices')
def get_prices():
    """Endpoint for live symbol prices shown on the dashboard."""
    prices = get_real_prices()
    return jsonify(prices if prices else {"status": "No API keys set"})


@app.route('/api/chart/<symbol>')
def get_chart_data(symbol):
    """Return 60 days of daily OHLC prices for candlestick chart."""
    _, data_client = alpaca_clients()
    if not data_client:
        return jsonify({"error": "No API keys"}), 400

    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed

    end = datetime.utcnow()
    start = end - timedelta(days=90)

    try:
        req = StockBarsRequest(
            symbol_or_symbols=symbol.upper(),
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
        bars = data_client.get_stock_bars(req).df
        sym_bars = bars.loc[symbol.upper()]
        candles = []
        for ts, row in sym_bars.iterrows():
            candles.append({
                "x": ts.strftime('%Y-%m-%d'),
                "o": round(float(row['open']), 2),
                "h": round(float(row['high']), 2),
                "l": round(float(row['low']), 2),
                "c": round(float(row['close']), 2),
            })
        return jsonify({"candles": candles, "symbol": symbol.upper()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Kick off bot.py as a background process."""
    import subprocess
    try:
        subprocess.Popen(
            ['python3', str(BASE_DIR / 'bot.py')],
            cwd=str(BASE_DIR),
            stdout=open(str(BASE_DIR / 'bot.log'), 'a'),
            stderr=subprocess.STDOUT,
        )
        return jsonify({"status": "Bot started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cron')
def cron_job():
    """Serverless endpoint triggered by Vercel Cron or a ping service."""
    try:
        import bot
        result = bot.run_bot_cycle()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8080)
