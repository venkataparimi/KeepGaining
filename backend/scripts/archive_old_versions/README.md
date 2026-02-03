# Archived Scripts - Old Versions

This directory contains deprecated scripts and old versions that have been superseded by newer implementations. All files are preserved for reference and historical context.

---

## 📂 Contents by Category

### Indicator Computation Scripts (Deprecated)
**Superseded by:** `indicators_optimized.py` (parent directory)

| File | Purpose | Notes |
|------|---------|-------|
| `compute_indicators.py` | Original indicator computation | SQLite-based, single-threaded |
| `compute_indicators_v2.py` | Second iteration | Added caching |
| `compute_indicators_v3.py` | Third iteration | Batch processing |
| `compute_indicators_v4.py` | Fourth iteration | Optimized queries |
| `compute_indicators_v5.py` | Fifth iteration | Parallel processing |
| `compute_indicators_v6.py` | Sixth iteration | Memory optimization |
| `compute_indicators_batch.py` | Batch variant | Alternative batch approach |
| `compute_indicators_final.py` | "Final" version | Superseded by optimized |
| `compute_indicators_mega.py` | Large dataset variant | Memory issues at scale |
| `compute_indicators_sql.py` | SQL-heavy variant | Poor performance |

**Migration Path:** All indicator computation now uses `indicators_optimized.py` with PostgreSQL and asyncio.

---

### Debug Scripts (Development Phase)
**Purpose:** Debugging during development phase

| File | Purpose | Notes |
|------|---------|-------|
| `debug_api.py` | API connection debugging | Used during broker integration |
| `debug_cache.py` | Cache debugging | Redis connection issues |
| `debug_candles.py` | Candle data debugging | OHLC data validation |
| `debug_coverage.py` | Data coverage debugging | Gap analysis |
| `debug_instruments.py` | Instrument debugging | Symbol resolution issues |

**Status:** Issues resolved, debugging no longer needed.

---

### Check/Validation Scripts (Development Phase)
**Purpose:** Schema validation and data integrity checks during migration

| File | Purpose | Notes |
|------|---------|-------|
| `check_active_fo.py` | Active F&O check | Pre-migration validation |
| `check_candle_schema.py` | Candle table schema | SQLite → PostgreSQL migration |
| `check_cols.py` | Column verification | Schema compatibility |
| `check_columns.py` | Column existence check | Migration validation |
| `check_data_completeness.py` | Data completeness | Post-backfill validation |
| `check_data_gaps.py` | Data gap detection | Historical gaps |
| `check_data_gaps_v2.py` | Gap detection v2 | Improved algorithm |
| `check_db.py` | Database connectivity | Connection testing |
| `check_fetch.py` | Fetch operation check | API fetch validation |
| `check_im_schema.py` | Instrument master schema | Master table validation |
| `check_ind_schema.py` | Indicator schema | Indicator table validation |
| `check_indexes.py` | Index existence | Performance validation |
| `check_master_schema.py` | Master schema | Reference table validation |
| `check_missing_indexes.py` | Missing index detection | Performance optimization |
| `check_schema.py` | General schema check | Overall validation |
| `check_symbols.py` | Symbol validation | Symbol master validation |
| `check_upstox_format.py` | Upstox format check | Broker data format |
| `check_upstox_specific.py` | Upstox-specific check | Broker integration |

**Status:** Migration complete, validation no longer needed in production.

---

### Profile Scripts (Performance Testing)
**Purpose:** Performance profiling during optimization phase

| File | Purpose | Notes |
|------|---------|-------|
| `profile_indicators.py` | Indicator performance | Identified bottlenecks |
| `profile_indicators2.py` | Second profiling run | After first optimization |
| `profile_detail.py` | Detailed profiling | Line-by-line analysis |

**Results:** Findings incorporated into `indicators_optimized.py`.

---

### Test Scripts (Development Testing)
**Purpose:** Unit and integration testing during development

| File | Purpose | Notes |
|------|---------|-------|
| `test_insert.py` | Insert performance test | Database write speed |
| `test_insert_speed.py` | Insert speed benchmark | Batch insert testing |
| `test_insert_speed2.py` | Second speed test | Optimized batch insert |
| `test_key_resolution.py` | Key resolution test | Composite key testing |
| `test_query_perf.py` | Query performance | Read performance |
| `test_record_build.py` | Record building test | ORM performance |
| `test_api_download.py` | API download test | Broker API testing |

**Replacement:** Tests now in `backend/tests/` directory using pytest.

---

### Analysis Scripts (Superseded)
**Purpose:** Data analysis during development

| File | Purpose | Superseded By |
|------|---------|---------------|
| `analyze_data.py` | Basic data analysis | `analysis/` directory scripts |
| `analyze_data_gaps.py` | Gap analysis | `refresh_and_verify.py` |
| `analyze_historical.py` | Historical analysis | Backtest scripts |
| `analyze_indexes.py` | Index analysis | `optimize_indexes.py` |

**Status:** Functionality moved to organized analysis scripts.

---

### Download Scripts (Legacy)
**Purpose:** Historical data downloads during initial setup

| File | Purpose | Superseded By |
|------|---------|---------------|
| `download_all_data.py` | Download all data | `backfill_all_data.py` |
| `download_corrected_symbols.py` | Corrected symbol downloads | Master table population |
| `download_historical_fo.py` | Historical F&O | `backfill_all_data.py` |

**Status:** Initial data load complete, using incremental refresh now.

---

### Utility/Exploration Scripts (One-Time Use)
**Purpose:** One-time exploration and fixes

| File | Purpose | Notes |
|------|---------|-------|
| `verify_coverage.py` | Coverage verification | One-time check |
| `verify_symbol_match.py` | Symbol matching | Resolved mismatches |
| `explore_fo_instruments.py` | F&O exploration | Initial research |
| `find_stocks.py` | Stock finding | Symbol discovery |
| `search_tata_zomato.py` | Specific symbol search | One-off search |
| `fix_missing_equities.py` | Equity data fix | Fixed missing data |

**Status:** Tasks completed, scripts kept for reference.

---

## 🔄 Why These Were Archived

### Evolution Over Time
```
compute_indicators.py (v1)
  └─> Added features (v2-v6)
      └─> Optimized architecture
          └─> indicators_optimized.py (production)
```

### Key Improvements in Current Code
1. **Async/Await**: All I/O is async for better performance
2. **PostgreSQL**: Moved from SQLite for better concurrency
3. **Batch Processing**: Optimized batch sizes based on profiling
4. **Memory Management**: Streaming results instead of loading all
5. **Error Handling**: Robust retry logic and error recovery
6. **Monitoring**: Structured logging and metrics

### Development Artifacts
- **Debug scripts**: Used during troubleshooting, issues resolved
- **Check scripts**: Used during migration, migration complete
- **Test scripts**: Ad-hoc tests, replaced by pytest suite
- **Profile scripts**: Results incorporated, no longer needed

---

## 📋 Reference Guide

### If You Need These Scripts

**For historical reference:**
- All files preserved as-is
- Code may not work with current PostgreSQL schema
- Contains valuable patterns and approaches

**For specific functionality:**
| Need | Use Instead |
|------|-------------|
| Compute indicators | `indicators_optimized.py` |
| Download data | `backfill_all_data.py` |
| Check data quality | `refresh_and_verify.py` |
| Test performance | Pytest suite in `tests/` |
| Analyze data | Scripts in `analysis/` |
| Debug issues | Structured logs in `logs/app.json` |

### Running Archived Scripts (Not Recommended)

⚠️ **Warning**: These scripts may not work with current database schema

If you must run them:
1. They expect SQLite database (`keepgaining.db`)
2. Schema may be incompatible with current PostgreSQL
3. Some dependencies may have changed
4. No longer maintained or supported

---

## 🗂️ Archive Organization

```
archive_old_versions/
├── README.md (this file)
├── compute_indicators*.py (10 files)
├── debug_*.py (5 files)
├── check_*.py (18 files)
├── profile_*.py (3 files)
├── test_*.py (7 files)
├── analyze_*.py (4 files)
├── download_*.py (3 files)
└── utility scripts (6 files)

Total: 56 archived scripts
```

---

## 📊 Timeline

| Phase | Scripts Created | Notes |
|-------|----------------|-------|
| **Initial (SQLite)** | v1-v3 indicators, downloads | Basic functionality |
| **Migration** | Check/verify scripts | SQLite → PostgreSQL |
| **Optimization** | v4-v6 indicators, profiles | Performance tuning |
| **Production** | indicators_optimized.py | Current stable version |
| **Archive** | Moved old versions | December 6, 2025 |

---

**Archive Date:** December 6, 2025  
**Total Files:** 56 scripts  
**Disk Space:** ~2MB  
**Status:** Preserved for reference, not for active use
