@echo off
setlocal

REM Build clearc GUI executable for Windows via PyInstaller.
REM Usage:
REM   scripts\build_windows_exe.bat

if not exist packaging\clearc-gui.spec (
  echo [ERROR] packaging\clearc-gui.spec not found.
  exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm --clean packaging\clearc-gui.spec

if errorlevel 1 (
  echo [ERROR] Build failed.
  exit /b 1
)

echo [OK] Build finished: dist\clearc.exe
endlocal
