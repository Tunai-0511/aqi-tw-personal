@echo off
REM 啟動 AgentAQI 後端（FastAPI + 多 agent）。先設金鑰再雙擊，或在命令列 set 後執行。
REM
REM ── 用 MiniMax ──（OpenAI 相容路徑，分析師/預警員/聊天走這條）
REM   set LLM_PROVIDER=minimax
REM   set LLM_KEY=你的MiniMax金鑰
REM   set LLM_MODEL=MiniMax-M2.7          （選填，留空用預設）
REM
REM ── 或用 Anthropic ──（可啟用「LLM 自己委派子 agent」的 agentic 協調者）
REM   set LLM_PROVIDER=anthropic
REM   set ANTHROPIC_API_KEY=sk-ant-...
REM
REM ── 共用 ──
REM   set EPA_KEY=你的環境部金鑰           （沒設會退 CAMS / 民間 / 模擬資料）
REM 沒設 LLM 金鑰也能啟動：資料端點照跑，分析/建議會略過。
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
