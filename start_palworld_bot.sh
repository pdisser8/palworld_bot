#!/usr/bin/env bash
set -e

# Change directory to script's location
cd "$(dirname "$0")"

# Remove old update logs
rm -f palworld_update_status.txt palworld_update_output.log

# Check for Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is not installed or not in PATH."
    echo "Install it via: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# Ensure virtual environment exists
if [ ! -f "palworld_env/bin/activate" ]; then
    echo "Virtual environment not found, creating it..."
    python3 -m venv palworld_env
    palworld_env/bin/pip install --upgrade pip
    palworld_env/bin/pip install -r requirements.pip
else
    echo "Using existing virtual environment."
fi

# Run the updater
echo "Checking for Palworld updates..."
palworld_env/bin/python3 palworld_updater.py || {
    echo "Palworld updater encountered an error, continuing to launch bot..."
}

# Run the bot
echo "Starting Palworld Discord Bot..."
palworld_env/bin/python3 palworld_bot.py

