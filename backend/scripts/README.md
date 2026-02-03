# Backend Scripts Directory

## 📂 Active Scripts (Production/Development Use)

### Data Management
- **`backfill_all_data.py`** - Comprehensive data backfill for all instruments
- **`data_cli.py`** - Command-line interface for data operations
- **`populate_master_tables.py`** - Initialize master reference tables
- **`refresh_indicators.py`** - Refresh computed technical indicators
- **`refresh_and_verify.py`** - Refresh data with verification
- **`indicators_optimized.py`** - Optimized indicator computation (production)

### Trading & Strategy
- **`trading_cli.py`** - Command-line trading interface
- **`test_paper_trading.py`** - Paper trading simulation
- **`multi_strategy_backtest.py`** - Multi-strategy backtesting framework
- **`run_full_fo_backtest.py`** - Full F&O backtest execution
- **`sanity_backtest.py`** - Quick sanity check backtest

### Strategy-Specific Backtests
- **`backtest_ema_scalping.py`** - EMA-based scalping strategy
- **`backtest_intraday_momentum.py`** - Intraday momentum strategy
- **`backtest_sector_momentum.py`** - Sector momentum strategy

### Analysis Scripts
- **`analyze_ce_trades.py`** - Call option trades analysis
- **`analyze_pe_exits.py`** - Put option exit analysis
- **`analyze_pe_volatility.py`** - Put option volatility analysis

### Exit Strategy Testing
- **`test_ce_exit_strategies.py`** - Test call option exit strategies
- **`test_pe_exit_strategies.py`** - Test put option exit strategies
- **`test_csv_gen.py`** - CSV generation testing

### Database & Optimization
- **`optimize_indexes.py`** - Database index optimization
- **`init_db.sql`** - Database initialization SQL

### Utilities
- **`run_daily_refresh.bat`** - Daily data refresh automation (Windows)
- **`setup_scheduler.ps1`** - Windows Task Scheduler setup
- **`UPSTOX_API_REFERENCE.md`** - Upstox API documentation

---

## 📁 Subdirectories

### `analysis/`
Advanced analysis scripts for trade patterns and signals

### `utils/`
Utility functions and helper scripts

### `tests/`
Test scripts and test data

### `temp/`
Temporary files and work-in-progress scripts

---

## 🗄️ Archive Directories

### `archive/`
Legacy backtest and download scripts that used SQLite
- Old backfill scripts
- Historical download scripts  
- Superseded backtest implementations

### `archive_old_versions/`
Old versions and deprecated scripts:

#### Deprecated Indicator Computation (superseded by `indicators_optimized.py`)
- `compute_indicators.py` (v1)
- `compute_indicators_v2.py` through `compute_indicators_v6.py`
- `compute_indicators_batch.py`
- `compute_indicators_final.py`
- `compute_indicators_mega.py`
- `compute_indicators_sql.py`

#### Debug & Check Scripts (development phase, no longer needed)
- `check_*.py` - Database schema and data validation scripts
- `debug_*.py` - Debugging utilities for API and data issues
- `profile_*.py` - Performance profiling scripts

#### Old Test Scripts
- `test_insert*.py` - Database insert performance tests
- `test_key_resolution.py` - Key resolution testing
- `test_query_perf.py` - Query performance testing
- `test_record_build.py` - Record building tests
- `test_api_download.py` - API download testing

#### Old Analysis Scripts
- `analyze_data.py` - Basic data analysis (superseded by `analysis/` dir)
- `analyze_data_gaps.py` - Data gap analysis
- `analyze_historical.py` - Historical data analysis
- `analyze_indexes.py` - Index analysis

#### Old Download Scripts
- `download_all_data.py` - Old download implementation
- `download_corrected_symbols.py` - Symbol correction downloads
- `download_historical_fo.py` - Historical F&O downloads

#### Utility/Exploration Scripts
- `verify_*.py` - Data verification scripts
- `explore_fo_instruments.py` - F&O instrument exploration
- `find_stocks.py` - Stock finding utilities
- `search_tata_zomato.py` - Specific symbol search
- `fix_missing_equities.py` - Equity data fixes

---

## 📝 Usage Guidelines

### Running Active Scripts

```bash
# Data refresh
python refresh_indicators.py

# Backtest a strategy
python backtest_ema_scalping.py

# Multi-strategy backtest
python multi_strategy_backtest.py

# Paper trading
python test_paper_trading.py

# Trading CLI
python trading_cli.py
```

### Common Patterns

**All scripts expect to be run from backend/ directory:**
```bash
cd backend
python scripts/script_name.py
```

**Most scripts use PostgreSQL database:**
- Configured via `.env` file
- `DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/keepgaining`

**Some scripts still use SQLite** (legacy compatibility):
- Check script header for database requirements
- SQLite scripts primarily in `archive/` directories

---

## 🔧 Maintenance

### When Adding New Scripts

1. **Add to appropriate section** in this README
2. **Follow naming convention:**
   - `backtest_*.py` for backtest scripts
   - `analyze_*.py` for analysis scripts
   - `test_*.py` for test scripts
   - Clear, descriptive names

3. **Include header docstring:**
   ```python
   """
   Script Name
   
   Description: What this script does
   Usage: python scripts/script_name.py
   Database: PostgreSQL / SQLite
   """
   ```

### When Deprecating Scripts

1. **Move to `archive_old_versions/`**
2. **Update this README** to reflect removal
3. **Note replacement** if applicable

---

## 🚨 Database Compatibility

| Script Type | Database | Notes |
|------------|----------|-------|
| **Active Production** | PostgreSQL | All new scripts use PostgreSQL |
| **Legacy (archive/)** | SQLite | Old scripts, kept for reference |
| **Backtest Engine** | Both | `app/backtest/` supports both |
| **Analysis Scripts** | Both | Some analysis uses SQLite for performance |

---

## 📊 Script Organization by Function

### Data Pipeline
```
populate_master_tables.py
    ↓
backfill_all_data.py
    ↓
indicators_optimized.py / refresh_indicators.py
    ↓
(Data ready for backtesting/trading)
```

### Backtest Pipeline
```
multi_strategy_backtest.py
    ├── backtest_ema_scalping.py
    ├── backtest_intraday_momentum.py
    └── backtest_sector_momentum.py
         ↓
analyze_ce_trades.py / analyze_pe_exits.py
         ↓
test_ce_exit_strategies.py / test_pe_exit_strategies.py
```

### Trading Pipeline
```
trading_cli.py
    ├── test_paper_trading.py (testing)
    └── (Live trading - future)
```

---

**Last Updated:** December 6, 2025  
**Active Scripts:** 26  
**Archived Scripts:** 50+  
**Database:** PostgreSQL (primary), SQLite (legacy)
