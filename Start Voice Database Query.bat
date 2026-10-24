@echo off
rem Starts Voice Database Query without a console window.
cd /d "%~dp0"
set "VDQ_PYW=%LOCALAPPDATA%\Voice Database Query\venv\Scripts\pythonw.exe"
if not exist "%VDQ_PYW%" (
  echo Voice Database Query is not installed yet. Please run "Install or Update Voice Database Query" first.
  echo Press any key to close this window.
  pause > nul
  exit /b 1
)
start "" "%VDQ_PYW%" -m voicedbquery %*
