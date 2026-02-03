"""Download comprehensive F&O data - ALL Stock Futures and Index Options."""
import asyncio
from datetime import date, timedelta
from app.services.data_download_service import DataDownloadService
from app.services.data_providers.upstox import create_upstox_provider

async def main():
    provider = create_upstox_provider('data/upstox_token.json')
    service = DataDownloadService(provider)
    
    try:
        await service.initialize()
        
        # ========================================
        # STEP 1: Download ALL Stock Futures
        # ========================================
        print('=' * 70)
        print('STEP 1: Downloading ALL STOCK FUTURES (Current + Near Month)')
        print('=' * 70)
        
        # Get all F&O instruments to find all unique stock underlyings
        fo_data = await service.get_fo_instruments_from_upstox()
        all_futures = fo_data['futures']
        
        # Get unique stock underlyings (exclude indices like NIFTY, BANKNIFTY)
        index_underlyings = {'NIFTY', 'BANKNIFTY', 'NIFTY50', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX', 'BANKEX'}
        stock_underlyings = set()
        for fut in all_futures:
            underlying = fut.get('underlying_symbol', '')
            if underlying and underlying not in index_underlyings:
                stock_underlyings.add(underlying)
        
        stock_underlyings = sorted(list(stock_underlyings))
        print(f'\nFound {len(stock_underlyings)} stock underlyings with futures')
        print(f'Sample: {stock_underlyings[:10]}...')
        
        # Download ALL stock futures
        futures_results = await service.download_futures_data(
            underlyings=stock_underlyings,
            from_date=date(2025, 6, 1),  # Last 6 months
            to_date=date.today()
        )
        
        print(f'\n--- Stock Futures Download Summary ---')
        print(f'  Total Contracts: {futures_results["total_contracts"]}')
        print(f'  Successful: {futures_results["successful"]}')
        print(f'  Failed: {futures_results["failed"]}')
        print(f'  Total Candles: {futures_results["total_candles"]:,}')
        
        if futures_results.get('errors'):
            print(f'\nFutures Errors (first 10):')
            for err in futures_results['errors'][:10]:
                print(f'  {err}')
        
        # ========================================
        # STEP 2: Download Index Futures
        # ========================================
        print('\n' + '=' * 70)
        print('STEP 2: Downloading INDEX FUTURES (NIFTY, BANKNIFTY, FINNIFTY)')
        print('=' * 70)
        
        index_futures_results = await service.download_futures_data(
            underlyings=['NIFTY', 'BANKNIFTY', 'FINNIFTY'],
            from_date=date(2025, 6, 1),
            to_date=date.today()
        )
        
        print(f'\n--- Index Futures Download Summary ---')
        print(f'  Total Contracts: {index_futures_results["total_contracts"]}')
        print(f'  Successful: {index_futures_results["successful"]}')
        print(f'  Failed: {index_futures_results["failed"]}')
        print(f'  Total Candles: {index_futures_results["total_candles"]:,}')
        
        # ========================================
        # STEP 3: Download Index Options
        # ========================================
        print('\n' + '=' * 70)
        print('STEP 3: Downloading INDEX OPTIONS (All Major Indices)')
        print('=' * 70)
        
        # Download options for all major indices
        index_options_underlyings = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']
        
        for underlying in index_options_underlyings:
            print(f'\n>>> Downloading {underlying} OPTIONS...')
            
            options_results = await service.download_options_data(
                underlyings=[underlying],
                strike_range=15,  # 15 strikes above and below ATM
                from_date=date(2025, 6, 1),
                to_date=date.today()
            )
            
            print(f'  {underlying} Options Summary:')
            print(f'    Contracts: {options_results["total_contracts"]}')
            print(f'    Successful: {options_results["successful"]}')
            print(f'    Candles: {options_results["total_candles"]:,}')
        
        # ========================================
        # FINAL SUMMARY
        # ========================================
        print('\n' + '=' * 70)
        print('DOWNLOAD COMPLETE - SUMMARY')
        print('=' * 70)
        
        # Query total candles in database
        from sqlalchemy import text
        async with service.async_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM candles"))
            total_candles = result.scalar()
            
            result = await session.execute(text("""
                SELECT instrument_type, COUNT(*) as count 
                FROM candles c 
                JOIN instruments i ON c.instrument_id = i.id 
                GROUP BY instrument_type
            """))
            type_counts = {row[0]: row[1] for row in result.fetchall()}
        
        print(f'\nTotal candles in database: {total_candles:,}')
        print(f'\nCandles by instrument type:')
        for itype, count in sorted(type_counts.items()):
            print(f'  {itype}: {count:,}')
                
    finally:
        await service.close()

if __name__ == "__main__":
    asyncio.run(main())
