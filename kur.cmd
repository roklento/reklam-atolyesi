@echo off
setlocal
chcp 65001 >nul
rem Reklam Atolyesi eski kok kurulum: kur.ps1 musteri-paketi\kur.ps1 dosyasina yonlendirir.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0kur.ps1" %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
