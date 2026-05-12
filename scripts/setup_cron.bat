@echo off
chcp 65001 >nul
title LobsterAQI - Setup Cron Push
echo.
echo  ===========================================
echo    LobsterAQI · Hourly Discord Push Setup
echo  ===========================================
echo.
echo  This script will register a cron job in OpenClaw that:
echo    - runs every hour at minute 0 (Asia/Taipei time)
echo    - asks the `analyst` agent to summarize Taiwan AQI
echo    - delivers the result to a Discord channel
echo.
echo  Prerequisites:
echo    [x] OpenClaw gateway running (openclaw gateway run --port 18789)
echo    [x] Discord configured in OpenClaw (openclaw configure)
echo    [x] Channel access token already paired (openclaw pairing approve discord <code>)
echo    [x] `analyst` agent already registered
echo.

set /p DISCORD_CHANNEL="Enter your Discord channel ID (e.g. 123456789012345678): "
if "%DISCORD_CHANNEL%"=="" (
    echo  [Error] Channel ID is required.
    pause
    exit /b 1
)

echo.
echo  Registering cron job...
echo.

openclaw cron add ^
    --name "TW-AQI-hourly" ^
    --cron "0 * * * *" ^
    --tz "Asia/Taipei" ^
    --session isolated ^
    --agent analyst ^
    --message "請拉取台灣即時 AQI 並用 3 段繁體中文摘要：① 全國概況與最高/最低城市 ② 對敏感族群的建議 ③ 未來 6 小時研判。引用 WHO/EPA 標準。每段 2-3 句。" ^
    --announce ^
    --channel discord ^
    --to "channel:%DISCORD_CHANNEL%"

echo.
echo  -----------------------------
echo   To inspect / modify:
echo     openclaw cron list
echo     openclaw cron edit TW-AQI-hourly
echo     openclaw cron remove TW-AQI-hourly
echo.
echo   To run once manually (for testing):
echo     openclaw cron run TW-AQI-hourly
echo  -----------------------------
echo.
pause
