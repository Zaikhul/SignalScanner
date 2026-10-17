@echo off
REM ======================================================================
REM Pemindai Area - Signal Scanner Quick Launcher
REM Double-click to launch Backend, Frontend, and Collector simultaneously.
REM ======================================================================

setlocal
cd /d "%~dp0"

REM Check if Python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in your PATH.
    echo Please install Python 3.10+ and add it to your system PATH.
    pause
    exit /b 1
)

REM Check if Node package manager is available
where pnpm >nul 2>nul
if %errorlevel% neq 0 (
    where npm >nul 2>nul
    if %errorlevel% neq 0 (
        echo [WARN] Neither 'pnpm' nor 'npm' was found in your PATH.
        echo Frontend will be skipped unless Node.js is installed.
    )
)

REM Run the unified orchestrator passing all CLI arguments
python run.py %*

if %errorlevel% neq 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Signal Scanner terminated with error code %errorlevel%.
    echo Please check the log messages above.
    echo ======================================================================
    echo Press any key to close this window...
    pause >nul
) else (
    echo.
    echo [INFO] Signal Scanner shut down cleanly.
)
endlocal
