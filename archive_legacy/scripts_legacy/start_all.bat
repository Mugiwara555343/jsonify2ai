@echo off
REM INTERNAL: convenience wrapper for start_all.ps1
REM Use scripts/start_all.ps1 directly for better error handling.
setlocal
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
"%PS%" -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
endlocal
