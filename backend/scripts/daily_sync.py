#!/usr/bin/env python
"""
Daily Data Sync Script

Reads sync_status.json to determine what needs syncing and performs incremental
updates for each segment. Updates the config after each successful sync.

Segments:
- equity: F&O eligible stocks
- indices_nse: NSE indices
- indices_bse: BSE indices (SENSEX, BANKEX)
- fo_current: Current expiry F&O (futures + options together)
- fo_historical: Historical F&O data
- indicators: Technical indicators

Usage:
    python scripts/daily_sync.py                       # Full sync
    python scripts/daily_sync.py --segment equity      # Sync specific segment
    python scripts/daily_sync.py --segment fo_current
    python scripts/daily_sync.py --force              # Force re-sync all
    python scripts/daily_sync.py --dry-run            # Show what would sync
    python scripts/daily_sync.py --status             # Show current status
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

# Add backend root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config paths
CONFIG_FILE = Path(__file__).parent / 'data' / 'sync_status.json'

# Segment definitions - order matters
SEGMENTS = [
    'fo_refresh_instruments',  # Standalone instrument refresh (fo_current also does this automatically)
    'equity',
    'indices_nse',
    'indices_bse',
    'fo_current',       # Daily: refresh instruments from Upstox, then sync data (next 60 days)
    'fo_historical',    # Manual only: heavy historical backfill
    'fo_expired',       # Weekly: sync expired index option expiries
    'indicators'
]

# Segments that run weekly (not daily)
WEEKLY_SEGMENTS = {'fo_refresh_instruments', 'fo_expired', 'fo_historical'}

# Default stale thresholds per segment (hours)
SEGMENT_THRESHOLDS = {
    'fo_refresh_instruments': 24 * 7,  # Weekly
    'equity': 20,
    'indices_nse': 20,
    'indices_bse': 20,
    'fo_current': 20,
    'fo_historical': 24 * 7,           # Weekly
    'fo_expired': 24 * 7,              # Weekly
    'indicators': 20,
}


def load_config() -> Dict[str, Any]:
    """Load sync status config."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"segments": {}, "sync_config": {}, "instruments": {}}


def save_config(config: Dict[str, Any]):
    """Save sync status config."""
    config['last_updated'] = datetime.now().isoformat()
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2, default=str)


def is_stale(segment_config: Dict, threshold_hours: int = 20) -> bool:
    """Check if segment needs sync based on last sync time."""
    last_sync = segment_config.get('last_sync')
    if not last_sync:
        return True
    
    try:
        last_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
        if last_dt.tzinfo:
            last_dt = last_dt.replace(tzinfo=None)
        age = datetime.now() - last_dt
        return age.total_seconds() > threshold_hours * 3600
    except:
        return True


def update_segment_status(
    config: Dict, 
    segment: str, 
    status: str, 
    count: int = 0,
    error: Optional[str] = None
):
    """Update segment status in config."""
    if segment not in config['segments']:
        config['segments'][segment] = {}
    
    config['segments'][segment].update({
        'last_sync': datetime.now().isoformat(),
        'last_sync_date': date.today().isoformat(),
        'status': status,
        'instruments_count': count,
        'error': error
    })
    save_config(config)


async def sync_equity(config: Dict, dry_run: bool = False) -> int:
    """Sync equity candle data."""
    logger.info("=" * 60)
    logger.info("SYNCING: Equity Stocks")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would sync ~200 equity stocks")
        return 200
    
    from scripts.backfill_all_data import run_backfill
    result = await run_backfill('equity')
    count = result.get('stats', {}).get('equity', {}).get('downloaded', 0)
    return count


async def sync_indices_nse(config: Dict, dry_run: bool = False) -> int:
    """Sync NSE indices."""
    logger.info("=" * 60)
    logger.info("SYNCING: NSE Indices")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would sync 15 NSE indices")
        return 15
    
    from scripts.backfill_all_data import run_backfill
    result = await run_backfill('index')
    count = result.get('stats', {}).get('index', {}).get('downloaded', 0)
    return count


async def sync_indices_bse(config: Dict, dry_run: bool = False) -> int:
    """Sync BSE indices (SENSEX, BANKEX)."""
    logger.info("=" * 60)
    logger.info("SYNCING: BSE Indices")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would sync SENSEX and BANKEX")
        return 2
    
    try:
        # Use subprocess to avoid encoding issues
        import subprocess
        result = subprocess.run(
            [sys.executable, 'scripts/temp/download_bse_indices.py'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode == 0:
            return 2
        else:
            logger.error(f"BSE sync failed: {result.stderr[:200]}")
            return 0
    except Exception as e:
        logger.error(f"BSE index sync error: {e}")
        return 0


async def sync_fo_refresh_instruments(config: Dict, dry_run: bool = False) -> int:
    """Refresh F&O instrument master from Upstox (NSE + BSE).
    
    Fetches the latest F&O contracts from Upstox for both NSE and BSE,
    then upserts new instruments into instrument_master. This ensures:
    - New weekly expiries are added as they become available
    - New monthly contracts (next month) are added
    - SENSEX, BANKEX, FINNIFTY, MIDCPNIFTY options are included
    - Stock options for all F&O eligible stocks are included
    
    Runs weekly (not daily) since instrument lists change slowly.
    """
    logger.info("=" * 60)
    logger.info("SYNCING: F&O Instrument Master Refresh (NSE + BSE)")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would fetch F&O instruments from Upstox and import new contracts")
        return 0
    
    import subprocess
    result = subprocess.run(
        [sys.executable, 'scripts/import_upstox_fno.py'],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=600  # 10 min timeout
    )
    
    if result.returncode == 0:
        # Parse count of new instruments from output
        new_count = 0
        for line in result.stdout.splitlines():
            if 'New instruments to insert:' in line:
                try:
                    new_count = int(line.split(':')[1].strip().replace(',', ''))
                except:
                    pass
        logger.info(f"  Instrument refresh complete. New instruments: {new_count}")
        if result.stdout:
            # Log last few lines of output for visibility
            tail = result.stdout.strip().splitlines()[-10:]
            for line in tail:
                logger.info(f"  {line}")
        return new_count
    else:
        logger.error(f"Instrument refresh failed: {result.stderr[:500]}")
        return 0


async def sync_fo_current(config: Dict, dry_run: bool = False) -> int:
    """Sync current expiry F&O (futures + options, next 60 days).
    
    Step 1: Refresh instrument list from Upstox — picks up any new weekly/monthly
            expiries not yet in instrument_master (runs import_upstox_fno.py).
    Step 2: Sync candle data for all instruments with missing or stale data.
    """
    logger.info("=" * 60)
    logger.info("SYNCING: Current Expiry F&O (Futures + Options)")
    logger.info("=" * 60)

    if dry_run:
        logger.info("  [DRY RUN] Would refresh instruments then sync F&O data (next 60 days)")
        return 1500

    # ── Step 1: Refresh instruments from Upstox ──────────────────────────────
    # Ensures new expiries (weekly options that just appeared, next-month
    # contracts etc.) are in instrument_master BEFORE data download starts.
    logger.info("")
    logger.info("  Step 1/2: Refreshing F&O instrument list from Upstox...")
    refresh_result = subprocess.run(
        [sys.executable, 'scripts/import_upstox_fno.py'],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=600
    )
    if refresh_result.returncode == 0:
        new_count = 0
        for line in refresh_result.stdout.splitlines():
            if 'New instruments to insert:' in line:
                try:
                    new_count = int(line.split(':')[1].strip().replace(',', ''))
                except Exception:
                    pass
        logger.info(f"  Instrument refresh complete — new instruments added: {new_count}")
    else:
        logger.warning(
            f"  Instrument refresh had errors (continuing anyway):\n"
            f"  {refresh_result.stderr[:300]}"
        )

    # ── Step 2: Sync candle data ──────────────────────────────────────────────
    logger.info("")
    logger.info("  Step 2/2: Syncing candle data for active F&O instruments (next 60 days)...")
    from scripts.backfill_all_data import run_backfill
    result = await run_backfill('current')
    count = result.get('stats', {}).get('current', {}).get('downloaded', 0)
    return count


async def sync_fo_historical(config: Dict, dry_run: bool = False) -> int:
    """Sync historical F&O data."""
    logger.info("=" * 60)
    logger.info("SYNCING: Historical F&O Data")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would sync historical F&O instruments")
        return 5000
    
    from scripts.backfill_all_data import run_backfill
    result = await run_backfill('historical')
    count = result.get('stats', {}).get('historical', {}).get('downloaded', 0)
    return count


async def sync_indicators(config: Dict, dry_run: bool = False) -> int:
    """Compute technical indicators for all instruments."""
    logger.info("=" * 60)
    logger.info("SYNCING: Technical Indicators")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would compute indicators for all synced instruments")
        return 1000
    
    try:
        import subprocess
        # Run indicator computation pipeline
        result = subprocess.run(
            [sys.executable, 'scripts/pipeline/stage1_compute.py'],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        if result.returncode == 0:
            return 1000
        else:
            logger.error(f"Indicator computation failed: {result.stderr[:500]}")
            return 0
    except subprocess.TimeoutExpired:
        logger.error("Indicator computation timed out after 1 hour")
        return 0
    except Exception as e:
        logger.error(f"Indicator sync error: {e}")
        return 0


async def sync_fo_expired(config: Dict, dry_run: bool = False) -> int:
    """Sync expired F&O options data (NIFTY, BANKNIFTY, SENSEX, BANKEX weekly expiries).
    
    Uses sync_status.json to track which expiries have been synced.
    Only syncs new expiries that haven't been processed yet.
    """
    logger.info("=" * 60)
    logger.info("SYNCING: Expired F&O Options (Historical Weekly Expiries)")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would sync expired F&O options")
        return 10000
    
    from scripts.backfill_expired_data import get_expired_expiries, get_expired_option_contracts, \
        download_expired_candles, save_candles_to_db, ensure_instrument, get_upstox_token
    import asyncpg
    
    token = get_upstox_token()
    if not token:
        logger.error("No Upstox token found")
        return 0
    
    # Indices to sync
    INDICES = [
        ('NIFTY', 'OPTIDX', 'NSE_INDEX|Nifty 50'),
        ('BANKNIFTY', 'OPTIDX', 'NSE_INDEX|Nifty Bank'),
        ('FINNIFTY', 'OPTIDX', 'NSE_INDEX|Nifty Fin Service'),
        ('SENSEX', 'OPTIDX', 'BSE_INDEX|SENSEX'),
        ('BANKEX', 'OPTIDX', 'BSE_INDEX|BANKEX'),
    ]
    
    # Initialize fo_expired tracking in config if not exists
    if 'fo_expired' not in config.get('segments', {}):
        config['segments']['fo_expired'] = {
            'description': 'Expired F&O options (historical weekly expiries)',
            'last_sync': None,
            'status': 'pending',
            # Track the oldest synced expiry per underlying - everything before this is complete
            'oldest_synced_expiry': {},  # {underlying: 'YYYY-MM-DD'}
            'synced_expiries': {}  # Legacy - kept for reference
        }
    
    segment_config = config['segments']['fo_expired']
    oldest_synced = segment_config.get('oldest_synced_expiry', {})
    synced_expiries = segment_config.get('synced_expiries', {})
    
    total_candles = 0
    total_new_expiries = 0
    DB_URL = "postgresql://user:password@localhost:5432/keepgaining"
    
    # First, query database to find expiries we already have data for
    # This prevents re-downloading data that's already in the DB
    logger.info("Checking database for existing expired options data...")
    conn = await asyncpg.connect(DB_URL)
    try:
        # Query option_master for distinct expiry dates per underlying
        existing_data = await conn.fetch('''
            SELECT DISTINCT im.underlying, om.expiry_date::text
            FROM option_master om
            JOIN instrument_master im ON om.instrument_id = im.instrument_id
            WHERE im.underlying IN ('NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX', 'BANKEX')
            AND om.expiry_date < CURRENT_DATE
        ''')
        
        for row in existing_data:
            underlying = row['underlying']
            expiry_str = row['expiry_date']
            if underlying not in synced_expiries:
                synced_expiries[underlying] = []
            if expiry_str not in synced_expiries[underlying]:
                synced_expiries[underlying].append(expiry_str)
        
        # Save the discovered expiries
        segment_config['synced_expiries'] = synced_expiries
        save_config(config)
        
        total_existing = sum(len(v) for v in synced_expiries.values())
        logger.info(f"    Found {total_existing} expiries already in database")
    finally:
        await conn.close()
    
    for underlying, inst_type, underlying_key in INDICES:
        logger.info(f"\n>>> Processing {underlying}...")
        
        # Get available expiries from Upstox
        all_expiries = await get_expired_expiries(token, inst_type, underlying_key)
        logger.info(f"    Available: {len(all_expiries)} expiries")
        
        # Get already synced expiries for this underlying (now includes DB data)
        already_synced = set(synced_expiries.get(underlying, []))
        logger.info(f"    Already synced: {len(already_synced)} expiries")
        
        # Find new expiries to sync
        new_expiries = [e for e in all_expiries if e not in already_synced]
        logger.info(f"    New to sync: {len(new_expiries)} expiries")
        
        if not new_expiries:
            logger.info(f"    [SKIP] All expiries already synced for {underlying}")
            continue
        
        # Sort OLDEST FIRST - this ensures contiguous sync from past to present
        # Once an expiry is synced, we can set oldest_synced_expiry and know
        # everything before that date is complete
        new_expiries = sorted(new_expiries, reverse=False)  # Oldest first
        
        for expiry in new_expiries:
            logger.info(f"\n    Syncing {underlying} expiry {expiry}...")
            
            contracts = await get_expired_option_contracts(token, expiry, underlying_key, inst_type)
            if not contracts:
                logger.warning(f"    No contracts found for {expiry}")
                # Still mark as synced (no data available)
                if underlying not in synced_expiries:
                    synced_expiries[underlying] = []
                synced_expiries[underlying].append(expiry)
                continue
            
            expiry_candles = 0
            conn = await asyncpg.connect(DB_URL)
            try:
                for i, contract in enumerate(contracts):
                    inst_id = await ensure_instrument(conn, contract, underlying)
                    if not inst_id:
                        continue
                    
                    # Calculate date range: 7 days before expiry to expiry
                    from datetime import datetime, timedelta
                    expiry_dt = datetime.strptime(expiry, '%Y-%m-%d').date()
                    from_date = expiry_dt - timedelta(days=7)
                    to_date = expiry_dt
                    
                    candles = await download_expired_candles(
                        token, contract.get('instrument_key'), from_date, to_date
                    )
                    if candles:
                        count = await save_candles_to_db(conn, inst_id, candles)
                        expiry_candles += count
                    
                    # Progress indicator every 50 contracts
                    if (i + 1) % 50 == 0:
                        logger.info(f"      [{i+1}/{len(contracts)}] contracts processed...")
            finally:
                await conn.close()
            
            total_candles += expiry_candles
            total_new_expiries += 1
            
            # Mark expiry as synced (legacy list)
            if underlying not in synced_expiries:
                synced_expiries[underlying] = []
            synced_expiries[underlying].append(expiry)
            
            # Update oldest_synced_expiry - since we process oldest first,
            # this is the contiguous sync boundary. Everything before this date is complete.
            oldest_synced[underlying] = expiry
            
            logger.info(f"    Completed {underlying} {expiry}: {expiry_candles:,} candles")
            logger.info(f"    >> Synced through: {expiry} (contiguous)")
            
            # Save config after each expiry to persist progress immediately
            segment_config['synced_expiries'] = synced_expiries
            segment_config['oldest_synced_expiry'] = oldest_synced
            segment_config['last_sync'] = datetime.now().isoformat()
            save_config(config)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Total: {total_new_expiries} new expiries synced, {total_candles:,} candles")
    return total_candles


# Segment sync function mapping
SYNC_FUNCTIONS = {
    'fo_refresh_instruments': sync_fo_refresh_instruments,
    'equity': sync_equity,
    'indices_nse': sync_indices_nse,
    'indices_bse': sync_indices_bse,
    'fo_current': sync_fo_current,
    'fo_historical': sync_fo_historical,
    'fo_expired': sync_fo_expired,
    'indicators': sync_indicators,
}


async def run_sync(
    segments: Optional[List[str]] = None,
    force: bool = False,
    dry_run: bool = False
):
    """Run sync for specified segments."""
    
    config = load_config()
    threshold = config.get('sync_config', {}).get('stale_threshold_hours', 20)
    
    if segments is None:
        segments = SEGMENTS
    
    logger.info("=" * 60)
    logger.info("DAILY DATA SYNC")
    logger.info("=" * 60)
    logger.info(f"Segments: {segments}")
    logger.info(f"Force: {force}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info(f"Stale threshold: {threshold} hours")
    logger.info("")
    
    results = {}
    
    for segment in segments:
        if segment not in SYNC_FUNCTIONS:
            logger.warning(f"Unknown segment: {segment}")
            continue
        
        seg_config = config.get('segments', {}).get(segment, {})
        
        # Use per-segment threshold, falling back to global config
        threshold = SEGMENT_THRESHOLDS.get(segment, config.get('sync_config', {}).get('stale_threshold_hours', 20))
        
        # Check if sync is needed
        needs_sync = force or is_stale(seg_config, threshold)
        
        if not needs_sync:
            last_sync = seg_config.get('last_sync_date', 'never')
            logger.info(f"SKIP: {segment} (last sync: {last_sync})")
            results[segment] = {'status': 'skipped', 'reason': 'not stale'}
            continue
        
        try:
            sync_func = SYNC_FUNCTIONS[segment]
            count = await sync_func(config, dry_run)
            
            if not dry_run:
                update_segment_status(config, segment, 'complete', count)
            
            results[segment] = {'status': 'success', 'count': count}
            logger.info(f"SUCCESS: {segment} - {count} instruments")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"FAILED: {segment} - {error_msg}")
            
            if not dry_run:
                update_segment_status(config, segment, 'failed', 0, error_msg)
            
            results[segment] = {'status': 'failed', 'error': error_msg}
    
    # Print summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("SYNC SUMMARY")
    logger.info("=" * 60)
    
    for segment, result in results.items():
        status = result['status']
        if status == 'success':
            logger.info(f"  [OK] {segment}: {result['count']} instruments")
        elif status == 'skipped':
            logger.info(f"  [--] {segment}: skipped ({result['reason']})")
        else:
            logger.info(f"  [XX] {segment}: {result.get('error', 'unknown error')}")
    
    return results


def show_status():
    """Display current sync status."""
    config = load_config()
    
    print("\n" + "=" * 70)
    print("CURRENT SYNC STATUS")
    print("=" * 70)
    print(f"{'Segment':<20} {'Status':<12} {'Last Sync':<12} {'Count':>10}")
    print("-" * 70)
    
    for seg in SEGMENTS:
        info = config.get('segments', {}).get(seg, {})
        status = info.get('status', 'pending')
        last_sync = info.get('last_sync_date', '-')
        count = info.get('instruments_count', 0)
        
        # Status indicators
        if status == 'complete':
            status_icon = '[OK]'
        elif status == 'failed':
            status_icon = '[XX]'
        else:
            status_icon = '[--]'
        
        print(f"  {seg:<18} {status_icon} {status:<8} {str(last_sync):<12} {count:>10}")
    
    print("-" * 70)
    print(f"Last updated: {config.get('last_updated', 'never')}")
    print()


def main():
    parser = argparse.ArgumentParser(description='Daily Data Sync')
    parser.add_argument(
        '--segment', '-s',
        choices=SEGMENTS,
        action='append',
        help='Specific segment(s) to sync (can specify multiple)'
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force sync even if not stale'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be synced without actually syncing'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show current sync status and exit'
    )
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    segments = args.segment if args.segment else None
    
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(run_sync(segments, args.force, args.dry_run))


if __name__ == '__main__':
    main()
