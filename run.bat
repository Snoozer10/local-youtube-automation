@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR="
if exist "%~dp0venv\Scripts\python.exe" (
    set "VENV_DIR=%~dp0venv"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "VENV_DIR=%~dp0.venv"
)

if "%VENV_DIR%"=="" (
    echo.
    echo =================================================================
    echo   [ERROR] Virtual environment not found!
    echo   Please run setup.bat first to configure your environment.
    echo =================================================================
    echo.
    pause
    exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b %ERRORLEVEL%
)

echo [INFO] Running YouTube Automation Pipeline (run_agency.py)...
echo.
python run_agency.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% NEQ 0 (
    echo.
    echo [ERROR] Pipeline terminated with exit code: %EXIT_CODE%
    pause
    exit /b %EXIT_CODE%
)

endlocal
exit /b 0
