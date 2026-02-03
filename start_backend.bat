@echo off
echo Starting KeepGaining Backend Server...
echo.

cd /d %~dp0backend
set PYTHONPATH=%CD%

echo [INFO] Starting FastAPI server on http://localhost:8000
echo [INFO] API Docs will be at http://localhost:8000/docs
echo.
echo Note: Database connection errors are expected if PostgreSQL is not running.
echo The API will still work for most endpoints.
echo.

python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
