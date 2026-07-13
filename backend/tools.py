"""Agent 可呼叫的工具（Anthropic schema + 本地實作）。

目前核心工具是 search_literature（RAG 檢索）——分析師與預警員用它找 WHO/EPA/Lancet 依據。
協調者的委派工具（gather / analyst / advisor）定義在 pipeline.py，因為它們要 closure 綁執行期 context。
"""
from __future__ import annotations

from . import rag

# ── search_literature：RAG 文獻檢索 ──────────────────────────────────────────
SEARCH_LITERATURE_TOOL = {
    "name": "search_literature",
    "description": (
        "檢索空氣品質與健康的權威文獻片段（WHO 2021 / US EPA NAAQS / Lancet 2023 / 台灣官方手冊）。"
        "當你需要引用具體標準或研究結論來支持分析或建議時呼叫。"
        "輸入一段查詢字串（可用污染物、疾病名稱、活動情境），回傳最相關的幾條文獻與來源。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "檢索查詢，例如「氣喘 PM2.5 劇烈運動」或「WHO PM2.5 24 小時標準」",
            },
        },
        "required": ["query"],
    },
}


def search_literature_impl(inp: dict) -> str:
    query = str(inp.get("query", "")).strip()
    chunks = rag.retrieve(query, top_k=5)
    if not chunks:
        return "（找不到相關文獻）"
    return "\n".join(f"[{c['source']}] {c['text']}" for c in chunks)
