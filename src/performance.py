import pandas as pd
from logger import log

def calculate_performance_metrics(trade_log_path: str) -> dict:
    """
    Reads the trade log and calculates key performance metrics.
    """
    try:
        df = pd.read_csv(trade_log_path)
    except FileNotFoundError:
        log.warning("Trade log file not found. Cannot calculate performance.")
        return None
    except pd.errors.EmptyDataError:
        log.info("Trade log is empty. No performance to calculate.")
        return None

    df['pnl'] = pd.to_numeric(df['pnl'], errors='coerce')
    df = df.dropna(subset=['pnl'])

    closing_trades = df[df['action'].str.contains('SELL', case=False)]
    
    if closing_trades.empty:
        return {"total_trades": 0}

    total_trades = len(closing_trades)
    winning_trades = closing_trades[closing_trades['pnl'] > 0]
    losing_trades = closing_trades[closing_trades['pnl'] <= 0]

    total_pnl = closing_trades['pnl'].sum()
    win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
    
    gross_profit = winning_trades['pnl'].sum()
    gross_loss = abs(losing_trades['pnl'].sum())
    
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
    avg_loss = abs(losing_trades['pnl'].mean()) if len(losing_trades) > 0 else 0
    
    loss_rate = 100 - win_rate
    expectancy = ((win_rate / 100) * avg_win) - ((loss_rate / 100) * avg_loss)

    exit_reasons = closing_trades['action'].value_counts().to_dict()

    return {
        "total_pnl": total_pnl,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "exit_reasons": exit_reasons
    }

def format_performance_report(metrics: dict) -> str:
    """
    Formats the performance metrics into a human-readable string for Telegram.
    """
    if not metrics or metrics.get("total_trades", 0) == 0:
        return "No trades have been completed yet. Performance report is not available."

    exit_reasons_str = "\n".join([f"  - {reason}: {count}" for reason, count in metrics.get('exit_reasons', {}).items()])

    report = (
        f"--- 📊 Performance Report ---\n\n"
        f"**Strategy Health:**\n"
        f"Net P&L: ₹{metrics['total_pnl']:,.2f}\n"
        f"Profit Factor: {metrics['profit_factor']:.2f}\n"
        f"Expectancy/Trade: ₹{metrics['expectancy']:,.2f}\n\n"
        f"**Trade Stats:**\n"
        f"Total Trades: {metrics['total_trades']}\n"
        f"Win Rate: {metrics['win_rate']:.2f}%\n"
        f"Avg. Win: ₹{metrics['avg_win']:,.2f}\n"
        f"Avg. Loss: ₹{metrics['avg_loss']:,.2f}\n\n"
        f"**Exit Analysis:**\n"
        f"{exit_reasons_str}"
    )
    return report

def query_trade_log(trade_log_path: str, query: str) -> pd.DataFrame:
    """
    Queries the trade log based on a given filter.
    """
    try:
        df = pd.read_csv(trade_log_path)
        if df.empty:
            return pd.DataFrame()

        if query == 'all':
            return df.tail(10)
        elif query == 'wins':
            return df[df['pnl'] > 0].tail(10)
        elif query == 'losses':
            return df[df['pnl'] <= 0].tail(10)
        else: # Query is a symbol
            return df[df['symbol'].str.upper() == query.upper()]

    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()

def format_trade_log_report(df: pd.DataFrame, query: str) -> str:
    """
    Formats a DataFrame of trades into a human-readable string.
    """
    if df.empty:
        return f"No trades found for query: '{query}'"

    report_lines = [f"--- 📜 Trade Log: {query.capitalize()} ---"]
    for _, row in df.iterrows():
        pnl_str = f"₹{row['pnl']:,.2f}"
        line = f"[{row['timestamp'].split(' ')[0]}] {row['action']} {row['symbol']} | P&L: {pnl_str}"
        report_lines.append(line)
    
    return "\n".join(report_lines)

if __name__ == '__main__':
    log.info("This module is intended to be imported, not run directly.")
