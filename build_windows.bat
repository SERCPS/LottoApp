@echo off
setlocal
title LottoGen - One Click Build (v2.3.1, iconless)

set LOGFILE=build_log.txt
del "%LOGFILE%" 2>nul
echo [*] Starting build... > "%LOGFILE%"
echo [*] Working dir: %CD% >> "%LOGFILE%"

where python >nul 2>&1
if errorlevel 1 (
  echo [!] "python" not found. Trying py -3.11... >> "%LOGFILE%"
  where py >nul 2>&1
  if errorlevel 1 (
    echo [X] Python not found. Install Python 3.11 and add to PATH. >> "%LOGFILE%"
    echo Python not found. Please install Python 3.11.
    pause
    exit /b 1
  )
  set USE_PYLAUNCH=1
) else (
  set USE_PYLAUNCH=0
)

if "%USE_PYLAUNCH%"=="1" (
  py -3.11 -m venv .venv >> "%LOGFILE%" 2>&1
) else (
  python -m venv .venv >> "%LOGFILE%" 2>&1
)
if errorlevel 1 (
  echo [X] Failed to create venv. See build_log.txt.
  pause
  exit /b 1
)

call .venv\Scripts\activate
if errorlevel 1 (
  echo [X] Failed to activate venv. >> "%LOGFILE%"
  echo Failed to activate venv.
  pause
  exit /b 1
)

python -m pip install --upgrade pip wheel >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [X] pip upgrade failed. See build_log.txt.
  pause
  exit /b 1
)

pip install pyinstaller==6.6.0 requests beautifulsoup4 >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [X] Dependency install failed. See build_log.txt.
  pause
  exit /b 1
)

echo [*] Building EXE... >> "%LOGFILE%"
pyinstaller --noconfirm --clean --onefile --windowed --icon NONE --noupx --name LottoGen --hidden-import=tkinter LottoGen.py >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [X] Build failed. See build_log.txt for details.
  echo.
  type "%LOGFILE%"
  pause
  exit /b 1
)

if exist "dist\LottoGen.exe" (
  echo [✓] Build complete! dist\LottoGen.exe >> "%LOGFILE%"
  echo.
  echo [✓] Build complete! Your EXE is at: "%CD%\dist\LottoGen.exe"
  echo If SmartScreen appears, click "More info" -> "Run anyway".
  echo.
  pause
  exit /b 0
) else (
  echo [X] Build finished but EXE missing. See build_log.txt. >> "%LOGFILE%"
  echo Build finished but EXE missing. See build_log.txt.
  type "%LOGFILE%"
  pause
  exit /b 1
)
