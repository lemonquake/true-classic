@echo off
title True Classic Discord Bot

echo ===================================================
echo             True Classic Discord Bot
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.8+ and try again.
    echo.
    pause
    exit /b
)

:: Create virtual environment if it doesn't exist
if not exist .venv (
    echo [System] Virtual environment not found. Creating .venv...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b
    )
)

:: Activate virtual environment
echo [System] Activating virtual environment...
call .venv\Scripts\activate.bat

:: Install requirements
echo [System] Checking/Installing dependencies...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b
)

:: Start the bot
echo.
echo [System] Starting True Classic Discord Bot...
echo ---------------------------------------------------
python main.py
echo ---------------------------------------------------
echo.
echo [System] Bot has stopped running.
pause
