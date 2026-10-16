@echo off
setlocal
chcp 65001 >nul
rem Reklam Atolyesi kurulum / guncelleme: kur.ps1 ile ayni klasorde olmali.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0kur.ps1" %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
