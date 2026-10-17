@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0guncelle.ps1" %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
