# AI Trading Agent

**This is an experimental project. Trading in financial markets involves substantial risk. You are solely responsible for any financial decisions and potential losses. It is highly recommended to run this agent in a paper trading environment before deploying it with real capital.**

This is a sophisticated, AI-powered swing trading agent designed to operate on the Indian stock market (NSE). It uses Google's Gemini for its core trading decisions and is integrated with the Zerodha Kite API for live data and trade execution. The agent is fully controllable via a Telegram bot and is built with a focus on reliability, transparency, and advanced risk management.

## Core Trading Strategy

The agent employs a multi-layered swing trading strategy designed to identify and act on high-probability momentum-based opportunities.

1.  **Dynamic Universe Creation**: At the start of each cycle, the agent scans a broad market index (e.g., NIFTY 100) and filters for highly liquid stocks based on price and average volume. This ensures it always works with a relevant and tradable set of stocks.
2.  **Opportunity Identification**: It screens the dynamic universe for stocks that are in a long-term uptrend (price > 50-day SMA) but are currently experiencing a short-term pullback (RSI < 55).
3.  **AI-Powered Analysis**: Each high-potential opportunity is sent to Google's Gemini model for a final decision. The AI is given strict rules and must return a structured JSON response containing a `decision`, a `confidence` score (1-10), and `reasoning`. The agent will only act on high-confidence signals.
4.  **Intelligent Exit Conditions**:
    - **Volatility-Adjusted Trailing Stop-Loss**: This is the primary risk management tool. The stop-loss is not a fixed percentage but is dynamically calculated using the **Average True Range (ATR)**. This adapts the stop-loss to each stock's unique volatility, preventing premature exits in choppy stocks while protecting capital in stable ones.
    - **Confirmation-Based Take-Profit**: To avoid selling too early in a strong uptrend, the agent requires two conditions to be met before taking profit: the stock must be overbought (RSI > 70) **and** the price must show weakness by closing below its 5-day EMA.
    - **Minimum Holding Period**: To prevent over-trading on market noise, the agent will not close a position for profit until it has been held for a configurable number of days (default is 3).

## Key Features

- **Advanced Risk Management:**
  - **ATR-Based Trailing Stop-Loss**: Dynamically adjusts the stop-loss based on market volatility.
  - **Risk-Based Position Sizing**: Calculates position size based on a fixed percentage of portfolio risk, not just available cash.
  - **Capital Allocation Limits**: Prevents over-concentration by limiting the percentage of capital that can be allocated to a single trade.
- **High Reliability & Resilience:**
  - **Circuit Breaker:** Automatically halts API calls to the broker if the service is down, preventing errors and allowing for graceful recovery.
  - **Graceful Shutdown & Startup:** Shuts down cleanly on `Ctrl+C` and is resilient to corrupted state files, recreating them if necessary.
  - **Automated Retry Mechanism:** Automatically retries failed API calls, making the agent robust against temporary network issues.
- **Full Transparency & Control:**
  - **Detailed Cycle Reports**: At the end of each cycle, the agent sends a detailed summary to Telegram, reporting not just the trades it made, but also the positions it held and the opportunities it skipped (and why).
  - **Comprehensive Logging**: Every action, decision, and error is logged to `tradelog.csv` and `logs/trading_agent.log` for complete auditability.
  - **Full Telegram Control**: Remotely start, stop, and monitor the agent from anywhere.

## Setup and Installation

### 1. Prerequisites
- Python 3.10+
- A Zerodha Kite developer account
- A Google Cloud account with the "Generative Language API" enabled
- A Telegram account and a bot token

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
```

The agent's strategy and risk parameters can be fine-tuned in `src/config.py`.

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
The agent will start, validate all API keys, reconcile its portfolio with your broker, and send you a startup message on Telegram.

## Disclaimer

This trading agent is provided for educational purposes only. Trading and investing in financial markets involve substantial risk. You are solely responsible for any financial decisions you make. The author and contributors are not liable for any losses you may incur. Always do your own research and consider running the agent in a paper trading environment before deploying it with real capital.