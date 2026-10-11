@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update EasyCrawl.ps1" %*
set "update_result=%errorlevel%"
echo.
pause
exit /b %update_result%
