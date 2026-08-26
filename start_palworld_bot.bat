@echo off
cd /d "%~dp0"

if not exist "palworld_env\Scripts\activate.bat" (
    echo Virtual environment not found, creating it...
    python -m venv palworld_env
    call palworld_env\Scripts\activate.bat
    python -m pip install -r requirements.pip
) else (
    call palworld_env\Scripts\activate.bat
)

pythonw palworld_bot.py
