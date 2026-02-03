"""
Ultra-simple data download using existing Fyers broker
Works with SQLite, no async/sync issues
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.models.candle_data import CandleData
from app.brokers.fyers import FyersBroker
from loguru import logger
import time

# Symbols - start with just the main ones
SYMBOLS = [
    "NSE:NIFTY50-INDEX",
    "NSE:NIFTYBANK-INDEX",
    "NSE:RELIANCE-EQ",
    "NSE:TCS-EQ",
    "NSE:INFY-EQ",
    "NSE:HDFCBANK-EQ",
    "NSE:ICICIBANK-EQ",
    "NSE:SBIN-EQ",
    "NSE:TATAMOTORS-EQ",
    "NSE:BAJFINANCE-EQ",
]

DAYS_BACK = 180


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute basic indicators"""
    # SMA
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    
    # EMA
    df['ema_9'] = df['close'].ewm(span=9).mean()
    df['ema_21'] = df['close'].ewm(span=21).mean()
    
    # VWMA
    pv = df['close'] * df['volume']
    df['vwma_20'] = pv.rolling(20).sum() / df['volume'].rolling(20).sum()
    
    return df


async def download_all():
    """Download all symbols"""
    logger.info("Starting download...")
    
    # Initialize broker
    broker = FyersBroker()
    
    # Initialize database (sync)
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    
    success = 0
    total_candles = 0
    
    for idx, symbol in enumerate(SYMBOLS, 1):
        logger.info(f"\n[{idx}/{len(SYMBOLS)}] {symbol}")
        
        try:
            # Fetch data (async)
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
            
            # Store (sync)
            logger.info(f"Storing to database...")
            session = SessionLocal()
            try:
                for _, row in df.iterrows():
                    candle = CandleData(
                        symbol=symbol,
                        timeframe="1m",
                        timestamp=row.get('timestamp', row.name),
                        open=float(row['open']),
                        high=float(row['high']),
                        low=float(row['low']),
                        close=float(row['close']),
                        volume=int(row['volume']),
                        sma_20=float(row.get('sma_20')) if pd.notna(row.get('sma_20')) else None,
                        sma_50=float(row.get('sma_50')) if pd.notna(row.get('sma_50')) else None,
                        ema_9=float(row.get('ema_9')) if pd.notna(row.get('ema_9')) else None,
                        ema_21=float(row.get('ema_21')) if pd.notna(row.get('ema_21')) else None,
                        vwma_20=float(row.get('vwma_20')) if pd.notna(row.get('vwma_20')) else None,
                    )
                    session.add(candle)
                
                session.commit()
                logger.success(f"✓ Stored {len(df)} candles")
                success += 1
                total_candles += len(df)
                
            finally:
                session.close()
            
            await asyncio.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            logger.error(f"Error with {symbol}: {e}")
    
    logger.info(f"\nDone! {success}/{len(SYMBOLS)} symbols, {total_candles:,} candles")


if __name__ == "__main__":
    asyncio.run(download_all())
