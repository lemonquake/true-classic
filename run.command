#!/bin/bash

# Change directory to the folder where this script is located
cd "$(dirname "$0")"

echo "==================================================="
echo "            True Classic Discord Bot"
echo "==================================================="
echo ""

# Determine python executable (prefer python3 on macOS)
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python is not installed or not in your PATH."
    echo "Please install Python 3.8+ and try again."
    echo ""
    read -p "Press [Enter] key to exit..."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "[System] Virtual environment not found. Creating .venv..."
    $PYTHON_CMD -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment."
        read -p "Press [Enter] key to exit..."
        exit 1
    fi
fi

# Activate virtual environment
echo "[System] Activating virtual environment..."
source .venv/bin/activate

# Install requirements
echo "[System] Checking/Installing dependencies..."
python -m pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install dependencies."
    read -p "Press [Enter] key to exit..."
    exit 1
fi

# Start the bot
echo ""
echo "[System] Starting True Classic Discord Bot..."
echo "---------------------------------------------------"
python main.py
echo "---------------------------------------------------"
echo ""
echo "[System] Bot has stopped running."
read -p "Press [Enter] key to continue..."
