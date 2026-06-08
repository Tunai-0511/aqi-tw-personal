@echo off
chcp 65001 >nul
cd /d "%~dp0"
title LobsterAQI 3D 流程圖

where python >nul 2>nul && (set "PY=python") || (set "PY=py")
%PY% --version >nul 2>nul || (
  echo.
  echo  [錯誤] 找不到 Python。請先安裝 Python 3 並勾選 "Add Python to PATH"
  echo         下載： https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

echo.
echo  ============================================
echo    LobsterAQI 3D 流程圖
echo    網址： http://localhost:8090
echo    這個視窗請保持開啟，關掉視窗即停止伺服器
echo  ============================================
echo.

rem 等伺服器起來後自動開瀏覽器（背景延遲 2 秒）
start "" /b cmd /c "ping -n 3 127.0.0.1 >nul & start "" http://localhost:8090"

%PY% -m http.server 8090
