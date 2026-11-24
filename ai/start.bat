@echo off
REM ═══════════════════════════════════════════════════════════════
REM  六爻 AI · 繁體版 — Windows 啟動腳本
REM  雙擊即可啟動，啟動後會自動開啟瀏覽器
REM ═══════════════════════════════════════════════════════════════
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set VENV_PY=..\.venv\Scripts\python.exe
if not exist "%VENV_PY%" (
    echo.
    echo   找不到虛擬環境 %VENV_PY%
    echo   請先執行：python -m venv --without-pip .venv
    echo   或直接以系統 Python 執行：python ai\server.py
    echo.
    pause
    exit /b 1
)

echo.
echo   正在啟動六爻 AI ...
echo.

start "" /b cmd /c "timeout /t 2 >nul & start http://127.0.0.1:8848/"

"%VENV_PY%" server.py
if errorlevel 1 (
    echo.
    echo   啟動失敗。請檢查上面的錯誤訊息。
    pause
)
endlocal
