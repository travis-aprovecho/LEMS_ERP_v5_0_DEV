@echo off
title LEMS ERP - Aprovecho Research Center

:: ── Change to the directory where this .bat file lives ───────────────────────
cd /d "%~dp0"

:: ── Check Python is available ─────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found.
    echo  Please install Python 3.10 or newer from https://www.python.org
    echo  and make sure "Add Python to PATH" is checked during install.
    echo.
    pause
    exit /b 1
)

:: ── Install / update dependencies quietly ────────────────────────────────────
echo  Checking dependencies...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  WARNING: Could not install dependencies automatically.
    echo  Run manually:  pip install -r requirements.txt
    echo.
)

:: ── Launch the app ────────────────────────────────────────────────────────────
echo.
echo  Starting LEMS ERP...
echo  Open your browser to:  http://localhost:8000
echo  Team members on the same network can access:  http://%COMPUTERNAME%:8000
echo  Close this window to stop the server.
echo.
set LEMS_HOST=0.0.0.0
python main.py

:: ── If we get here the server exited ─────────────────────────────────────────
echo.
echo  Server stopped.
pause
