"""AgentAQI 後端套件：FastAPI + Anthropic Agent SDK 多 agent 協同。

- data.py / tsdb.py 是 UI 無關的核心，作為工具與資料層。
- agents.py 裡的分析師 / 預警員是真正的 Claude agent（用 Anthropic SDK 的工具迴圈）。
- pipeline.py 的協調者把三個 agent 串起來（決定性），或用 LLM 協調者動態委派（互相協同）。
"""
import sys
from pathlib import Path

# 確保專案根（有 data.py / tsdb.py）在 import path 上，不論從哪裡啟動 uvicorn。
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
