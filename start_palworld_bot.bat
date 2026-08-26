@echo off
cd /d "%~dp0"
call palworld_env\Scripts\activate.bat
pythonw palworld_bot.py
