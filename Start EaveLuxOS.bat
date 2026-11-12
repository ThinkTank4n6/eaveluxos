@echo off
rem SPDX-License-Identifier: MIT
rem Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
title EaveLuxOS
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto nopython
python -c "import tzdata" >nul 2>nul
if errorlevel 1 (
  echo Installing time zone data, one time only...
  python -m pip install --user --quiet tzdata
)
python -c "import cryptography" >nul 2>nul
if errorlevel 1 (
  echo Installing the encryption package, one time only...
  python -m pip install --user --quiet cryptography
)
start "" pythonw "%~dp0main.py" run --open
exit /b 0
:nopython
echo EaveLuxOS needs Python 3.11 or newer.
echo Opening the download page. When installing, tick "Add python.exe to PATH".
start https://www.python.org/downloads/
pause
