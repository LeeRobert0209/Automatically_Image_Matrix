@echo off
setlocal

:: 1. Check if config.ini exists
if not exist "config.ini" (
    echo Config file not found, using default 'python' command...
    python main.py
    pause
    exit /b
)

:: 2. Read python_path from config.ini
:: We iterate through the file, looking for the key "python_path="
set PYTHON_CMD=

for /f "tokens=1* delims==" %%A in ('type config.ini ^| findstr /b "python_path="') do (
    set "PYTHON_CMD=%%B"
)

if "%PYTHON_CMD%"=="" (
    echo Could not read python_path from config.ini, using default 'python'...
    set PYTHON_CMD=python
)

echo Using Python interpreter: "%PYTHON_CMD%"

:: 4. Run main.py
"%PYTHON_CMD%" main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%.
    pause
)

