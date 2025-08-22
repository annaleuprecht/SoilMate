@echo off
REM build.bat — one-click builder for SoilMate on Windows
REM Usage: double-click or run from a Developer Command Prompt

setlocal

REM 1) Ensure Python and pip are in PATH
where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python not found in PATH. Install Python 3.10/3.11 and try again.
  pause
  exit /b 1
)

REM 2) (Optional) Create/activate venv
if not exist .venv (
  echo [i] Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate

REM 3) Install requirements
echo [i] Installing PyInstaller...
python -m pip install --upgrade pip
python -m pip install pyinstaller

REM If you have a requirements.txt, uncomment:
REM python -m pip install -r requirements.txt

REM 4) Build using the spec
if not exist SoilMate.spec (
  echo [!] SoilMate.spec not found in current directory.
  echo     Place this file in your project root (same folder as GUI_run.py)
  pause
  exit /b 1
)

echo [i] Building SoilMate.exe ...
pyinstaller SoilMate.spec

echo.
echo [✓] Build complete. Your app is in the dist\SoilMate\ folder.
echo     Double-click dist\SoilMate\SoilMate.exe to run.
pause
endlocal
