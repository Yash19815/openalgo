@echo off
REM Start OpenAlgo on the Flask dev server (http://127.0.0.1:5000).
REM Usage: start-app.bat [--build]
REM   --build  rebuild the React frontend first (needs Node.js)
REM A missing .env is created from .sample.env on first start.
REM Live order execution stays blocked for the NIFTY paper system.

setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found. Install it from https://docs.astral.sh/uv/ and retry.
    exit /b 1
)

if /i "%~1"=="--build" (
    if not exist "frontend\package.json" (
        echo frontend\package.json not found.
        exit /b 1
    )
    pushd frontend
    call npm install
    if errorlevel 1 ( popd & exit /b 1 )
    call npm run build
    if errorlevel 1 ( popd & exit /b 1 )
    popd
)

echo Syncing dependencies...
uv sync
if errorlevel 1 exit /b 1

echo Starting OpenAlgo on http://127.0.0.1:5000 ...
uv run app.py
exit /b %errorlevel%
