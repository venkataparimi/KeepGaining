# Incremental Dataset Generation

## Purpose
This script updates the strategy dataset with only the newest candles since the last run. It is **fast** (a few seconds) and avoids re‑processing the entire historical data.

## How it works
1. **`generate_dataset_incremental.py`** reads the existing Parquet file for each instrument.
2. It fetches only candles newer than the latest timestamp stored in that file.
3. Technical indicators are recomputed for the new candles (using a 200‑row context for SMA).
4. The new rows are appended to the existing Parquet file.
5. A log entry is written to `backend/data/strategy_dataset/incremental_run.log`.

## Running manually
```powershell
# From the project root
python backend/scripts/generate_dataset_incremental.py
```
You can also limit the run to a single symbol:
```powershell
python backend/scripts/generate_dataset_incremental.py --symbol RELIANCE
```

## Automated daily run (Windows)
A small batch file `run_incremental_dataset.bat` is provided (see `backend/scripts/run_incremental_dataset.bat`).
It:
- Changes to the project root
- Executes the incremental script
- Appends a timestamped entry to `incremental_run.log`

### Scheduling with Task Scheduler (command line)
Open an **elevated** PowerShell or Command Prompt and run:
```powershell
schtasks /Create ^
  /SC DAILY ^
  /TN "IncrementalDatasetUpdate" ^
  /TR "C:\code\KeepGaining\backend\scripts\run_incremental_dataset.bat" ^
  /ST 02:00 ^
  /F
```
- `/SC DAILY` – run every day
- `/ST 02:00` – run at 02:00 AM (adjust as needed)
- `/TN` – name of the task
- `/TR` – full path to the batch file
- `/F` – overwrite if the task already exists

You can verify the task with:
```powershell
schtasks /Query /TN "IncrementalDatasetUpdate" /V /FO LIST
```

## Troubleshooting
- **No new data**: The script reports `No new data` when the Parquet file already contains the latest candles.
- **Decimal type errors**: Fixed in the script by converting numeric columns to `float` after fetching from PostgreSQL.
- **Log file location**: `backend/data/strategy_dataset/incremental_run.log`. Check this file for timestamps and any error messages.

## Customisation
- **Virtual environment**: Uncomment the `call venv\Scripts\activate` line in the batch file if you use a venv.
- **Time window**: Change the schedule (`/ST`) to run at a different hour.
- **Limit instruments**: Use `--limit N` argument in the script if you only want to process a subset for testing.

---
*Generated on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")*
