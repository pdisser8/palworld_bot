@echo off
cd /d "%~dp0"

del /q "palworld_update_status.txt" 2>nul

del /q "palworld_update_output.log" 2>nul

python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or is not available on PATH.
    echo Install Python 3 from https://www.python.org/downloads/ and enable "Add Python to PATH", then run this file again.
    pause
    exit /b 1
)

if not exist "palworld_env\Scripts\activate.bat" (
    echo Virtual environment not found, creating it...
    python -m venv palworld_env
    if errorlevel 1 (
        echo Failed to create palworld_env.
        pause
        exit /b 1
    )
    palworld_env\Scripts\python.exe -m pip install -r requirements.pip
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo Using existing virtual environment.
)

palworld_env\Scripts\python.exe palworld_updater.py
if errorlevel 1 (
    echo.
    echo Palworld updater failed to run.
)

palworld_env\Scripts\python.exe palworld_bot.py
if errorlevel 1 (
    echo.
    echo Full Python traceback is shown above.
    pause
)
