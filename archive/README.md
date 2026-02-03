# Archive Directory

This directory contains files archived during the codebase cleanup on **December 18, 2025**.

## Contents

### `backtest_results/`
Old backtest output files (CSV/JSON) from previous strategy testing sessions.
- Various `backtest_*.csv` files from December 2025 runs
- `final_realistic_*.csv` files from backtest sessions
- `strategy_*.csv` and `strategy_*.json` files
- `identified_strategy.json`

**Can be deleted** if backtest results have been analyzed and documented.

### `logs/`
Historical log files:
- `backfill.log` - Data backfill logs
- `backfill_*.log` - Dated backfill logs
- `migration_*.log` - Database migration logs

**Can be deleted** - these are old operational logs.

### `docs/`
Superseded or dated documentation:
- `CLEANUP_SUMMARY_DEC_6.md` - Previous cleanup session
- `SESSION_SUMMARY_DEC_6.md` - Previous debugging session
- `COMET_*.md` files - Comet AI docs (consolidated into main docs)
- `TIMESCALEDB_MIGRATION.md` - Migration complete
- `open_tasks_summary.md` - Outdated task list

**Can be deleted** after verifying content is captured in:
- `docs/CODEBASE_OVERVIEW.md` - New comprehensive guide
- `docs/HIGH_LEVEL_DESIGN.md` - Architecture reference

---

## Restoring Files

If you need any files:
```bash
# Restore a file
cp archive/subfolder/filename.ext .
```

---

**Archived:** December 18, 2025  
**Reason:** Codebase cleanup and documentation consolidation
