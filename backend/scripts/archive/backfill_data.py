"""
Backfill Missing Data for F&O Stocks
Downloads data from last available date to today, computes indicators, and loads to DB
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

DB_PATH = "keepgaining.db"

async def get_last_date(symbol):
    """Get the last date we have data for this symbol"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT MAX(timestamp) FROM candle_data WHERE symbol = ?",
        (symbol,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return pd.to_datetime(result[0])
    return None

async def backfill_stock(broker, symbol):
    """Backfill data for a single stock"""
    last_date = await get_last_date(symbol)
    
    if not last_date:
        logger.warning(f"  No existing data for {symbol}")
        return 0
    
    # Calculate days missing
    today = datetime.now()
    days_missing = (today - last_date).days
    
    if days_missing <= 1:
        logger.info(f"  ✓ Up to date (last: {last_date.date()})")
        return 0
    
    logger.info(f"  Missing {days_missing} days (last: {last_date.date()})")
    
    # Download missing data
    try:
        df = await broker.get_historical_data(
            symbol=symbol,
            resolution="1",
            start_date=last_date + timedelta(days=1),
            end_date=today
        )
        
        if df.empty:
            logger.warning(f"  No new data available")
            return 0
        
        # Compute indicators
        df_with_indicators = IndicatorComputationService.compute_all_indicators(df)
        
        # Prepare for database insertion
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        inserted = 0
        for _, row in df_with_indicators.iterrows():
            try:
                cursor.execute("""
                    INSERT INTO candle_data (
                        symbol, timestamp, open, high, low, close, volume, oi,
                        sma_9, sma_20, sma_50, sma_200,
                        ema_9, ema_21, ema_50, ema_200,
                        rsi_14, rsi_9,
                        macd, macd_signal, macd_histogram,
                        stoch_k, stoch_d,
                        bb_upper, bb_middle, bb_lower,
                        atr_14, supertrend, supertrend_direction,
                        adx, vwap,
                        vwma_20, vwma_22, vwma_31, vwma_50,
                        obv,
                        pivot, r1, r2, r3, s1, s2, s3,
                        fib_r1, fib_r2, fib_r3, fib_s1, fib_s2, fib_s3,
                        cam_r4, cam_r3, cam_r2, cam_r1, cam_s1, cam_s2, cam_s3, cam_s4
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol, row['timestamp'], row['open'], row['high'], row['low'], row['close'],
                    int(row['volume']), int(row.get('oi', 0)),
                    row.get('sma_9'), row.get('sma_20'), row.get('sma_50'), row.get('sma_200'),
                    row.get('ema_9'), row.get('ema_21'), row.get('ema_50'), row.get('ema_200'),
                    row.get('rsi_14'), row.get('rsi_9'),
                    row.get('macd'), row.get('macd_signal'), row.get('macd_histogram'),
                    row.get('stoch_k'), row.get('stoch_d'),
                    row.get('bb_upper'), row.get('bb_middle'), row.get('bb_lower'),
                    row.get('atr_14'), row.get('supertrend'), row.get('supertrend_direction'),
                    row.get('adx'), row.get('vwap'),
                    row.get('vwma_20'), row.get('vwma_22'), row.get('vwma_31'), row.get('vwma_50'),
                    int(row.get('obv', 0)) if pd.notna(row.get('obv')) else None,
                    row.get('pivot'), row.get('r1'), row.get('r2'), row.get('r3'),
                    row.get('s1'), row.get('s2'), row.get('s3'),
                    row.get('fib_r1'), row.get('fib_r2'), row.get('fib_r3'),
                    row.get('fib_s1'), row.get('fib_s2'), row.get('fib_s3'),
                    row.get('cam_r4'), row.get('cam_r3'), row.get('cam_r2'), row.get('cam_r1'),
                    row.get('cam_s1'), row.get('cam_s2'), row.get('cam_s3'), row.get('cam_s4')
                ))
                inserted += 1
            except sqlite3.IntegrityError:
                # Duplicate, skip
                pass
        
        conn.commit()
        conn.close()
        
        logger.success(f"  ✓ Inserted {inserted:,} new candles")
        return inserted
        
    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return 0

async def main():
    logger.info("="*80)
    logger.info("BACKFILLING MISSING DATA FOR F&O STOCKS")
    logger.info("="*80)
    
    # Get all symbols from database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT symbol FROM candle_data ORDER BY symbol")
    symbols = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"\nFound {len(symbols)} symbols in database\n")
    
    broker = FyersBroker()
    total_inserted = 0
    updated_count = 0
    
    for idx, symbol in enumerate(symbols, 1):
        logger.info(f"[{idx}/{len(symbols)}] {symbol}")
        inserted = await backfill_stock(broker, symbol)
        
        if inserted > 0:
            total_inserted += inserted
            updated_count += 1
        
        # Small delay to respect rate limits
        await asyncio.sleep(0.1)
    
    logger.info("\n" + "="*80)
    logger.success("BACKFILL COMPLETE!")
    logger.success(f"Updated: {updated_count}/{len(symbols)} symbols")
    logger.success(f"Total new candles: {total_inserted:,}")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
