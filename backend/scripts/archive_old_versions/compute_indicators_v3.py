"""
Compute technical indicators using pandas-ta library.
Much more reliable than hand-rolled implementations.

Indicators computed:
- SMA (9, 20, 50, 200)
- EMA (9, 21, 50, 200)
- RSI (14)
- MACD (12, 26, 9)
- Bollinger Bands (20, 2)
- ATR (14)
- VWAP
- SuperTrend (10, 3)
- ADX with +DI/-DI
- Stochastic (14, 3)
- CCI (20)
- Williams %R (14)
- OBV
- Volume SMA
- Pivot Points:
  * Classic/Standard (P, R1, R2, R3, S1, S2, S3)
  * Fibonacci (R1, R2, R3, S1, S2, S3)
  * Camarilla (R1-R4, S1-S4)
- CPR (Central Pivot Range): TC, Pivot, BC, Width%
- PDH/PDL/PDC (Previous Day High/Low/Close)
"""
import asyncio
import asyncpg
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_URL = 'postgresql://user:password@localhost:5432/keepgaining'
BATCH_SIZE = 5000


def safe_float(val) -> Optional[float]:
    """Convert to float, return None if NaN."""
    if val is None or pd.isna(val):
        return None
    return float(val)


def safe_int(val) -> Optional[int]:
    """Convert to int, return None if NaN."""
    if val is None or pd.isna(val):
        return None
    return int(val)


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all technical indicators using pandas-ta.
    Input df must have: open, high, low, close, volume columns.
    """
    # Make a copy to avoid modifying original
    df = df.copy()
    
    # === Moving Averages ===
    df['sma_9'] = ta.sma(df['close'], length=9)
    df['sma_20'] = ta.sma(df['close'], length=20)
    df['sma_50'] = ta.sma(df['close'], length=50)
    df['sma_200'] = ta.sma(df['close'], length=200)
    
    df['ema_9'] = ta.ema(df['close'], length=9)
    df['ema_21'] = ta.ema(df['close'], length=21)
    df['ema_50'] = ta.ema(df['close'], length=50)
    df['ema_200'] = ta.ema(df['close'], length=200)
    
    # === Volume Weighted ===
    df['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
    df['vwma_20'] = ta.vwma(df['close'], df['volume'], length=20)
    df['vwma_22'] = ta.vwma(df['close'], df['volume'], length=22)
    df['vwma_31'] = ta.vwma(df['close'], df['volume'], length=31)
    
    # === Momentum ===
    df['rsi_14'] = ta.rsi(df['close'], length=14)
    
    # MACD
    macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
    if macd is not None:
        df['macd'] = macd['MACD_12_26_9']
        df['macd_signal'] = macd['MACDs_12_26_9']
        df['macd_histogram'] = macd['MACDh_12_26_9']
    
    # Stochastic
    stoch = ta.stoch(df['high'], df['low'], df['close'], k=14, d=3)
    if stoch is not None:
        df['stoch_k'] = stoch['STOCHk_14_3_3']
        df['stoch_d'] = stoch['STOCHd_14_3_3']
    
    df['cci'] = ta.cci(df['high'], df['low'], df['close'], length=20)
    df['williams_r'] = ta.willr(df['high'], df['low'], df['close'], length=14)
    
    # === Volatility ===
    df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # Bollinger Bands
    bbands = ta.bbands(df['close'], length=20, std=2)
    if bbands is not None:
        # Column names vary by version: BBU_20_2.0 or BBU_20_2.0_2.0
        bb_cols = bbands.columns.tolist()
        df['bb_upper'] = bbands[[c for c in bb_cols if c.startswith('BBU')][0]]
        df['bb_middle'] = bbands[[c for c in bb_cols if c.startswith('BBM')][0]]
        df['bb_lower'] = bbands[[c for c in bb_cols if c.startswith('BBL')][0]]
    
    # === Trend ===
    # ADX
    adx = ta.adx(df['high'], df['low'], df['close'], length=14)
    if adx is not None:
        df['adx'] = adx['ADX_14']
        df['plus_di'] = adx['DMP_14']
        df['minus_di'] = adx['DMN_14']
    
    # SuperTrend
    supertrend = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
    if supertrend is not None:
        # Column names: SUPERT_10_3.0 or SUPERT_10_3
        st_cols = supertrend.columns.tolist()
        df['supertrend'] = supertrend[[c for c in st_cols if c.startswith('SUPERT_') and 'd' not in c][0]]
        df['supertrend_direction'] = supertrend[[c for c in st_cols if 'SUPERTd' in c][0]]
    
    # === Volume ===
    df['obv'] = ta.obv(df['close'], df['volume'])
    df['volume_sma_20'] = ta.sma(df['volume'], length=20)
    df['volume_ratio'] = df['volume'] / df['volume_sma_20']
    
    # === Pivot Points ===
    # We compute pivots based on previous candle's H/L/C
    # For intraday, this should ideally use previous day's daily OHLC
    # Here we use rolling previous candle as approximation
    
    prev_high = df['high'].shift(1)
    prev_low = df['low'].shift(1)
    prev_close = df['close'].shift(1)
    range_hl = prev_high - prev_low
    
    # PDH, PDL, PDC (Previous values)
    df['pdh'] = prev_high
    df['pdl'] = prev_low
    df['pdc'] = prev_close
    
    # Classic/Standard Pivots
    pivot = (prev_high + prev_low + prev_close) / 3
    df['pivot_point'] = pivot
    df['pivot_r1'] = 2 * pivot - prev_low
    df['pivot_r2'] = pivot + range_hl
    df['pivot_r3'] = prev_high + 2 * (pivot - prev_low)
    df['pivot_s1'] = 2 * pivot - prev_high
    df['pivot_s2'] = pivot - range_hl
    df['pivot_s3'] = prev_low - 2 * (prev_high - pivot)
    
    # Fibonacci Pivots
    df['fib_r1'] = pivot + 0.382 * range_hl
    df['fib_r2'] = pivot + 0.618 * range_hl
    df['fib_r3'] = pivot + 1.000 * range_hl
    df['fib_s1'] = pivot - 0.382 * range_hl
    df['fib_s2'] = pivot - 0.618 * range_hl
    df['fib_s3'] = pivot - 1.000 * range_hl
    
    # Camarilla Pivots
    df['cam_r1'] = prev_close + range_hl * 1.1 / 12
    df['cam_r2'] = prev_close + range_hl * 1.1 / 6
    df['cam_r3'] = prev_close + range_hl * 1.1 / 4
    df['cam_r4'] = prev_close + range_hl * 1.1 / 2
    df['cam_s1'] = prev_close - range_hl * 1.1 / 12
    df['cam_s2'] = prev_close - range_hl * 1.1 / 6
    df['cam_s3'] = prev_close - range_hl * 1.1 / 4
    df['cam_s4'] = prev_close - range_hl * 1.1 / 2
    
    # CPR (Central Pivot Range)
    cpr_bc = (prev_high + prev_low) / 2
    df['cpr_bc'] = cpr_bc
    df['cpr_pivot'] = pivot
    df['cpr_tc'] = 2 * pivot - cpr_bc
    df['cpr_width'] = abs(df['cpr_tc'] - df['cpr_bc']) / pivot * 100
    
    return df


async def compute_indicators_for_instrument(
    conn,
    instrument_id: str,
    timeframe: str = '1m'
) -> int:
    """Compute all indicators for a single instrument using pandas-ta."""
    
    # Fetch candle data
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data
        WHERE instrument_id = $1 AND timeframe = $2
        ORDER BY timestamp
    ''', instrument_id, timeframe)
    
    if len(rows) < 200:
        return 0
    
    # Convert to DataFrame
    df = pd.DataFrame([dict(r) for r in rows])
    df.set_index('timestamp', inplace=True)
    
    # Convert Decimal columns to float64 for pandas-ta compatibility
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype('float64')
    
    # Compute all indicators
    df = compute_all_indicators(df)
    
    # Reset index to get timestamp as column
    df = df.reset_index()
    
    # Filter to rows with valid indicators (skip first ~200)
    df = df.iloc[199:].copy()
    
    # Prepare records
    records = []
    for _, row in df.iterrows():
        records.append((
            instrument_id,
            timeframe,
            row['timestamp'],
            safe_float(row.get('sma_9')),
            safe_float(row.get('sma_20')),
            safe_float(row.get('sma_50')),
            safe_float(row.get('sma_200')),
            safe_float(row.get('ema_9')),
            safe_float(row.get('ema_21')),
            safe_float(row.get('ema_50')),
            safe_float(row.get('ema_200')),
            safe_float(row.get('vwap')),
            safe_float(row.get('vwma_20')),
            safe_float(row.get('vwma_22')),
            safe_float(row.get('vwma_31')),
            safe_float(row.get('rsi_14')),
            safe_float(row.get('macd')),
            safe_float(row.get('macd_signal')),
            safe_float(row.get('macd_histogram')),
            safe_float(row.get('stoch_k')),
            safe_float(row.get('stoch_d')),
            safe_float(row.get('cci')),
            safe_float(row.get('williams_r')),
            safe_float(row.get('atr_14')),
            safe_float(row.get('bb_upper')),
            safe_float(row.get('bb_middle')),
            safe_float(row.get('bb_lower')),
            safe_float(row.get('adx')),
            safe_float(row.get('plus_di')),
            safe_float(row.get('minus_di')),
            safe_float(row.get('supertrend')),
            safe_int(row.get('supertrend_direction')),
            safe_float(row.get('pivot_point')),
            safe_float(row.get('pivot_r1')),
            safe_float(row.get('pivot_r2')),
            safe_float(row.get('pivot_r3')),
            safe_float(row.get('pivot_s1')),
            safe_float(row.get('pivot_s2')),
            safe_float(row.get('pivot_s3')),
            safe_float(row.get('cam_r4')),
            safe_float(row.get('cam_r3')),
            safe_float(row.get('cam_r2')),
            safe_float(row.get('cam_r1')),
            safe_float(row.get('cam_s1')),
            safe_float(row.get('cam_s2')),
            safe_float(row.get('cam_s3')),
            safe_float(row.get('cam_s4')),
            safe_int(row.get('obv')),
            safe_int(row.get('volume_sma_20')),
            safe_float(row.get('volume_ratio')),
            safe_float(row.get('pdh')),
            safe_float(row.get('pdl')),
            safe_float(row.get('pdc')),
            safe_float(row.get('cpr_tc')),
            safe_float(row.get('cpr_pivot')),
            safe_float(row.get('cpr_bc')),
            safe_float(row.get('cpr_width')),
            safe_float(row.get('fib_r1')),
            safe_float(row.get('fib_r2')),
            safe_float(row.get('fib_r3')),
            safe_float(row.get('fib_s1')),
            safe_float(row.get('fib_s2')),
            safe_float(row.get('fib_s3')),
        ))
    
    if not records:
        return 0
    
    # Delete existing
    await conn.execute('''
        DELETE FROM indicator_data 
        WHERE instrument_id = $1 AND timeframe = $2
    ''', instrument_id, timeframe)
    
    # Insert in batches
    insert_sql = '''
        INSERT INTO indicator_data (
            instrument_id, timeframe, timestamp,
            sma_9, sma_20, sma_50, sma_200,
            ema_9, ema_21, ema_50, ema_200,
            vwap, vwma_20, vwma_22, vwma_31,
            rsi_14, macd, macd_signal, macd_histogram,
            stoch_k, stoch_d, cci, williams_r,
            atr_14, bb_upper, bb_middle, bb_lower,
            adx, plus_di, minus_di, supertrend, supertrend_direction,
            pivot_point, pivot_r1, pivot_r2, pivot_r3,
            pivot_s1, pivot_s2, pivot_s3,
            cam_r4, cam_r3, cam_r2, cam_r1,
            cam_s1, cam_s2, cam_s3, cam_s4,
            obv, volume_sma_20, volume_ratio,
            pdh, pdl, pdc,
            cpr_tc, cpr_pivot, cpr_bc, cpr_width,
            fib_r1, fib_r2, fib_r3, fib_s1, fib_s2, fib_s3
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
            $29, $30, $31, $32, $33, $34, $35, $36, $37, $38, $39, $40, $41,
            $42, $43, $44, $45, $46, $47, $48, $49, $50, $51, $52, $53, $54,
            $55, $56, $57, $58, $59, $60, $61, $62, $63
        )
    '''
    
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        await conn.executemany(insert_sql, batch)
    
    return len(records)


async def main(instrument_type: str = None, limit: int = 100):
    """Main entry point."""
    conn = await asyncpg.connect(DB_URL)
    
    print("=" * 60)
    print("INDICATOR COMPUTATION (using pandas-ta)")
    print("=" * 60)
    
    # Build query for instruments
    if instrument_type:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.instrument_type, m.trading_symbol
            FROM candle_data_summary s
            JOIN instrument_master m ON s.instrument_id = m.instrument_id
            WHERE s.candle_count >= 200 AND m.instrument_type = $1
            ORDER BY s.candle_count DESC
            LIMIT $2
        ''', instrument_type, limit)
    else:
        instruments = await conn.fetch('''
            SELECT s.instrument_id, s.candle_count, m.instrument_type, m.trading_symbol
            FROM candle_data_summary s
            JOIN instrument_master m ON s.instrument_id = m.instrument_id
            WHERE s.candle_count >= 200
            ORDER BY s.candle_count DESC
            LIMIT $1
        ''', limit)
    
    print(f"\nFound {len(instruments)} instruments with >= 200 candles")
    
    total_records = 0
    start_time = datetime.now()
    
    for i, inst in enumerate(instruments):
        try:
            count = await compute_indicators_for_instrument(
                conn, 
                inst['instrument_id'],
                '1m'
            )
            total_records += count
            
            if (i + 1) % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"Progress: {i + 1}/{len(instruments)} | Records: {total_records:,} | Rate: {rate:.1f}/s")
                
        except Exception as e:
            logger.error(f"Error processing {inst['trading_symbol']}: {e}")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*60}")
    print(f"COMPLETE")
    print(f"{'='*60}")
    print(f"Instruments processed: {len(instruments)}")
    print(f"Total indicator records: {total_records:,}")
    print(f"Time elapsed: {elapsed:.1f}s")
    
    await conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute technical indicators')
    parser.add_argument('--type', type=str, help='Instrument type (EQUITY, INDEX, CE, PE, FUTURES)')
    parser.add_argument('--limit', type=int, default=100, help='Max instruments to process')
    args = parser.parse_args()
    
    asyncio.run(main(args.type, args.limit))
