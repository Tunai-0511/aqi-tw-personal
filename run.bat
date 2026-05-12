@echo off
chcp 65001 >nul
title LobsterAQI

echo.
echo  ===========================================
echo    LOBSTERAQI - Taiwan Air Quality Monitor
echo  ===========================================
echo.

REM ── Check Python ───────────────────────────────────────────────────────
where python >nul 2>nul
if errorlevel 1 (
    echo  [Error] Python not found.
    echo.
    echo  Please install Python 3.10+ from:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during install.
    echo.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ── First-time setup: create venv + install deps ───────────────────────
if not exist ".venv" (
    echo  First launch detected. Setting up environment...
    echo  This will take 1-2 minutes.
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo  [Error] Could not create virtual environment.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip --quiet
    echo  Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo  [Error] Dependency install failed. Check internet connection.
        pause
        exit /b 1
    )
    echo.
    echo  [OK] Environment ready.
    echo.
) else (
    call .venv\Scripts\activate.bat
)

REM ── Reminder about OpenClaw ────────────────────────────────────────────
echo  -------------------------------------------------
echo   Reminder: OpenClaw gateway (port 18789) is
echo   managed separately. If not running yet, see
echo   README -> "OpenClaw Setup".
echo.
echo   LobsterAQI will still work without OpenClaw —
echo   the 5 lobsters will use fallback content.
echo  -------------------------------------------------
echo.

echo  Launching LobsterAQI on http://localhost:8501
echo  Close this window to stop the app.
echo.

streamlit run app.py
