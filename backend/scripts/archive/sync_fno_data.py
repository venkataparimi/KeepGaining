"""
Universal Data Sync Script for F&O Stocks
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import asyncio
from loguru import logger
from app.brokers.fyers import FyersBroker
from app.services.indicator_computation import IndicatorComputationService
from scripts.fno_symbols import FNO_STOCKS

DB_PATH = "keepgaining.db"

async def get_last_complete_date(symbol):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(timestamp) FROM candle_data WHERE symbol = ?", (symbol,))
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return None
    
    last_timestamp = pd.to_datetime(result[0])
    last_time = last_timestamp.time()
    market_close_threshold = pd.to_datetime("15:00:00").time()
    
    if last_time < market_close_threshold:
        return pd.to_datetime(last_timestamp.date()) - timedelta(days=1)
    else:
        return pd.to_datetime(last_timestamp.date())

async def insert_data_to_db(symbol, df_with_indicators):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timeframe = "1"
    inserted = 0
    
    for _, row in df_with_indicators.iterrows():
        try:
            cursor.execute("""
                INSERT INTO candle_data (
                    symbol, timeframe, timestamp, open, high, low, close, volume,
                    sma_9, sma_20, sma_50, sma_200, ema_9, ema_21, ema_50, ema_200,
                    rsi_14, rsi_9, macd, macd_signal, macd_histogram, stoch_k, stoch_d,
                    bb_upper, bb_middle, bb_lower, atr_14, supertrend, supertrend_direction, adx,
                    pivot_point, pivot_r1, pivot_r2, pivot_r3, pivot_s1, pivot_s2, pivot_s3,
                    fib_pivot, fib_r1, fib_r2, fib_r3, fib_s1, fib_s2, fib_s3,
                    cam_r4, cam_r3, cam_r2, cam_r1, cam_s1, cam_s2, cam_s3, cam_s4,
                    vwap, vwma_20, vwma_22, vwma_31, vwma_50, obv
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                symbol, timeframe, pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                row['open'], row['high'], row['low'], row['close'], int(row['volume']),
                row.get('sma_9'), row.get('sma_20'), row.get('sma_50'), row.get('sma_200'),
                row.get('ema_9'), row.get('ema_21'), row.get('ema_50'), row.get('ema_200'),
                row.get('rsi_14'), row.get('rsi_9'),
                row.get('macd'), row.get('macd_signal'), row.get('macd_histogram'),
                row.get('stoch_k'), row.get('stoch_d'),
                row.get('bb_upper'), row.get('bb_middle'), row.get('bb_lower'),
                row.get('atr_14'), row.get('supertrend'), row.get('supertrend_direction'), row.get('adx'),
                row.get('pivot'), row.get('r1'), row.get('r2'), row.get('r3'), row.get('s1'), row.get('s2'), row.get('s3'),
                row.get('fib_pivot'), row.get('fib_r1'), row.get('fib_r2'), row.get('fib_r3'), row.get('fib_s1'), row.get('fib_s2'), row.get('fib_s3'),
                row.get('cam_r4'), row.get('cam_r3'), row.get('cam_r2'), row.get('cam_r1'), row.get('cam_s1'), row.get('cam_s2'), row.get('cam_s3'), row.get('cam_s4'),
                row.get('vwap'), row.get('vwma_20'), row.get('vwma_22'), row.get('vwma_31'), row.get('vwma_50'),
                int(row.get('obv', 0)) if pd.notna(row.get('obv')) else None
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            pass
    
    conn.commit()
    conn.close()
    return inserted

async def sync_stock(broker, symbol):
    last_date = await get_last_complete_date(symbol)
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    if last_date:
        if last_date.date() >= yesterday.date():
            logger.info(f"  ✓ Up to date")
            return 0
        days_missing = (today - last_date).days
        logger.info(f"  Backfill: {days_missing} days")
        start_date = last_date + timedelta(days=1)
        end_date = today
    else:
        logger.info(f"  Initial: 6 months")
        start_date = today - timedelta(days=180)
        end_date = today
    
    try:
        df = await broker.get_historical_data(symbol=symbol, resolution="1", start_date=start_date, end_date=end_date)
        if df.empty:
            return 0
        df_with_indicators = IndicatorComputationService.compute_all_indicators(df)
        inserted = await insert_data_to_db(symbol, df_with_indicators)
        logger.success(f"  ✓ {inserted:,} candles")
        return inserted
    except Exception as e:
        logger.error(f"  ✗ {e}")
        return 0

async def main():
    logger.info("="*80)
    logger.info("F&O DATA SYNC")
    logger.info("="*80)
    
    broker = FyersBroker()
    symbols = [s for s in FNO_STOCKS if '-EQ' in s]
    logger.info(f"\n{len(symbols)} stocks\n")
    
    total = 0
    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"[{idx}/{len(symbols)}] {symbol}")
        total += await sync_stock(broker, symbol)
        await asyncio.sleep(0.1)
    
    logger.info("\n" + "="*80)
    logger.success(f"DONE! {total:,} candles")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
