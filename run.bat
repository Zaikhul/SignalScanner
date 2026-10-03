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

REM Run the unified orchestrator passing all CLI arguments
python run.py %*

if %errorlevel% neq 0 (
    echo.
    echo [INFO] Signal Scanner shut down.
)
endlocal
