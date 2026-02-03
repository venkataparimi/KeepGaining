@echo off
REM Daily Incremental Dataset Generation

REM Change to project root directory
cd /d "%~dp0..\.."

REM Activate virtual environment if needed (uncomment and adjust path)
REM call venv\Scripts\activate

REM Run the incremental dataset script
python backend/scripts/generate_dataset_incremental.py

REM Log completion time
echo Incremental dataset generation completed at %date% %time% >> backend\data\strategy_dataset\incremental_run.log
