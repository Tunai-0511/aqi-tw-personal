@echo off
chcp 65001 >nul
title LobsterAQI - Build Knowledge Base
echo.
echo  ===========================================
echo    LobsterAQI · Knowledge Base Builder
echo  ===========================================
echo.

set "ROOT=%~dp0.."
set "DOCS=%ROOT%\openclaw_skills\aqi-knowledge\docs"

if not exist "%DOCS%" mkdir "%DOCS%"

echo  [1/4] WHO Air Quality Guidelines 2021 (PDF, ~3.6 MB) ...
curl -L -o "%DOCS%\who-aqg-2021.pdf" ^
    "https://iris.who.int/server/api/core/bitstreams/551b515e-2a32-4e1a-a58c-cdaecd395b19/content"

echo.
echo  [2/4] US EPA NAAQS Table (HTML) ...
curl -L -o "%DOCS%\epa-naaqs.html" ^
    "https://www.epa.gov/criteria-air-pollutants/naaqs-table"

echo.
echo  [3/4] Taiwan AQI Standard (HTML) ...
curl -L -o "%DOCS%\taiwan-aqi-standard.html" ^
    "https://airtw.moenv.gov.tw/CHT/Information/Standard/AirQualityIndicator.aspx"

echo.
echo  [4/4] Lancet 2023 PM2.5 + CV (article landing page) ...
curl -L -o "%DOCS%\lancet-2023-pm25-cv.html" ^
    "https://www.thelancet.com/journals/lanplh/article/PIIS2542-5196(23)00047-5/fulltext"

echo.
echo  -----------------------------
echo   Downloaded to:
echo     %DOCS%
echo  -----------------------------
echo.
echo  Next steps to make OpenClaw use this skill:
echo.
echo    1. Copy or symlink the skill folder to OpenClaw's workspace:
echo       robocopy "%ROOT%\openclaw_skills\aqi-knowledge" ^
                  "%%USERPROFILE%%\.openclaw\workspace\skills\aqi-knowledge" /E
echo.
echo    2. (Optional) Reindex:
echo       openclaw memory reindex --skill aqi-knowledge
echo.
echo    3. Edit each agent's SOUL.md (collector / analyst / advisor) to mention:
echo       "Prefer aqi-knowledge skill for citations."
echo.
pause
