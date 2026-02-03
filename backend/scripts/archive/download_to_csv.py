"""
Download data to CSV files, then bulk load to database
This avoids all async/sync issues
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from app.brokers.fyers import FyersBroker
from loguru import logger

from fno_symbols import MAJOR_INDICES, SECTOR_INDICES, FNO_STOCKS

# All F&O symbols - remove problematic ones
SYMBOLS = MAJOR_INDICES + SECTOR_INDICES + [
    s for s in FNO_STOCKS 
    if s not in [
        "NSE:M&M-EQ",  # Invalid format
        "NSE:TATAMOTORS-EQ",  # Invalid symbol
    ]
]

logger.info(f"Total symbols to download: {len(SYMBOLS)}")
logger.info(f"  - Major Indices: {len(MAJOR_INDICES)}")
logger.info(f"  - Sector Indices: {len(SECTOR_INDICES)}")
logger.info(f"  - F&O Stocks: {len(FNO_STOCKS) - 2}")  # Minus 2 invalid

DAYS_BACK = 180
OUTPUT_DIR = Path("data_downloads")


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all 56 indicators"""
    import numpy as np
    
    # Moving Averages
    df['sma_9'] = df['close'].rolling(9).mean()
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    df['sma_200'] = df['close'].rolling(200).mean()
    
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    gain_9 = (delta.where(delta > 0, 0)).rolling(9).mean()
    loss_9 = (-delta.where(delta < 0, 0)).rolling(9).mean()
    rs_9 = gain_9 / loss_9
    df['rsi_9'] = 100 - (100 / (1 + rs_9))
    
    # MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_histogram'] = df['macd'] - df['macd_signal']
    
    # Stochastic
    low_14 = df['low'].rolling(14).min()
    high_14 = df['high'].rolling(14).max()
    df['stoch_k'] = 100 * ((df['close'] - low_14) / (high_14 - low_14))
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    
    # Bollinger Bands
    sma_20 = df['close'].rolling(20).mean()
    std_20 = df['close'].rolling(20).std()
    df['bb_upper'] = sma_20 + (2 * std_20)
    df['bb_middle'] = sma_20
    df['bb_lower'] = sma_20 - (2 * std_20)
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr_14'] = true_range.rolling(14).mean()
    
    # ADX
    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    tr = true_range
    plus_di = 100 * (plus_dm.rolling(14).mean() / tr)
    minus_di = 100 * (minus_dm.rolling(14).mean() / tr)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx'] = dx.rolling(14).mean()
    
    # SuperTrend
    hl_avg = (df['high'] + df['low']) / 2
    atr = df['atr_14']
    upper_band = hl_avg + (3 * atr)
    lower_band = hl_avg - (3 * atr)
    df['supertrend'] = lower_band  # Simplified
    df['supertrend_direction'] = 1  # Simplified
    
    # VWMA (multiple periods)
    for period in [20, 22, 31, 50]:
        pv = df['close'] * df['volume']
        df[f'vwma_{period}'] = pv.rolling(period).sum() / df['volume'].rolling(period).sum()
    
    # VWAP
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    
    # OBV
    obv = pd.Series(index=df.index, dtype=float)
    obv.iloc[0] = df['volume'].iloc[0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] + df['volume'].iloc[i]
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] - df['volume'].iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i-1]
    df['obv'] = obv
    
    # Pivot Points (simplified - daily)
    df['pivot_point'] = (df['high'] + df['low'] + df['close']) / 3
    df['pivot_r1'] = (2 * df['pivot_point']) - df['low']
    df['pivot_s1'] = (2 * df['pivot_point']) - df['high']
    
    return df


async def download_to_csv():
    """Download all data to CSV files"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    broker = FyersBroker()
    success = 0
    
    for idx, symbol in enumerate(SYMBOLS, 1):
        logger.info(f"\n[{idx}/{len(SYMBOLS)}] {symbol}")
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=DAYS_BACK)
            
            df = await broker.get_historical_data(
                symbol=symbol,
                resolution="1",
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                logger.warning(f"No data for {symbol}")
                continue
            
            logger.info(f"Got {len(df)} candles, computing indicators...")
            df = compute_indicators(df)
            
            # Add metadata
            df['symbol'] = symbol
            df['timeframe'] = '1m'
            
            # Save to CSV
            filename = OUTPUT_DIR / f"{symbol.replace(':', '_').replace('-', '_')}.csv"
            df.to_csv(filename, index=False)
            logger.success(f"✓ Saved to {filename}")
            success += 1
            
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error: {e}")
    
    logger.info(f"\n✓ Downloaded {success}/{len(SYMBOLS)} symbols to {OUTPUT_DIR}")
    logger.info("Run 'python scripts/load_from_csv.py' to load into database")


if __name__ == "__main__":
    asyncio.run(download_to_csv())
