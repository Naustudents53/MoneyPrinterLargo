@echo off
REM MoneyPrinter Largo — launches both backend (FastAPI) and frontend (Vite)
REM Run from the project root: webapp\start.bat

setlocal
cd /d %~dp0\..

echo.
echo ===================================================
echo   MoneyPrinter Largo — starting backend + frontend
echo ===================================================
echo.

REM Backend (FastAPI on :8000) — uses the project venv if it exists
if exist venv\Scripts\python.exe (
    set PY=venv\Scripts\python.exe
) else (
    set PY=python
)

echo [api] Starting FastAPI on http://127.0.0.1:8000 ...
start "MPL API" cmd /k "%PY% -m uvicorn webapp.api.main:app --host 127.0.0.1 --port 8000 --reload"

REM Give the API a moment before launching the frontend
timeout /t 2 /nobreak >nul

echo [web] Starting Vite on http://127.0.0.1:5173 ...
start "MPL Web" cmd /k "cd webapp\web && npm run dev"

echo.
echo Both services launched in separate windows.
echo Open http://127.0.0.1:5173 in your browser.
echo.
endlocal
