@echo off
echo Starting KeepGaining Frontend...
echo.

cd /d %~dp0frontend

echo [INFO] Installing dependencies (if needed)...
call npm install

echo.
echo [INFO] Starting Next.js dev server on http://localhost:3000
echo.

call npm run dev

pause
