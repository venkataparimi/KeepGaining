"""
Batch backfill all historical expired options data for major indices.
Run this in background - it will take several hours.
"""
import asyncio
import subprocess
import sys
from datetime import datetime

# All indices to backfill
INDICES = [
    ('NIFTY', 'OPTIDX'),
    ('BANKNIFTY', 'OPTIDX'),
    ('FINNIFTY', 'OPTIDX'),
    ('SENSEX', 'OPTIDX'),
    ('BANKEX', 'OPTIDX'),
]

async def get_expiries(underlying: str, inst_type: str) -> list:
    """Get all available expiries for an underlying."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'scripts/backfill_expired_data.py',
        '--list-expiries', '--type', inst_type, '--underlying', underlying,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd='.'
    )
    stdout, _ = await proc.communicate()
    
    # Parse expiries from output
    expiries = []
    for line in stdout.decode().split('\n'):
        line = line.strip()
        if line and line[0].isdigit() and '-' in line:
            expiries.append(line)
    return expiries

async def backfill_expiry(underlying: str, inst_type: str, expiry: str) -> dict:
    """Backfill a single expiry."""
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting {underlying} {expiry}")
    print('='*60)
    
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'scripts/backfill_expired_data.py',
        '--expiry', expiry, '--underlying', underlying, '--type', inst_type,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd='.'
    )
    
    # Stream output
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        print(line.decode().rstrip())
    
    await proc.wait()
    return {'underlying': underlying, 'expiry': expiry, 'success': proc.returncode == 0}

async def main():
    print(f"Starting batch backfill at {datetime.now()}")
    print("="*60)
    
    results = []
    
    for underlying, inst_type in INDICES:
        print(f"\n>>> Getting expiries for {underlying}...")
        expiries = await get_expiries(underlying, inst_type)
        print(f"    Found {len(expiries)} expiries")
        
        for expiry in expiries:
            result = await backfill_expiry(underlying, inst_type, expiry)
            results.append(result)
    
    # Summary
    print("\n" + "="*60)
    print("BATCH BACKFILL COMPLETE")
    print("="*60)
    successful = sum(1 for r in results if r['success'])
    print(f"Total: {len(results)} expiries processed")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")

if __name__ == '__main__':
    asyncio.run(main())
