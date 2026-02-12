"""
Generic Stock Data Backfill Script

Downloads historical equity data from Upstox API and stores in TimescaleDB.

Features:
- Any stock symbol(s)
- Multiple timeframes: 1min, 5min, 15min, 30min, 1hour, 1day
- Automatic instrument creation if not exists
- Raw OHLCV data storage (indicators computed on-the-fly by strategies)
- Date range support
- Batch processing with progress tracking

Timeframe Availability (Upstox API):
- 1min, 5min, 15min: Last 30 days (from Jan 2022)
- 30min, 1hour: Last 90 days (from Jan 2018)  
- 1day, 1week, 1month: Last 365 days (from Jan 2000)

Data Storage:
- Raw OHLCV candles stored in TimescaleDB (candle_data table)
- Indicators NOT pre-computed - calculated by strategies on-demand
- This keeps database lean and strategies flexible

Usage Examples:
    # Single stock, single timeframe
    python backfill_equity_data.py --symbol IEX --start 2024-12-01 --end 2024-12-06 --timeframe 5min
    
    # Single stock, multiple timeframes
    python backfill_equity_data.py --symbol RELIANCE --start 2024-12-01 --timeframes 1min,5min,1day
    
    # Multiple stocks, multiple timeframes
    python backfill_equity_data.py --symbols IEX,RELIANCE,TCS --start 2024-11-01 --timeframes 5min,1day
    
    # Download today's data
    python backfill_equity_data.py --symbol IEX --today --timeframe 5min
"""
import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, date
import pandas as pd
from typing import List, Optional
import json

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.db.models.instrument import InstrumentMaster
from app.db.models import CandleData, BrokerSymbolMapping
from app.services.data_providers.upstox import UpstoxDataProvider
from app.services.data_providers.base import DataProviderConfig, Interval, Exchange
from sqlalchemy import select, and_

# Timeframe mapping
TIMEFRAME_MAP = {
    '1min': Interval.MINUTE_1,
    '5min': Interval.MINUTE_5,
    '15min': Interval.MINUTE_15,
    '30min': Interval.MINUTE_30,
    '1hour': Interval.HOUR_1,
    '1day': Interval.DAY,
    '1week': Interval.WEEK,
    '1month': Interval.MONTH,
}

# Upstox data availability
DATA_LIMITS = {
    '1min': 30,   # days
    '5min': 30,
    '15min': 30,
    '30min': 90,
    '1hour': 90,
    '1day': 365,
    '1week': 365,
    '1month': 365 * 5,
}


async def get_or_create_instrument(db, symbol: str, exchange: str = 'NSE') -> Optional[str]:
    """Get existing instrument or create new one"""
    
    # Check if exists
    result = await db.execute(
        select(InstrumentMaster).where(
            InstrumentMaster.trading_symbol == symbol,
            InstrumentMaster.instrument_type == 'EQUITY',
            InstrumentMaster.exchange == exchange
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        print(f"  ✅ Found existing: {existing.trading_symbol} (ID: {existing.instrument_id})")
        return str(existing.instrument_id)
    
    # Create new
    print(f"  📝 Creating new instrument: {symbol}")
    instrument = InstrumentMaster(
        trading_symbol=symbol,
        exchange=exchange,
        segment='EQ',
        instrument_type='EQUITY',
        lot_size=1,
        tick_size=0.05,
        is_active=True
    )
    
    db.add(instrument)
    await db.commit()
    await db.refresh(instrument)
    
    print(f"  ✅ Created: {symbol} (ID: {instrument.instrument_id})")
    return str(instrument.instrument_id)


async def check_existing_data(db, instrument_id: str, timeframe: str, start_date: date, end_date: date):
    """Check what data already exists"""
    
    result = await db.execute(
        select(CandleData.timestamp).where(
            and_(
                CandleData.instrument_id == instrument_id,
                CandleData.timeframe == timeframe,
                CandleData.timestamp >= pd.Timestamp(start_date).tz_localize('UTC'),
                CandleData.timestamp <= pd.Timestamp(end_date).tz_localize('UTC')
            )
        ).order_by(CandleData.timestamp)
    )
    
    existing_timestamps = [row[0] for row in result.all()]
    
    if existing_timestamps:
        print(f"  📊 Existing data: {len(existing_timestamps)} candles")
        print(f"     From: {existing_timestamps[0]}")
        print(f"     To: {existing_timestamps[-1]}")
        return set(existing_timestamps)
    else:
        print(f"  📊 No existing data found")
        return set()


import gzip
import io
import aiohttp

async def fetch_upstox_keys() -> dict:
    """Fetch Upstox instrument keys for NSE."""
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    print(f"⏳ Fetching instrument keys from {url}...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                    data = json.loads(f.read().decode('utf-8'))
                
                cache = {}
                for item in data:
                    if item.get('trading_symbol'):
                         cache[item['trading_symbol']] = item.get('instrument_key')
                
                print(f"✅ Loaded {len(cache)} instrument keys")
                return cache
            else:
                print(f"❌ Failed to fetch keys: {response.status}")
                return {}

async def download_and_store_data(
    provider: UpstoxDataProvider,
    instrument_id: str,
    symbol: str,
    timeframe: str,
    start_date: date,
    end_date: date,
    upstox_cache: dict = None,
    skip_existing: bool = True
):
    """Download data from Upstox and store in database"""
    
    print(f"\n{'='*70}")
    print(f"📥 DOWNLOADING: {symbol} | {timeframe} | {start_date} to {end_date}")
    print(f"{'='*70}")
    
    # Check data limits
    max_days = DATA_LIMITS.get(timeframe, 30)
    days_requested = (end_date - start_date).days
    
    if days_requested > max_days:
        print(f"⚠️  Warning: Requested {days_requested} days, but {timeframe} supports max {max_days} days")
        start_date = end_date - timedelta(days=max_days)
        print(f"   Adjusted start date to: {start_date}")
    
    # Get existing data
    async with AsyncSessionLocal() as db:
        if skip_existing:
            existing_timestamps = await check_existing_data(db, instrument_id, timeframe, start_date, end_date)
        else:
            existing_timestamps = set()
    
    # Download data
    interval = TIMEFRAME_MAP[timeframe]
    
    try:
        print(f"\n🌐 Fetching from Upstox API...")
        
        # Create Instrument object for the provider
        from app.services.data_providers.base import Instrument as ProviderInstrument, InstrumentType, Exchange
        
        # Upstox instrument key lookup
        provider_token = None
        
        # 1. Try cache (dynamic fetch)
        if upstox_cache:
            provider_token = upstox_cache.get(symbol)
            if provider_token:
                print(f"  🔑 Found cached token: {provider_token}")
        
        # 2. Try DB Mapping
        if not provider_token:
            async with AsyncSessionLocal() as db:
                stmt = select(BrokerSymbolMapping).where(
                    BrokerSymbolMapping.instrument_id == instrument_id,
                    BrokerSymbolMapping.broker_name == 'UPSTOX'
                )
                mapping_result = await db.execute(stmt)
                mapping = mapping_result.scalar_one_or_none()
                if mapping and mapping.broker_token:
                    provider_token = mapping.broker_token
                    print(f"  🔑 Found mapped token: {provider_token}")

        # 3. Fallback
        if not provider_token:
             provider_token = f"NSE_EQ|{symbol}"
             print(f"  ⚠️  No mapping found, using fallback: {provider_token}")
        
        instrument_obj = ProviderInstrument(
            symbol=symbol,
            name=symbol,
            instrument_type=InstrumentType.EQUITY,
            exchange=Exchange.NSE,
            provider_token=provider_token
        )
        
        candles = await provider.get_historical_candles(
            instrument=instrument_obj,
            interval=interval,
            from_date=start_date,
            to_date=end_date
        )
        
        print(f"✅ Downloaded {len(candles)} candles")
        
        if not candles:
            print("❌ No data returned from API")
            print(f"   Key used: {provider_token}")
            return
        
        # Filter out existing
        if skip_existing:
            new_candles = []
            for candle in candles:
                candle_ts = pd.Timestamp(candle.timestamp).tz_localize('UTC')
                if candle_ts not in existing_timestamps:
                    new_candles.append(candle)
            
            print(f"📊 New candles to insert: {len(new_candles)} (skipped {len(candles) - len(new_candles)} existing)")
            candles = new_candles
        
        if not candles:
            print("✅ All data already exists, nothing to insert")
            return
        
        # Insert in batches
        batch_size = 1000
        total_inserted = 0
        
        async with AsyncSessionLocal() as db:
            for i in range(0, len(candles), batch_size):
                batch = candles[i:i+batch_size]
                
                db_candles = []
                for candle in batch:
                    db_candle = CandleData(
                        instrument_id=instrument_id,
                        timeframe=timeframe,
                        timestamp=pd.Timestamp(candle.timestamp).tz_localize('UTC'),
                        open=float(candle.open),
                        high=float(candle.high),
                        low=float(candle.low),
                        close=float(candle.close),
                        volume=int(candle.volume)
                    )
                    db_candles.append(db_candle)
                
                db.add_all(db_candles)
                await db.commit()
                
                total_inserted += len(db_candles)
                print(f"  ✅ Batch {i//batch_size + 1}: {total_inserted}/{len(candles)} inserted")
        
        print(f"\n✅ COMPLETE: {total_inserted} new candles stored")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    parser = argparse.ArgumentParser(
        description='Backfill equity data from Upstox API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Symbol(s)
    parser.add_argument('--symbol', type=str, help='Single stock symbol (e.g., IEX, RELIANCE)')
    parser.add_argument('--symbols', type=str, help='Comma-separated stock symbols (e.g., IEX,RELIANCE,TCS)')
    
    # Timeframe(s)
    parser.add_argument('--timeframe', type=str, help='Single timeframe (1min, 5min, 15min, 30min, 1hour, 1day)')
    parser.add_argument('--timeframes', type=str, help='Comma-separated timeframes (e.g., 5min,1day)')
    
    # Date range
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD), defaults to today')
    parser.add_argument('--today', action='store_true', help='Download today\'s data only')
    parser.add_argument('--last-7-days', action='store_true', help='Download last 7 days')
    parser.add_argument('--last-30-days', action='store_true', help='Download last 30 days')
    
    # Options
    parser.add_argument('--force', action='store_true', help='Re-download even if data exists')
    parser.add_argument('--exchange', type=str, default='NSE', help='Exchange (default: NSE)')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not args.symbol and not args.symbols:
        print("❌ Error: Must specify --symbol or --symbols")
        parser.print_help()
        return
    
    if not args.timeframe and not args.timeframes:
        print("❌ Error: Must specify --timeframe or --timeframes")
        parser.print_help()
        return
    
    # Parse symbols
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',')]
    else:
        symbols = [args.symbol.upper()]
    
    # Parse timeframes
    if args.timeframes:
        timeframes = [tf.strip() for tf in args.timeframes.split(',')]
    else:
        timeframes = [args.timeframe]
    
    # Validate timeframes
    for tf in timeframes:
        if tf not in TIMEFRAME_MAP:
            print(f"❌ Error: Invalid timeframe '{tf}'")
            print(f"   Valid options: {', '.join(TIMEFRAME_MAP.keys())}")
            return
    
    # Parse dates
    if args.today:
        start_date = date.today()
        end_date = date.today()
    elif args.last_7_days:
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
    elif args.last_30_days:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
    else:
        if not args.start:
            print("❌ Error: Must specify --start date or use --today/--last-7-days/--last-30-days")
            return
        
        start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
        
        if args.end:
            end_date = datetime.strptime(args.end, '%Y-%m-%d').date()
        else:
            end_date = date.today()
    
    # Summary
    print("="*70)
    print("  📊 EQUITY DATA BACKFILL")
    print("="*70)
    print(f"\n📝 Configuration:")
    print(f"   Symbols: {', '.join(symbols)}")
    print(f"   Timeframes: {', '.join(timeframes)}")
    print(f"   Date Range: {start_date} to {end_date} ({(end_date - start_date).days} days)")
    print(f"   Exchange: {args.exchange}")
    print(f"   Skip Existing: {not args.force}")
    
    print(f"\n💡 Data Storage:")
    print(f"   • Raw OHLCV candles stored in TimescaleDB")
    print(f"   • Indicators computed on-the-fly by strategies")
    print(f"   • Total operations: {len(symbols)} × {len(timeframes)} = {len(symbols) * len(timeframes)}")
    
    # Load Upstox credentials
    token_file = Path(__file__).parent.parent / 'data' / 'upstox_token.json'
    
    if not token_file.exists():
        print(f"\n❌ Error: Upstox token not found at {token_file}")
        print("   Run the authentication flow first")
        return
    
    with open(token_file) as f:
        token_data = json.load(f)
        access_token = token_data.get('access_token')
    
    if not access_token:
        print("❌ Error: No access_token in token file")
        return
    
    # Initialize Upstox provider
    config = DataProviderConfig(
        provider_name='upstox',
        api_key='',  # Not needed for historical data
        access_token=access_token
    )
    
    provider = UpstoxDataProvider(config)
    
    # Fetch Upstox Keys
    upstox_cache = await fetch_upstox_keys()
    
    # Process each symbol × timeframe combination
    total_operations = len(symbols) * len(timeframes)
    current_operation = 0
    
    async with AsyncSessionLocal() as db:
        for symbol in symbols:
            print(f"\n\n{'='*70}")
            print(f"📈 PROCESSING: {symbol}")
            print(f"{'='*70}")
            
            # Get or create instrument
            instrument_id = await get_or_create_instrument(db, symbol, args.exchange)
            
            if not instrument_id:
                print(f"❌ Failed to get/create instrument for {symbol}")
                continue
            
            # Download each timeframe
            for timeframe in timeframes:
                current_operation += 1
                print(f"\n[{current_operation}/{total_operations}]", end=' ')
                
                await download_and_store_data(
                    provider,
                    instrument_id,
                    symbol,
                    timeframe,
                    start_date,
                    end_date,
                    upstox_cache=upstox_cache,
                    skip_existing=not args.force
                )
    
    print(f"\n\n{'='*70}")
    print("✅ BACKFILL COMPLETE!")
    print(f"{'='*70}")
    print(f"\n📊 Summary:")
    print(f"   Symbols processed: {len(symbols)}")
    print(f"   Timeframes: {len(timeframes)}")
    print(f"   Total operations: {total_operations}")
    
    print(f"\n💡 Next Steps:")
    print(f"   1. Verify data: SELECT COUNT(*) FROM candle_data WHERE instrument_id IN (...);")
    print(f"   2. Run strategy analysis on this data")
    print(f"   3. Indicators will be computed automatically by strategies")


if __name__ == "__main__":
    asyncio.run(main())
