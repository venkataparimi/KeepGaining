"""
Backfill IEX equity data from Upstox API
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import json

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal
from app.db.models.instrument import InstrumentMaster
from app.db.models import CandleData
from app.brokers.upstox import UpstoxBroker
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

async def add_iex_instrument():
    """Add IEX equity to instrument master if not exists"""
    async with AsyncSessionLocal() as db:
        # Check if IEX exists
        result = await db.execute(
            select(InstrumentMaster).where(
                InstrumentMaster.trading_symbol == 'IEX',
                InstrumentMaster.instrument_type == 'EQUITY'
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"✅ IEX already exists: {existing.instrument_id}")
            return existing.instrument_id
        
        # Add IEX
        iex = InstrumentMaster(
            trading_symbol='IEX',
            exchange='NSE',
            segment='EQ',
            instrument_type='EQUITY',
            isin='INE931S01010',  # IEX ISIN
            lot_size=1,
            tick_size=0.05,
            is_active=True
        )
        
        db.add(iex)
        await db.commit()
        await db.refresh(iex)
        
        print(f"✅ Added IEX equity: {iex.instrument_id}")
        return iex.instrument_id

async def backfill_iex_data(instrument_id, start_date, end_date):
    """Backfill IEX equity data from Upstox API"""
    
    # Initialize Upstox broker
    token_file = Path(__file__).parent.parent / 'data' / 'upstox_token.json'
    if not token_file.exists():
        print(f"❌ Upstox token not found: {token_file}")
        print(f"   Run: python exchange_code.py")
        return
    
    with open(token_file) as f:
        token_data = json.load(f)
    
    config = {
        'api_key': token_data.get('api_key', ''),
        'api_secret': token_data.get('api_secret', ''),
        'access_token': token_data.get('access_token', '')
    }
    
    broker = UpstoxBroker(config)
    
    print(f"📊 Fetching IEX data from Upstox API...")
    print(f"   Date range: {start_date} to {end_date}")
    
    # Upstox instrument key for IEX
    instrument_key = "NSE_EQ|INE931S01010"  # IEX ISIN
    
    current_date = start_date
    total_inserted = 0
    
    async with AsyncSessionLocal() as db:
        while current_date <= end_date:
            try:
                # Fetch intraday data for the day
                to_date = current_date.replace(hour=15, minute=30)
                from_date = current_date.replace(hour=9, minute=15)
                
                print(f"\n📅 Fetching {current_date.date()}...")
                
                # Get historical data from Upstox
                candles = await broker.get_historical_data(
                    instrument_key=instrument_key,
                    interval='5minute',
                    from_date=from_date,
                    to_date=to_date
                )
                
                if candles and len(candles) > 0:
                    # Prepare candle data for insertion
                    candle_records = []
                    for candle in candles:
                        candle_records.append({
                            'instrument_id': instrument_id,
                            'timeframe': '5min',
                            'timestamp': candle['timestamp'],
                            'open': candle['open'],
                            'high': candle['high'],
                            'low': candle['low'],
                            'close': candle['close'],
                            'volume': candle['volume']
                        })
                    
                    # Upsert candles (insert or ignore duplicates)
                    stmt = insert(CandleData).values(candle_records)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=['instrument_id', 'timeframe', 'timestamp']
                    )
                    
                    await db.execute(stmt)
                    await db.commit()
                    
                    total_inserted += len(candle_records)
                    print(f"   ✅ Inserted {len(candle_records)} candles | Total: {total_inserted}")
                else:
                    print(f"   ⚠️ No data available")
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
            
            # Move to next day
            current_date += timedelta(days=1)
            
            # Rate limiting - wait 1 second between requests
            await asyncio.sleep(1)
    
    print(f"\n✅ Backfill complete: {total_inserted} candles inserted")

async def main():
    print("="*70)
    print("  IEX EQUITY BACKFILL")
    print("="*70)
    
    # Add instrument
    print("\n📝 Step 1: Add IEX to instrument master...")
    instrument_id = await add_iex_instrument()
    
    # Backfill data for December 2024
    print("\n📊 Step 2: Backfill data...")
    start_date = datetime(2024, 12, 1)
    end_date = datetime(2024, 12, 6)
    
    await backfill_iex_data(instrument_id, start_date, end_date)
    
    print("\n" + "="*70)
    print("✅ COMPLETE!")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
