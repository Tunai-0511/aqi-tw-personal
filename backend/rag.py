"""RAG 知識庫（無狀態函式）。

演算法逐字保留：2-char n-gram 字元重疊 / √len，個人 chunk 1.4x 加權，全 miss 退前 4 條。
未來要接使用者上傳的個人病歷，把 chunk（scope="personal"）用 extra_chunks 傳進 retrieve 即可。
"""
from __future__ import annotations

# 預植入的 4 份權威文獻（來源 → 內容）
RAG_SNIPPETS = [
    {"source": "WHO Air Quality Guidelines 2021",
     "quote": "PM2.5 年均不應超過 5 μg/m³，24 小時均值不應超過 15 μg/m³；長期暴露與心血管疾病、肺癌風險顯著相關。"},
    {"source": "US EPA NAAQS",
     "quote": "PM2.5 24 小時平均標準為 35 μg/m³，年均標準為 12 μg/m³；AQI > 100 屬於對敏感族群不健康。"},
    {"source": "Lancet PM2.5 Cardiovascular 2023",
     "quote": "高 PM2.5 暴露下進行劇烈戶外運動，肺部沉積量提升 3-5 倍；建議 AQI > 100 時改為室內活動。"},
    {"source": "台灣空氣品質指標技術手冊",
     "quote": "AQI 分六級：良好 (0-50)、普通 (51-100)、對敏感族群不健康 (101-150)、對所有族群不健康 (151-200)、非常不健康 (201-300)、危害 (>300)。"},
]

PERSONAL_BOOST = 1.4


def _base_chunks() -> list[dict]:
    return [
        {"source": s["source"], "text": s["quote"], "page": 1, "scope": "global"}
        for s in RAG_SNIPPETS
    ]


def _score_chunk(query: str, chunk_text: str) -> float:
    """2-char n-gram（字元雙連字符）重疊，用 √len(chunk) 標準化。中英混排免分詞。"""
    q = (query or "").lower()
    c = (chunk_text or "").lower()
    if len(q) < 2 or len(c) < 2:
        return 0.0
    qgrams = {q[i:i + 2] for i in range(len(q) - 1)}
    if not qgrams:
        return 0.0
    hits = sum(1 for i in range(len(c) - 1) if c[i:i + 2] in qgrams)
    return hits / (len(c) ** 0.5)


def retrieve(query: str, top_k: int = 5, extra_chunks: list[dict] | None = None) -> list[dict]:
    """回傳最相關的 top_k 個 chunk。全部 miss 時退回前 min(top_k,4) 條（確保 LLM 有上下文）。"""
    chunks = _base_chunks() + list(extra_chunks or [])
    scored = []
    for c in chunks:
        s = _score_chunk(query, c["text"])
        if c.get("scope") == "personal":
            s *= PERSONAL_BOOST
        scored.append((c, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [c for c, s in scored[:top_k] if s > 0]
    return top if top else chunks[: min(top_k, 4)]


def format_block(chunks: list[dict],
                 header: str = "=== RAG 檢索結果（可引用，標註來源）===") -> str:
    """把檢索結果組成 prompt 用的區塊字串（每行 `  [source] text`）。空則回空字串。"""
    if not chunks:
        return ""
    body = "\n".join(f"  [{c['source']}] {c['text']}" for c in chunks)
    return "\n" + header + "\n" + body + "\n"
