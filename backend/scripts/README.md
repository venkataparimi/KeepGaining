# Instrument Management Tool

This directory contains `manage_instruments.py`, a unified CLI tool for inspecting, verifying, and repairing instrument data (Stocks, Futures, Options) in the KeepGaining system.

## Usage

Run the script from the project root:
```bash
python backend/scripts/manage_instruments.py <command> [options]
```

## Commands

### 1. `inspect-upstox`
Downloads the latest `complete.json.gz` from Upstox (active contracts) and allows filtering.
Useful for checking if a symbol exists in the source feed.

```bash
# Check for Adani Options expiring in Dec 2026
python backend/scripts/manage_instruments.py inspect-upstox --query ADANIENT --type CE --expiry 12-2026

# Check for NIFTY Futures
python backend/scripts/manage_instruments.py inspect-upstox --query NIFTY --type FUT
```

### 2. `inspect-db`
Queries the local `InstrumentMaster` table.
Useful for verifying what data has been synced to the database.

```bash
# Find all NIFTY Futures
python backend/scripts/manage_instruments.py inspect-db --symbol NIFTY --type FUTURE --details

# Find Adani Options
python backend/scripts/manage_instruments.py inspect-db --symbol ADANIENT --type OPTION --limit 5
```

### 3. `verify-api`
Hits the running backend API (`http://localhost:8001`) to ensure endpoints are responsive and return valid data.
Checks `/symbols`, `/expiries`, `/option-chain`, and `/futures-contract`.

```bash
python backend/scripts/manage_instruments.py verify-api
```

### 4. `repair-futures`
Scans for `FutureMaster` records that are missing a link to their `Underlying` instrument (e.g., `NIFTY` Future not linked to `NIFTY 50` Index).
Attempts to fix these links automatically.

```bash
# Dry run to see what would be fixed
python backend/scripts/manage_instruments.py repair-futures --dry-run

# Apply fixes
python backend/scripts/manage_instruments.py repair-futures
```
