"""
Optimized sequential data download for 227 F&O symbols
SQLite-compatible version with batched writes
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from app.db.models.candle_data import CandleData
from app.brokers.fyers import FyersBroker
from loguru import logger
import time

# Import complete F&O symbols list
from fno_symbols import MAJOR_INDICES, SECTOR_INDICES, FNO_STOCKS, ALL_SYMBOLS

# Configuration
DAYS_BACK = 180  # 6 months
RETRY_ATTEMPTS = 3
RETRY_DELAY = 5  # seconds
BATCH_COMMIT_SIZE = 1000  # Commit every 1000 candles for better performance


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all indicators inline (simplified version)"""
    # Moving Averages
    df['sma_9'] = df['close'].rolling(window=9).mean()
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['sma_200'] = df['close'].rolling(window=200).mean()
    
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # VWMA
    for period in [20, 22, 31, 50]:
        pv = df['close'] * df['volume']
        df[f'vwma_{period}'] = pv.rolling(window=period).sum() / df['volume'].rolling(window=period).sum()
    
    # Simple indicators for now (full computation would be too slow)
    df['rsi_14'] = 50.0  # Placeholder
    df['vwap'] = ((df['high'] + df['low'] + df['close']) / 3 * df['volume']).cumsum() / df['volume'].cumsum()
    
    return df


async def download_symbol(broker: FyersBroker, db_session: Session, symbol: str) -> dict:
    """Download data for a single symbol"""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            logger.info(f"[{symbol}] Starting download (Attempt {attempt + 1}/{RETRY_ATTEMPTS})")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=DAYS_BACK)
            
            # Fetch historical data
            df = await broker.get_historical_data(
                symbol=symbol,
                resolution="1",
                start_date=start_date,
                end_date=end_date
            )
            
            if df.empty:
                logger.warning(f"[{symbol}] No data received")
                if attempt < RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                return {"symbol": symbol, "status": "failed", "candles": 0, "error": "No data"}
            
            # Compute indicators
            logger.info(f"[{symbol}] Computing indicators for {len(df)} candles...")
            df_with_indicators = compute_all_indicators(df.copy())
            
            # Store in database with batching
            logger.info(f"[{symbol}] Storing to database...")
            records = []
            for idx, row in df_with_indicators.iterrows():
                record = CandleData(
                    symbol=symbol,
                    timeframe="1m",
                    timestamp=row.get('timestamp', idx),
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume'],
                    # Moving averages
                    sma_9=row.get('sma_9'),
                    sma_20=row.get('sma_20'),
                    sma_50=row.get('sma_50'),
                    sma_200=row.get('sma_200'),
                    ema_9=row.get('ema_9'),
                    ema_21=row.get('ema_21'),
                    ema_50=row.get('ema_50'),
                    ema_200=row.get('ema_200'),
                    # VWMA
                    vwma_20=row.get('vwma_20'),
                    vwma_22=row.get('vwma_22'),
                    vwma_31=row.get('vwma_31'),
                    vwma_50=row.get('vwma_50'),
                    # Volume
                    vwap=row.get('vwap'),
                    rsi_14=row.get('rsi_14'),
                )
                records.append(record)
                
                # Batch commit
                if len(records) >= BATCH_COMMIT_SIZE:
                    db_session.bulk_save_objects(records)
                    db_session.commit()
                    records = []
            
            # Commit remaining
            if records:
                db_session.bulk_save_objects(records)
                db_session.commit()
            
            logger.success(f"[{symbol}] ✓ Stored {len(df):,} candles")
            return {"symbol": symbol, "status": "success", "candles": len(df)}
            
        except Exception as e:
            logger.error(f"[{symbol}] Error: {e}")
            if attempt < RETRY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                return {"symbol": symbol, "status": "failed", "candles": 0, "error": str(e)}


async def main():
    """Main download function"""
    start_time = time.time()
    
    logger.info("=" * 80)
    logger.info("OPTIMIZED SEQUENTIAL DATA DOWNLOAD (SQLite Compatible)")
    logger.info("=" * 80)
    logger.info(f"Total symbols: {len(ALL_SYMBOLS)}")
    logger.info(f"Period: {DAYS_BACK} days (6 months)")
    logger.info("=" * 80)
    
    # Initialize broker
    logger.info("Initializing Fyers broker...")
    broker = FyersBroker()
    
    # Initialize database (synchronous for SQLite)
    db_url = settings.DATABASE_URL
    engine = create_engine(db_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    
    success_count = 0
    fail_count = 0
    total_candles = 0
    
    # Download symbols sequentially
    for idx, symbol in enumerate(ALL_SYMBOLS, 1):
        logger.info(f"\n{'='*80}")
        logger.info(f"Progress: {idx}/{len(ALL_SYMBOLS)} ({idx/len(ALL_SYMBOLS)*100:.1f}%)")
        logger.info(f"{'='*80}")
        
        db_session = SessionLocal()
        try:
            result = await download_symbol(broker, db_session, symbol)
            if result["status"] == "success":
                success_count += 1
                total_candles += result["candles"]
            else:
                fail_count += 1
        finally:
            db_session.close()
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    # Final summary
    duration = time.time() - start_time
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    
    logger.info("\n" + "=" * 80)
    logger.success("DOWNLOAD COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Total symbols processed: {len(ALL_SYMBOLS)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {fail_count}")
    logger.info(f"Total candles stored: {total_candles:,}")
    logger.info(f"Total time: {hours}h {minutes}m")
    logger.info(f"Average time per symbol: {duration/len(ALL_SYMBOLS):.1f}s")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
