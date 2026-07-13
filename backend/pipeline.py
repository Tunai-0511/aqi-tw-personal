"""協調者（Coordinator）：把採集者 → 分析師 → 預警員 串起來，產出完整結果。

兩種模式：
  run_pipeline()    — 決定性協調（可靠，排程與預設 API 用）。三個 agent 依序協作。
  run_coordinator() — LLM 協調者 agent，用委派工具動態調度子 agent（展示「多 agent 互相協同」）。
                      需要 ANTHROPIC 金鑰；沒有時 API 會自動退回 run_pipeline。

兩者都回傳 {"payload": <build_agent_payload 契約>, "history": <每城市 24h 序列>}，
payload 與現有靜態站 / Agent Bot 的 JSON 契約完全一致。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import pandas as pd

import data
from . import agents
from .config import settings
from .personalize import UserProfile, persona_dict
# 注意：agent_runtime（會 import anthropic）只在 run_coordinator 內延遲載入，
# 這樣純 MiniMax / OpenAI 部署不必安裝 anthropic 套件。

Event = Callable[[str, dict], None]
TAIPEI = timezone(timedelta(hours=8))


def now_tpe_iso() -> str:
    """回傳帶 +08:00 的台灣時間，讓全球瀏覽器都能正確計算資料新鮮度。"""
    return datetime.now(TAIPEI).isoformat(timespec="seconds")


def timeseries_payload(ts_df, hours: int = 24) -> dict:
    """把時序 DataFrame 轉成前端要的「每城市一條序列」（與 fetch_headless 一致）。"""
    cities: dict[str, dict] = {}
    if ts_df is None or getattr(ts_df, "empty", True):
        return {"cities": cities}
    df = ts_df.sort_values("timestamp")
    cutoff = pd.Timestamp(df["timestamp"].max()) - pd.Timedelta(hours=hours)
    df = df[df["timestamp"] >= cutoff]
    for cid, g in df.groupby("city_id"):
        head = g.iloc[0]
        points = []
        for _, r in g.iterrows():
            aqi = r["aqi"]
            # CAMS 某些小時 us_aqi 為 null → NaN。跳過缺值，否則 JSON 會出現裸 NaN，
            # 瀏覽器 JSON.parse 會整包拒收、看板載入失敗。
            if pd.isna(aqi):
                continue
            pm = r.get("PM2.5", 0)
            if pd.isna(pm):
                pm = 0.0
            t = r["timestamp"]
            points.append({
                "t": t.isoformat(timespec="minutes") if hasattr(t, "isoformat") else str(t),
                "aqi": round(float(aqi), 1),
                "pm25": round(float(pm), 1),
            })
        cities[str(cid)] = {
            "city": str(head.get("city", cid)),
            "region": str(head.get("region", "")),
            "points": points,
        }
    return {"cities": cities}


def _assemble(snapshot, ts, data_mode, analysis, advisory, city_id, profile, summary=""):
    """把各 agent 產物組成 payload + history（共用於兩種協調模式）。"""
    city_name = data.CITY_BY_ID.get(city_id, {}).get("name", city_id)
    advisories_raw = f"<<<CITY:{city_name}>>>\n{advisory.strip()}\n" if advisory else ""
    payload = data.build_agent_payload(
        snapshot,
        analysis=analysis or "",
        advisories_raw=advisories_raw,
        data_mode=data_mode,
        user_city=city_id,
        threshold=int(profile.threshold),
        user_profile=persona_dict(profile),
        generated_at=now_tpe_iso(),
    )
    if summary:
        payload["coordinator_summary"] = summary
    history = timeseries_payload(ts)
    history["generated_at"] = payload["generated_at"]
    history["data_mode"] = data_mode
    out = {"payload": payload, "history": history}
    if summary:
        out["coordinator_summary"] = summary
    return out


# ── 決定性協調：採集 → 分析 → 預警 ──────────────────────────────────────────
def run_pipeline(profile: UserProfile, city_id: str | None = None,
                 epa_key: str | None = None, on_event: Event | None = None,
                 override: dict | None = None) -> dict:
    epa_key = epa_key if epa_key is not None else settings.epa_key
    city_id = city_id or profile.city or "taipei"

    snapshot, ts, data_mode, national = agents.run_collector(epa_key, on_event)

    analysis, advisory = "", None
    has_llm = settings.has_llm or bool(override and override.get("key"))
    if has_llm:
        try:
            analysis = agents.run_analyst(snapshot, national, profile, on_event, override)
        except Exception as exc:  # noqa: BLE001
            if on_event:
                on_event("agent_error", {"agent": "analyst", "error": str(exc)})
        try:
            advisory = agents.run_advisor(snapshot, national, city_id, profile, on_event, override)
        except Exception as exc:  # noqa: BLE001
            if on_event:
                on_event("agent_error", {"agent": "advisor", "error": str(exc)})
    elif on_event:
        on_event("agent_note", {"agent": "coordinator",
                                "text": "未設定 LLM 金鑰，略過分析師/預警員（資料照常產出）"})

    return _assemble(snapshot, ts, data_mode, analysis, advisory, city_id, profile)


# ── LLM 協調者：委派工具動態調度子 agent（多 agent 互相協同）─────────────────
def run_coordinator(profile: UserProfile, city_id: str | None = None,
                    epa_key: str | None = None, on_event: Event | None = None) -> dict:
    from .agent_runtime import run_agent  # 延遲載入：只有 anthropic agentic 模式才需要 anthropic 套件
    epa_key = epa_key if epa_key is not None else settings.epa_key
    city_id = city_id or profile.city or "taipei"

    ctx = {"snapshot": None, "ts": None, "data_mode": "mock", "national": None,
           "analysis": "", "advisory": None, "advised_city_id": city_id}

    def _gather(_inp):
        snap, ts, mode, nat = agents.run_collector(epa_key, on_event)
        ctx.update(snapshot=snap, ts=ts, data_mode=mode, national=nat)
        return (f"已採集 {len(snap)} 城市（{mode}）。全國平均 AQI {nat['avg_aqi']:.1f}；"
                f"最高 {nat['worst']['city']} {nat['worst']['aqi']:.0f}；"
                f"最低 {nat['best']['city']} {nat['best']['aqi']:.0f}。")

    def _analyze(_inp):
        if ctx["snapshot"] is None:
            return "尚未採集資料，請先呼叫 gather_air_quality。"
        ctx["analysis"] = agents.run_analyst(ctx["snapshot"], ctx["national"], profile, on_event)
        return ctx["analysis"]

    def _advise(inp):
        if ctx["snapshot"] is None:
            return "尚未採集資料，請先呼叫 gather_air_quality。"
        cid = str(inp.get("city_id") or city_id)
        adv = agents.run_advisor(ctx["snapshot"], ctx["national"], cid, profile, on_event)
        ctx["advisory"] = adv
        ctx["advised_city_id"] = cid  # 記住 LLM 實際建議的城市，讓 sentinel 標籤對得上
        return adv or "使用者未填個人健康檔案，無法產生個人化建議（可略過）。"

    coord_tools = [
        {"name": "gather_air_quality",
         "description": "呼叫「採集者」收集全台 20 縣市即時空品資料。這是第一步，一定要先做。",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "run_analyst",
         "description": "呼叫「分析師」產出全國層級的三段風險分析。需先 gather_air_quality。",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "run_advisor",
         "description": "呼叫「預警員」為指定城市與使用者產出個人化健康建議。需先 gather_air_quality。",
         "input_schema": {"type": "object",
                          "properties": {"city_id": {"type": "string", "description": "城市 id，例如 taipei"}}}},
    ]
    coord_impls = {"gather_air_quality": _gather, "run_analyst": _analyze, "run_advisor": _advise}

    system = (
        "你是台灣空氣品質多代理人系統的協調者。你手下有三個專職 agent：採集者、分析師、預警員，"
        "各自包成一個工具。請依序協調：先 gather_air_quality 採集，再 run_analyst 做全國分析，"
        f"接著 run_advisor（city_id={city_id!r}）為使用者所在城市產生個人化建議。"
        "最後用繁體中文寫 2-3 句總結，說明你協調了哪些 agent、得到什麼結論。"
        "重要：禁止編造資料；所有數字只能來自工具回傳。"
    )
    _emit = on_event
    if _emit:
        _emit("agent_start", {"agent": "coordinator", "name": "協調者"})
    summary = run_agent(
        system=system,
        user_prompt="請開始協調今天的空品分析工作流程，並在最後給我總結。",
        tools=coord_tools, tool_impls=coord_impls,
        max_tokens=4096, max_iters=10, on_event=on_event,
    )
    if _emit:
        _emit("agent_done", {"agent": "coordinator", "chars": len(summary)})

    # 協調者若沒採集（極少數），補跑一次確保有資料可組 payload。
    if ctx["snapshot"] is None:
        snap, ts, mode, nat = agents.run_collector(epa_key, on_event)
        ctx.update(snapshot=snap, ts=ts, data_mode=mode, national=nat)

    # 用 LLM 實際建議的城市當 sentinel 標籤（可能與傳入的 city_id 不同）。
    return _assemble(ctx["snapshot"], ctx["ts"], ctx["data_mode"],
                     ctx["analysis"], ctx["advisory"],
                     ctx.get("advised_city_id") or city_id, profile, summary=summary)
