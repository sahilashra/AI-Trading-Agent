# AI Trading Agent

This is a sophisticated, AI-powered swing trading agent designed to operate on the Indian stock market (NSE). It uses Google's Gemini for its core trading decisions and is integrated with the Zerodha Kite API for live data and trade execution. The agent is fully controllable via a Telegram bot and is built with a focus on reliability and risk management.

## Features

- **Intelligent Trading Strategy:**
  - **Momentum Pullback Screener:** Identifies high-potential opportunities by finding stocks in a strong, long-term uptrend that have recently experienced a short-term price dip.
  - **AI-Powered Analysis:** Leverages Google's Gemini model to analyze technical indicators and news sentiment to make focused buy/sell/hold decisions based on the pullback strategy.
  - **Market Trend Filter:** Protects capital by disabling new purchases during a market downtrend (based on the Nifty 50's 200-day SMA).
- **Advanced Risk Management:**
  - **Pre-Trade Safety Checks:** Before placing any order, the agent verifies that there is sufficient cash and that the trade will not exceed a user-defined percentage of the total portfolio.
  - **Volatility-Adjusted Position Sizing:** Calculates trade size based on a stock's volatility (ATR) to ensure consistent risk on every trade.
  - **Dynamic Profit-Taking:** Monitors the RSI of holdings to sell positions when they become overbought, aiming to secure profits near the peak.
  - **Trailing Stop-Loss:** Protects profits by automatically raising the stop-loss as a stock's price increases.
- **High Reliability & Resilience:**
  - **Circuit Breaker:** Automatically halts API calls to the broker if the service is down, preventing the agent from spamming a failing service and allowing it to recover gracefully.
  - **Graceful Shutdown:** Shuts down cleanly on `Ctrl+C` or system signals, ensuring all operations are completed and no data is corrupted.
  - **Automated Retry Mechanism:** Automatically retries failed API calls, making the agent resilient to temporary network glitches.
  - **Order Execution Monitoring (Live Mode):** Tracks the status of every order and only updates the portfolio once the broker confirms it is fully 'COMPLETE'.
  - **Daily Data Cache:** Caches historical data to improve performance and reduce API calls, with an intelligent invalidation system that clears the cache at the start of each new trading day.
- **Full Telegram Control:**
  - `/start` & `/stop`: Remotely start and stop the agent's trading activity.
  - `/status`: Get an instant, on-demand summary of your portfolio.
  - `/health`: Receive a comprehensive, real-time diagnostic report of the agent's status, including API connectivity, memory usage, and circuit breaker state.
  - `/performance`: Receive a detailed performance report with key metrics.
  - `/trades <query>`: Query the trade history.
- **State Persistence & Reconciliation:**
  - Remembers its portfolio, watchlist, and pending orders across restarts.
  - Automatically syncs its internal state with your actual Kite holdings at startup.

## Setup and Installation

### 1. Prerequisites
- Python 3.10+
- A Zerodha Kite developer account
- A Google Cloud account with the "Generative Language API" enabled
- A Telegram account and a bot token
- An ngrok account and authtoken (for local testing)

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
Install all required packages using the `requirements.txt` file:
```bash
pip install -r requirements.txt
```

## Configuration

Create a file named `.env` in the root directory of the project (`ai_trading_agent/`) and add the following, replacing the placeholder values with your actual credentials.

```env
# Zerodha Kite API Credentials
KITE_API_KEY="your_kite_api_key"
ACCESS_TOKEN="your_kite_access_token" # This needs to be generated daily using authenticate.py

# Google Gemini API Key
GEMINI_API_KEY="your_gemini_api_key_from_google_cloud"

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="your_telegram_chat_id" # Your personal Telegram user ID

# ngrok Credentials (Optional, for local webhook testing)
NGROK_AUTH_TOKEN="your_ngrok_authtoken"
```

**To get your Kite `ACCESS_TOKEN`:** You need to run the `authenticate.py` script once every morning before starting the agent.

**To get your `GEMINI_API_KEY`:** It is highly recommended to generate this from the [Google Cloud Platform (GCP) Console](https://console.cloud.google.com/) to ensure it does not expire.

**To get your `TELEGRAM_CHAT_ID`:** Message a bot like `@userinfobot` on Telegram.

## Running the Agent

### 1. Authenticate with Broker (Daily)
Run the authentication script and follow the prompts. This will save your `access_token` to the `.env` file.
```bash
cd src
python authenticate.py
```

### 2. Start the Main Agent
Once authenticated, run the main script:
```bash
python main.py
```
The agent will start, validate all API keys, establish a tunnel with ngrok, and send you a startup message on Telegram.

### Backtesting Mode
To run a backtest on the predefined stocks and date range in the configuration, use the `--backtest` flag:
```bash
python main.py --backtest
```
The backtest report will be printed to the console upon completion.

## Telegram Commands

- `/start`: Starts or resumes the agent's trading cycles.
- `/stop`: Pauses the agent. It will complete any current analysis but will not start a new cycle.
- `/status`: Provides an instant summary of your portfolio's value and holdings.
- `/health`: Runs a full diagnostic health check on the agent and reports the status of all components.
- `/performance`: Shows a detailed report of your strategy's historical performance.
- `/trades <query>`: Shows a log of past trades.
  - `/trades all`: Last 10 trades.
  - `/trades wins`: Last 10 winning trades.
  - `/trades losses`: Last 10 losing trades.
  - `/trades RELIANCE`: All trades for a specific symbol.

## Disclaimer

This trading agent is provided for educational purposes only. Trading and investing in financial markets involve substantial risk. You are solely responsible for any financial decisions you make. The author and contributors are not liable for any losses you may incur. Always do your own research and consider running the agent in a paper trading environment before deploying it with real capital.
