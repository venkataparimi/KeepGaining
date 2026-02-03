#!/usr/bin/env python3
"""
Data Management CLI

Unified command-line interface for data download and status operations.
All data operations should go through this CLI which uses the DataDownloadService.

Usage:
    python scripts/data_cli.py status          # Show data coverage report
    python scripts/data_cli.py download-equity # Download equity historical data
    python scripts/data_cli.py download-fo     # Download F&O historical data
    python scripts/data_cli.py download-all    # Download all data
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta

# Ensure we're in the backend directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from app.services.data_download_service import DataDownloadService
from app.services.data_providers.upstox import create_upstox_provider


async def show_status():
    """Show comprehensive data coverage report."""
    provider = create_upstox_provider('data/upstox_token.json')
    service = DataDownloadService(provider)
    
    try:
        await service.initialize()
        report = await service.get_data_coverage_report()
        service.print_data_coverage_report(report)
    finally:
        await service.close()


async def download_equity(from_date: date, to_date: date):
    """Download equity historical data."""
    provider = create_upstox_provider('data/upstox_token.json')
    service = DataDownloadService(provider)
    
    try:
        await service.initialize()
        
        print(f"Downloading equity data from {from_date} to {to_date}...")
        results = await service.download_historical_data(
            from_date=from_date,
            to_date=to_date
        )
        
        print(f"\n--- Equity Download Summary ---")
        print(f"  Successful: {results['successful']}/{results['total_symbols']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Total Candles: {results['total_candles']:,}")
        
        if results.get('errors'):
            print(f"\nErrors (first 10):")
            for err in results['errors'][:10]:
                print(f"  {err.get('symbol', 'N/A')}: {err.get('error', 'Unknown')}")
        
    finally:
        await service.close()


async def download_fo(months_back: int = 6):
    """Download historical expired F&O data."""
    provider = create_upstox_provider('data/upstox_token.json')
    service = DataDownloadService(provider)
    
    index_underlyings = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']
    
    try:
        await service.initialize()
        
        # Step 1: Download Futures
        print("=" * 70)
        print(f"STEP 1: Downloading HISTORICAL EXPIRED FUTURES ({months_back} months)")
        print("=" * 70)
        
        futures_results = await service.download_historical_expired_futures(
            underlyings=index_underlyings,
            months_back=months_back
        )
        
        print(f"\n--- Expired Futures Summary ---")
        print(f"  Total Expiries: {futures_results.get('total_expiries', 0)}")
        print(f"  Total Contracts: {futures_results.get('total_contracts', 0)}")
        print(f"  Successful: {futures_results.get('successful', 0)}")
        print(f"  Failed: {futures_results.get('failed', 0)}")
        print(f"  Total Candles: {futures_results.get('total_candles', 0):,}")
        
        # Step 2: Download Options
        print("\n" + "=" * 70)
        print(f"STEP 2: Downloading HISTORICAL EXPIRED OPTIONS ({months_back} months)")
        print("=" * 70)
        
        options_results = await service.download_historical_expired_options(
            underlyings=index_underlyings,
            months_back=months_back
        )
        
        print(f"\n--- Expired Options Summary ---")
        print(f"  Total Expiries: {options_results.get('total_expiries', 0)}")
        print(f"  Total Contracts: {options_results.get('total_contracts', 0)}")
        print(f"  Successful: {options_results.get('successful', 0)}")
        print(f"  Failed: {options_results.get('failed', 0)}")
        print(f"  Total Candles: {options_results.get('total_candles', 0):,}")
        
        # Final Summary
        print("\n" + "=" * 70)
        print("F&O DOWNLOAD COMPLETE")
        print("=" * 70)
        
        total_contracts = futures_results.get('total_contracts', 0) + options_results.get('total_contracts', 0)
        total_candles = futures_results.get('total_candles', 0) + options_results.get('total_candles', 0)
        
        print(f"\nThis session:")
        print(f"  Total Contracts: {total_contracts:,}")
        print(f"  Total Candles: {total_candles:,}")
        
    finally:
        await service.close()


async def download_stock_fo(months_back: int = 6, stock_list: list = None, skip_futures: bool = False, skip_options: bool = False, start_from: int = 0):
    """
    Download HISTORICAL EXPIRED stock F&O data (futures and options).
    
    Uses the Expired Instruments API with correct underlying_key format (NSE_EQ|ISIN).
    
    Args:
        months_back: Number of months of historical data
        stock_list: Optional list of specific stocks
        skip_futures: Skip futures download (useful if rate limited)
        skip_options: Skip options download
        start_from: Start from this stock index (0-based, for resuming)
    """
    provider = create_upstox_provider('data/upstox_token.json')
    service = DataDownloadService(provider)
    
    try:
        await service.initialize()
        
        # Get F&O stocks if not specified
        if stock_list is None:
            fo_data = await service.get_fo_instruments_from_upstox()
            # Get unique stock underlyings (exclude indices)
            stock_underlyings = set()
            for f in fo_data.get('futures', []):
                if f.get('underlying_type') == 'EQUITY':
                    stock_underlyings.add(f.get('underlying_symbol'))
            stock_list = sorted(list(stock_underlyings))
        
        # Apply start_from offset
        if start_from > 0:
            print(f"Resuming from stock index {start_from} ({stock_list[start_from] if start_from < len(stock_list) else 'N/A'})")
            stock_list = stock_list[start_from:]
        
        print("=" * 70)
        print(f"DOWNLOADING STOCK F&O DATA (Historical Expired Contracts)")
        print(f"Stocks: {len(stock_list)}, Months back: {months_back}")
        if skip_futures:
            print(">>> SKIPPING FUTURES (--skip-futures)")
        if skip_options:
            print(">>> SKIPPING OPTIONS (--skip-options)")
        print("=" * 70)
        
        futures_results = {'total_expiries': 0, 'total_contracts': 0, 'successful': 0, 'failed': 0, 'total_candles': 0}
        options_results = {'total_expiries': 0, 'total_contracts': 0, 'successful': 0, 'failed': 0, 'total_candles': 0}
        
        # Step 1: Download Stock EXPIRED Futures
        if not skip_futures:
            print("\n" + "=" * 70)
            print(f"STEP 1: Downloading HISTORICAL EXPIRED Stock Futures ({months_back} months)")
            print("=" * 70)
            
            futures_results = await service.download_historical_expired_futures(
                underlyings=stock_list,
                months_back=months_back
            )
            
            print(f"\n--- Expired Stock Futures Summary ---")
            print(f"  Expiries: {futures_results.get('total_expiries', 0)}")
            print(f"  Contracts: {futures_results.get('total_contracts', 0)}")
            print(f"  Successful: {futures_results.get('successful', 0)}")
            print(f"  Failed: {futures_results.get('failed', 0)}")
            print(f"  Total Candles: {futures_results.get('total_candles', 0):,}")
        else:
            print("\n>>> Skipping futures download")
        
        # Step 2: Download Stock EXPIRED Options
        if not skip_options:
            print("\n" + "=" * 70)
            print(f"STEP 2: Downloading HISTORICAL EXPIRED Stock Options ({months_back} months)")
            print("NOTE: Stock options data is massive, this will take a long time!")
            print("=" * 70)
            
            options_results = await service.download_historical_expired_options(
                underlyings=stock_list,
                months_back=months_back
            )
            
            print(f"\n--- Expired Stock Options Summary ---")
            print(f"  Expiries: {options_results.get('total_expiries', 0)}")
            print(f"  Contracts: {options_results.get('total_contracts', 0)}")
            print(f"  Successful: {options_results.get('successful', 0)}")
            print(f"  Failed: {options_results.get('failed', 0)}")
            print(f"  Total Candles: {options_results.get('total_candles', 0):,}")
        else:
            print("\n>>> Skipping options download")
        
        # Final Summary
        print("\n" + "=" * 70)
        print("STOCK F&O DOWNLOAD COMPLETE")
        print("=" * 70)
        
        total_contracts = futures_results.get('total_contracts', 0) + options_results.get('total_contracts', 0)
        total_candles = futures_results.get('total_candles', 0) + options_results.get('total_candles', 0)
        
        print(f"\nThis session:")
        print(f"  Total Contracts: {total_contracts:,}")
        print(f"  Total Candles: {total_candles:,}")
        
    finally:
        await service.close()


async def download_all(from_date: date, to_date: date, fo_months: int = 6):
    """Download all data - equity and F&O."""
    print("=" * 70)
    print("DOWNLOADING ALL DATA")
    print("=" * 70)
    
    # Download equity first
    print("\n>>> EQUITY DATA <<<")
    await download_equity(from_date, to_date)
    
    # Then download F&O
    print("\n>>> F&O DATA <<<")
    await download_fo(fo_months)
    
    # Show final status
    print("\n>>> FINAL STATUS <<<")
    await show_status()


def main():
    parser = argparse.ArgumentParser(
        description="Data Management CLI for KeepGaining",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/data_cli.py status
    python scripts/data_cli.py download-equity --from-date 2022-01-01
    python scripts/data_cli.py download-fo --months 6           # Index F&O (expired historical)
    python scripts/data_cli.py download-stock-fo --months 6     # Stock F&O (expired historical)
    python scripts/data_cli.py download-all --from-date 2022-01-01 --months 6
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Status command
    subparsers.add_parser("status", help="Show data coverage report")
    
    # Download equity command
    equity_parser = subparsers.add_parser("download-equity", help="Download equity historical data")
    equity_parser.add_argument("--from-date", type=str, default="2022-01-01",
                               help="Start date (YYYY-MM-DD)")
    equity_parser.add_argument("--to-date", type=str, default=None,
                               help="End date (YYYY-MM-DD), defaults to today")
    
    # Download F&O command (expired index options/futures)
    fo_parser = subparsers.add_parser("download-fo", help="Download expired F&O historical data (indices)")
    fo_parser.add_argument("--months", type=int, default=6,
                           help="Months of historical expired data to download")
    
    # Download Stock F&O command (expired stock options/futures)
    stock_fo_parser = subparsers.add_parser("download-stock-fo", help="Download stock F&O expired historical data")
    stock_fo_parser.add_argument("--months", type=int, default=6,
                                  help="Months of historical expired data to download")
    stock_fo_parser.add_argument("--skip-futures", action="store_true",
                                  help="Skip futures download (useful if rate limited)")
    stock_fo_parser.add_argument("--skip-options", action="store_true",
                                  help="Skip options download")
    stock_fo_parser.add_argument("--start-from", type=int, default=0,
                                  help="Start from this stock index (0-based, for resuming)")
    
    # Download all command
    all_parser = subparsers.add_parser("download-all", help="Download all data")
    all_parser.add_argument("--from-date", type=str, default="2022-01-01",
                            help="Start date for equity (YYYY-MM-DD)")
    all_parser.add_argument("--to-date", type=str, default=None,
                            help="End date for equity (YYYY-MM-DD)")
    all_parser.add_argument("--months", type=int, default=6,
                            help="Months of F&O historical data")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "status":
        asyncio.run(show_status())
    
    elif args.command == "download-equity":
        from_date = date.fromisoformat(args.from_date)
        to_date = date.fromisoformat(args.to_date) if args.to_date else date.today()
        asyncio.run(download_equity(from_date, to_date))
    
    elif args.command == "download-fo":
        asyncio.run(download_fo(args.months))
    
    elif args.command == "download-stock-fo":
        asyncio.run(download_stock_fo(
            months_back=args.months,
            skip_futures=args.skip_futures,
            skip_options=args.skip_options,
            start_from=args.start_from
        ))
    
    elif args.command == "download-all":
        from_date = date.fromisoformat(args.from_date)
        to_date = date.fromisoformat(args.to_date) if args.to_date else date.today()
        asyncio.run(download_all(from_date, to_date, args.months))


if __name__ == "__main__":
    main()
