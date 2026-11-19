@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM  Dong goi AutoSearch thanh EXE (PyInstaller, onedir)
REM  Cung cach voi project yodo_auto:
REM   - PyArmor obfuscate (neu loi -> dung source goc)
REM   - PyInstaller --onedir --noconsole --contents-directory lib
REM   - Copy file du lieu (proxy.txt, icon.ico) ra canh EXE
REM ============================================================

set APP_NAME=AutoSearch
set ENTRY=gui.py
set SRC_DIR=%~dp0
set OBF_DIR=%SRC_DIR%_obf
set DIST_DIR=%SRC_DIR%output\%APP_NAME%

echo ============================================
echo  STEP 1: Install PyInstaller + PyArmor
echo ============================================
pip install --upgrade "pyinstaller>=6.0" pyarmor --quiet
if errorlevel 1 (
  echo [!] pip install failed
  exit /b 1
)

echo.
echo ============================================
echo  STEP 2: PyArmor obfuscate
echo ============================================
if exist "%OBF_DIR%" rmdir /s /q "%OBF_DIR%"
pyarmor gen -O "%OBF_DIR%" "%SRC_DIR%gui.py" "%SRC_DIR%auto.py"

if not exist "%OBF_DIR%\gui.py" (
  echo [i] PyArmor khong tao duoc gui.py - dung source goc
  if exist "%OBF_DIR%" rmdir /s /q "%OBF_DIR%"
  mkdir "%OBF_DIR%"
)
if not exist "%OBF_DIR%\gui.py"  copy /Y "%SRC_DIR%gui.py"  "%OBF_DIR%\gui.py"  >nul
if not exist "%OBF_DIR%\auto.py" copy /Y "%SRC_DIR%auto.py" "%OBF_DIR%\auto.py" >nul
echo [+] Step 2 OK

echo.
echo ============================================
echo  STEP 3: PyInstaller EXE
echo ============================================
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
pushd "%OBF_DIR%"
python -m PyInstaller --noconfirm --onedir --noconsole --windowed ^
    --name "%APP_NAME%" ^
    --icon "%SRC_DIR%icon.ico" ^
    --distpath "%SRC_DIR%output" ^
    --workpath "%SRC_DIR%_build_tmp" ^
    --specpath "%SRC_DIR%_build_tmp" ^
    --contents-directory lib ^
    --hidden-import auto ^
    --hidden-import uiautomator2 ^
    --hidden-import adbutils ^
    --hidden-import websocket ^
    --hidden-import retry ^
    --hidden-import lxml ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtWidgets ^
    --collect-data uiautomator2 ^
    --exclude-module matplotlib ^
    --exclude-module cv2 ^
    --exclude-module IPython ^
    --exclude-module jedi ^
    --exclude-module tkinter ^
    "%OBF_DIR%\%ENTRY%"
set PYI_ERR=!errorlevel!
popd
if not "!PYI_ERR!"=="0" (
  echo [!] PyInstaller failed
  exit /b 1
)
echo [+] PyInstaller OK

echo.
echo ============================================
echo  STEP 4: Copy data files
echo ============================================
if exist "%SRC_DIR%icon.ico" (
  copy /Y "%SRC_DIR%icon.ico" "%DIST_DIR%\" >nul
  echo [+] icon.ico
)
if not exist "%DIST_DIR%\proxy.txt" (
  copy /Y "%SRC_DIR%proxy.txt" "%DIST_DIR%\" >nul
  echo [+] proxy.txt
) else (
  echo [i] proxy.txt da co - giu nguyen
)

echo.
echo ============================================
echo  STEP 5: Cleanup
echo ============================================
if exist "%SRC_DIR%_build_tmp" rmdir /s /q "%SRC_DIR%_build_tmp"
if exist "%SRC_DIR%%APP_NAME%.spec" del /q "%SRC_DIR%%APP_NAME%.spec"

echo.
echo ============================================
echo  DONE
echo  EXE: output\%APP_NAME%\%APP_NAME%.exe
echo ============================================
exit /b 0
