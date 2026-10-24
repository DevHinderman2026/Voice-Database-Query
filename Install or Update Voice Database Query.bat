@echo off
setlocal
title Voice Database Query installer
cd /d "%~dp0"
call "%~dp0tools\find_base_python.bat"
if not defined VDQ_BASE_PY (
  echo Python 3 was not found. Please install Python from python.org, then run this again.
  echo Press any key to close this window.
  pause > nul
  exit /b 1
)
"%VDQ_BASE_PY%" -u "%~dp0tools\install.py"
if errorlevel 1 goto :failed
echo Press any key to close this window.
pause > nul
exit /b 0
:failed
echo The installation had a problem. Scroll up in this window to read the message.
echo Press any key to close this window.
pause > nul
exit /b 1
