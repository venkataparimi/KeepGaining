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

# Segment definitions
SEGMENTS = [
    'equity',
    'indices_nse', 
    'indices_bse',
    'fo_current',
    'fo_historical',
    'indicators'
]


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


async def sync_fo_current(config: Dict, dry_run: bool = False) -> int:
    """Sync current expiry F&O (futures + options)."""
    logger.info("=" * 60)
    logger.info("SYNCING: Current Expiry F&O (Futures + Options)")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("  [DRY RUN] Would sync ~1500 current F&O instruments")
        return 1500
    
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


# Segment sync function mapping
SYNC_FUNCTIONS = {
    'equity': sync_equity,
    'indices_nse': sync_indices_nse,
    'indices_bse': sync_indices_bse,
    'fo_current': sync_fo_current,
    'fo_historical': sync_fo_historical,
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
