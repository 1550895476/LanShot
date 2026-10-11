@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=python"
if exist ".build-venv\Scripts\python.exe" set "PYTHON=.build-venv\Scripts\python.exe"
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --name LanShot --icon assets\lanshot.ico --hidden-import pystray._win32 main.py
if errorlevel 1 exit /b %errorlevel%
echo.
echo Build complete: dist\LanShot.exe
