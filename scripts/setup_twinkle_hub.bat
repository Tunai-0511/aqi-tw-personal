@echo off
chcp 65001 >nul
title LobsterAQI - Setup Twinkle Hub MCP
echo.
echo  ===============================================
echo    LobsterAQI · Twinkle Hub (open-data MCP) Setup
echo  ===============================================
echo.
echo  This registers the "twinkle-hub" MCP server in OpenClaw so the
echo  `analyst` / `advisor` agents can OPTIONALLY look up Taiwan
echo  government open data (weather / front / typhoon / dust / advisories)
echo  as *background context* when they write their AQI analysis.
echo.
echo  What this is NOT:
echo    - NOT a new AQI measurement source (Hub re-serves 環境部 data)
echo    - NOT used by the in-app Pipeline (single-call, cannot use tools)
echo    - NOT touching data.py / map / charts (dashboard numbers unchanged)
echo.
echo  Only the OpenClaw agent runtime (cron / subscription pushes +
echo  direct OpenClaw chats) can reach this tool.
echo.
echo  Prerequisites:
echo    [x] OpenClaw installed            (openclaw --version)
echo    [x] A Twinkle Hub API key (sk-...) from https://hub.twinkleai.tw/login
echo.
echo  Heads-up: Twinkle Hub is ALPHA - nightly maintenance 22:00-07:00 TW,
echo            may be unstable, no SLA, future per-tool billing. The agents
echo            are told to degrade gracefully (finish from dashboard data
echo            if the tool times out or errors).
echo.

set /p TWKEY="Paste your Twinkle Hub API key (sk-...): "
if "%TWKEY%"=="" (
    echo.
    echo  [Error] API key is required. Get one at https://hub.twinkleai.tw/login
    pause
    exit /b 1
)

echo.
echo  Registering MCP server "twinkle-hub" ...
echo  (key is written only to your local ~/.openclaw config; never echoed back)
echo.

openclaw config set mcp.servers.twinkle-hub.url "https://api.twinkleai.tw/mcp/"
openclaw config set mcp.servers.twinkle-hub.transport "streamable-http"
openclaw config set mcp.servers.twinkle-hub.headers.Authorization "Bearer %TWKEY%"

echo.
echo  Config written. Configured MCP servers now:
echo.
openclaw mcp list

echo.
echo  -----------------------------------------------
echo   IMPORTANT - restart the gateway so it loads the new server:
echo     service mode:   openclaw gateway stop    then   openclaw gateway start
echo     foreground:     Ctrl+C the gateway window, then  openclaw gateway run
echo     check status:   openclaw gateway status
echo.
echo   Inspect (note: `show` prints the bearer header in full):
echo     openclaw mcp list
echo     openclaw mcp show twinkle-hub
echo.
echo   Tool scope: the agents are guided (in their SOUL.md) to use ONLY the
echo   `opendata-*` tools and to ignore the `twtools-*` ID/統編/calendar
echo   utilities. This OpenClaw build has no per-server tool-filter flag, so
echo   the scope is enforced by agent guidance rather than config.
echo.
echo   To remove later:
echo     openclaw mcp unset twinkle-hub
echo  -----------------------------------------------
echo.
pause
