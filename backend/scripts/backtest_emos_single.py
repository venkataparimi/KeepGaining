import asyncio
import os
import sys
from datetime import datetime, date
import pandas as pd
from loguru import logger

# Add parent dir to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.strategies.emos_strategy import EMOSStrategy
from app.brokers.fyers import FyersBroker
from app.brokers.upstox_data import create_upstox_service

async def run_single_stock_backtest(symbol: str, earnings_date: str, result_timing: str = "After Market"):
    """
    Run EMOS backtest for a single stock around a specific earnings date.
    """
    logger.info(f"--- Running EMOS Backtest for {symbol} ---")
    
    # 1. Setup
    config = {
        "capital": 100000,
        "stock_universe": [symbol],
        "risk_per_trade": 0.01,
        "surprise_threshold": 0.001 # 0.1% daily avg move threshold (lowered for testing)
    }
    
    # Initialize Dependencies
    # Note: Broker is not really used in backtest method logic (purely data analysis)
    # but strategy init requires it.
    broker = FyersBroker() 
    upstox = await create_upstox_service(auto_auth=True)
    
    strategy = EMOSStrategy(broker, upstox, config)
    
    # 2. Prepare Data
    e_date = datetime.strptime(earnings_date, "%Y-%m-%d")
    # Test around the event: 7 days before to 5 days after
    start_date = e_date - pd.Timedelta(days=7)
    end_date = e_date + pd.Timedelta(days=10)   
    
    earnings_map = {
        symbol: [e_date]
    }
    
    try:
        if not await strategy.upstox.initialize():
             logger.error("Failed to auth Upstox. Please ensure valid token is active or auto-login works.")
             return

        # 3. Execute Backtest
        # result_timing="After Market" -> Trade on Morning of Earnings Day
        # result_timing="Market" -> Trade on E-1 Close
        results = await strategy.backtest(
            start_date=start_date, 
            end_date=end_date, 
            earnings_map=earnings_map,
            result_timing=result_timing
        )
        
        # 4. Report
        print("\n" + "="*30)
        print(f"BACKTEST RESULTS: {symbol}")
        print(f"Earnings Date: {earnings_date}")
        print("-" * 30)
        print(f"Total PnL: INR {results['total_pnl']}")
        print(f"Win Rate:  {results['win_rate']:.0%}")
        print(f"Trades Taken: {results['num_trades']}")
        
        if results['trades']:
            print("\nTrade Details:")
            df = pd.DataFrame(results['trades'])
            # Ensure columns exist before printing
            cols = ['event_date', 'entry_date', 'direction', 'underlying_entry', 'underlying_exit', 'option_symbol', 'est_option_ret', 'pnl']
            print(df[cols].to_string(index=False))
        else:
            print("\nNo trades generated based on strategy criteria.")
            
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
    finally:
        await strategy.on_stop()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        symbol = sys.argv[1]
        e_date = sys.argv[2]
        # Optional 3rd arg for timing
        timing = sys.argv[3] if len(sys.argv) > 3 else "After Market"
    else:
        # Default Test Case (Titan Q3 FY26 - Data up to Feb 13, 2026 available)
        symbol = "TITAN"
        e_date = "2026-02-10"
        timing = "After Market"
        
    asyncio.run(run_single_stock_backtest(symbol, e_date, timing))
