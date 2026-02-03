"""Download 6-month historical expired F&O data using Upstox expired instruments APIs."""
import asyncio
import traceback
import sys
import signal
import os
from datetime import date, timedelta
from app.services.data_download_service import DataDownloadService
from app.services.data_providers.upstox import create_upstox_provider

# Force stdout to be unbuffered
sys.stdout.reconfigure(line_buffering=True)

# Ignore SIGINT (Ctrl+C) to prevent interruptions
signal.signal(signal.SIGINT, signal.SIG_IGN)

# Change to backend directory
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    print("Starting download script...", flush=True)
    print(f"Working directory: {os.getcwd()}", flush=True)
    
    token_path = 'data/upstox_token.json'
    print(f"Token path: {os.path.abspath(token_path)}", flush=True)
    
    provider = create_upstox_provider(token_path)
    service = DataDownloadService(provider)
    
    try:
        print("Initializing service...", flush=True)
        await service.initialize()
        print("Service initialized successfully!", flush=True)
        
        # Index underlyings for F&O
        index_underlyings = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']
        print(f"Processing underlyings: {index_underlyings}", flush=True)
        
        # ========================================
        # STEP 1: Download Historical Expired Futures
        # ========================================
        print('=' * 70, flush=True)
        print('STEP 1: Downloading HISTORICAL EXPIRED FUTURES (6 months)', flush=True)
        print('=' * 70, flush=True)
        
        print("Calling download_historical_expired_futures...", flush=True)
        futures_results = await service.download_historical_expired_futures(
            underlyings=index_underlyings,
            months_back=6
        )
        print("Futures download complete!", flush=True)
        
        print(f'\n--- Expired Futures Download Summary ---')
        print(f'  Total Expiries: {futures_results.get("total_expiries", 0)}')
        print(f'  Total Contracts: {futures_results.get("total_contracts", 0)}')
        print(f'  Successful: {futures_results.get("successful", 0)}')
        print(f'  Failed: {futures_results.get("failed", 0)}')
        print(f'  Total Candles: {futures_results.get("total_candles", 0):,}')
        
        if futures_results.get('errors'):
            print(f'\nErrors (first 5):')
            for err in futures_results['errors'][:5]:
                print(f'  {err}')
        
        # ========================================
        # STEP 2: Download Historical Expired Options
        # ========================================
        print('\n' + '=' * 70)
        print('STEP 2: Downloading HISTORICAL EXPIRED OPTIONS (6 months)')
        print('=' * 70)
        
        options_results = await service.download_historical_expired_options(
            underlyings=index_underlyings,
            months_back=6
        )
        
        print(f'\n--- Expired Options Download Summary ---')
        print(f'  Total Expiries: {options_results.get("total_expiries", 0)}')
        print(f'  Total Contracts: {options_results.get("total_contracts", 0)}')
        print(f'  Successful: {options_results.get("successful", 0)}')
        print(f'  Failed: {options_results.get("failed", 0)}')
        print(f'  Total Candles: {options_results.get("total_candles", 0):,}')
        
        if options_results.get('errors'):
            print(f'\nErrors (first 5):')
            for err in options_results['errors'][:5]:
                print(f'  {err}')
        
        # ========================================
        # Final Summary
        # ========================================
        print('\n' + '=' * 70)
        print('DOWNLOAD COMPLETE - FINAL SUMMARY')
        print('=' * 70)
        
        total_contracts = futures_results.get("total_contracts", 0) + options_results.get("total_contracts", 0)
        total_candles = futures_results.get("total_candles", 0) + options_results.get("total_candles", 0)
        
        print(f'\nThis session:')
        print(f'  Total Contracts Downloaded: {total_contracts:,}')
        print(f'  Total Candles Downloaded: {total_candles:,}')
        
        # Query total candles in database
        from sqlalchemy import text
        async with service.async_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM candle_data"))
            db_total = result.scalar()
        
        print(f'\nTotal candles in database: {db_total:,}')
                
    except asyncio.CancelledError:
        print("\n⚠️ Task was cancelled. Partial progress may have been saved.", flush=True)
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        
    finally:
        print("Closing service...", flush=True)
        try:
            await service.close()
        except:
            pass
        print("Done!", flush=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Keyboard interrupt received. Exiting...", flush=True)
