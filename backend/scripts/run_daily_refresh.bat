@echo off
REM Daily Indicator Refresh - Run after market hours
REM Schedule this task using Windows Task Scheduler to run at 4:30 PM IST daily

cd /d "%~dp0"

echo Starting Daily Indicator Refresh at %date% %time%
echo.

python refresh_indicators.py --parallel 4

echo.
echo Refresh completed at %date% %time%
