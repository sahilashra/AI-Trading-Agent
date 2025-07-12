import pandas as pd
from logger import log
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
from technical_analysis import calculate_indicators

def run_dynamic_backtest(kite, config, portfolio_sim, historical_data_map):
    """
    Runs a high-fidelity backtest that dynamically screens and ranks stocks each day.
    """
    log.info("--- Starting Dynamic High-Fidelity Backtest ---")
    
    equity_curve = []
    start_date = config['BACKTEST_START_DATE']
    end_date = config['BACKTEST_END_DATE']
    sim_days = pd.date_range(start=start_date, end=end_date, freq='B')

    for sim_date in sim_days:
        log.info(f"--- Simulating Day: {sim_date.strftime('%Y-%m-%d')} ---")
        
        # --- 1. Daily Screening and Ranking ---
        daily_scores = {}
        for symbol, history in historical_data_map.items():
            day_history = [d for d in history if d['date'].date() < sim_date.date()]
            if len(day_history) < 50:
                continue

            indicators = calculate_indicators(day_history)
            score = 0
            if indicators.get('rsi_14', 50) < 60:
                score += 1
            if indicators.get('macd_line', 0) > indicators.get('macd_signal', 0):
                score += 1
            if day_history[-1]['close'] > indicators.get('sma_50', 0):
                score += 1
            daily_scores[symbol] = score

        sorted_stocks = sorted(daily_scores.items(), key=lambda item: item[1], reverse=True)
        scan_list = [s[0] for s in sorted_stocks[:config['TOP_N_STOCKS']]]

        # --- 2. Manage Existing Holdings ---
        for symbol, position in list(portfolio_sim['holdings'].items()):
            if symbol not in historical_data_map:
                continue
            
            day_data_list = [d for d in historical_data_map[symbol] if d['date'].date() == sim_date.date()]
            if not day_data_list:
                continue
            current_candle = day_data_list[0]
            
            if current_candle['low'] <= position['stop_loss']:
                exit_price = position['stop_loss']
                pnl = (exit_price - position['entry_price']) * position['quantity']
                pnl -= (config['COMMISSION_PER_TRADE'] * exit_price * position['quantity'])
                pnl -= (config['SLIPPAGE_PERCENTAGE'] * exit_price * position['quantity'])
                
                portfolio_sim['cash'] += exit_price * position['quantity']
                portfolio_sim['trade_log'].append({'date': sim_date, 'pnl': pnl, 'symbol': symbol, 'action': 'SELL_SL'})
                del portfolio_sim['holdings'][symbol]

        # --- 3. Analyze and Act on New Opportunities ---
        for symbol in scan_list:
            if symbol not in portfolio_sim['holdings']:
                # Simulate a buy decision if the score is high
                if daily_scores.get(symbol, 0) >= 3: # Buy only if score is 3
                    day_data_list = [d for d in historical_data_map[symbol] if d['date'].date() == sim_date.date()]
                    if not day_data_list:
                        continue
                    
                    entry_price = day_data_list[0]['close']
                    quantity = 10 # Simplified quantity for backtest
                    trade_value = entry_price * quantity

                    if portfolio_sim['cash'] >= trade_value:
                        portfolio_sim['holdings'][symbol] = {
                            'entry_price': entry_price,
                            'stop_loss': entry_price * 0.9,
                            'quantity': quantity
                        }
                        portfolio_sim['cash'] -= trade_value
                        portfolio_sim['trade_log'].append({'date': sim_date, 'pnl': 0, 'symbol': symbol, 'action': 'BUY'})


        # --- 4. End of Day Accounting ---
        current_holdings_value = 0
        for symbol, position in portfolio_sim['holdings'].items():
            day_data_list = [d for d in historical_data_map[symbol] if d['date'].date() == sim_date.date()]
            if day_data_list:
                current_holdings_value += day_data_list[0]['close'] * position['quantity']
            else:
                current_holdings_value += position['entry_price'] * position['quantity']

        total_value = portfolio_sim['cash'] + current_holdings_value
        equity_curve.append({'date': sim_date, 'value': total_value})

    return equity_curve, portfolio_sim['trade_log']


def calculate_backtest_performance(equity_curve, trade_log):
    if not equity_curve:
        return {"message": "Backtest did not generate any results."}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"backtest_equity_curve_{timestamp}.csv"

    equity_df = pd.DataFrame(equity_curve)
    equity_df['date'] = pd.to_datetime(equity_df['date'])
    equity_df = equity_df.set_index('date')

    peak = equity_df['value'].cummax()
    drawdown = (equity_df['value'] - peak) / peak
    max_drawdown = drawdown.min()
    
    trade_df = pd.DataFrame(trade_log)
    total_pnl = trade_df['pnl'].sum() if not trade_df.empty else 0
    total_trades = len(trade_df[trade_df['action'] != 'BUY'])
    
    equity_df.to_csv(csv_filename)
    log.info(f"Backtest equity curve saved to {csv_filename}")

    return {
        "total_pnl": total_pnl,
        "total_trades": total_trades,
        "max_drawdown_pct": max_drawdown * 100,
        "equity_df": equity_df,
        "drawdown_series": drawdown,
        "timestamp": timestamp
    }

def plot_performance(metrics: dict):
    if 'equity_df' not in metrics:
        log.warning("Equity data not found in metrics. Cannot plot performance.")
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
        f"--- 📈 High-Fidelity Backtest Report ---\n\n"
        f"**Performance:**\n"
        f"Net P&L (after costs): ₹{metrics['total_pnl']:,.2f}\n"
        f"Total Trades: {metrics['total_trades']}\n\n"
        f"**Risk Analysis:**\n"
        f"Maximum Drawdown: {metrics['max_drawdown_pct']:.2f}%\n\n"
        f"Visual report saved to `backtest_performance_{timestamp}.png`.\n"
        f"Equity curve data saved to `backtest_equity_curve_{timestamp}.csv`."
    )
    return report
