"""
Stage 1: Parallel Indicator Computation
Fetches candle data from DB, computes all indicators, outputs to staging directory.
"""
import asyncio
import asyncpg
import numpy as np
import pickle
import json
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
OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'computed'
PROGRESS_FILE = Path(__file__).parent.parent / 'data' / 'compute_progress.json'


# ============================================================================
# INDICATOR FUNCTIONS (optimized numpy implementations)
# ============================================================================

def compute_sma(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    if len(data) >= period:
        cumsum = np.cumsum(np.insert(data, 0, 0))
        result[period-1:] = (cumsum[period:] - cumsum[:-period]) / period
    return result


def compute_ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    if len(data) < period:
        return result
    multiplier = 2 / (period + 1)
    result[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    result = np.full(len(close), np.nan)
    if len(close) < period + 1:
        return result
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        result[period] = 100
    else:
        result[period] = 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(close)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            result[i] = 100
        else:
            result[i] = 100 - (100 / (1 + avg_gain / avg_loss))
    return result


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    result = np.full(n, np.nan)
    if n < 2:
        return result
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1])
    ])
    if n >= period:
        result[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def compute_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, timestamps) -> np.ndarray:
    """VWAP that resets at the start of each trading day."""
    n = len(close)
    result = np.full(n, np.nan)
    typical_price = (high + low + close) / 3
    
    if hasattr(timestamps[0], 'date'):
        dates = np.array([ts.date() for ts in timestamps])
    else:
        dates = np.array([np.datetime64(ts, 'D') for ts in timestamps])
    
    day_starts = np.where(np.concatenate([[True], dates[1:] != dates[:-1]]))[0]
    
    for i, start in enumerate(day_starts):
        end = day_starts[i + 1] if i + 1 < len(day_starts) else n
        day_tp = typical_price[start:end]
        day_vol = volume[start:end]
        cumulative_tpv = np.cumsum(day_tp * day_vol)
        cumulative_vol = np.cumsum(day_vol)
        with np.errstate(divide='ignore', invalid='ignore'):
            result[start:end] = np.where(cumulative_vol > 0, cumulative_tpv / cumulative_vol, np.nan)
    
    return result


def compute_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = np.full(len(close), np.nan)
    valid_macd = ~np.isnan(macd_line)
    if np.sum(valid_macd) >= signal:
        macd_valid = macd_line[valid_macd]
        signal_calc = compute_ema(macd_valid, signal)
        start_idx = np.where(valid_macd)[0][0]
        signal_line[start_idx:start_idx + len(signal_calc)] = signal_calc
    return macd_line, signal_line, macd_line - signal_line


def compute_bollinger(close: np.ndarray, period: int = 20, num_std: float = 2) -> tuple:
    from numpy.lib.stride_tricks import sliding_window_view
    n = len(close)
    sma = compute_sma(close, period)
    std = np.full(n, np.nan)
    if n >= period:
        windows = sliding_window_view(close, period)
        std[period-1:] = np.std(windows, axis=1, ddof=0)
    return sma + (std * num_std), sma, sma - (std * num_std)


def compute_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       period: int = 10, multiplier: float = 3.0) -> tuple:
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    n = len(close)
    supertrend = np.full(n, np.nan)
    direction = np.zeros(n, dtype=np.int16)
    if n >= period:
        supertrend[period - 1] = upper_band[period - 1]
        direction[period - 1] = -1
        for i in range(period, n):
            if close[i - 1] > supertrend[i - 1]:
                supertrend[i] = max(lower_band[i], supertrend[i - 1] if direction[i - 1] == 1 else lower_band[i])
                direction[i] = 1
            else:
                supertrend[i] = min(upper_band[i], supertrend[i - 1] if direction[i - 1] == -1 else upper_band[i])
                direction[i] = -1
    return supertrend, direction


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> tuple:
    n = len(close)
    up_move = np.diff(high, prepend=high[0])
    down_move = np.diff(-low, prepend=-low[0])
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    tr[1:] = np.maximum.reduce([high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])])
    atr = compute_ema(tr, period)
    smooth_plus_dm = compute_ema(plus_dm, period)
    smooth_minus_dm = compute_ema(minus_dm, period)
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    dx = np.full(n, np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        valid = atr > 0
        plus_di[valid] = 100 * smooth_plus_dm[valid] / atr[valid]
        minus_di[valid] = 100 * smooth_minus_dm[valid] / atr[valid]
        di_sum = plus_di + minus_di
        valid_sum = di_sum > 0
        dx[valid_sum] = 100 * np.abs(plus_di[valid_sum] - minus_di[valid_sum]) / di_sum[valid_sum]
    return compute_ema(dx, period), plus_di, minus_di


def compute_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    signs = np.sign(np.diff(close, prepend=close[0]))
    signs[0] = 1
    return np.cumsum(signs * volume).astype(np.int64)


# ============================================================================
# MAIN COMPUTATION
# ============================================================================

def compute_all_indicators(timestamps, high, low, close, volume):
    """Compute all indicators and return as a dictionary."""
    n = len(close)
    
    # Compute all indicators
    indicators = {
        'timestamp': timestamps,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'sma_9': compute_sma(close, 9),
        'sma_20': compute_sma(close, 20),
        'sma_50': compute_sma(close, 50),
        'sma_200': compute_sma(close, 200),
        'ema_9': compute_ema(close, 9),
        'ema_21': compute_ema(close, 21),
        'ema_50': compute_ema(close, 50),
        'ema_200': compute_ema(close, 200),
        'vwap': compute_vwap(high, low, close, volume, timestamps),
        'rsi_14': compute_rsi(close, 14),
        'atr_14': compute_atr(high, low, close, 14),
    }
    
    # MACD
    macd, macd_signal, macd_histogram = compute_macd(close, 12, 26, 9)
    indicators['macd'] = macd
    indicators['macd_signal'] = macd_signal
    indicators['macd_histogram'] = macd_histogram
    
    # Bollinger Bands
    bb_upper, bb_middle, bb_lower = compute_bollinger(close, 20, 2)
    indicators['bb_upper'] = bb_upper
    indicators['bb_middle'] = bb_middle
    indicators['bb_lower'] = bb_lower
    
    # Supertrend
    supertrend, supertrend_dir = compute_supertrend(high, low, close, 10, 3)
    indicators['supertrend'] = supertrend
    indicators['supertrend_direction'] = supertrend_dir
    
    # ADX
    adx, plus_di, minus_di = compute_adx(high, low, close, 14)
    indicators['adx'] = adx
    indicators['plus_di'] = plus_di
    indicators['minus_di'] = minus_di
    
    # OBV
    indicators['obv'] = compute_obv(close, volume)
    
    # Volume SMA
    indicators['volume_sma_20'] = compute_sma(volume, 20)
    
    # Pivots (simplified)
    range_hl = high - low
    pivot = (high + low + close) / 3
    indicators['pivot_point'] = pivot
    indicators['pivot_r1'] = 2 * pivot - low
    indicators['pivot_r2'] = pivot + range_hl
    indicators['pivot_s1'] = 2 * pivot - high
    indicators['pivot_s2'] = pivot - range_hl
    
    # Fibonacci pivots
    indicators['fib_r1'] = pivot + 0.382 * range_hl
    indicators['fib_r2'] = pivot + 0.618 * range_hl
    indicators['fib_s1'] = pivot - 0.382 * range_hl
    indicators['fib_s2'] = pivot - 0.618 * range_hl
    
    return indicators


async def compute_for_instrument(conn, instrument_id: str, symbol: str, timeframe: str = '1m') -> bool:
    """Compute indicators for a single instrument and save to staging."""
    
    # Fetch candle data
    rows = await conn.fetch('''
        SELECT timestamp, open, high, low, close, volume
        FROM candle_data 
        WHERE instrument_id = $1 AND timeframe = $2
        ORDER BY timestamp
    ''', instrument_id, timeframe)
    
    n = len(rows)
    # Minimum 20 candles required - indicators with longer periods (e.g., SMA-200) 
    # will simply be NaN until enough data accumulates
    if n < 20:
        logger.info(f"  {symbol}: Skipped (only {n} candles, need >= 20)")
        return False
    
    # Convert to numpy arrays
    timestamps = [r['timestamp'] for r in rows]
    high = np.array([float(r['high']) for r in rows])
    low = np.array([float(r['low']) for r in rows])
    close = np.array([float(r['close']) for r in rows])
    volume = np.array([float(r['volume']) for r in rows])
    
    # Compute indicators
    indicators = compute_all_indicators(timestamps, high, low, close, volume)
    
    # Add metadata
    indicators['instrument_id'] = str(instrument_id)
    indicators['trading_symbol'] = symbol
    indicators['timeframe'] = timeframe
    indicators['computed_at'] = datetime.now().isoformat()
    indicators['candle_count'] = n
    
    # Save to staging directory
    output_file = OUTPUT_DIR / f"{instrument_id}.pkl"
    with open(output_file, 'wb') as f:
        pickle.dump(indicators, f)
    
    logger.info(f"  {symbol}: {n} candles -> {output_file.name}")
    return True


async def process_worker(pool, inst_id: str, symbol: str) -> tuple:
    """Worker to process a single instrument."""
    try:
        async with pool.acquire() as conn:
            success = await compute_for_instrument(conn, inst_id, symbol)
            return (str(inst_id), symbol, success, None)
    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")
        return (str(inst_id), symbol, False, str(e))


def load_progress() -> dict:
    """Load progress tracking file."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {'completed': [], 'failed': []}


def save_progress(progress: dict):
    """Save progress tracking file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


async def main(workers: int = 8, instrument_type: str = None, limit: int = None, resume: bool = True):
    """Main parallel computation."""
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    pool = await asyncpg.create_pool(DB_URL, min_size=workers, max_size=workers + 2)
    
    logger.info("=" * 80)
    logger.info(f"STAGE 1: INDICATOR COMPUTATION ({workers} workers)")
    logger.info("=" * 80)
    
    # Load progress
    progress = load_progress() if resume else {'completed': [], 'failed': []}
    completed_ids = set(progress['completed'])
    
    # Get instruments to process
    async with pool.acquire() as conn:
        if instrument_type:
            query = '''
                SELECT DISTINCT c.instrument_id, m.trading_symbol, COUNT(*) as candle_count
                FROM candle_data c
                JOIN instrument_master m ON c.instrument_id = m.instrument_id
                WHERE c.timeframe = '1m' AND m.instrument_type = $1
                GROUP BY c.instrument_id, m.trading_symbol
                HAVING COUNT(*) >= 200
                ORDER BY COUNT(*) DESC
            '''
            if limit:
                query += f' LIMIT {limit}'
            instruments = await conn.fetch(query, instrument_type)
        else:
            query = '''
                SELECT DISTINCT c.instrument_id, m.trading_symbol, COUNT(*) as candle_count
                FROM candle_data c
                JOIN instrument_master m ON c.instrument_id = m.instrument_id
                WHERE c.timeframe = '1m'
                GROUP BY c.instrument_id, m.trading_symbol
                HAVING COUNT(*) >= 200
                ORDER BY COUNT(*) DESC
            '''
            if limit:
                query += f' LIMIT {limit}'
            instruments = await conn.fetch(query)
    
    # Filter out already completed
    instruments = [i for i in instruments if str(i['instrument_id']) not in completed_ids]
    
    logger.info(f"Found {len(instruments)} instruments to process (skipping {len(completed_ids)} already done)")
    
    # Process in batches
    total_success = 0
    total_failed = 0
    start_time = datetime.now()
    
    inst_list = list(instruments)
    
    for batch_start in range(0, len(inst_list), workers):
        batch = inst_list[batch_start:batch_start + workers]
        
        tasks = [
            process_worker(pool, inst['instrument_id'], inst['trading_symbol'])
            for inst in batch
        ]
        
        results = await asyncio.gather(*tasks)
        
        for inst_id, symbol, success, error in results:
            if success:
                progress['completed'].append(inst_id)
                total_success += 1
            else:
                if error:
                    progress['failed'].append({'id': inst_id, 'symbol': symbol, 'error': error})
                total_failed += 1
        
        # Save progress after each batch
        save_progress(progress)
        
        # Progress update
        processed = batch_start + len(batch)
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = processed / elapsed if elapsed > 0 else 0
        logger.info(f"Progress: {processed}/{len(inst_list)} | Success: {total_success} | Failed: {total_failed} | Rate: {rate:.1f}/s")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("\n" + "=" * 80)
    logger.info("STAGE 1 COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Success: {total_success}")
    logger.info(f"Failed: {total_failed}")
    logger.info(f"Time: {elapsed/60:.1f} minutes")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    
    await pool.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Stage 1: Compute indicators')
    parser.add_argument('--workers', type=int, default=8, help='Parallel workers (default: 8)')
    parser.add_argument('--type', choices=['EQUITY', 'INDEX', 'FUTURES', 'CE', 'PE'], help='Instrument type filter')
    parser.add_argument('--limit', type=int, help='Limit number of instruments')
    parser.add_argument('--no-resume', action='store_true', help='Start fresh, ignore previous progress')
    
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.workers, args.type, args.limit, not args.no_resume))
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
