import pandas as pd
import numpy as np
from logger import log
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from technical_analysis import calculate_indicators
import config as cfg

# --- Advanced Cost Modeling Functions ---

def calculate_advanced_commission(trade_value: float) -> float:
    """Calculates a more realistic, tiered commission based on config."""
    brokerage = max(cfg.COMMISSION_MIN_PER_TRADE, trade_value * cfg.COMMISSION_BROKERAGE_PERCENTAGE)
    stt = trade_value * cfg.COMMISSION_STT_CTT
    exchange_fee = trade_value * cfg.COMMISSION_EXCHANGE_FEE
    
    taxable_value = brokerage + exchange_fee
    gst = taxable_value * cfg.COMMISSION_GST
    sebi_fee = trade_value * cfg.COMMISSION_SEBI_FEE
    
    total_cost = brokerage + stt + exchange_fee + gst + sebi_fee
    return total_cost

def calculate_variable_slippage(day_candle: dict, trade_value: float) -> float:
    """Calculates slippage based on the day's price range (volatility)."""
    price_range = day_candle['high'] - day_candle['low']
    slippage_per_share = price_range * cfg.SLIPPAGE_VOLATILITY_FACTOR
    return slippage_per_share * (trade_value / day_candle['close'])


def run_dynamic_backtest(kite, historical_data_map, historical_constituents=None):
    """
    Runs a high-fidelity backtest that dynamically screens and ranks stocks each day.
    Can run in AI-driven mode or a rules-only benchmark mode.
    """
    mode = "AI Analysis" if cfg.USE_AI_ANALYSIS else "Rules-Only Benchmark"
    log.info(f"--- Starting Backtest in {mode} Mode ---")
    
    portfolio_sim = {'cash': cfg.VIRTUAL_CAPITAL, 'holdings': {}, 'trade_log': []}
    equity_curve = []
    sim_days = pd.date_range(start=cfg.BACKTEST_START_DATE, end=cfg.BACKTEST_END_DATE, freq='B')

    for sim_date in sim_days:
        log.debug(f"--- Simulating Day: {sim_date.strftime('%Y-%m-%d')} ---")
        
        daily_universe = list(historical_data_map.keys())
        daily_scores = {}
        # This loop is simplified for the example. A real implementation would use the AI for scoring.
        for symbol in daily_universe:
            if symbol not in historical_data_map: continue
            history = historical_data_map[symbol]
            day_history = [d for d in history if d['date'].date() < sim_date.date()]
            if len(day_history) < 50: continue
            
            indicators = calculate_indicators(day_history)
            # Simple rules-based scoring
            score = 0
            if indicators.get('rsi_14', 50) < 55 and day_history[-1]['close'] > indicators.get('sma_50', 0):
                score = 3 # High score if basic criteria met
            daily_scores[symbol] = score

        sorted_stocks = sorted(daily_scores.items(), key=lambda item: item[1], reverse=True)
        scan_list = [s[0] for s in sorted_stocks if s[1] > 0][:cfg.TOP_N_STOCKS]

        # Sell logic (remains the same for both modes)
        for symbol, position in list(portfolio_sim['holdings'].items()):
            # ... (sell logic as before)

        # Buy logic (this is where the benchmark mode differs)
        for symbol in scan_list:
            if symbol not in portfolio_sim['holdings']:
                
                # --- BENCHMARK LOGIC ---
                # If AI is disabled, buy based on the rules score alone.
                # If AI is enabled, this would be where you call the Gemini model.
                # For this example, we'll simulate that the AI agrees if the score is high.
                decision_to_buy = False
                if not cfg.USE_AI_ANALYSIS and daily_scores.get(symbol, 0) >= 3:
                    decision_to_buy = True
                elif cfg.USE_AI_ANALYSIS and daily_scores.get(symbol, 0) >= 3:
                    # In a real run, this would be: ai_decision = analysis.get_market_analysis(...)
                    # We simulate the AI agreeing to demonstrate the logic path.
                    log.info(f"Simulating AI analysis for {symbol}... AI approves.")
                    decision_to_buy = True

                if decision_to_buy:
                    day_data_list = [d for d in historical_data_map[symbol] if d['date'].date() == sim_date.date()]
                    if not day_data_list: continue
                    
                    current_candle = day_data_list[0]
                    entry_price = current_candle['close']
                    quantity = 10
                    trade_value = entry_price * quantity
                    costs = calculate_advanced_commission(trade_value) + calculate_variable_slippage(current_candle, trade_value) if cfg.USE_ADVANCED_COST_MODEL else trade_value * (cfg.SIMPLE_COMMISSION_PER_TRADE + cfg.SIMPLE_SLIPPAGE_PERCENTAGE)
                    
                    if portfolio_sim['cash'] >= trade_value + costs:
                        portfolio_sim['holdings'][symbol] = {'entry_price': entry_price, 'stop_loss': entry_price * 0.9, 'quantity': quantity}
                        portfolio_sim['cash'] -= (trade_value + costs)
                        portfolio_sim['trade_log'].append({'date': sim_date, 'pnl': -costs, 'symbol': symbol, 'action': 'BUY'})

        current_holdings_value = sum(
            (day_data[0]['close'] if (day_data := [d for d in historical_data_map[s] if d['date'].date() == sim_date.date()]) else p['entry_price']) * p['quantity']
            for s, p in portfolio_sim['holdings'].items()
        )
        equity_curve.append({'date': sim_date, 'value': portfolio_sim['cash'] + current_holdings_value})

    return equity_curve, portfolio_sim['trade_log']



def calculate_backtest_performance(equity_curve, trade_log):
    if not equity_curve or not trade_log:
        return {"message": "Backtest did not generate any results."}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    equity_df = pd.DataFrame(equity_curve).set_index('pd.to_datetime(equity_curve["date"]))')
    equity_df['returns'] = equity_df['value'].pct_change().fillna(0)
    
    # --- Risk Analysis ---
    peak = equity_df['value'].cummax()
    drawdown = (equity_df['value'] - peak) / peak
    max_drawdown = drawdown.min()
    
    # --- Sharpe & Sortino Ratios ---
    daily_risk_free_rate = (1 + cfg.RISK_FREE_RATE_ANNUAL)**(1/252) - 1
    excess_returns = equity_df['returns'] - daily_risk_free_rate
    
    sharpe_ratio = excess_returns.mean() / excess_returns.std() * np.sqrt(252) if excess_returns.std() != 0 else 0
    
    downside_returns = excess_returns[excess_returns < 0]
    sortino_ratio = excess_returns.mean() / downside_returns.std() * np.sqrt(252) if downside_returns.std() != 0 else 0

    # --- Trade Analysis ---
    trade_df = pd.DataFrame(trade_log)
    sell_trades = trade_df[trade_df['action'] != 'BUY']
    total_trades = len(sell_trades)
    
    if total_trades == 0:
        return {"message": "No closing trades were made during the backtest."}

    winners = sell_trades[sell_trades['pnl'] > 0]
    losers = sell_trades[sell_trades['pnl'] <= 0]
    
    win_rate = len(winners) / total_trades if total_trades > 0 else 0
    avg_win = winners['pnl'].mean() if not winners.empty else 0
    avg_loss = losers['pnl'].mean() if not losers.empty else 0
    
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    equity_df.to_csv(f"backtest_equity_curve_{timestamp}.csv")
    log.info(f"Backtest equity curve saved to backtest_equity_curve_{timestamp}.csv")

    return {
        "total_pnl": sell_trades['pnl'].sum(),
        "total_trades": total_trades,
        "max_drawdown_pct": max_drawdown * 100,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "win_rate_pct": win_rate * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "equity_df": equity_df,
        "drawdown_series": drawdown,
        "timestamp": timestamp
    }

def plot_performance(metrics: dict):
    if 'equity_df' not in metrics:
        log.warning("Equity data not found for plotting.")
        return

    timestamp = metrics.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
    png_filename = f"backtest_performance_{timestamp}.png"

    sns.set_style("whitegrid")
    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
    
    ax1.plot(metrics['equity_df'].index, metrics['equity_df']['value'], label='Portfolio Value', color='blue')
    ax1.set_title('Portfolio Equity Curve', fontsize=16)
    ax1.set_ylabel('Portfolio Value (₹)')
    ax1.legend()
    
    ax2.fill_between(metrics['drawdown_series'].index, metrics['drawdown_series'] * 100, 0, color='red', alpha=0.3)
    ax2.set_title('Drawdown (%)', fontsize=12)
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_xlabel('Date')
    
    plt.tight_layout()
    plt.savefig(png_filename)
    log.info(f"Performance plot saved to {png_filename}")
    plt.close()


def format_backtest_report(metrics: dict) -> str:
    if "message" in metrics:
        return metrics["message"]

    timestamp = metrics.get("timestamp", "N/A")
    report = (
        f"--- 📈 High-Fidelity Backtest Report ---

"
        f"**Model Used:** {'Advanced (Tiered Costs)' if cfg.USE_ADVANCED_COST_MODEL else 'Simple (Fixed %)'}

"
        f"**Overall Performance:**
"
        f"  - Net P&L (after costs): ₹{metrics['total_pnl']:,.2f}
"
        f"  - Total Trades: {metrics['total_trades']}
"
        f"  - Maximum Drawdown: {metrics['max_drawdown_pct']:.2f}%

"
        f"**Risk-Adjusted Returns:**
"
        f"  - Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
"
        f"  - Sortino Ratio: {metrics['sortino_ratio']:.2f}

"
        f"**Trade Statistics:**
"
        f"  - Win Rate: {metrics['win_rate_pct']:.2f}%
"
        f"  - Average Win: ₹{metrics['avg_win']:,.2f}
"
        f"  - Average Loss: ₹{metrics['avg_loss']:,.2f}
"
        f"  - Expectancy per Trade: ₹{metrics['expectancy']:,.2f}

"
        f"Visual report saved to `backtest_performance_{timestamp}.png`.
"
        f"Equity curve data saved to `backtest_equity_curve_{timestamp}.csv`."
    )
    return report
