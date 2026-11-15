@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 goto error
)

echo Installing dependencies...
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

"venv\Scripts\python.exe" pdf_generator.py
if errorlevel 1 goto error
exit /b 0

:error
echo.
echo Failed. Check the messages above.
pause
exit /b 1
