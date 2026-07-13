"""FastAPI 應用：對外的可呼叫端點。

  GET  /api/health              後端狀態（有沒有金鑰、用哪個模型）
  GET  /api/snapshot            最新 20 城市快照（純資料，無需 LLM，前端看板用）
  GET  /api/history             24 小時每城市時序（看板趨勢用）
  POST /api/pipeline/run        跑決定性多 agent 管線（採集→分析→預警），回完整 payload
  POST /api/coordinator/stream  SSE：LLM 協調者「即時」委派子 agent，前端可看到協同過程
  POST /api/advisor             單獨呼叫預警員，為某城市＋個人檔案產生客製建議
  POST /api/chat                RAG 聊天助理（右下角小視窗）

所有 LLM 端點在沒有 ANTHROPIC 金鑰時都會優雅降級（回資料事實 / 提示未設定），不會 500。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

import data
from . import agents, chat as chat_mod, pipeline
from .config import settings
from .personalize import UserProfile
from .schemas import AdvisorRequest, ChatRequest, PipelineRequest

app = FastAPI(title="AgentAQI 後端", version="2.0")
# CORS：預設只放行本機（localhost / 127.0.0.1，任意 port），避免公開部署時被任意網站
# 跨站 POST 盜刷 LLM / EPA 金鑰（denial-of-wallet）。要讓 GitHub Pages 前端連上部署後的
# 後端，明確設環境變數 AQI_CORS=https://你的帳號.github.io（可逗號分隔多個）。
if settings.cors_origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── 快照快取：避免每個請求都打 EPA（TTL 內共用同一份）───────────────────────
_cache: dict[str, Any] = {"snapshot": None, "ts": None, "national": None,
                          "data_mode": "mock", "at": 0.0}


def _get_snapshot(force: bool = False) -> dict[str, Any]:
    now = time.time()
    if (not force and _cache["snapshot"] is not None
            and (now - _cache["at"]) < settings.snapshot_ttl_sec):
        return _cache
    snap, ts, mode, nat = agents.run_collector(settings.epa_key)
    _cache.update(snapshot=snap, ts=ts, national=nat, data_mode=mode, at=now)
    return _cache


def _profile(req_profile) -> UserProfile:
    return UserProfile.from_dict(req_profile.model_dump() if req_profile else None)


def _override(req) -> dict | None:
    """從請求取出使用者自帶的 LLM 設定（BYO key）。沒填就回 None → 用伺服器設定。"""
    llm_cfg = getattr(req, "llm", None)
    return llm_cfg.model_dump() if llm_cfg else None


def _has_llm(override: dict | None) -> bool:
    return settings.has_llm or bool(override and override.get("key"))


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "provider": settings.llm_provider,
        "model": settings.llm_model or "（供應商預設）",
        "has_llm": settings.has_llm,
        "agentic": settings.use_anthropic_agentic,  # True 才有「LLM 自己委派」的協調者
        "has_epa": bool(settings.epa_key),
    }


@app.get("/api/snapshot")
def snapshot(force: bool = False) -> dict:
    c = _get_snapshot(force)
    return data.build_agent_payload(
        c["snapshot"], analysis="", advisories_raw="", data_mode=c["data_mode"],
        user_city="taipei", threshold=100, user_profile=None,
        generated_at=pipeline.now_tpe_iso(),
    )


@app.get("/api/history")
def history() -> dict:
    c = _get_snapshot()
    h = pipeline.timeseries_payload(c["ts"])
    h["generated_at"] = pipeline.now_tpe_iso()
    h["data_mode"] = c["data_mode"]
    return h


@app.post("/api/pipeline/run")
def pipeline_run(req: PipelineRequest) -> dict:
    return pipeline.run_pipeline(_profile(req.profile), req.city, override=_override(req))


@app.post("/api/advisor")
def advisor(req: AdvisorRequest):
    profile = _profile(req.profile)
    if not profile.is_filled:
        return JSONResponse({"error": "請先提供個人空氣偏好或受信任的健康檔案"},
                            status_code=400)
    ov = _override(req)
    if not _has_llm(ov):
        return JSONResponse({"error": "未設定 LLM 金鑰（伺服器或 sidebar 都可），無法產生個人化建議"},
                            status_code=503)
    c = _get_snapshot()
    # 城市必須真的在當下快照裡，否則回傳的建議會是別的城市（標籤不符）。
    if req.city not in set(c["snapshot"]["city_id"]):
        return JSONResponse({"error": f"查無「{req.city}」的即時資料"}, status_code=404)
    text = agents.run_advisor(c["snapshot"], c["national"], req.city, profile, override=ov)
    return {"city": req.city, "advice": text}


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    profile = _profile(req.profile)
    c = _get_snapshot()
    return chat_mod.answer(req.message, c["snapshot"], c["data_mode"], profile,
                           settings.has_llm, override=_override(req))


# ── SSE：協調者多 agent 協同即時進度 ────────────────────────────────────────
def _sse(gen) -> StreamingResponse:
    return StreamingResponse(
        gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/coordinator/stream")
async def coordinator_stream(req: PipelineRequest):
    profile = _profile(req.profile)
    city = req.city or profile.city
    override = _override(req)
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)  # 有界：客戶端斷線後不會無限堆積事件
    loop = asyncio.get_running_loop()

    def _put(item) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass  # 沒人在讀（斷線）→ 丟棄事件，不佔記憶體

    def on_event(kind: str, payload: dict) -> None:
        loop.call_soon_threadsafe(_put, {"kind": kind, **payload})

    def work() -> None:
        try:
            # anthropic（伺服器金鑰）→ LLM 協調者自己委派子 agent；
            # 其他供應商 / BYO 金鑰（含 MiniMax）→ 決定性協調（可帶 override）。
            if settings.use_anthropic_agentic and not (override and override.get("key")):
                res = pipeline.run_coordinator(profile, city, on_event=on_event)
            else:
                res = pipeline.run_pipeline(profile, city, on_event=on_event, override=override)
            loop.call_soon_threadsafe(_put, {
                "kind": "done",
                "payload": res["payload"],
                "summary": res.get("coordinator_summary", ""),
            })
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(_put, {"kind": "error", "error": str(exc)})
        finally:
            loop.call_soon_threadsafe(_put, None)  # 結束哨兵

    async def gen():
        # 同步的多 agent 協同丟到 executor 跑，事件經 queue 串回。
        # 不保留 / await future：客戶端斷線時 generator 直接關閉，worker 會自行跑完釋放執行緒，
        # 而有界 queue 的丟棄策略確保這期間不會累積記憶體。
        loop.run_in_executor(None, work)
        while True:
            item = await q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return _sse(gen())
