@echo off
chcp 65001 >nul
title AgentAQI - Seed Demo Data
echo.
echo  ===========================================
echo    AgentAQI · Seed Demo Data (期末 demo)
echo  ===========================================
echo.
echo  This seeds the local SQLite with demo-only data so SECTION 08-10
echo  are full on open (16-day AQI history; the diary is auto-filled by the app).
echo  Everything is tagged as demo and can be removed with --clear.
echo.

REM ── Jump to project root (this .bat lives in scripts\) ─────────────────
cd /d "%~dp0.."

REM ── Activate venv if present (created by run.bat first launch) ──────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo  [Note] .venv not found - using system Python.
    echo         If imports fail, run run.bat once first to create the venv.
    echo.
)

REM ── Pass through any args, e.g.  seed_demo_data.bat --clear ────────────
python scripts\seed_demo_data.py %*

echo.
pause
