"""
Refresh Equity Indicators for a specific date range.
Fetches all candle data (for proper indicator warmup) but only stores 
indicator rows from the specified date range.
"""
import asyncio
import asyncpg
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'

# Import indicator functions from stage1
from stage1_compute import compute_all_indicators


async def refresh_indicators_for_date_range(
    start_date: str = '2025-10-01',
    end_date: str = '2026-01-30',
    instrument_type: str = 'EQUITY',
    workers: int = 8
):
    """Refresh indicators for a specific date range."""
    
    pool = await asyncpg.create_pool(DB_URL, min_size=workers, max_size=workers + 2)
    
    logger.info("=" * 80)
    logger.info(f"REFRESH INDICATORS: {start_date} to {end_date}")
    logger.info(f"Instrument type: {instrument_type}")
    logger.info("=" * 80)
    
    # Get instruments
    async with pool.acquire() as conn:
        instruments = await conn.fetch('''
            SELECT DISTINCT m.instrument_id, m.trading_symbol
            FROM instrument_master m
            JOIN candle_data c ON m.instrument_id = c.instrument_id
            WHERE m.instrument_type = $1
            AND c.timeframe = '1m'
            GROUP BY m.instrument_id, m.trading_symbol
            HAVING COUNT(*) >= 200
        ''', instrument_type)
    
    logger.info(f"Found {len(instruments)} {instrument_type} instruments to refresh")
    
    total_updated = 0
    total_instruments = 0
    start_time = datetime.now()
    
    for i, inst in enumerate(instruments):
        inst_id = inst['instrument_id']
        symbol = inst['trading_symbol']
        
        try:
            async with pool.acquire() as conn:
                # Fetch ALL candle data (needed for indicator warmup)
                rows = await conn.fetch('''
                    SELECT timestamp, open, high, low, close, volume
                    FROM candle_data 
                    WHERE instrument_id = $1 AND timeframe = '1m'
                    ORDER BY timestamp
                ''', inst_id)
                
                if len(rows) < 200:
                    continue
                
                # Convert to numpy
                timestamps = [r['timestamp'] for r in rows]
                high = np.array([float(r['high']) for r in rows])
                low = np.array([float(r['low']) for r in rows])
                close = np.array([float(r['close']) for r in rows])
                volume = np.array([float(r['volume']) for r in rows])
                
                # Compute all indicators
                indicators = compute_all_indicators(timestamps, high, low, close, volume)
                
                # Build DataFrame
                df = pd.DataFrame({
                    'timestamp': timestamps,
                    'instrument_id': str(inst_id),
                    'timeframe': '1m',
                })
                
                for col_name, col_data in indicators.items():
                    if col_name not in ['timestamp']:
                        if isinstance(col_data, np.ndarray):
                            df[col_name] = col_data
                        elif isinstance(col_data, list):
                            df[col_name] = col_data
                
                # Filter to only the date range we want
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                start_dt = pd.Timestamp(start_date, tz='UTC')
                end_dt = pd.Timestamp(end_date, tz='UTC') + pd.Timedelta(days=1)
                
                df_filtered = df[(df['timestamp'] >= start_dt) & (df['timestamp'] < end_dt)]
                
                if len(df_filtered) == 0:
                    continue
                
                # Delete existing rows for this range
                await conn.execute('''
                    DELETE FROM indicator_data 
                    WHERE instrument_id = $1 
                    AND timeframe = '1m'
                    AND timestamp >= $2 
                    AND timestamp < $3
                ''', inst_id, start_dt, end_dt)
                
                # Prepare columns
                db_columns = [
                    'instrument_id', 'timeframe', 'timestamp',
                    'sma_9', 'sma_20', 'sma_50', 'sma_200',
                    'ema_9', 'ema_21', 'ema_50', 'ema_200',
                    'vwap', 'rsi_14',
                    'macd', 'macd_signal', 'macd_histogram',
                    'atr_14', 'bb_upper', 'bb_middle', 'bb_lower',
                    'adx', 'plus_di', 'minus_di',
                    'supertrend', 'supertrend_direction',
                    'obv', 'volume_sma_20',
                    'pivot_point', 'pivot_r1', 'pivot_r2', 'pivot_s1', 'pivot_s2',
                    'fib_r1', 'fib_r2', 'fib_s1', 'fib_s2'
                ]
                
                available_cols = [c for c in db_columns if c in df_filtered.columns]
                df_insert = df_filtered[available_cols].copy()
                df_insert = df_insert.replace({np.nan: None})
                
                if 'supertrend_direction' in df_insert.columns:
                    df_insert['supertrend_direction'] = df_insert['supertrend_direction'].apply(
                        lambda x: int(x) if x is not None and not pd.isna(x) else None
                    )
                
                # Insert rows
                records = df_insert.to_records(index=False)
                insert_sql = f"""
                    INSERT INTO indicator_data ({', '.join(available_cols)})
                    VALUES ({', '.join([f'${i+1}' for i in range(len(available_cols))])})
                    ON CONFLICT (instrument_id, timeframe, timestamp) DO UPDATE SET
                    {', '.join([f'{c} = EXCLUDED.{c}' for c in available_cols if c not in ['instrument_id', 'timeframe', 'timestamp']])}
                """
                
                await conn.executemany(insert_sql, [tuple(r) for r in records])
                
                total_updated += len(df_insert)
                total_instruments += 1
                
                if (i + 1) % 10 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = (i + 1) / elapsed if elapsed > 0 else 0
                    logger.info(f"Progress: {i+1}/{len(instruments)} | Updated: {total_updated:,} rows | Rate: {rate:.1f}/s")
                    
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("\n" + "=" * 80)
    logger.info("REFRESH COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Instruments updated: {total_instruments}")
    logger.info(f"Total rows updated: {total_updated:,}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")
    
    await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Refresh indicators for date range')
    parser.add_argument('--start', default='2025-10-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', default='2026-01-30', help='End date (YYYY-MM-DD)')
    parser.add_argument('--type', default='EQUITY', help='Instrument type')
    parser.add_argument('--workers', type=int, default=8, help='Parallel workers')
    
    args = parser.parse_args()
    
    asyncio.run(refresh_indicators_for_date_range(
        args.start, args.end, args.type, args.workers
    ))
