"""
Simple synchronous data download for F&O symbols
Fully compatible with SQLite
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.models.candle_data import CandleData
from loguru import logger
import time

# Import symbols
from fno_symbols import MAJOR_INDICES, SECTOR_INDICES, FNO_STOCKS

# Filter out invalid symbols
VALID_SYMBOLS = MAJOR_INDICES + [
    s for s in FNO_STOCKS if s not in ["NSE:M&M-EQ"]  # Remove problematic symbols
]

# Configuration
DAYS_BACK = 180
BATCH_SIZE = 1000

logger.info(f"Total symbols to download: {len(VALID_SYMBOLS)}")


def compute_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute basic indicators"""
    # Moving Averages
    for period in [9, 20, 50, 200]:
        df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    
    # VWMA
    for period in [20, 22, 31, 50]:
        pv = df['close'] * df['volume']
        df[f'vwma_{period}'] = pv.rolling(window=period).sum() / df['volume'].rolling(window=period).sum()
    
    # VWAP
    df['vwap'] = ((df['high'] + df['low'] + df['close']) / 3 * df['volume']).cumsum() / df['volume'].cumsum()
    
    return df


def download_symbol(symbol: str, session, fyers_client) -> dict:
    """Download data for one symbol"""
    try:
        logger.info(f"[{symbol}] Downloading...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=DAYS_BACK)
        
        # Fetch data synchronously
        df = fyers_client.fetch_historical_data_sync(
            symbol=symbol,
            resolution="1",
            start_date=start_date,
            end_date=end_date
        )
        
        if df is None or df.empty:
            logger.warning(f"[{symbol}] No data")
            return {"symbol": symbol, "status": "no_data", "candles": 0}
        
        logger.info(f"[{symbol}] Got {len(df)} candles, computing indicators...")
        df = compute_basic_indicators(df)
        
        logger.info(f"[{symbol}] Storing to database...")
        count = 0
        for idx, row in df.iterrows():
            candle = CandleData(
                symbol=symbol,
                timeframe="1m",
                timestamp=row.get('timestamp', idx),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=int(row['volume']),
                sma_9=float(row.get('sma_9')) if pd.notna(row.get('sma_9')) else None,
                sma_20=float(row.get('sma_20')) if pd.notna(row.get('sma_20')) else None,
                sma_50=float(row.get('sma_50')) if pd.notna(row.get('sma_50')) else None,
                sma_200=float(row.get('sma_200')) if pd.notna(row.get('sma_200')) else None,
                ema_9=float(row.get('ema_9')) if pd.notna(row.get('ema_9')) else None,
                ema_20=float(row.get('ema_20')) if pd.notna(row.get('ema_20')) else None,
                ema_50=float(row.get('ema_50')) if pd.notna(row.get('ema_50')) else None,
                ema_200=float(row.get('ema_200')) if pd.notna(row.get('ema_200')) else None,
                vwma_20=float(row.get('vwma_20')) if pd.notna(row.get('vwma_20')) else None,
                vwma_22=float(row.get('vwma_22')) if pd.notna(row.get('vwma_22')) else None,
                vwma_31=float(row.get('vwma_31')) if pd.notna(row.get('vwma_31')) else None,
                vwma_50=float(row.get('vwma_50')) if pd.notna(row.get('vwma_50')) else None,
                vwap=float(row.get('vwap')) if pd.notna(row.get('vwap')) else None,
            )
            session.add(candle)
            count += 1
            
            if count % BATCH_SIZE == 0:
                session.commit()
                logger.info(f"[{symbol}] Committed {count} candles...")
        
        session.commit()
        logger.success(f"[{symbol}] ✓ Stored {count} candles")
        return {"symbol": symbol, "status": "success", "candles": count}
        
    except Exception as e:
        session.rollback()
        logger.error(f"[{symbol}] Error: {e}")
        return {"symbol": symbol, "status": "error", "candles": 0, "error": str(e)}


def main():
    """Main download function"""
    start_time = time.time()
    
    logger.info("=" * 80)
    logger.info("SIMPLE SYNCHRONOUS DATA DOWNLOAD")
    logger.info("=" * 80)
    logger.info(f"Total symbols: {len(VALID_SYMBOLS)}")
    logger.info(f"Period: {DAYS_BACK} days")
    logger.info("=" * 80)
    
    # Initialize database
    engine = create_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    
    # Initialize Fyers (synchronous)
    from app.brokers.fyers_client import FyersClient
    fyers = FyersClient()
    
    success = 0
    failed = 0
    total_candles = 0
    
    for idx, symbol in enumerate(VALID_SYMBOLS, 1):
        logger.info(f"\n{'='*80}")
        logger.info(f"Progress: {idx}/{len(VALID_SYMBOLS)} ({idx/len(VALID_SYMBOLS)*100:.1f}%)")
        logger.info(f"{'='*80}")
        
        session = SessionLocal()
        try:
            result = download_symbol(symbol, session, fyers)
            if result["status"] == "success":
                success += 1
                total_candles += result["candles"]
            else:
                failed += 1
        finally:
            session.close()
        
        time.sleep(0.5)  # Rate limiting
    
    duration = time.time() - start_time
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    
    logger.info("\n" + "=" * 80)
    logger.success("DOWNLOAD COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Successful: {success}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total candles: {total_candles:,}")
    logger.info(f"Time: {hours}h {minutes}m")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
