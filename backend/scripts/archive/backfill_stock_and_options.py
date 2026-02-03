# Backfill Stock + Options Data for Volume Rocket Signals

"""
This script:
1. Scans the historical stock candles (Nov 2025) for Volume‑Rocket entry signals.
2. For each signal it looks up the *closest‑to‑ATM* option (CE for LONG, PE for SHORT) at the entry time.
3. It then fetches the same option's premium at the exit time (or the nearest later candle).
4. Calculates both stock P&L and option P&L and writes a comprehensive CSV.

Assumptions:
- Stock candles are stored in the SQLite table `candle_data`.
- Option data is stored in per‑stock CSV files located in a sibling `data` folder, named `<TICKER>_options.csv` (e.g., `HEROMOTOCO_options.csv`).
- If an option CSV is missing, the script still records the stock side and leaves option columns as NaN.
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd
from loguru import logger
import warnings

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH = "keepgaining.db"
DATA_DIR = Path(__file__).parents[2] / "data"  # <project_root>/data

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add the technical indicators used by the Volume‑Rocket strategy."""
    df = df.copy()
    # EMA 9 (trailing stop)
    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
    # EMA 200 (trend)
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
    # Bollinger Bands (20, 2)
    sma20 = df["close"].rolling(window=20).mean()
    std20 = df["close"].rolling(window=20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    # RSI 14
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    # Volume MA 20
    df["vol_ma"] = df["volume"].rolling(window=20).mean()
    return df.dropna()


def load_option_csv(symbol: str) -> pd.DataFrame:
    """Load option data for *symbol* from a CSV file.
    The CSV is expected to have columns: timestamp, strike, type (CE/PE), premium.
    If the file does not exist an empty DataFrame with those columns is returned.
    """
    ticker = symbol.replace("NSE:", "").replace("-EQ", "")
    csv_path = DATA_DIR / f"{ticker}_options.csv"
    if not csv_path.is_file():
        return pd.DataFrame(columns=["timestamp", "strike", "type", "premium"])
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def nearest_option(df_opt: pd.DataFrame, ts: pd.Timestamp, opt_type: str, atm_price: float) -> pd.Series:
    """Return the option row whose strike is closest to *atm_price* within ±5 min.
    If no candidate exists an empty Series is returned.
    """
    window = pd.Timedelta(minutes=5)
    mask = (df_opt["type"] == opt_type) & df_opt["timestamp"].between(ts - window, ts + window)
    candidates = df_opt[mask]
    if candidates.empty:
        return pd.Series()
    candidates = candidates.copy()
    candidates["strike_dist"] = (candidates["strike"] - atm_price).abs()
    best = candidates.sort_values(["strike_dist", "timestamp"]).iloc[0]
    return best

# ---------------------------------------------------------------------------
# Main back‑fill routine
# ---------------------------------------------------------------------------

def backfill_stock_and_options():
    logger.info("=== Backfill Stock + Options for Volume Rocket (Nov 2025) ===")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM candle_data")
    symbols = [row[0] for row in cur.fetchall()]
    results = []

    for symbol in symbols:
        stock_name = symbol.replace("NSE:", "").replace("-EQ", "")
        # -------------------------------------------------------------------
        # Load stock candles for the November 2025 window
        # -------------------------------------------------------------------
        sql_stock = """
            SELECT timestamp, open, high, low, close, volume
            FROM candle_data
            WHERE symbol = ?
            AND timestamp BETWEEN '2025-11-01' AND '2025-11-25'
            ORDER BY timestamp
        """
        df_stock = pd.read_sql_query(sql_stock, conn, params=(symbol,))
        if len(df_stock) < 200:
            continue
        df_stock["timestamp"] = pd.to_datetime(df_stock["timestamp"])
        df_stock = calculate_indicators(df_stock)

        # Load option data from CSV (fallback to empty DataFrame)
        df_opt = load_option_csv(symbol)

        active_trade = None
        for _, row in df_stock.iterrows():
            # ---------------------------------------------------------------
            # Entry – only consider candles at or after 09:16
            # ---------------------------------------------------------------
            if active_trade is None:
                if row["timestamp"].hour == 9 and row["timestamp"].minute >= 16:
                    # LONG (CE) condition
                    if (
                        row["volume"] > row["vol_ma"] * 3
                        and row["close"] > row["bb_upper"]
                        and row["rsi"] > 70
                        and row["close"] > row["ema_200"]
                    ):
                        active_trade = {
                            "type": "CE",
                            "entry_time": row["timestamp"],
                            "entry_price": row["close"],
                            "stock": stock_name,
                        }
                    # SHORT (PE) condition
                    elif (
                        row["volume"] > row["vol_ma"] * 3
                        and row["close"] < row["bb_lower"]
                        and row["rsi"] < 30
                        and row["close"] < row["ema_200"]
                    ):
                        active_trade = {
                            "type": "PE",
                            "entry_time": row["timestamp"],
                            "entry_price": row["close"],
                            "stock": stock_name,
                        }
            else:
                # -----------------------------------------------------------
                # Exit – EMA9 trailing stop or forced end‑of‑day (15:25)
                # -----------------------------------------------------------
                is_eod = row["timestamp"].hour == 15 and row["timestamp"].minute >= 25
                exit_signal = False
                if active_trade["type"] == "CE" and row["close"] < row["ema_9"]:
                    exit_signal = True
                if active_trade["type"] == "PE" and row["close"] > row["ema_9"]:
                    exit_signal = True
                if is_eod:
                    exit_signal = True
                if exit_signal:
                    exit_time = row["timestamp"]
                    exit_price = row["close"]
                    # Stock P&L
                    if active_trade["type"] == "CE":
                        stock_pnl = ((exit_price - active_trade["entry_price"]) / active_trade["entry_price"]) * 100
                    else:  # PE
                        stock_pnl = ((active_trade["entry_price"] - exit_price) / active_trade["entry_price"]) * 100
                    # Option lookup – nearest‑to‑ATM strike at entry & exit
                    atm_price = active_trade["entry_price"]
                    opt_entry = nearest_option(df_opt, active_trade["entry_time"], active_trade["type"], atm_price)
                    opt_exit = nearest_option(df_opt, exit_time, active_trade["type"], atm_price)
                    entry_prem = opt_entry.get("premium") if not opt_entry.empty else float("nan")
                    exit_prem = opt_exit.get("premium") if not opt_exit.empty else float("nan")
                    # Option P&L (percentage change of premium)
                    if pd.notna(entry_prem) and pd.notna(exit_prem) and entry_prem != 0:
                        opt_pnl = ((exit_prem - entry_prem) / entry_prem) * 100
                        if active_trade["type"] == "PE":
                            opt_pnl = -opt_pnl
                    else:
                        opt_pnl = float("nan")
                    results.append(
                        {
                            "Stock": stock_name,
                            "OptionType": active_trade["type"],
                            "EntryTime": active_trade["entry_time"],
                            "ExitTime": exit_time,
                            "StockEntry": active_trade["entry_price"],
                            "StockExit": exit_price,
                            "StockGain%": stock_pnl,
                            "OptionStrike": opt_entry.get("strike") if not opt_entry.empty else None,
                            "OptionEntryPremium": entry_prem,
                            "OptionExitPremium": exit_prem,
                            "OptionGain%": opt_pnl,
                        }
                    )
                    active_trade = None
    conn.close()

    if not results:
        logger.warning("No Volume‑Rocket signals were backfilled in the period.")
        return

    df_res = pd.DataFrame(results)
    total = len(df_res)
    win_rate = (df_res["OptionGain%"] > 0).mean() * 100
    avg_opt_gain = df_res["OptionGain%"].mean()

    logger.info("\n" + "=" * 80)
    logger.info("BACKFILL RESULT SUMMARY (Nov 2025)")
    logger.info("=" * 80)
    logger.info(f"Total backfilled trades: {total}")
    logger.info(f"Option Win Rate: {win_rate:.2f}%")
    logger.info(f"Avg Option Gain: {avg_opt_gain:.2f}%")

    out_path = "volume_rocket_backfill_nov2025.csv"
    df_res.to_csv(out_path, index=False)
    logger.success(f"Full backfilled dataset saved to '{out_path}'")

if __name__ == "__main__":
    backfill_stock_and_options()
