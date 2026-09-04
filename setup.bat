@echo off
setlocal
cd /d "%~dp0"

echo =================================================================
echo   YouTube Automation Pipeline - Windows Setup Launcher
echo =================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% NEQ 0 (
    echo.
    echo =================================================================
    echo   [ERROR] Setup failed with exit code: %EXIT_CODE%
    echo =================================================================
    echo.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo =================================================================
echo   [SUCCESS] Setup completed successfully.
echo =================================================================
echo.
endlocal
exit /b 0
