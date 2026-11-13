@echo off
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
if not exist "%PS%" (
  echo PowerShell not found: %PS%
  echo Please tell Claude this message.
  pause
  exit /b 1
)
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; irm https://raw.githubusercontent.com/psw9715-debug/busyardapp/main/alcohol-pc/install.ps1 | iex"
pause
