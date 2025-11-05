@echo off
setlocal
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
"%PS%" -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
endlocal
