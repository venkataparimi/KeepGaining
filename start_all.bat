@echo off
echo ========================================
echo  KeepGaining Trading Platform
echo ========================================
echo.
echo Starting both Backend and Frontend...
echo.

echo [1/2] Starting Backend Server...
start "KeepGaining Backend" cmd /k "cd /d %~dp0 && start_backend.bat"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Frontend Server...
start "KeepGaining Frontend" cmd /k "cd /d %~dp0 && start_frontend.bat"

echo.
echo ========================================
echo  Servers Starting...
echo ========================================
echo.
echo Backend:  http://localhost:8000/docs
echo Frontend: http://localhost:3000
echo.
echo Check the separate terminal windows for logs.
echo.
pause
