@echo off
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync_src.ps1"
exit /b %ERRORLEVEL%
