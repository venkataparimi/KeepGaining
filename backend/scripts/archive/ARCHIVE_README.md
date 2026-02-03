# Archived Scripts

**Archived:** December 18, 2025  
**Reason:** Cleanup per development guidelines - remove one-off, stock-specific, and duplicate scripts

---

## Categories

### `stock_specific/` (11 files)
Scripts hardcoded for specific stocks (hindzinc, iex, etc.):
- `backfill_hindzinc_options.py`
- `backfill_iex_equity.py`
- `backfill_stock.py`, `backfill_stock_v2.py`
- `check_hindzinc_*.py`, `check_iex_*.py`
- `quick_check_hindzinc.py`
- `reverse_engineer_hindzinc.py`
- `verify_february_data.py`

**Why archived:** Violates guideline of generic, reusable scripts. Use generic `backfill_all_data.py` instead.

---

### `one_off_analysis/` (7 files)
Analysis for specific trades/dates:
- `analyze_dec1_hindzinc.py`
- `analyze_hero_trade.py`
- `analyze_hindzinc_trade.py`
- `analyze_iex_trade.py`, `analyze_iex_trade_db.py`
- `analyze_spot_triggers.py`
- `deep_alternative_analysis.py`

**Why archived:** One-time analysis, not reusable.

---

### `debug_temp/` (24 files)
Debug scripts, temp checks, and test files:
- `debug_backtest.py`, `debug_token.py`
- `check_active_queries.py`, `check_*_temp.py`, `check_schema.py`
- `test_csv_gen.py`, `test_expired_api.py`, `test_historical_limits.py`
- `test_token_*.py`, `test_local_ai.py`, `test_ollama_connection.py`
- `parse_option_symbol.py`, `parse_symbol_fixed.py`
- `ollama_quickstart.py`, `pull_phi3.py`, `install_fast_models.py`
- `finetuning_pipeline.py`, `refresh_and_verify.py`
- `indicator_computation.log`

**Why archived:** Debug/temp scripts or one-time setup.

---

### `migration_complete/` (10 files)
Scripts for completed database migrations:
- `complete_migration.py`, `finish_migration.py`
- `quick_complete_migration.py`, `quick_finish_migration.py`
- `check_migration_progress.py`
- `migrate_to_hypertable.py`, `setup_timescale_tables.py`
- `optimize_db.py`, `optimize_indexes.py`, `setup_indicator_index.py`

**Why archived:** TimescaleDB migration is complete.

---

### `duplicate_versions/` (8 files)
Multiple versions of similar backtest scripts:
- `backtest_cluster1_fast.py`, `backtest_cluster1_october.py`
- `backtest_strategy_a_relaxed.py`
- `final_realistic_backtest.py`, `realistic_backtest_final.py`
- `realistic_fo_backtest.py`, `run_full_fo_backtest.py`
- `sanity_backtest.py`

**Why archived:** Use unified `backtest_cli.py` instead.

---

## Kept Scripts (52 active)

Generic, reusable scripts that remain active:
- **Backfill:** `backfill_all_data.py`, `backfill_equity_data.py`, `backfill_fo_historical.py`
- **Analysis:** `analyze_ce_trades.py`, `analyze_pe_exits.py`, `analyze_user_trades.py`
- **Backtest:** `backtest_cli.py`, `backtest_comparison.py`, `multi_strategy_backtest.py`
- **CLIs:** `data_cli.py`, `trading_cli.py`
- **Indicators:** `compute_indicators_bulk.py`, `refresh_indicators.py`
- **Dataset:** `generate_dataset.py`, `update_dataset.py`

---

## Restoring Files

```bash
# To restore a file
cp archive/subfolder/filename.py ../
```
