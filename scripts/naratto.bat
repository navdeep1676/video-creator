@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0naratto.ps1" %*
exit /b %ERRORLEVEL%
