@echo off
rem Sets VDQ_BASE_PY to the system Python (not Voice Database Query's own environment).
rem Same search order as Musician Forge.
set "VDQ_BASE_PY="
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "VDQ_BASE_PY=%%P"
if defined VDQ_BASE_PY goto :eof
for %%V in (315 314 313 312 311 310) do if not defined VDQ_BASE_PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "VDQ_BASE_PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
if defined VDQ_BASE_PY goto :eof
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "VDQ_BASE_PY=%%P"
goto :eof
