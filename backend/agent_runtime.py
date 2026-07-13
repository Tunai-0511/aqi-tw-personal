"""通用 agentic 工具迴圈（Anthropic Agent SDK）。

這是「多 agent」的共用底層：每個 agent = 一次 run_agent 呼叫（system + prompt + 一組工具）。
用官方 anthropic SDK 的 messages.create 手動跑 tool-use 迴圈，好完全掌握進度回呼（供 SSE）。

模型與 thinking 設定依 claude-api skill：
  - 預設 claude-opus-4-8
  - thinking={"type":"adaptive"}（adaptive-only 模型；budget_tokens 會 400）
  - 不傳 temperature/top_p/top_k（在 opus-4-8 會 400）
  - 把整包 resp.content（含 thinking blocks）原樣回填，才不會破壞 thinking 簽章
"""
from __future__ import annotations

from typing import Any, Callable

import anthropic

from .config import settings

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # 零參數建構：SDK 依序解析 ANTHROPIC_API_KEY / AUTH_TOKEN / ant profile。
        _client = anthropic.Anthropic()
    return _client


class AgentError(RuntimeError):
    pass


def run_agent(
    *,
    system: str,
    user_prompt: str,
    tools: list[dict] | None = None,
    tool_impls: dict[str, Callable[[dict], str]] | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
    max_iters: int = 6,
    on_event: Callable[[str, dict], None] | None = None,
) -> str:
    """跑一個 agent，回傳最終文字。

    tools: Anthropic 工具 schema（list of {name, description, input_schema}）。
    tool_impls: {tool_name: fn(input_dict)->str}，本地執行工具。
    on_event(kind, payload): 進度回呼，kind ∈ {tool_use, tool_result, text}。
    """
    client = get_client()
    model = model or settings.model
    tools = tools or []
    tool_impls = tool_impls or {}
    messages: list[dict] = [{"role": "user", "content": user_prompt}]

    resp = None
    for _ in range(max_iters):
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
        )
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)

        # 安全政策婉拒（HTTP 200 但 content 可能為空）——明確回一句話，不要靜默回空字串。
        if resp.stop_reason == "refusal":
            note = "（模型基於安全政策婉拒回答本次請求）"
            if on_event:
                on_event("text", {"chars": len(note)})
            return note

        if resp.stop_reason == "tool_use":
            # 原樣回填 assistant 內容（含 thinking + tool_use blocks），順序不可改。
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                if on_event:
                    on_event("tool_use", {"name": block.name, "input": block.input})
                impl = tool_impls.get(block.name)
                is_err = impl is None
                try:
                    out = impl(block.input) if impl else f"（未知工具 {block.name}）"
                except Exception as exc:  # noqa: BLE001
                    out = f"工具執行失敗：{exc}"
                    is_err = True
                out = str(out)
                if on_event:
                    on_event("tool_result", {"name": block.name, "chars": len(out)})
                result = {"type": "tool_result", "tool_use_id": block.id, "content": out}
                if is_err:
                    result["is_error"] = True  # 讓模型知道這是失敗，可自行改用其他方法
                results.append(result)
            messages.append({"role": "user", "content": results})
            continue

        # end_turn / max_tokens / 其他 → 收尾，取文字 blocks
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        if on_event:
            on_event("text", {"chars": len(text)})
        return text

    # 迴圈用盡仍在要工具：回目前拿到的文字（若有），否則報錯
    if resp is not None:
        tail = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        if tail:
            return tail
    raise AgentError("agent 迴圈達到上限仍未收斂")
