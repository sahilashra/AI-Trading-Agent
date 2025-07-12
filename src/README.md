# AI Trading Agent

This is a sophisticated, AI-powered swing trading agent designed to operate on the Indian stock market (NSE). It uses Google's Gemini for its core trading decisions and is integrated with the Zerodha Kite API for live data and trade execution. The agent is fully controllable via a Telegram bot.

## Features

- **AI-Driven Decisions:** Leverages a Large Language Model (Gemini) to analyze market data, technical indicators, and financial news to make buy/sell/hold decisions.
- **Portfolio-First Logic:** Prioritizes managing existing holdings before scanning for new opportunities.
- **Market Trend Filter:** Protects capital by disabling new purchases during a market downtrend (based on the Nifty 50's 200-day SMA).
- **Confirmation Signals:** Waits for price confirmation before entering new trades to avoid false starts and improve entry quality.
- **Advanced Risk Management:**
  - **Volatility-Adjusted Position Sizing:** Calculates trade size based on a stock's volatility (ATR) to ensure equal risk on every trade.
  - **Trailing Stop-Loss:** Protects profits by automatically raising the stop-loss as a stock's price increases.
- **Full Telegram Control:**
  - `/start` & `/stop`: Remotely start and stop the agent's trading activity.
  - `/status`: Get an instant, on-demand summary of your portfolio.
  - `/performance`: Receive a detailed performance report with key metrics (P&L, Win Rate, Profit Factor, etc.).
  - `/trades <all|wins|losses|SYMBOL>`: Query the trade history.
- **Robust Operation:**
  - **State Persistence:** Remembers its portfolio and watchlist across restarts using `portfolio.json`.
  - **Broker Reconciliation:** Automatically syncs its internal state with your actual Kite holdings at startup.
- **High-Fidelity Backtesting:** Includes a backtesting engine to simulate strategies with realistic costs and risk analysis (Maximum Drawdown).

## Setup and Installation

### 1. Prerequisites
- Python 3.10+
- A Zerodha Kite developer account
- A Telegram account and a bot token
- An ngrok account and authtoken

### 2. Clone the Repository
```bash
git clone <repository_url>
cd ai_trading_agent
```

### 3. Create and Activate a Virtual Environment
```bash
# For Windows
python -m venv .venv
.\.venv\Scripts\activate

# For macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
Install all required packages using the following command:
```bash
pip install python-dotenv pandas kiteconnect google-generativeai beautifulsoup4 feedparser gnews pandas_ta "python-telegram-bot[webhooks]" pyngrok aiohttp
```

## Configuration

Create a file named `.env` in the root directory of the project (`ai_trading_agent/`) and add the following, replacing the placeholder values with your actual credentials.

```env
# Zerodha Kite API Credentials
KITE_API_KEY="your_kite_api_key"
ACCESS_TOKEN="your_kite_access_token" # This needs to be generated daily using authenticate.py

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="your_telegram_chat_id" # Your personal Telegram user ID

# ngrok Credentials
NGROK_AUTH_TOKEN="your_ngrok_authtoken"
```

**To get your Kite `ACCESS_TOKEN`:** You need to run the `authenticate.py` script once every morning before starting the agent.

**To get your `TELEGRAM_CHAT_ID`:** Message a bot like `@userinfobot` on Telegram.

## Running the Agent

### Live Trading Mode
To run the agent in live trading mode, simply execute the `main.py` script from within the `src` directory:
```bash
cd src
python main.py
```
The agent will start, establish a tunnel with ngrok, and send you a startup message on Telegram.

### Backtesting Mode
To run a backtest on the predefined stocks and date range in the configuration, use the `--backtest` flag:
```bash
cd src
python main.py --backtest
```
The backtest report will be printed to the console upon completion.

## Telegram Commands

- `/start`: Starts or resumes the agent's trading cycles.
- `/stop`: Pauses the agent. It will complete any current analysis but will not start a new cycle.
- `/status`: Provides an instant summary of your portfolio's value and current holdings.
- `/performance`: Shows a detailed report of your strategy's historical performance.
- `/trades <query>`: Shows a log of past trades.
  - `/trades all`: Last 10 trades.
  - `/trades wins`: Last 10 winning trades.
  - `/trades losses`: Last 10 losing trades.
  - `/trades RELIANCE`: All trades for a specific symbol.

## Disclaimer

This trading agent is provided for educational purposes only. Trading and investing in financial markets involve substantial risk. You are solely responsible for any financial decisions you make. The author and contributors are not liable for any losses you may incur. Always do your own research and consider running the agent in a paper trading environment before deploying it with real capital.
