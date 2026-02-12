@echo off
setlocal EnableDelayedExpansion

REM KeepGaining Daily Automation Script
REM Usage: Add to Windows Task Scheduler to run daily (e.g. 18:30)

cd /d %~dp0

REM Set log file with date
set LOG_FILE=logs\daily_automation_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log
if not exist logs mkdir logs

echo ======================================================== >> %LOG_FILE%
echo  KeepGaining Daily Sync Started: %date% %time% >> %LOG_FILE%
echo ======================================================== >> %LOG_FILE%

REM 1. Check Docker (PostgreSQL)
echo [1/4] Checking Database... >> %LOG_FILE%
docker ps | findstr "timescaledb" > nul
if %errorlevel% neq 0 (
    echo ERROR: TimescaleDB container not running! >> %LOG_FILE%
    echo Starting database... >> %LOG_FILE%
    docker-compose up -d db
    timeout /t 10 /nobreak > nul
)

REM 2. Run Data Sync (Equity + Indices + F&O + Indicators)
echo [2/4] Running Daily Sync... >> %LOG_FILE%
echo Running: python scripts/daily_sync.py --segment all >> %LOG_FILE%
python scripts/daily_sync.py --segment all >> %LOG_FILE% 2>&1

if %errorlevel% neq 0 (
    echo ERROR: Daily sync failed! Check logs. >> %LOG_FILE%
    goto :End
)

REM 3. Run Indicator Pipeline (if daily_sync didn't cover it fully or for deep recompute)
REM daily_sync with --segment all already includes 'indicators' segment which runs stage1
REM We just need to make sure Stage 2 and 3 run if Stage 1 ran.

echo [3/4] Verifying Indicator Pipeline... >> %LOG_FILE%

REM Trigger Stage 2 (Parquet) just in case
echo Running Stage 2 (Parquet)... >> %LOG_FILE%
python scripts/pipeline/stage2_parquet.py >> %LOG_FILE% 2>&1

REM Trigger Stage 3 (DB Load - Fast)
echo Running Stage 3 (DB Load)... >> %LOG_FILE%
python scripts/pipeline/stage3_db_load_fast.py >> %LOG_FILE% 2>&1

REM 4. Cleanup
echo [4/4] Cleanup... >> %LOG_FILE%
REM Add any cleanup logic here if needed

:End
echo. >> %LOG_FILE%
echo ======================================================== >> %LOG_FILE%
echo  Finished: %date% %time% >> %LOG_FILE%
echo ======================================================== >> %LOG_FILE%

endlocal
