@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_dev.ps1"
exit /b %ERRORLEVEL%
