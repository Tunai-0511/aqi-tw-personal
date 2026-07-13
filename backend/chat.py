"""RAG 聊天助理。

無狀態：每次呼叫自帶當下資料快照 + 每題即時 RAG 檢索。
系統提示 ANTI_HALLUCINATION_SYSTEM 與組 prompt 邏輯逐字沿用原 app.py。
沒有 LLM 金鑰時退回「只依資料的事實摘要」（與原本 fallback 一致）。
"""
from __future__ import annotations

import pandas as pd

from . import llm, rag
from .personalize import UserProfile, profile_block

ANTI_HALLUCINATION_SYSTEM = (
    "你是 AgentAQI 的 AI 助理。你必須嚴格遵守以下規則：\n"
    "1. 只能基於使用者訊息中提供的『資料快照』和『RAG 文獻庫』作答，禁止編造資料中沒有的數字、城市、等級或事件。\n"
    "2. 若使用者問題的答案不在資料中，必須明確回覆：『目前資料中沒有這項資訊』，並建議使用者調整提問或啟動 Pipeline。\n"
    "3. 回答時直接引用具體數值（例如『台北市 AQI 為 42』），不使用模糊詞如『大概』、『可能』。\n"
    "4. 若引用 WHO/EPA/Lancet 結論，只引用 RAG 文獻庫中已列出的條目，標明來源。\n"
    "5. 一律使用繁體中文，回覆長度不設限——該講完的就講完整，但不要灌水或重複。\n"
    "6. 不要回答與台灣空氣品質、健康建議無關的話題。"
)


def build_context(snapshot: pd.DataFrame, data_mode: str, profile: UserProfile) -> str:
    w = snapshot.sort_values("aqi", ascending=False).iloc[0]
    b = snapshot.sort_values("aqi").iloc[0]
    lines = [
        f"=== 資料快照（{data_mode.upper()}）===",
        f"全國平均 AQI：{snapshot['aqi'].mean():.1f}",
        f"最高：{w['city']} {w['aqi']:.0f}（{w['level']}）；最低：{b['city']} {b['aqi']:.0f}（{b['level']}）",
        "各城市 AQI：" + "、".join(f"{r['city']} {r['aqi']:.0f}" for _, r in snapshot.iterrows()),
    ]
    pb = profile_block(profile)
    if pb:
        lines.append(pb)
    return "\n".join(lines)


def answer(message: str, snapshot: pd.DataFrame, data_mode: str,
           profile: UserProfile, has_llm: bool, override: dict | None = None) -> dict:
    picked = rag.retrieve(message, top_k=5)
    refs = [{"source": c["source"], "quote": c["text"]} for c in picked]

    if not (has_llm or (override and override.get("key"))):
        w = snapshot.sort_values("aqi", ascending=False).iloc[0]
        b = snapshot.sort_values("aqi").iloc[0]
        txt = (
            "⚠ 後端未設定 LLM 金鑰，僅依資料回覆事實摘要：\n\n"
            f"目前全國平均 AQI **{snapshot['aqi'].mean():.0f}**。"
            f"最高：{w['city']} {w['aqi']:.0f}（{w['level']}），"
            f"最低：{b['city']} {b['aqi']:.0f}（{b['level']}）。"
        )
        return {"answer": txt, "refs": []}

    rag_block = "=== RAG 檢索結果（僅可引用以下條目） ===\n" + "\n".join(
        f"  [{c['source']}] {c['text']}" for c in picked
    )
    full_prompt = (
        build_context(snapshot, data_mode, profile)
        + "\n\n" + ANTI_HALLUCINATION_SYSTEM
        + "\n\n" + rag_block
        + f"\n\n=== 使用者問題 ===\n{message}\n\n"
        "請嚴格依據上方資料作答。如資料不足，明確說明無法回答。"
        "若上方有使用者設定段落，請依實際提供的敏感程度、活動、門檻或健康因素個人化；"
        "不得推測未提供的疾病或病史。"
    )
    txt = llm.complete(ANTI_HALLUCINATION_SYSTEM, full_prompt, max_tokens=8192, override=override)
    return {"answer": txt or "（LLM 無回覆）", "refs": refs}
