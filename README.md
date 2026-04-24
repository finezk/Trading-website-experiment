# AuraBot — Automated Algorithmic Trading Bot

An autonomous, cloud-hosted algorithmic trading bot built with Python (Flask) and deployed on Vercel. AuraBot uses a multi-indicator ensemble strategy to scan US Stocks and Cryptocurrencies, executing bracket orders with built-in risk management — all without human intervention.

> ⚠️ **DISCLAIMER — PLEASE READ BEFORE USE**
>
> This software is provided strictly for **educational and paper trading purposes only**. It is not financial advice. Trading stocks and cryptocurrencies involves substantial risk of loss and is not suitable for every investor. Past performance is not indicative of future results.
>
> **The creator(s) of this software are not liable for any financial losses incurred through the use of this bot.** By using AuraBot, you acknowledge that you are solely responsible for your own trading decisions and any resulting gains or losses. Use at your own risk.

---

## Features

- **Ensemble Indicator Strategy** — Combines EMA Crossover, MACD, and RSI into a single consensus signal. A trade is only executed when **all three indicators align**, reducing false entries.
- **Automated Bracket Orders** — Every stock trade includes a built-in **1% Stop-Loss** and **3% Take-Profit** (1:3 risk/reward ratio), managed automatically by Alpaca.
- **Crypto Support (24/7)** — Scans BTC, ETH, and SOL around the clock. Since Alpaca doesn't support bracket orders for crypto, the bot manually monitors positions and exits at the defined SL/TP levels on each cycle.
- **Serverless Architecture** — Deployed on Vercel as a stateless serverless function. No server to maintain, no process to keep alive.
- **Discord Notifications** — Real-time alerts sent to a Discord channel whenever a trade is opened, filled, or closed.
- **Live Dashboard** — A web-based UI with real-time portfolio balance, candlestick charts (powered by Chart.js), and live position tracking.

---

## Tech Stack

| Layer        | Technology                              |
|--------------|-----------------------------------------|
| Backend      | Python, Flask                           |
| Trading API  | Alpaca Markets (Paper & Live)           |
| Indicators   | `ta` (Technical Analysis Library)       |
| Data         | `pandas`, Alpaca Stock & Crypto APIs    |
| Frontend     | Vanilla JS, Chart.js (Candlestick)      |
| Hosting      | Vercel (Serverless Functions)           |
| Scheduling   | cron-job.org (External Cron Trigger)    |
| Alerts       | Discord Webhooks                        |

---

## Watchlist

### Stocks (Market Hours Only)
`AAPL` · `MSFT` · `TSLA` · `NVDA` · `SPY`

### Crypto (24/7)
`BTC/USD` · `ETH/USD` · `SOL/USD`

---

## Strategy Overview

AuraBot runs an **ensemble indicator strategy** using daily candlestick data. A trade signal is only generated when all three of the following conditions agree:

| Indicator | Bullish Condition               | Bearish Condition               |
|-----------|----------------------------------|---------------------------------|
| EMA       | Fast (12) > Slow (26)           | Fast (12) < Slow (26)          |
| MACD      | MACD Line > Signal Line         | MACD Line < Signal Line        |
| RSI (14)  | Between 50–70 (not overbought)  | Between 30–50 (not oversold)   |

### Risk Management
- **Stop-Loss**: 1% below entry price
- **Take-Profit**: 3% above entry price
- **Position Size**: 1 share per stock / $50 notional per crypto trade

---

## Setup & Deployment

### Prerequisites
- [Alpaca](https://alpaca.markets/) account (Paper Trading)
- [Discord Webhook URL](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) (optional, for notifications)
- [Vercel](https://vercel.com/) account
- [cron-job.org](https://cron-job.org/) account (free external cron)

### Environment Variables

Set the following in Vercel's **Project Settings → Environment Variables**:

| Variable              | Description                        |
|-----------------------|------------------------------------|
| `APCA_API_KEY_ID`     | Your Alpaca API Key ID             |
| `APCA_API_SECRET_KEY` | Your Alpaca API Secret Key         |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook URL        |

### Deployment Steps

1. **Clone** the repository
2. Push to GitHub and **import** the repo into Vercel
3. Set the **Root Directory** to `backend` in Vercel project settings
4. Add the environment variables listed above
5. **Deploy** — Vercel will automatically install dependencies from `requirements.txt`
6. Set up a cron job on [cron-job.org](https://cron-job.org/) pointing to:
   ```
   https://your-vercel-domain.vercel.app/api/cron
   ```
   With a cron expression of `*/5 * * * *` (every 5 minutes, 24/7)

### Local Development

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Visit `http://localhost:8080` to see the dashboard.

---

## Project Structure

```
backend/
├── app.py              # Flask web server & API routes
├── bot.py              # Trading engine & indicator logic
├── requirements.txt    # Python dependencies
├── vercel.json         # Vercel deployment configuration
├── .env                # Local environment variables (not committed)
├── static/
│   ├── app.js          # Dashboard frontend logic
│   └── style.css       # Dashboard styling
└── templates/
    └── index.html      # Dashboard HTML template
```

---

## API Endpoints

| Endpoint          | Method | Description                                |
|-------------------|--------|--------------------------------------------|
| `/`               | GET    | Serves the trading dashboard               |
| `/api/status`     | GET    | Returns portfolio balance & bot status     |
| `/api/trades`     | GET    | Returns open positions & signals           |
| `/api/prices`     | GET    | Returns latest prices for all symbols      |
| `/api/chart/<sym>`| GET    | Returns 90 days of OHLC candlestick data   |
| `/api/cron`       | GET    | Triggers one full bot scan cycle           |

---

## License

This project is for personal and educational use. See disclaimer above.

---

*Built with ❤️ and algorithms.*
