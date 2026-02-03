"""
Compute technical indicators for F&O (Options and Futures) data
Processes candle data and stores computed indicators in indicator_data table
"""
import asyncio
import asyncpg
import numpy as np
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Import indicator functions from generate_dataset
from generate_dataset import (
    compute_sma, compute_ema, compute_rsi, compute_macd,
    compute_bollinger, compute_supertrend, compute_adx,
    compute_atr, compute_vwap
)

DB_URL = 'postgresql://user:password@127.0.0.1:5432/keepgaining'

async def compute_indicators_for_instrument(conn, instrument_id, symbol, min_candles=200):
    """Compute indicators for a single F&O instrument"""
    
    # Fetch candle data
    rows = await conn.fetch("""
        SELECT timestamp, open, high, low, close, volume, oi
        FROM candle_data
        WHERE instrument_id = $1 AND timeframe = '1m'
        ORDER BY timestamp ASC
    """, instrument_id)
    
    if len(rows) < min_candles:
        return 0, f"Insufficient data ({len(rows)} candles)"
    
    # Convert to DataFrame
    df = pd.DataFrame([dict(r) for r in rows])
    
    # Convert Decimal to float
    for col in ['open', 'high', 'low', 'close', 'volume', 'oi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Extract arrays
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values
    timestamps = df['timestamp'].values
    
    # Compute indicators
    indicators = pd.DataFrame()
    indicators['instrument_id'] = instrument_id
    indicators['timestamp'] = df['timestamp']
    indicators['timeframe'] = '1m'
    
    # Moving averages
    indicators['sma_5'] = compute_sma(close, 5)
    indicators['sma_10'] = compute_sma(close, 10)
    indicators['sma_20'] = compute_sma(close, 20)
    indicators['sma_50'] = compute_sma(close, 50)
    indicators['sma_200'] = compute_sma(close, 200)
    
    indicators['ema_9'] = compute_ema(close, 9)
    indicators['ema_21'] = compute_ema(close, 21)
    indicators['ema_50'] = compute_ema(close, 50)
    indicators['ema_200'] = compute_ema(close, 200)
    
    # RSI
    indicators['rsi_14'] = compute_rsi(close, 14)
    
    # MACD
    macd, signal, hist = compute_macd(close)
    indicators['macd'] = macd
    indicators['macd_signal'] = signal
    indicators['macd_histogram'] = hist
    
    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = compute_bollinger(close, 20, 2)
    indicators['bb_upper'] = bb_upper
    indicators['bb_middle'] = bb_middle
    indicators['bb_lower'] = bb_lower
    
    # VWAP
    indicators['vwap'] = compute_vwap(high, low, close, volume, timestamps)
    
    # Supertrend
    st, st_dir = compute_supertrend(high, low, close)
    indicators['supertrend'] = st
    indicators['supertrend_direction'] = st_dir
    
    # ADX
    adx, plus_di, minus_di = compute_adx(high, low, close)
    indicators['adx'] = adx
    indicators['plus_di'] = plus_di
    indicators['minus_di'] = minus_di
    
    # ATR
    indicators['atr_14'] = compute_atr(high, low, close, 14)
    
    # Drop rows with NaN in critical indicators
    indicators_clean = indicators.dropna(subset=['sma_200']).copy()
    
    if indicators_clean.empty:
        return 0, "No valid indicators after cleaning"
    
    # Insert into database
    inserted = 0
    for _, row in indicators_clean.iterrows():
        try:
            await conn.execute("""
                INSERT INTO indicator_data (
                    instrument_id, timestamp, timeframe,
                    sma_5, sma_10, sma_20, sma_50, sma_200,
                    ema_9, ema_21, ema_50, ema_200,
                    rsi_14, macd, macd_signal, macd_histogram,
                    bb_upper, bb_middle, bb_lower,
                    vwap, supertrend, supertrend_direction,
                    adx, plus_di, minus_di, atr_14
                ) VALUES (
                    $1, $2, $3,
                    $4, $5, $6, $7, $8,
                    $9, $10, $11, $12,
                    $13, $14, $15, $16,
                    $17, $18, $19,
                    $20, $21, $22,
                    $23, $24, $25, $26
                )
                ON CONFLICT (instrument_id, timestamp, timeframe) DO UPDATE SET
                    sma_5 = EXCLUDED.sma_5,
                    sma_10 = EXCLUDED.sma_10,
                    sma_20 = EXCLUDED.sma_20,
                    sma_50 = EXCLUDED.sma_50,
                    sma_200 = EXCLUDED.sma_200,
                    ema_9 = EXCLUDED.ema_9,
                    ema_21 = EXCLUDED.ema_21,
                    ema_50 = EXCLUDED.ema_50,
                    ema_200 = EXCLUDED.ema_200,
                    rsi_14 = EXCLUDED.rsi_14,
                    macd = EXCLUDED.macd,
                    macd_signal = EXCLUDED.macd_signal,
                    macd_histogram = EXCLUDED.macd_histogram,
                    bb_upper = EXCLUDED.bb_upper,
                    bb_middle = EXCLUDED.bb_middle,
                    bb_lower = EXCLUDED.bb_lower,
                    vwap = EXCLUDED.vwap,
                    supertrend = EXCLUDED.supertrend,
                    supertrend_direction = EXCLUDED.supertrend_direction,
                    adx = EXCLUDED.adx,
                    plus_di = EXCLUDED.plus_di,
                    minus_di = EXCLUDED.minus_di,
                    atr_14 = EXCLUDED.atr_14
            """,
                row['instrument_id'], row['timestamp'], row['timeframe'],
                float(row['sma_5']) if not pd.isna(row['sma_5']) else None,
                float(row['sma_10']) if not pd.isna(row['sma_10']) else None,
                float(row['sma_20']) if not pd.isna(row['sma_20']) else None,
                float(row['sma_50']) if not pd.isna(row['sma_50']) else None,
                float(row['sma_200']) if not pd.isna(row['sma_200']) else None,
                float(row['ema_9']) if not pd.isna(row['ema_9']) else None,
                float(row['ema_21']) if not pd.isna(row['ema_21']) else None,
                float(row['ema_50']) if not pd.isna(row['ema_50']) else None,
                float(row['ema_200']) if not pd.isna(row['ema_200']) else None,
                float(row['rsi_14']) if not pd.isna(row['rsi_14']) else None,
                float(row['macd']) if not pd.isna(row['macd']) else None,
                float(row['macd_signal']) if not pd.isna(row['macd_signal']) else None,
                float(row['macd_histogram']) if not pd.isna(row['macd_histogram']) else None,
                float(row['bb_upper']) if not pd.isna(row['bb_upper']) else None,
                float(row['bb_middle']) if not pd.isna(row['bb_middle']) else None,
                float(row['bb_lower']) if not pd.isna(row['bb_lower']) else None,
                float(row['vwap']) if not pd.isna(row['vwap']) else None,
                float(row['supertrend']) if not pd.isna(row['supertrend']) else None,
                int(row['supertrend_direction']) if not pd.isna(row['supertrend_direction']) else None,
                float(row['adx']) if not pd.isna(row['adx']) else None,
                float(row['plus_di']) if not pd.isna(row['plus_di']) else None,
                float(row['minus_di']) if not pd.isna(row['minus_di']) else None,
                float(row['atr_14']) if not pd.isna(row['atr_14']) else None
            )
            inserted += 1
        except Exception as e:
            pass
    
    return inserted, f"Computed {inserted} indicator rows"

async def compute_fo_indicators(
    underlying: str = None,
    instrument_type: str = None,
    limit: int = 0
):
    """
    Compute indicators for F&O instruments
    
    Args:
        underlying: Filter by underlying (e.g., 'NIFTY', 'BANKNIFTY')
        instrument_type: Filter by type ('FUTURES', 'CE', 'PE')
        limit: Limit number of instruments (0 = all)
    """
    print("=" * 80)
    print("COMPUTING INDICATORS FOR F&O DATA")
    print("=" * 80)
    
    pool = await asyncpg.create_pool(DB_URL)
    
    async with pool.acquire() as conn:
        # Build query
        query = """
            SELECT DISTINCT
                im.instrument_id,
                im.trading_symbol,
                im.instrument_type,
                im.underlying
            FROM instrument_master im
            JOIN candle_data cd ON im.instrument_id = cd.instrument_id
            WHERE im.instrument_type IN ('FUTURES', 'CE', 'PE')
        """
        
        params = []
        if underlying:
            query += " AND im.underlying = $1"
            params.append(underlying)
        
        if instrument_type:
            if params:
                query += f" AND im.instrument_type = ${len(params) + 1}"
            else:
                query += " AND im.instrument_type = $1"
            params.append(instrument_type)
        
        query += " ORDER BY im.underlying, im.instrument_type, im.trading_symbol"
        
        if limit > 0:
            query += f" LIMIT {limit}"
        
        instruments = await conn.fetch(query, *params) if params else await conn.fetch(query)
        
        print(f"Found {len(instruments)} F&O instruments with candle data")
        print()
        
        total = len(instruments)
        processed = 0
        total_indicators = 0
        
        for idx, inst in enumerate(instruments, 1):
            inst_id = inst['instrument_id']
            symbol = inst['trading_symbol']
            
            count, status = await compute_indicators_for_instrument(conn, inst_id, symbol)
            
            if count > 0:
                print(f"[{idx}/{total}] {symbol:40} | ✅ {count:,} indicators")
                processed += 1
                total_indicators += count
            else:
                print(f"[{idx}/{total}] {symbol:40} | ⏭️  {status}")
        
        print()
        print("=" * 80)
        print(f"✅ Processed {processed}/{total} instruments")
        print(f"✅ Total indicators computed: {total_indicators:,}")
        print("=" * 80)
    
    await pool.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Compute indicators for F&O data')
    parser.add_argument('--underlying', help='Filter by underlying (e.g., NIFTY, BANKNIFTY)')
    parser.add_argument('--type', choices=['FUTURES', 'CE', 'PE'], help='Filter by instrument type')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of instruments (0 = all)')
    
    args = parser.parse_args()
    
    asyncio.run(compute_fo_indicators(
        underlying=args.underlying,
        instrument_type=args.type,
        limit=args.limit
    ))
