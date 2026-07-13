"""供應商中性的「單次完成」LLM 呼叫。

全部走 data.call_llm_api —— 它已經同時支援 anthropic 的 Messages API 與
minimax / openai / gemini / custom 的 OpenAI 相容 /chat/completions。
所以分析師 / 預警員 / 聊天不管用哪家供應商，程式都一樣；MiniMax 直接可用。

（provider=anthropic 的「LLM 自己用工具委派」agentic 模式在 agent_runtime.py，另外走。）
"""
from __future__ import annotations

import data

from .config import settings


def resolve(override: dict | None = None) -> tuple[str, str, str, str]:
    """回傳 (provider, key, model, base_url)。

    override（使用者 BYO key）有帶 key 時優先用它；否則用伺服器環境變數設定。
    未指定的欄位用 data.LLM_PROVIDERS 的預設補齊。
    """
    if override and override.get("key"):
        prov = override.get("provider") or settings.llm_provider
        cfg = data.LLM_PROVIDERS.get(prov, {})
        model = override.get("model") or cfg.get("default_model", "")
        base = override.get("base_url") or cfg.get("base_url", "")
        return prov, override["key"], model, base
    prov = settings.llm_provider
    cfg = data.LLM_PROVIDERS.get(prov, {})
    model = settings.llm_model or cfg.get("default_model", "")
    base = settings.llm_base_url or cfg.get("base_url", "")
    return prov, settings.effective_llm_key, model, base


def has_key(override: dict | None = None) -> bool:
    """伺服器有金鑰、或請求自帶金鑰，都算「可呼叫 LLM」。"""
    return bool(settings.effective_llm_key) or bool(override and override.get("key"))


def complete(system: str, prompt: str, max_tokens: int = 4096,
             timeout: int = 120, override: dict | None = None) -> str:
    """單次完成。沒金鑰回空字串（呼叫端據此優雅降級）。失敗也回空字串
    （原因寫在 data.LAST_LLM_ERROR）。"""
    prov, key, model, base = resolve(override)
    if not key:
        return ""
    resp = data.call_llm_api(
        prov, key, prompt, model, base,
        system=system, max_tokens=max_tokens, timeout=timeout,
    )
    return resp or ""
