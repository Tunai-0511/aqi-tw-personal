"""集中設定：全部從環境變數讀，不寫死任何金鑰。

LLM 供應商（多 agent / 聊天）可切換，對齊 data.LLM_PROVIDERS：
  LLM_PROVIDER   anthropic（預設）/ minimax / openai / gemini / custom
  LLM_KEY        該供應商的金鑰
  LLM_MODEL      模型（留空用該供應商預設，例如 minimax → MiniMax-M2.7）
  LLM_BASE_URL   自訂端點（留空用該供應商預設）
  ANTHROPIC_API_KEY  provider=anthropic 時可改用 SDK 慣用的這個變數

其他：
  EPA_KEY            環境部金鑰（沒有仍可拿 CAMS/民間/模擬資料）
  AQI_MODEL          provider=anthropic 的 agentic 協調者用的模型（預設 claude-opus-4-8）
  AQI_CORS           允許的前端來源，逗號分隔（預設只放行本機）
  AQI_SNAPSHOT_TTL   快照快取秒數（預設 600）
"""
from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        # ── LLM 供應商 ──
        self.llm_provider = (os.environ.get("LLM_PROVIDER", "anthropic").strip() or "anthropic")
        self.llm_key = os.environ.get("LLM_KEY", "").strip()
        self.llm_model = os.environ.get("LLM_MODEL", "").strip()
        self.llm_base_url = os.environ.get("LLM_BASE_URL", "").strip()
        # anthropic 也接受 SDK 慣用的 ANTHROPIC_API_KEY / AUTH_TOKEN
        self.anthropic_env_key = (
            os.environ.get("ANTHROPIC_API_KEY", "")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        ).strip()

        # ── 其他 ──
        self.model = os.environ.get("AQI_MODEL", "claude-opus-4-8")  # anthropic agentic 用
        self.max_tokens = int(os.environ.get("AQI_MAX_TOKENS", "4096"))
        self.epa_key = os.environ.get("EPA_KEY", "").strip()
        self.snapshot_ttl_sec = int(os.environ.get("AQI_SNAPSHOT_TTL", "600"))
        raw_cors = os.environ.get("AQI_CORS", "*")
        self.cors_origins = [o.strip() for o in raw_cors.split(",") if o.strip()] or ["*"]

    @property
    def effective_llm_key(self) -> str:
        """實際要用的金鑰：anthropic 可用 LLM_KEY 或 ANTHROPIC_API_KEY；其他供應商用 LLM_KEY。"""
        if self.llm_provider == "anthropic":
            return self.llm_key or self.anthropic_env_key
        return self.llm_key

    @property
    def has_llm(self) -> bool:
        """有沒有可用的 LLM 金鑰（任何供應商）。沒有時分析師/預警員/聊天會優雅降級。"""
        return bool(self.effective_llm_key)

    @property
    def use_anthropic_agentic(self) -> bool:
        """只有 provider=anthropic 且有金鑰時，才啟用 Agent SDK 的工具迴圈協調者
        （LLM 自己委派子 agent）。其他供應商走決定性協調（一樣三個 agent 依序協作）。"""
        return self.llm_provider == "anthropic" and self.has_llm

    # 舊呼叫點相容別名
    @property
    def has_anthropic(self) -> bool:
        return self.use_anthropic_agentic


settings = Settings()
