# Archive Directory

This directory contains legacy files and unused code that have been archived for historical reference.

## Archived on: December 6, 2025

### 📦 Contents

#### Legacy Database & Setup Scripts
- **`keepgaining.db.backup`** (14GB) - Old SQLite database file
  - **Reason:** System now uses PostgreSQL (as per HIGH_LEVEL_DESIGN.md)
  - **Status:** Backup only, not in active use
  
- **`create_tables.py`** - SQLite table creation script
  - **Reason:** Using Alembic migrations with PostgreSQL now
  - **Replaced by:** `alembic/versions/*.py` migration files
  
- **`add_broker.py`** - SQLite broker configuration script
  - **Reason:** Broker config now managed via environment variables and database
  - **Replaced by:** `app/brokers/` integration and `.env` configuration

- **`exchange_code.py`** - Legacy exchange code utilities
  - **Reason:** Functionality integrated into broker adapters
  - **Location now:** `app/brokers/base.py` and broker-specific implementations

#### Legacy Test Files
- **`test_upstox.py`** - Upstox integration test
  - **Reason:** Moved to proper test structure
  - **Location now:** `tests/` directory with pytest structure

#### Third-Party Source Code
- **`upstox-python-master/`** - Downloaded Upstox Python SDK
  - **Reason:** Using official pip package instead
  - **Replaced by:** Official package in `requirements.txt`

#### Old Log Files
- **`backfill.log`** - Historical data backfill logs
- **`download_fo.log`** - F&O data download logs  
- **`fyersApi.log`** - Fyers API interaction logs
- **`fyersRequests.log`** - Fyers request logs
  - **Reason:** Old logs from development/testing
  - **Current logs:** `logs/app.json` (structured JSON logging via loguru)

#### Symbol Master Files
- **`fyers_symbol_master.csv`** - Old symbol master
- **`fyers_symbol_master_dec.csv`** - December symbol master
  - **Reason:** Symbol data now managed via API calls and database
  - **Current approach:** Real-time symbol lookup via broker APIs

#### Old Backtest Results
- **`historical_backtest_results.csv`** - Historical backtest data
- **`volume_rocket_entry_09_16_plus.csv`** - Volume Rocket strategy results
- **`volume_rocket_fixed_entry.csv`** - Fixed entry backtest
- **`volume_rocket_options.csv`** - Options backtest results  
- **`volume_rocket_results.csv`** - General results
  - **Reason:** Old backtest data, superseded by new runs
  - **Current location:** `backtest_results/` directory

---

## ⚠️ Important Notes

### Can These Files Be Deleted?

**Yes**, but consider:

1. **`keepgaining.db.backup`** (14GB) - Contains historical data
   - If you have PostgreSQL populated with data, safe to delete
   - If not migrated yet, consider exporting data first

2. **Scripts** - Safe to delete unless you need reference for migration
   
3. **Logs** - Safe to delete, purely historical

4. **CSV files** - Safe to delete if results documented elsewhere

### Restoring From Archive

If you need any of these files:
```bash
# Example: Restore a file
cp archive/filename.ext .
```

### Migration Notes

**Database Migration:**
- Old: SQLite (`keepgaining.db`)
- New: PostgreSQL (`postgresql+asyncpg://user:password@localhost:5432/keepgaining`)
- Migration tool: Alembic

**Logging Migration:**
- Old: Individual `.log` files
- New: Structured JSON logs in `logs/app.json` via loguru

**Configuration Migration:**
- Old: Hardcoded scripts with `DATABASE_URL = "sqlite:///..."`
- New: Environment variables via `.env` and Pydantic settings

---

## 🗂️ Current Active Structure

For reference, the current active structure is:

```
backend/
├── app/                    # Main application code
│   ├── api/               # FastAPI routes
│   ├── brokers/           # Broker integrations
│   ├── comet/             # Comet AI integration
│   ├── core/              # Configuration
│   ├── db/                # Database models & session
│   ├── schemas/           # Pydantic schemas
│   ├── services/          # Business logic
│   └── strategies/        # Trading strategies
├── alembic/               # Database migrations
├── config/                # Configuration files
├── data/                  # Runtime data
├── logs/                  # Application logs
├── notebooks/             # Jupyter analysis notebooks
├── prompts/               # Comet AI prompt templates
├── scripts/               # Utility scripts
├── tests/                 # Test suite
└── archive/               # This directory (archived files)
```

---

**Archive Date:** December 6, 2025  
**Archived By:** System Cleanup  
**Reason:** Transitioning to production-ready PostgreSQL architecture per HIGH_LEVEL_DESIGN.md
