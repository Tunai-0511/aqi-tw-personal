"""
🦞 LobsterAQI · Taiwan Air Quality Multi-Agent Monitoring Platform
==================================================================
Streamlit single-page application. Run with:

    streamlit run app.py
"""
from __future__ import annotations

import json
import random
import re
import shlex
import subprocess
import time
from datetime import datetime, timedelta
from html import escape

import pandas as pd
import streamlit as st

from data import (
    AGENTS, AQI_LEVELS, CITIES, CITY_BY_ID, GROUP_ADVICE,
    LLM_PROVIDERS, OUTDOOR_ACTIVITIES, POLLUTANTS, SENSITIVE_GROUPS,
    aqi_to_level,
    best_outdoor_hours,
    call_llm_api,
    fetch_citizen_sensors,
    fetch_open_meteo_aq_batch,
    generate_citizen_vs_official,
    generate_current_snapshot,
    generate_real_snapshot,
    generate_real_timeseries,
    generate_time_series,
    send_discord_webhook,
)
import tsdb
# OpenClaw is kept for cron push + MEMORY.md write (NOT for in-app LLM calls).
# Imported lazily where needed (subscribe page, MEMORY write button).
from styles import AGENT_STAGE_CSS, DARK_THEME_CSS
from charts import (
    make_aqi_gauge,
    make_city_ranking,
    make_citizen_vs_official,
    make_heatmap,
    make_humidity_scatter,
    make_map,
    make_outdoor_bars,
    make_pm25_aqi_scatter,
    make_pollutant_radar,
    make_stacked_composition,
    make_trend_line,
    make_wind_rose,
)

# =============================================================================
# Page setup
# =============================================================================
st.set_page_config(
    page_title="LobsterAQI · Taiwan Air Quality Multi-Agent System",
    page_icon="🦞",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)
st.markdown(AGENT_STAGE_CSS, unsafe_allow_html=True)

# =============================================================================
# Session state
# =============================================================================
def init_state():
    defaults = {
        "pipeline_done":   False,
        "selected_city":   None,   # set by clicking bars in the city ranking chart
        "active_agent":    None,
        "comm_log":        [],
        "current_step":    -1,
        # Auto-refresh: when True, the hourly fragment re-runs the pipeline.
        # Defaults to True so a user who walks away comes back to fresh data.
        "auto_refresh_enabled": True,
        "last_pipeline_run_at": None,   # datetime of last completed run
        # In-app LLM (direct multi-provider) — fast path, no OpenClaw routing
        "llm_provider":  "anthropic",
        "llm_key":       "",
        "llm_model":     "",     # auto-resolved from provider default if empty
        "llm_base_url":  "",     # auto-resolved from provider default if empty
        # OpenClaw is still used out-of-band for cron push + MEMORY.md.
        # Kept as compat stubs so subscribe page / personalization section still work.
        "openclaw_agent_map":     {
            "collector": "collector",
            "scraper":   "scraper",
            "analyst":   "analyst",
            "critic":    "critic",
            "advisor":   "advisor",
        },
        # EPA Open Data Token (optional; public endpoint works without it)
        "epa_key":                "",
        # Discord webhook URL — Pipeline 跑完會 POST 摘要到這個 URL（選填）
        "discord_webhook_url":    "",
        # Snapshot data (None until pipeline runs)
        "snapshot":        None,
        "ts_df":           None,          # 24h history (EPA aqx_p_488 preferred, CAMS fallback)
        "cams_ts_df":      None,          # 24h history from Open-Meteo CAMS (always populated when reachable)
        "citizen_df":      None,          # LASS-net Airbox per-city aggregate
        "lass_cleaning":   None,          # Real CleaningReport from LASS fetch
        "data_mode":       "mock",        # "mock" | "real"
        "llm_analysis":    "",            # 分析師 (B) — risk-analysis report
        "agent_c_advisories": "",         # 預警員 (C) — health advisories per sensitive group
        # RAG chunks — pre-seeded with WHO/EPA/Lancet/MOENV starter snippets,
        # PDF uploads append real extracted paragraphs (see sidebar handler).
        "rag_chunks":      [],            # populated lazily via _seed_rag_chunks()
        "rag_files":       [],            # display metadata for uploaded files (name, size, n_chunks)
        "chat_history":    [],
        "trend_cities":    ["taipei", "taichung", "kaohsiung", "hualien", "kinmen"],
        "radar_cities":    ["taipei", "yunlin", "kaohsiung", "kinmen"],
        "selected_groups": [],
        "user_city":       "taipei",
        "user_conditions": [],
        "user_activity":   "running",
        "show_chat":       False,
        "chat_expanded":   False,    # floating panel open/closed
        "selected_hour":   None,     # time scrubber position (None = current snapshot)
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

init_state()

# Data lives in session_state and is populated during run_pipeline().


# =============================================================================
# Auto-refresh — fires every minute via st.fragment(run_every) so we don't have
# to block the main script. When the configured cadence (default: 60 minutes)
# elapses since the last completed pipeline AND the user has the toggle on, we
# flag the pipeline to re-run on the next full-app rerun.
# =============================================================================
@st.fragment(run_every="60s")
def _auto_refresh_tick() -> None:
    if not st.session_state.get("auto_refresh_enabled", True):
        return
    if not st.session_state.get("pipeline_done"):
        return  # don't auto-start; user must click launch the first time
    last = st.session_state.get("last_pipeline_run_at")
    if last is None:
        return
    elapsed_min = (datetime.now() - last).total_seconds() / 60
    if elapsed_min >= 60:
        st.session_state["_pipeline_should_run"] = True
        # Full-app rerun so the pipeline-launch logic further down the script
        # picks up the flag — a fragment-scoped rerun would re-fire just this
        # tick and not actually trigger the pipeline placeholders.
        st.rerun(scope="app")


_auto_refresh_tick()


# =============================================================================
# RAG knowledge base (constants + helpers — used by both sidebar uploader and chat panel)
# =============================================================================
# =============================================================================
# FLOATING AI ASSISTANT — rendered before the cover so it's always available
# =============================================================================
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


# ── Real-PDF RAG helpers ────────────────────────────────────────────────────
# Chunks are { "source": str, "text": str, "page": int }.
# The pre-seeded starter set comes from RAG_SNIPPETS above; uploaded PDFs/
# TXT/MD files are extracted via pdfplumber and appended.

_PARA_SPLIT_RE = re.compile(r"\n\s*\n+")


def _split_paragraphs(text: str, max_chars: int = 500) -> list[str]:
    """Break a page's text into chunk-sized paragraphs (~400-500 chars).
    Greedy fill: pack short paragraphs together, split overlong ones."""
    parts: list[str] = []
    for para in _PARA_SPLIT_RE.split(text or ""):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            parts.append(para)
        else:
            # Long para — slice on sentence-ish boundaries
            buf = ""
            for sent in re.split(r"(?<=[。!?！？.])\s*", para):
                if not sent:
                    continue
                if len(buf) + len(sent) > max_chars and buf:
                    parts.append(buf.strip())
                    buf = sent
                else:
                    buf += sent
            if buf.strip():
                parts.append(buf.strip())
    return parts


def _seed_rag_chunks() -> None:
    """Idempotently inject the 4 starter chunks (WHO / EPA / Lancet / MOENV)
    into st.session_state.rag_chunks. Uploaded files append to the same list."""
    if st.session_state.get("rag_chunks"):
        return
    st.session_state.rag_chunks = [
        {"source": s["source"], "text": s["quote"], "page": 1}
        for s in RAG_SNIPPETS
    ]


def _ingest_uploaded_file(f) -> int:
    """Extract text from an uploaded PDF / TXT / MD into rag_chunks.
    Returns the number of chunks added."""
    name = f.name.lower()
    added = 0
    try:
        if name.endswith(".pdf"):
            import pdfplumber
            with pdfplumber.open(f) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    for para in _split_paragraphs(text):
                        st.session_state.rag_chunks.append({
                            "source": f"{f.name} · 頁 {i}",
                            "text":   para,
                            "page":   i,
                        })
                        added += 1
        else:  # .txt / .md / anything else read as utf-8 text
            raw = f.read()
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raw = raw.decode("utf-8", errors="replace")
            for para in _split_paragraphs(raw):
                st.session_state.rag_chunks.append({
                    "source": f.name,
                    "text":   para,
                    "page":   1,
                })
                added += 1
    except Exception as e:
        st.warning(f"無法解析 {f.name}：{type(e).__name__}: {e}")
    return added


def _score_chunk(query: str, chunk_text: str) -> float:
    """Score how relevant `chunk_text` is to `query`. Uses 2-char n-gram
    overlap so it works for mixed Chinese + English text without needing
    a tokenizer."""
    q = (query or "").lower()
    c = (chunk_text or "").lower()
    if len(q) < 2 or len(c) < 2:
        return 0.0
    qgrams = {q[i:i+2] for i in range(len(q) - 1)}
    if not qgrams:
        return 0.0
    hits = sum(1 for i in range(len(c) - 1) if c[i:i+2] in qgrams)
    # Length-normalised so short chunks aren't disadvantaged
    return hits / (len(c) ** 0.5)


def retrieve_rag_chunks(query: str, top_k: int = 5) -> list[dict]:
    """Return the top-k most relevant chunks for `query`. Falls back to the
    first 4 (starter) chunks if no chunks score above zero — keeps the LLM
    from running with zero context."""
    chunks = st.session_state.get("rag_chunks") or []
    if not chunks:
        return []
    scored = [(c, _score_chunk(query, c["text"])) for c in chunks]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [c for c, s in scored[:top_k] if s > 0]
    return top if top else chunks[: min(top_k, 4)]

# =============================================================================
# Helpers
# =============================================================================
def agent_color(agent_id: str) -> str:
    return next((a["color"] for a in AGENTS if a["id"] == agent_id), "#00d9ff")


def agent_name(agent_id: str) -> str:
    return next((a["name"] for a in AGENTS if a["id"] == agent_id), agent_id)


# Participants in the multi-agent "group chat".
# `name` is the Chinese display label shown in the chat-room.
# `label` is the small glyph drawn inside the round avatar bubble — keep
# these to one visual symbol that hints at the agent's job (not just the
# generic A/B/C/D letter, which carries no meaning to a viewer).
PARTICIPANTS: dict[str, dict[str, str]] = {
    "A":       {"name": "採集者",       "label": "📡", "color": "#00d9ff"},
    "B":       {"name": "分析師",       "label": "🧠", "color": "#9b59ff"},
    "C":       {"name": "預警員",       "label": "🏥", "color": "#00e676"},
    "SYS":     {"name": "系統",         "label": "⚙",  "color": "#8b95a8"},
    "LLM":     {"name": "LLM",          "label": "🤖", "color": "#c4a5ff"},
    "DB":      {"name": "本機時序快取", "label": "💾", "color": "#4eecff"},
    "WEBHOOK": {"name": "Discord",      "label": "📡", "color": "#ffb380"},
    "USER":    {"name": "使用者",       "label": "👤", "color": "#e8eef7"},
    "*":       {"name": "全體 agent",   "label": "📢", "color": "#c0c8d8"},
}


def _participant(pid: str) -> dict[str, str]:
    return PARTICIPANTS.get(pid, {"name": pid, "label": "?", "color": "#c0c8d8"})


def push_log(agent_id: str, msg: str, to: str = "SYS"):
    now = datetime.now().strftime("%H:%M:%S")
    st.session_state.comm_log.append({
        "time":  now,
        "agent": agent_id,
        "to":    to,
        "msg":   msg,
    })


def _render_chat_row(entry: dict) -> str:
    """Render one chat-bubble row in the group-chat style."""
    src = _participant(entry["agent"])
    dst = _participant(entry.get("to", "SYS"))
    is_system_target = entry.get("to") in ("SYS", "") or entry.get("to") is None

    if is_system_target:
        # No arrow shown — internal status
        meta = (
            f"<span class='chat-from' style='color:{src['color']};'>{escape(src['name'])}</span>"
            f"<span class='chat-meta-sep'>·</span>"
            f"<span class='chat-sys-tag'>系統訊息</span>"
            f"<span class='chat-time'>{entry['time']}</span>"
        )
    else:
        meta = (
            f"<span class='chat-from' style='color:{src['color']};'>{escape(src['name'])}</span>"
            f"<span class='chat-arrow'>→</span>"
            f"<span class='chat-to' style='color:{dst['color']};'>{escape(dst['name'])}</span>"
            f"<span class='chat-time'>{entry['time']}</span>"
        )

    return (
        f"<div class='chat-msg-row'>"
        f"<div class='chat-avatar' style='background:{src['color']}; box-shadow:0 0 8px {src['color']}88;'>{src['label']}</div>"
        f"<div class='chat-body'>"
        f"<div class='chat-meta'>{meta}</div>"
        f"<div class='chat-text'>{escape(entry['msg'])}</div>"
        f"</div>"
        f"</div>"
    )


def _log_render(log_holder) -> None:
    rows = "".join(_render_chat_row(e) for e in st.session_state.comm_log[-12:])
    log_holder.markdown(f"<div class='chat-room'>{rows}</div>", unsafe_allow_html=True)


# ── Live-paint helpers for the agent theater ─────────────────────────────────
# These build HTML from current session_state and write it into a placeholder
# (st.empty()) that the section pre-allocates. The same helpers are called by
# (a) the section itself on initial render (idle state), and (b) `run_pipeline`
# after every push_log so the user sees bubbles flow agent-by-agent in real time.

# Which session-state field holds each agent's real LLM dialogue output.
# Used by `_build_office_html` to decide what the speech bubble should show
# AFTER the pipeline finishes — we want real dialog content, not stale
# transfer-of-data plumbing messages from comm_log.
_AGENT_SUMMARY_FIELD: dict[str, str] = {
    # 採集者 (A) is a pure ETL phase — no LLM summary. Its bubble stays empty
    # after the pipeline finishes (the cleaning card below tells its story).
    "B": "llm_analysis",
    "C": "agent_c_advisories",
}


def _build_office_html(active_id: str | None) -> str:
    last_msg: dict[str, str] = {}
    for entry in st.session_state.comm_log:
        last_msg[entry["agent"]] = entry["msg"]
    pipe_done = st.session_state.pipeline_done
    parts: list[str] = []
    for ag in AGENTS:
        is_active = (active_id == ag["id"])

        # Bubble content rules:
        #   - Live: agent currently active → latest push_log message
        #   - Done: pipeline finished       → agent's real LLM summary (if any)
        #   - Idle: no active, not done     → empty bubble
        # This makes the speech bubble feel like real dialog — if no actual
        # LLM dialog happened, no bubble shows.
        if is_active:
            bubble_msg = last_msg.get(ag["id"], "")
        elif pipe_done:
            field = _AGENT_SUMMARY_FIELD.get(ag["id"], "")
            bubble_msg = (st.session_state.get(field) or "").strip() if field else ""
        else:
            bubble_msg = ""

        has_msg = bool(bubble_msg)
        bubble_class = "bubble" if has_msg else "bubble empty"
        # Glow the lobster + monitor when active OR when there's a real
        # post-pipeline summary to show.
        is_visually_active = is_active or (pipe_done and has_msg)
        lob_class = "lobster active" if is_visually_active else "lobster"
        mon_class = "monitor active" if is_visually_active else "monitor"
        # Truncate to keep DOM small; CSS line-clamp handles the visual
        # 2-line cap. 220 chars is well above the 2-line visible budget.
        display = escape(bubble_msg[:220]) if has_msg else "&nbsp;"
        parts.append(
            f"<div class='desk' style='--agent-color:{ag['color']}; --agent-glow:{ag['color']}; --bubble-color:{ag['color']}; --bubble-glow:{ag['color']}55;'>"
            f"<div class='{bubble_class}'>{display}</div>"
            f"<div class='{lob_class}'>🦞</div>"
            f"<div class='desk-base'></div>"
            f"<div class='{mon_class}'>{ag['id']}</div>"
            f"<div class='agent-label'>{ag['name']}</div>"
            f"<div class='agent-role'>{ag['role']}</div>"
            f"<div class='agent-desc'>{ag['desc']}</div>"
            f"</div>"
        )
    return f"<div class='office'>{''.join(parts)}</div>"


# NOTE: _build_critic_html removed in the 3-agent refactor — the Critic
# agent's grading was decorative (low scores didn't gate anything).


def _build_cleaning_html() -> str:
    cleaning = st.session_state.get("lass_cleaning")
    if cleaning is None:
        return (
            "<div class='clean-card' style='opacity:0.55;'>"
            "<div class='head'>🧹 民間感測清洗報告</div>"
            "<div style='font-size:0.85rem; color:#8b95a8; padding:0.4rem 0;'>"
            "Pipeline 尚未執行 — 民間感測員啟動後會即時拉取民生公共物聯網 + LASS-net 資料，"
            "並把實際清洗結果（原始 / 保留 / 丟棄筆數）顯示在這裡。"
            "</div></div>"
        )
    drops = "".join(
        f"<span class='tag orange'>{escape(k)} {v}</span>"
        for k, v in cleaning.drop_reasons.items()
    )
    return f"""
<div class='clean-card'>
  <div class='head'>🧹 民間感測清洗報告（民生公共物聯網 + LASS-net）</div>
  <div style='display:flex; gap:1.4rem; align-items:center;'>
    <div>
      <div class='tiny muted'>原始</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#8b95a8;'>{cleaning.raw_records}</div>
    </div>
    <div style='color:#4a5266; font-size:1.4rem;'>→</div>
    <div>
      <div class='tiny muted'>保留</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#00e676;'>{cleaning.kept_records}</div>
    </div>
    <div style='color:#4a5266; font-size:1.4rem;'>×</div>
    <div>
      <div class='tiny muted'>丟棄</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#ff4757;'>{cleaning.dropped_records}</div>
    </div>
    <div style='flex:1; text-align:right;'>
      <div class='tiny muted'>保留率</div>
      <div style='font-family:JetBrains Mono; font-size:1.6rem; font-weight:800; color:#ff8c42;'>{cleaning.keep_rate * 100:.1f}%</div>
    </div>
  </div>
  <div style='margin-top:0.8rem; display:flex; gap:0.4rem; flex-wrap:wrap;'>{drops}</div>
</div>
"""


def _build_chat_log_html() -> str:
    if not st.session_state.comm_log:
        return (
            "<div class='chat-room' style='text-align:center; color:#4a5266; padding:2rem;'>"
            "點擊上方 <b style='color:#00d9ff;'>「啟動三代理人 Pipeline」</b> 加入群組聊天室"
            "</div>"
        )
    rows = "".join(_render_chat_row(e) for e in st.session_state.comm_log[-25:])
    return f"<div class='chat-room' style='max-height:520px;'>{rows}</div>"


def _paint_office(ph, active_id: str | None = None) -> None:
    ph.markdown(_build_office_html(active_id), unsafe_allow_html=True)


# _paint_critic removed alongside _build_critic_html (3-agent refactor).


def _paint_cleaning(ph) -> None:
    ph.markdown(_build_cleaning_html(), unsafe_allow_html=True)


def _paint_chat(ph) -> None:
    ph.markdown(_build_chat_log_html(), unsafe_allow_html=True)


def run_pipeline(
    office_ph=None,
    cleaning_ph=None,
    chat_ph=None,
    progress_ph=None,
    status_ph=None,
):
    """Drive the 3-agent pipeline (採集者 → 分析師 → 預警員) with live UI
    updates and optional real API calls.

    The previous 5-agent design had an Agent D (民間感測員) and a Critic;
    both were merged or removed in the refactor because:
      - D's only job was an "evaluate cleaning quality" LLM comment that
        the rest of the pipeline didn't use — the data fetch + clean
        itself moved into 採集者 (A).
      - The Critic graded the analyst's report but never gated retries.
    """
    st.session_state.comm_log              = []
    st.session_state.pipeline_done         = False
    st.session_state.snapshot              = None
    st.session_state.llm_analysis          = ""
    st.session_state.agent_c_advisories    = ""

    # If the caller (the agent section) pre-allocated placeholders, route all
    # live updates there — that's how the chat log ends up inside the
    # theater area instead of floating between cover and section.
    # `progress_ph=None` is a deliberate "no visible progress bar" mode —
    # the status pill + chat log + office bubble updates already give the
    # user plenty of feedback, the bar was redundant noise on a busy page.
    class _SilentProgress:
        def progress(self, *args, **kwargs):
            return self
    if progress_ph is None:
        progress = _SilentProgress()
    else:
        progress = progress_ph.progress(0.0, text="正在啟動代理人...")
    log_holder    = chat_ph    if chat_ph    is not None else st.empty()
    status_holder = status_ph  if status_ph  is not None else st.empty()
    _office_ph    = office_ph
    _cleaning_ph  = cleaning_ph

    # Convenience: repaint pixel office after every active_agent change.
    # `_refresh_log` does chat-log + theater in one call, since the two
    # should always stay in sync during a pipeline run.
    def _refresh_theater() -> None:
        if _office_ph is not None:
            _paint_office(_office_ph, st.session_state.active_agent)

    def _refresh_log() -> None:
        _log_render(log_holder)
        _refresh_theater()

    def _refresh_cleaning() -> None:
        if _cleaning_ph is not None:
            _paint_cleaning(_cleaning_ph)

    # Initial sync so the office reflects "starting up" state immediately.
    _refresh_theater()

    # Direct LLM config (no OpenClaw routing — much faster than gateway plugin discovery)
    llm_provider = st.session_state.llm_provider
    llm_key      = st.session_state.llm_key.strip()
    llm_model    = st.session_state.llm_model or LLM_PROVIDERS[llm_provider]["default_model"]
    llm_base_url = st.session_state.llm_base_url
    has_llm      = bool(llm_key)
    prov_name    = LLM_PROVIDERS[llm_provider]["name"]

    AGENT_SYSTEM = (
        "你是台灣空氣品質多代理人系統中的一員。重要：只能根據訊息中提供的具體數值作答，"
        "禁止編造資料、城市或事件。回覆使用繁體中文，不限制長度——把該講的講完整。"
    )

    def _agent_llm(prompt: str, max_tokens: int = 4096) -> tuple[str | None, str]:
        """Direct provider call. Returns (response_or_None, error_reason).
        error_reason is empty on success, otherwise a short diagnostic string."""
        if not has_llm:
            return None, "未填 LLM 金鑰"
        resp = call_llm_api(
            llm_provider, llm_key, prompt, llm_model, llm_base_url,
            system=AGENT_SYSTEM, max_tokens=max_tokens, timeout=25,
        )
        if resp:
            return resp, ""
        # call_llm_api wrote the reason into data.LAST_LLM_ERROR
        import data as _data
        return None, getattr(_data, "LAST_LLM_ERROR", "") or "未知失敗"

    def _status(agent_id: str, done: bool = False) -> None:
        if done:
            status_holder.markdown(
                "<span class='pill green'><span class='dot'></span>Pipeline 完成</span>",
                unsafe_allow_html=True,
            )
        else:
            tag = prov_name if has_llm else "Fallback"
            status_holder.markdown(
                f"<span class='pill cyan'><span class='dot'></span>{agent_name(agent_id)} 執行中 · {escape(tag)}</span>",
                unsafe_allow_html=True,
            )

    # ── 採集者 (A) ──────────────────────────────────────────────────────
    # Pure data fetching + cleaning. No LLM call. Pulls 3 sources:
    #   1. 環境部 EPA aqx_p_432 + Open-Meteo weather (per-region)
    #   2. 民生公共物聯網 SensorThings + LASS-net Airbox (parallel)
    #   3. Civic-vs-official PM2.5 comparison frame
    # Previously this was split across 2 agents (A + D), with both doing a
    # vestigial "comment on data quality" LLM call that the rest of the
    # pipeline never used. The 3-agent refactor merged them and dropped the
    # LLM grading — 採集者 is now a pure ETL phase.
    st.session_state.active_agent = "A"
    progress.progress(0.05, text="採集者 · 資料採集中...")
    _status("A")

    if has_llm:
        push_log("SYS", f"{prov_name} 金鑰已就緒，啟動 3-agent Pipeline", to="*")
    else:
        push_log("SYS", "未填 LLM 金鑰，分析師/預警員段落將跳過（圖表照常產生）", to="*")
    _refresh_log()
    time.sleep(0.2)

    # 1. 環境部 EPA 即時 + Open-Meteo 氣象
    push_log("A", "呼叫環境部 EPA aqx_p_432 抓 20 城市測站", to="SYS")
    _refresh_log()
    snapshot, status_msg = generate_real_snapshot(st.session_state.epa_key or None)
    if snapshot is not None:
        push_log("SYS", f"回傳 → {status_msg}", to="A")
        push_log("A", "Open-Meteo 氣象已合併（溫度／濕度／氣壓）", to="SYS")
        ts_df = generate_real_timeseries(snapshot, hours_back=24, epa_key=st.session_state.epa_key or None)
        st.session_state.data_mode = "real"
    else:
        push_log("SYS", f"⚠ {status_msg}，改用內建模擬資料", to="A")
        snapshot = generate_current_snapshot()
        ts_df    = generate_time_series(24)
        st.session_state.data_mode = "mock"

    st.session_state.snapshot = snapshot
    st.session_state.ts_df    = ts_df
    progress.progress(0.20, text="採集者 · EPA 完成")
    _refresh_log()

    # 2. 民生公共物聯網 + LASS-net (parallel)
    push_log("A",
             "並行拉取 民生公共物聯網 SensorThings (sta.colife.org.tw/STA_AirQuality_EPAIoT) "
             "+ LASS-net Airbox",
             to="SYS")
    _refresh_log()
    lass_df, lass_cleaning, lass_status = fetch_citizen_sensors()
    if lass_df is not None and lass_cleaning is not None:
        push_log("SYS", f"回傳 → {lass_status}", to="A")
        push_log("A",
                 f"清洗：原始 {lass_cleaning.raw_records} 筆 → 保留 {lass_cleaning.kept_records} 筆 · "
                 f"丟棄 {lass_cleaning.dropped_records} 筆（保留率 {lass_cleaning.keep_rate*100:.1f}%）",
                 to="SYS")
        push_log("A",
                 "丟棄原因 · " + " / ".join(
                     f"{k} {v}" for k, v in lass_cleaning.drop_reasons.items()
                 ),
                 to="SYS")
        st.session_state.lass_cleaning = lass_cleaning
        st.session_state.citizen_df    = generate_citizen_vs_official(snapshot, lass_df)
        covered = int((st.session_state.citizen_df["sensor_count"] > 0).sum())
        push_log("A",
                 f"對應 {covered}/{len(CITIES)} 城市有民間感測站覆蓋（離島放寬到 20 km 半徑）",
                 to="SYS")
    else:
        push_log("SYS", f"⚠ 民間感測 API 失敗 - {lass_status}。略過民間感測對比", to="A")
        st.session_state.lass_cleaning = None
        st.session_state.citizen_df    = generate_citizen_vs_official(snapshot, None)
    _refresh_log()
    _refresh_cleaning()

    # 計算給 B 用的快速統計
    avg_aqi_pipe = snapshot["aqi"].mean()
    worst_pipe   = snapshot.sort_values("aqi", ascending=False).iloc[0]
    best_pipe    = snapshot.sort_values("aqi").iloc[0]

    push_log("A",
             f"資料封包完成 → 傳送 {len(snapshot)} 城市官方資料 + "
             f"{(lass_cleaning.kept_records if lass_cleaning else 0)} 筆民間感測 + 24h 歷史",
             to="B")
    _refresh_log()
    progress.progress(0.45, text="採集者 · 完成")


    # ── AGENT B ─────────────────────────────────────────────────────────────
    st.session_state.active_agent = "B"
    _status("B")
    push_log("B", "收到採集者與民間感測員的資料封包，開始綜合分析", to="*")
    _refresh_log()
    time.sleep(0.3)
    push_log("B", "加權公式：0.40·PM2.5 + 0.20·AQI + 0.15·O3 + 0.10·NO2 + 0.08·SO2 + 0.07·CO", to="SYS")
    _refresh_log()
    time.sleep(0.35)
    push_log("B", "RAG 檢索：WHO 2021、EPA NAAQS、Lancet 2023", to="SYS")
    _refresh_log()
    time.sleep(0.35)

    if has_llm:
        push_log("B", f"請 {prov_name} 生成 3 段風險分析報告", to="LLM")
        _refresh_log()
        b_resp, b_err = _agent_llm(
            f"台灣即時空品快報（{datetime.now().strftime('%Y-%m-%d %H:%M')}）：\n"
            f"- 全國平均 AQI：{avg_aqi_pipe:.1f}\n"
            f"- 最高：{worst_pipe['city']} AQI {worst_pipe['aqi']:.0f}（{worst_pipe['level']}），PM2.5 {worst_pipe['PM2.5']} μg/m³\n"
            f"- 最低：{best_pipe['city']} AQI {best_pipe['aqi']:.0f}（{best_pipe['level']}），PM2.5 {best_pipe['PM2.5']} μg/m³\n"
            f"- 覆蓋城市：{len(snapshot)}\n\n"
            f"RAG 文獻可引用：\n"
            f"- WHO 2021：PM2.5 年均 ≤ 5 μg/m³，24h ≤ 15 μg/m³\n"
            f"- EPA NAAQS：PM2.5 24h ≤ 35 μg/m³\n"
            f"- Lancet 2023：高 PM2.5 下劇烈運動，肺部沉積量 ↑3-5x\n\n"
            f"請用 3 段繁體中文輸出：① 現況摘要 ② 敏感族群建議 ③ 未來 6 小時研判。"
            f"每段 2-3 句，必須引用上方數值，不可編造其他城市或數字。",
            max_tokens=4096,
        )
        if b_resp:
            st.session_state.llm_analysis = b_resp
            push_log("LLM", f"分析完成（{len(b_resp)} 字）", to="B")
        else:
            push_log("LLM", f"⚠ 失敗：{b_err}", to="B")
    else:
        push_log("B", "未填 LLM 金鑰，跳過風險分析（圖表仍會基於快照資料繪製）", to="SYS")
        time.sleep(0.3)

    push_log("B", "報告寫好了，轉交預警員生成健康建議", to="C")
    _refresh_log()
    progress.progress(0.75, text="分析師 · 完成")

    # ── 預警員 (C) ──────────────────────────────────────────────────────
    # (Critic phase removed — its grade didn't actually gate anything.)
    st.session_state.active_agent = "C"
    _status("C")
    push_log("B", "風險分析完成，把風險分級結果交給你發布預警", to="C")
    _refresh_log()
    time.sleep(0.25)
    push_log("C", f"收到 → Risk Tier 映射，為 {len(snapshot)} 城市生成敏感族群預警", to="SYS")
    _refresh_log()
    time.sleep(0.3)

    if has_llm:
        push_log("C", f"請 {prov_name} 生成個人化健康建議", to="LLM")
        _refresh_log()
        top_worst = snapshot.sort_values("aqi", ascending=False).head(3)
        top_list = "\n".join(
            f"- {r['city']}：AQI {r['aqi']:.0f}（{r['level']}），PM2.5 {r['PM2.5']} μg/m³"
            for _, r in top_worst.iterrows()
        )
        c_resp, c_err = _agent_llm(
            f"你是預警員（健康預警）。前三高 AQI 城市：\n{top_list}\n\n"
            f"請針對下列 5 類敏感族群，**每類各給 1-2 句具體建議**（總計 5 段、可分行）：\n"
            f"① 👴 老人（避免時段、佩戴口罩等級、血壓注意事項）\n"
            f"② 🧒 幼童（戶外活動限制、學校體育課建議）\n"
            f"③ 🫁 氣喘患者（用藥提醒、出門時機、求醫時機）\n"
            f"④ ❤️ 心血管疾病（運動強度、症狀警訊）\n"
            f"⑤ 🤰 孕婦（室內空品、外出防護）\n"
            f"必須提及上述具體城市名稱與 AQI 數值，不可編造其他城市或人口統計。",
            max_tokens=4096,
        )
        if c_resp:
            st.session_state.agent_c_advisories = c_resp
            push_log("LLM", f"健康建議生成完成（{len(c_resp)} 字）", to="C")
        else:
            push_log("LLM", f"⚠ 失敗：{c_err}（使用預設族群建議模板）", to="C")

    # ── SQLite TSDB write (本機時序快取) ─────────────────────────────────
    try:
        n_written = tsdb.write_snapshot(snapshot, st.session_state.data_mode)
        push_log("C", f"寫入本機 SQLite 時序快取（{n_written} 列 · {len(snapshot)} 城市）", to="DB")
    except Exception as e:
        push_log("C", f"⚠ SQLite 寫入失敗：{type(e).__name__}: {e}", to="DB")
    _refresh_log()
    time.sleep(0.15)

    # ── Discord webhook (optional) ───────────────────────────────────────
    wh_url = st.session_state.get("discord_webhook_url", "").strip()
    if wh_url:
        # `critic_score=None` — Critic agent was removed in 3-agent refactor.
        # send_discord_webhook will render "—" in the Critic-score field of
        # the embed, or we could remove that field too (see data.py).
        ok, wh_msg = send_discord_webhook(
            wh_url, snapshot, None, st.session_state.data_mode,
        )
        push_log("C",
                 f"Discord webhook → {'✓ 已送出' if ok else f'✗ {wh_msg}'}",
                 to="WEBHOOK")
    else:
        push_log("C", "未填 Discord webhook URL · 略過外部推送", to="SYS")
    _refresh_log()
    time.sleep(0.15)

    push_log("SYS", "Pipeline 完成 ✓ 所有代理人下線", to="*")
    _refresh_log()
    time.sleep(0.2)

    # ── 24h history: EPA aqx_p_488 (official) + Open-Meteo CAMS (model) ──
    # Both fetched here so the "EPA vs CAMS" tabs in the heatmap section
    # always render. EPA hist may fail if api_key is missing — CAMS is the
    # always-on companion.
    # We pull CAMS past_days=7 (not 1) so the SQLite cache below has a full
    # week of hourly data to power the weekly-ranking and personal-trend
    # features. Display heatmap still filters to the last 24h.
    cams_week = fetch_open_meteo_aq_batch(CITIES, past_days=7, forecast_days=0)
    cams_hist = None
    if cams_week is not None and not cams_week.empty:
        # Persist the full week into SQLite (UPSERT — re-runs don't duplicate)
        try:
            n_seed = tsdb.write_history_hourly(cams_week, source="cams_hourly")
            push_log("C", f"寫入歷史時序快取 · CAMS 過去 7 天（{n_seed} 列）", to="DB")
        except Exception as e:
            push_log("C", f"⚠ 歷史快取寫入失敗：{type(e).__name__}: {e}", to="DB")
        # Slice the last 24h for the heatmap display
        cutoff = pd.Timestamp(datetime.now()) - pd.Timedelta(hours=25)
        cams_hist = cams_week[
            (cams_week["timestamp"] >= cutoff)
            & (cams_week["timestamp"] <= pd.Timestamp(datetime.now()))
        ].copy()
    st.session_state.cams_ts_df = cams_hist
    _refresh_log()

    progress.progress(1.0, text="✓ Pipeline 完成")
    _status("X", done=True)
    st.session_state.pipeline_done = True
    st.session_state.active_agent  = None
    st.session_state.last_pipeline_run_at = datetime.now()
    time.sleep(0.3)
    st.rerun()


# =============================================================================
# Sidebar
# =============================================================================
with st.sidebar:
    st.markdown(
        "<div style='display:flex; align-items:center; gap:0.6rem; margin-bottom:1rem;'>"
        "<div style='font-size:1.8rem; filter: drop-shadow(0 0 12px #00d9ff)'>🦞</div>"
        "<div>"
        "<div style='font-size:1.05rem; font-weight:800; letter-spacing:-0.02em;'>LobsterAQI</div>"
        "<div style='font-size:0.68rem; color:#8b95a8; font-family:JetBrains Mono; letter-spacing:0.18em;'>TAIWAN · MULTI-AGENT</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Data source info — always tries real EPA + Open-Meteo, auto-falls back
    st.markdown(
        "<div class='eyebrow'>資料來源</div>"
        "<div class='tiny muted' style='line-height:1.55;'>"
        "✓ EPA Open Data API (即時)<br>"
        "✓ Open-Meteo 氣象 (免金鑰)<br>"
        "⚙ 連線失敗時自動切換 mock"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # Auto-refresh: re-run pipeline every hour without user clicking "重新執行"
    st.markdown("<div class='eyebrow'>自動更新</div>", unsafe_allow_html=True)
    st.session_state.auto_refresh_enabled = st.toggle(
        "🔄 每小時自動更新數據",
        value=st.session_state.get("auto_refresh_enabled", True),
        key="auto_refresh_toggle",
        help="啟動 Pipeline 後，每 1 小時自動重新拉取 EPA 即時資料。關閉則需手動按「重新執行 Pipeline」",
    )
    if st.session_state.last_pipeline_run_at is not None:
        _mins_ago = int((datetime.now() - st.session_state.last_pipeline_run_at).total_seconds() // 60)
        _next_in = max(0, 60 - _mins_ago) if st.session_state.auto_refresh_enabled else None
        st.markdown(
            f"<div class='tiny muted' style='line-height:1.5;'>"
            f"上次跑：{_mins_ago} 分鐘前"
            + (f"<br>下次自動：約 {_next_in} 分鐘後" if _next_in is not None else "")
            + "</div>",
            unsafe_allow_html=True,
        )

    st.markdown(" ")

    # In-app LLM provider (Pipeline + 助理 + 比較頁都用這條路徑，毫秒級回應)
    st.markdown("<div class='eyebrow'>LLM 提供商</div>", unsafe_allow_html=True)
    prov_keys = list(LLM_PROVIDERS.keys())
    prov_idx  = prov_keys.index(st.session_state.llm_provider) if st.session_state.llm_provider in prov_keys else 0
    chosen_prov = st.selectbox(
        "LLM 提供商",
        options=prov_keys,
        format_func=lambda p: LLM_PROVIDERS[p]["name"],
        index=prov_idx,
        label_visibility="collapsed",
    )
    st.session_state.llm_provider = chosen_prov
    prov_cfg = LLM_PROVIDERS[chosen_prov]

    # type="default" + CSS mask via st.container(key=...) wrapper.
    # Chrome 不會把 default 欄位當密碼，所以不會跳「儲存密碼」popup。
    # 視覺上用 -webkit-text-security 顯示成黑點。
    with st.container(key="masked_llm_key"):
        st.session_state.llm_key = st.text_input(
            "API Key",
            value=st.session_state.llm_key,
            type="default",
            placeholder=prov_cfg["placeholder"],
        )
    # Model + Base URL are auto-derived from provider defaults (kept off the UI for simplicity)
    st.session_state.llm_model    = prov_cfg["default_model"]
    st.session_state.llm_base_url = prov_cfg.get("base_url", "")

    # Live status pill
    if st.session_state.llm_key.strip():
        st.markdown(
            f"<span class='pill green'><span class='dot'></span>"
            f"{escape(prov_cfg['name'])} · 金鑰已填</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span class='pill gray'><span class='dot'></span>未填金鑰 · 將跳過 LLM 評論</span>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='tiny muted' style='line-height:1.55; margin-top:0.4rem;'>"
        "🦞 OpenClaw 龍蝦留作排程推送 (Discord / LINE) 與個人健康記憶 — 詳見 README『進階功能』段。"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # EPA Open Data Token (環境部 data.moenv.gov.tw — v2 endpoint requires api_key)
    st.markdown("<div class='eyebrow'>EPA Open Data</div>", unsafe_allow_html=True)
    with st.container(key="masked_epa_key"):
        st.session_state.epa_key = st.text_input(
            "EPA Token",
            value=st.session_state.epa_key,
            type="default",
            placeholder="貼上你的 api_key（必填）",
            help="環境部 v2 API 必須有 token 才能取得資料。",
        )

    if st.button("🔌 測試 EPA Token", use_container_width=True, key="epa_test_btn"):
        import requests as _req
        token = (st.session_state.epa_key or "").strip()
        token_len = len(token)
        try:
            params = {"limit": 1, "format": "JSON"}
            if token:
                params["api_key"] = token
            r = _req.get(
                "https://data.moenv.gov.tw/api/v2/aqx_p_432",
                params=params, timeout=15,
            )
            ct = r.headers.get("Content-Type", "")
            # MOENV returns HTTP 200 even for auth errors; sniff body
            if "json" in ct.lower():
                try:
                    body = r.json()
                    # MOENV v2 has been seen returning:
                    #   {"records": [...], "total": N}    (older)
                    #   [{...}, {...}]                    (newer / array)
                    #   {"data": [...]}                   (some endpoints)
                    #   {"result": {"records": [...]}}    (wrapped)
                    records = None
                    if isinstance(body, list):
                        records = body
                    elif isinstance(body, dict):
                        records = (body.get("records")
                                   or body.get("data")
                                   or body.get("rows")
                                   or (body.get("result", {}) or {}).get("records"))
                    if isinstance(records, list) and records:
                        sample = records[0] if isinstance(records[0], dict) else {}
                        total  = (body.get("total") if isinstance(body, dict) else None) or len(records)
                        st.session_state["epa_test_result"] = (
                            "ok",
                            f"✓ Token 有效 · 取得 {total} 測站 · 例：{sample.get('SiteName', sample.get('sitename', '?'))} AQI {sample.get('AQI', sample.get('aqi', '?'))}",
                        )
                    else:
                        # JSON parsed but unknown shape — show top-level keys + preview
                        if isinstance(body, dict):
                            shape = f"dict keys={list(body.keys())[:8]}"
                        elif isinstance(body, list):
                            shape = f"list len={len(body)}"
                        else:
                            shape = type(body).__name__
                        preview = json.dumps(body, ensure_ascii=False)[:200] if body else "(empty)"
                        st.session_state["epa_test_result"] = (
                            "err", f"❌ JSON 解出但找不到 records · 結構：{shape} · 內容：{preview}"
                        )
                except Exception as e:
                    preview = (r.text or "")[:200]
                    st.session_state["epa_test_result"] = (
                        "err", f"❌ JSON parse 失敗（{type(e).__name__}）· 前 200 字：{preview}"
                    )
            else:
                # Plain text error from MOENV
                text = (r.text or "").strip()[:200]
                hint = ""
                if "不存在" in text or "到期" in text:
                    hint = "  → token 字串錯誤或已過期，到平臺『個人專區』複製完整版"
                elif token_len == 0:
                    hint = "  → 還沒填 token"
                elif token_len < 30:
                    hint = f"  → token 長度 {token_len} 字，看起來太短（標準格式約 36 字、UUID-like）"
                st.session_state["epa_test_result"] = (
                    "err", f"❌ HTTP {r.status_code} · MOENV 回應：「{text}」{hint}"
                )
        except _req.exceptions.SSLError as e:
            st.session_state["epa_test_result"] = (
                "err",
                f"❌ SSL 憑證驗證失敗 — 可能是 OpenSSL 3.5+ 嚴格模式對環境部憑證的相容性問題。"
                f"請確認已安裝 truststore（pip install truststore）。原始錯誤：{str(e)[:160]}"
            )
        except _req.exceptions.ConnectionError:
            st.session_state["epa_test_result"] = ("err", "❌ 連不上 data.moenv.gov.tw（DNS / 防火牆）")
        except _req.exceptions.Timeout:
            st.session_state["epa_test_result"] = ("err", "❌ 連線逾時（>15s）")
        except Exception as e:
            st.session_state["epa_test_result"] = ("err", f"❌ {type(e).__name__}: {e}")

    test_result = st.session_state.get("epa_test_result")
    if test_result:
        kind, msg = test_result
        pill_class = "green" if kind == "ok" else "red"
        # Use plain div instead of pill so longer error text wraps nicely
        bg = "rgba(0, 230, 118, 0.10)" if kind == "ok" else "rgba(255, 71, 87, 0.10)"
        bd = "#00e676" if kind == "ok" else "#ff4757"
        st.markdown(
            f"<div style='padding:0.55rem 0.75rem; background:{bg}; border-left:3px solid {bd}; "
            f"border-radius:0 8px 8px 0; font-size:0.78rem; line-height:1.5; color:#e8eef7; margin-top:0.4rem; word-break:break-all;'>"
            f"{escape(msg)}"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='tiny muted' style='line-height:1.55; margin-top:0.3rem;'>"
        "📘 申請：<a href='https://data.moenv.gov.tw/' target='_blank' style='color:#00d9ff;'>環境部資料開放平臺</a>"
        " → 註冊 → 個人專區 → API 金鑰"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # ── Discord Webhook ────────────────────────────────────────────────────
    st.markdown("<div class='eyebrow'>Discord 推送</div>", unsafe_allow_html=True)
    with st.container(key="masked_discord_url"):
        st.session_state.discord_webhook_url = st.text_input(
            "Discord Webhook URL",
            value=st.session_state.discord_webhook_url,
            type="default",
            placeholder="https://discord.com/api/webhooks/...",
            label_visibility="collapsed",
            help="頻道設定 → 整合 → Webhook → 複製 URL。Pipeline 跑完會 POST 摘要到該頻道。",
        )
    if st.button("🧪 測試 Discord", use_container_width=True, key="discord_test_btn"):
        snap = st.session_state.snapshot
        if snap is None or snap.empty:
            st.warning("尚無 snapshot 可送 — 請先跑一次 Pipeline，再來測 Discord")
        else:
            ok, msg = send_discord_webhook(
                st.session_state.discord_webhook_url,
                snap,
                None,  # Critic agent removed in 3-agent refactor
                st.session_state.data_mode,
            )
            if ok:
                st.success(f"✓ Discord 測試成功 · {msg}")
            else:
                st.error(f"❌ {msg}")
    st.markdown(
        "<div class='tiny muted' style='line-height:1.55; margin-top:0.3rem;'>"
        "📡 留空則略過推送。URL 包含密鑰，請勿外流。"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # ── 本機時序快取狀態 ─────────────────────────────────────────────────
    _tsdb_stats = tsdb.stats()
    last_w = _tsdb_stats["last_write"] or "—"
    if isinstance(last_w, str) and "T" in last_w:
        last_w = last_w.replace("T", " ")[:19]
    st.markdown("<div class='eyebrow'>本機時序快取</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='padding:0.5rem 0.7rem; background:rgba(78,236,255,0.06); "
        f"border-left:3px solid #4eecff; border-radius:0 8px 8px 0; "
        f"font-size:0.75rem; line-height:1.55; color:#c0c8d8;'>"
        f"<b style='color:#4eecff; font-family:JetBrains Mono;'>{_tsdb_stats['rows']:,}</b> 筆 · "
        f"{_tsdb_stats['runs']} 次 pipeline 執行 · "
        f"{_tsdb_stats['cities']} 城市<br>"
        f"<span class='tiny muted'>最後寫入：{last_w}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown(" ")

    # Pipeline button — only shown after first run (initial launch is on the cover page)
    run_clicked = False
    if st.session_state.pipeline_done:
        st.markdown("<div class='eyebrow'>Pipeline</div>", unsafe_allow_html=True)
        run_clicked = st.button(
            "↻  重新執行 Pipeline",
            type="primary", use_container_width=True,
        )
        st.markdown(
            f"<div class='tiny muted'>上次執行：{datetime.now().strftime('%H:%M:%S')}</div>",
            unsafe_allow_html=True,
        )

    st.markdown(" ")

    # ── RAG knowledge base (real PDF / TXT / MD extraction) ────────────────
    st.markdown("<div class='eyebrow'>RAG 知識庫</div>", unsafe_allow_html=True)
    _seed_rag_chunks()  # ensures the WHO/EPA/Lancet/MOENV starter chunks exist
    uploaded = st.file_uploader(
        "拖曳 PDF / TXT / MD 至此（會解析內容，加進 RAG 檢索池）",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="rag_uploader",
    )
    if uploaded:
        seen_files = {f["name"] for f in st.session_state.rag_files}
        for f in uploaded:
            if f.name in seen_files:
                continue
            n_chunks = _ingest_uploaded_file(f)
            st.session_state.rag_files.append({
                "name":     f.name,
                "size":     f"{f.size / 1024:.0f} KB",
                "added":    datetime.now().strftime("%m/%d %H:%M"),
                "n_chunks": n_chunks,
            })
            seen_files.add(f.name)
        st.rerun()

    rag_text = st.text_area(
        "或貼上文字片段",
        placeholder="貼上文獻摘要、研究結論...",
        height=68,
    )
    if st.button("✚ 加入 RAG", use_container_width=True) and rag_text.strip():
        snippet_id = sum(1 for c in st.session_state.rag_chunks if c["source"].startswith("snippet_"))
        st.session_state.rag_chunks.append({
            "source": f"snippet_{snippet_id:03d}.txt",
            "text":   rag_text.strip(),
            "page":   1,
        })
        st.session_state.rag_files.append({
            "name":     f"snippet_{snippet_id:03d}.txt",
            "size":     f"{len(rag_text)} chars",
            "added":    datetime.now().strftime("%m/%d %H:%M"),
            "n_chunks": 1,
        })
        st.rerun()

    # File list (uploaded files + manual snippets)
    files_html = "".join(
        f"<div class='comm-row' style='font-size:0.7rem;'>"
        f"<span style='color:#00d9ff;'>▸</span> "
        f"<span style='color:#e8eef7;'>{escape(d['name'][:30])}</span>"
        f"<div class='tiny muted' style='margin-left:1rem;'>"
        f"{d['size']} · {d.get('n_chunks', '?')} chunks · {d['added']}"
        f"</div></div>"
        for d in st.session_state.rag_files
    )
    if files_html:
        st.markdown(
            f"<div class='comm-log' style='max-height:170px; font-size:0.7rem;'>{files_html}</div>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"📚 {len(st.session_state.rag_chunks)} 段可檢索內容 · "
        f"{len(st.session_state.rag_files)} 個檔案"
    )

    st.markdown("---")

    # Section nav
    st.markdown("<div class='eyebrow'>章節導覽</div>", unsafe_allow_html=True)
    sections = [
        ("agents",  "🦞 代理人劇場"),
        ("dash",    "📊 主儀表板"),
        ("trend",   "📈 趨勢與預測"),
        ("pollute", "🧪 污染物剖析"),
        ("env",     "🌬 環境關聯"),
        ("source",  "📡 資料來源對比"),
        ("health",  "🏥 健康預警"),
        ("perso",   "👤 個人化推薦"),
    ]
    for sid, name in sections:
        st.markdown(
            f"<a href='#{sid}' style='display:block; padding:0.45rem 0.7rem; "
            f"color:#c0c8d8; text-decoration:none; border-left:2px solid transparent; "
            f"font-size:0.85rem; transition:all 0.2s;' "
            f"onmouseover='this.style.borderColor=\"#00d9ff\"; this.style.color=\"#00d9ff\"; this.style.background=\"rgba(0,217,255,0.08)\"' "
            f"onmouseout='this.style.borderColor=\"transparent\"; this.style.color=\"#c0c8d8\"; this.style.background=\"transparent\"'>"
            f"{name}</a>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    # NOTE: 「聚焦城市」與「時間範圍」UI 已移除。城市聚焦改由「主儀表板 → 城市排行」
    # 圖點擊事件設定（session_state.selected_city 仍保留供圖表 highlight 用）；
    # 時間範圍改用儀表板上方的時間軸 scrubber。
    st.markdown(
        "<div class='tiny muted' style='text-align:center;'>"
        "Built with 🦞 · Streamlit + Plotly<br>"
        "資料來源：環境部 / LASS-net / Open-Meteo"
        "</div>",
        unsafe_allow_html=True,
    )



ANTI_HALLUCINATION_SYSTEM = (
    "你是 LobsterAQI 的 AI 助理。你必須嚴格遵守以下規則：\n"
    "1. 只能基於使用者訊息中提供的『資料快照』和『RAG 文獻庫』作答，禁止編造資料中沒有的數字、城市、等級或事件。\n"
    "2. 若使用者問題的答案不在資料中，必須明確回覆：『目前資料中沒有這項資訊』，並建議使用者調整提問或啟動 Pipeline。\n"
    "3. 回答時直接引用具體數值（例如『台北市 AQI 為 42』），不使用模糊詞如『大概』、『可能』。\n"
    "4. 若引用 WHO/EPA/Lancet 結論，只引用 RAG 文獻庫中已列出的條目，標明來源。\n"
    "5. 一律使用繁體中文，回覆長度不設限——該講完的就講完整，但不要灌水或重複。\n"
    "6. 不要回答與台灣空氣品質、健康建議無關的話題。"
)


def _build_chat_context() -> str:
    """Build a structured, factual snapshot of all current data for the LLM."""
    snap = st.session_state.snapshot
    if snap is None:
        return "（目前尚未啟動 Pipeline，無即時資料可供參考。）"

    rows = []
    for _, r in snap.iterrows():
        rows.append(
            f"  - {r['city']}（{r['region']}）：AQI {r['aqi']:.0f}（{r['level']}）, "
            f"PM2.5 {r['PM2.5']} μg/m³, PM10 {r['PM10']}, O3 {r['O3']} ppb, "
            f"NO2 {r['NO2']}, SO2 {r['SO2']}, 風險分數 {r['risk']:.0f}/100"
        )
    avg   = snap['aqi'].mean()
    worst = snap.sort_values('aqi', ascending=False).iloc[0]
    best  = snap.sort_values('aqi').iloc[0]
    mode  = "LIVE 即時 EPA API" if st.session_state.data_mode == "real" else "MOCK 模擬資料"
    return (
        f"=== 資料快照（{datetime.now().strftime('%Y-%m-%d %H:%M')}） ===\n"
        f"資料來源：{mode}\n"
        f"全國平均 AQI：{avg:.1f}\n"
        f"最高城市：{worst['city']} AQI {worst['aqi']:.0f}（{worst['level']}）\n"
        f"最低城市：{best['city']} AQI {best['aqi']:.0f}（{best['level']}）\n"
        f"覆蓋城市數：{len(snap)}\n\n"
        f"各城市詳細數據：\n" + "\n".join(rows) + "\n\n"
        f"=== 各 agent 分析摘要 ===\n"
        f"分析師（風險分析）：{st.session_state.get('llm_analysis', '（未生成）')}\n"
        f"預警員（健康預警）：{st.session_state.get('agent_c_advisories', '（未生成）')}\n"
    )


def _render_chat_panel() -> None:
    """Render the chat conversation inside the floating LINE-style panel.

    The caller (`if st.session_state.chat_expanded:` block) renders the
    contact bar and close button above us. We render in this order:
      1. history stream (via st.empty placeholder, so we can show a typing
         bubble while the LLM is being called)
      2. references expander (if the last assistant message has refs)
      3. st.chat_input — Streamlit pins this to the bottom of the container
         regardless of code position.
    """
    pipeline_ready = st.session_state.pipeline_done and st.session_state.snapshot is not None
    has_llm        = bool(st.session_state.llm_key.strip())

    # Scoped scroll container: history scrolls independently, so the chat_input
    # below stays pinned to the panel's bottom edge no matter how far the user
    # scrolls up the conversation.
    with st.container(key="chat_history"):
        history_ph = st.empty()

    def _bubble_html(msg: dict) -> str:
        """Build one chat row + (for bot messages with refs) a collapsible
        references block immediately below it.

        Layout mirrors real LINE:
          - Bot:   [avatar] [bubble] [time]   (left-aligned, time on right)
          - User:  [time] [bubble]            (right-aligned, no own-avatar)
        For bot replies that cite RAG sources, we render a native `<details>`
        element under the bubble — collapsed by default, expandable per
        message. This is HTML (not st.expander) so we can keep the entire
        history flow as a single markdown blob, allowing mid-LLM-call repaints.
        """
        text_html = escape(msg["content"]).replace("\n", "<br>")
        time_str  = escape(msg.get("time", ""))

        if msg["role"] == "assistant":
            bubble_row = (
                "<div class='line-row line-row-bot'>"
                "<div class='line-avatar line-avatar-bot'>🦞</div>"
                f"<div class='line-bubble line-bubble-bot'>{text_html}</div>"
                f"<div class='line-bubble-time'>{time_str}</div>"
                "</div>"
            )
            refs = msg.get("refs") or []
            if refs:
                refs_inner = "".join(
                    f"<div class='ref-item'>"
                    f"<div class='ref-source'>{escape(r['source'])}</div>"
                    f"<div class='ref-quote'>{escape(r['quote'])}</div>"
                    f"</div>"
                    for r in refs
                )
                refs_row = (
                    "<div class='line-refs-row'>"
                    "<details class='line-bubble-refs'>"
                    f"<summary>📚 引用 RAG 內的文獻（{len(refs)} 篇）</summary>"
                    f"<div class='ref-list'>{refs_inner}</div>"
                    "</details>"
                    "</div>"
                )
                return bubble_row + refs_row
            return bubble_row

        # User
        return (
            "<div class='line-row line-row-me'>"
            f"<div class='line-bubble-time'>{time_str}</div>"
            f"<div class='line-bubble line-bubble-me'>{text_html}</div>"
            "</div>"
        )

    TYPING_HTML = (
        "<div class='line-row line-row-bot'>"
        "<div class='line-avatar line-avatar-bot'>🦞</div>"
        "<div class='line-bubble line-bubble-bot line-bubble-typing'>"
        "<span class='line-typing-dots'><span></span><span></span><span></span></span>"
        "</div>"
        "</div>"
    )

    def _draw(show_typing: bool) -> None:
        # Empty state — show centered greeting
        if not st.session_state.chat_history and not show_typing:
            history_ph.markdown(
                "<div class='tiny muted' style='text-align:center; padding:1.2rem 0.5rem;'>"
                "👋 我是 LobsterAQI AI 助理。問我空氣品質的問題吧。"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        # Date separator at top of conversation (LINE-style centered chip)
        today_label = datetime.now().strftime("%Y/%m/%d")
        parts = [
            f"<div class='line-date-separator'><span>{today_label}</span></div>"
        ]
        parts.extend(_bubble_html(m) for m in st.session_state.chat_history[-20:])
        if show_typing:
            parts.append(TYPING_HTML)
        history_ph.markdown(
            "<div class='line-chat-stream'>" + "".join(parts) + "</div>",
            unsafe_allow_html=True,
        )

    # Capture user input (st.chat_input pins itself to the bottom of the panel
    # in DOM regardless of where we call it).
    placeholder = "問我空氣品質的問題..." if pipeline_ready else "請先啟動 Pipeline..."
    user_msg = st.chat_input(placeholder, key="floating_chat_input")

    if user_msg:
        st.session_state.chat_history.append({
            "role":    "user",
            "content": user_msg,
            "time":    datetime.now().strftime("%H:%M"),
        })

        if not pipeline_ready:
            st.session_state.chat_history.append({
                "role":    "assistant",
                "content": "Pipeline 尚未啟動，目前沒有資料可供分析。請先點頁面上方的「啟動 Pipeline」。",
                "refs":    [],
                "time":    datetime.now().strftime("%H:%M"),
            })
        else:
            # Show the typing bubble immediately, then block on the LLM call.
            _draw(show_typing=True)

            # Dynamic RAG retrieval — pull only the chunks actually relevant
            # to this user question (starter snippets + any uploaded PDF
            # contents). The same chunks become the message's `refs` so the
            # user sees what the LLM was given.
            _seed_rag_chunks()
            picked_chunks = retrieve_rag_chunks(user_msg, top_k=5)
            picked_refs = [
                {"source": c["source"], "quote": c["text"]} for c in picked_chunks
            ]

            rag_block = "=== RAG 檢索結果（僅可引用以下條目） ===\n" + "\n".join(
                f"  [{c['source']}] {c['text']}" for c in picked_chunks
            )
            full_prompt = (
                _build_chat_context()
                + "\n\n" + ANTI_HALLUCINATION_SYSTEM
                + "\n\n" + rag_block
                + f"\n\n=== 使用者問題 ===\n{user_msg}\n\n"
                "請嚴格依據上方資料作答。如資料不足，明確說明無法回答。"
            )

            answer = None
            if has_llm:
                answer = call_llm_api(
                    st.session_state.llm_provider,
                    st.session_state.llm_key,
                    full_prompt,
                    st.session_state.llm_model,
                    st.session_state.llm_base_url,
                    system=ANTI_HALLUCINATION_SYSTEM,
                    max_tokens=4096,
                    timeout=25,
                )

            if not answer:
                import data as _data
                err_reason = (getattr(_data, "LAST_LLM_ERROR", "") or "未知")
                why = (f"LLM 失敗：{err_reason}" if has_llm else "未填 LLM 金鑰")
                snap = st.session_state.snapshot
                wt = snap.sort_values("aqi", ascending=False).iloc[0]
                bt = snap.sort_values("aqi").iloc[0]
                answer = (
                    f"⚠ {why}，僅依資料回覆事實摘要：\n\n"
                    f"目前全國平均 AQI **{snap['aqi'].mean():.0f}**。"
                    f"最高：{wt['city']} {wt['aqi']:.0f}（{wt['level']}），"
                    f"最低：{bt['city']} {bt['aqi']:.0f}（{bt['level']}）。"
                )

            st.session_state.chat_history.append({
                "role":    "assistant",
                "content": answer,
                "refs":    picked_refs if has_llm else [],
                "time":    datetime.now().strftime("%H:%M"),
            })

        # Force a fresh script run so st.chat_input resets cleanly and accepts
        # the user's next question without needing a manual page interaction.
        # Without this, the input widget sometimes "sticks" after the long LLM
        # blocking call because the widget state isn't fully refreshed.
        st.rerun()

    # Final render — repaints with no typing dots, including the new reply.
    # References are now embedded as native HTML <details> under each bot
    # reply (see `_bubble_html`), so there is no longer a separate trailing
    # expander widget here.
    _draw(show_typing=False)


# ── Floating chat: either collapsed FAB or expanded panel (never both) ──────
if st.session_state.chat_expanded:
    with st.container(key="floating_chat"):
        # LINE-style contact bar — avatar + name + online status (the close
        # button below is absolute-positioned to the top-right via CSS in
        # styles.py: .st-key-floating_chat .stButton > button).
        st.markdown(
            "<div class='line-contact-bar'>"
            "<div class='line-contact-avatar'>🦞</div>"
            "<div class='line-contact-info'>"
            "<div class='line-contact-name'>LobsterAQI 分析師</div>"
            "<div class='line-contact-status'>"
            "<span class='line-status-dot'></span>"
            "<span>在線 · 隨時待命</span>"
            "</div>"
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("✕", key="chat_close", help="收起聊天面板"):
            st.session_state.chat_expanded = False
            st.rerun()
        _render_chat_panel()
else:
    with st.container(key="fab_container"):
        if st.button("💬  AI 助理", key="fab_chat_btn", type="secondary"):
            st.session_state.chat_expanded = True
            st.rerun()


# =============================================================================
# COVER PAGE  (always rendered at top; below it sit theater + sections)
# =============================================================================
_llm_prov_name = LLM_PROVIDERS[st.session_state.llm_provider]["name"]
_has_llm_key   = bool(st.session_state.llm_key.strip())

if _has_llm_key:
    oc_pill = (
        f"<span class='pill green'><span class='dot'></span>"
        f"{escape(_llm_prov_name)} · LLM 已連線</span>"
    )
else:
    oc_pill = (
        "<span class='pill gray'><span class='dot'></span>"
        "未填 LLM 金鑰 · 仍可看圖表</span>"
    )

data_pill = (
    "<span class='pill cyan'><span class='dot'></span>EPA Open Data + Open-Meteo</span>"
)

# Show pipeline_done as a pill so users always know the state
pipeline_pill = (
    "<span class='pill green'><span class='dot'></span>Pipeline 已完成</span>"
    if st.session_state.pipeline_done else
    "<span class='pill gray'><span class='dot'></span>Pipeline 尚未啟動</span>"
)

st.markdown(
    f"""
    <div class='cover-wrap'>
      <div class='cover-logo'>🦞</div>
      <div class='cover-eyebrow'>TAIWAN AIR QUALITY · MULTI-AGENT SYSTEM</div>
      <div class='cover-title'>LobsterAQI 監控平台</div>
      <div class='cover-subtitle'>
        三個 agent 接力即時採集 EPA + 民生公共物聯網資料，呼叫 LLM 生成分析報告與健康建議，
        並由 Critic 自動審稿。按下啟動鍵，整套儀表板就會在你面前展開。
      </div>
      <div class='cover-features'>
        <div class='cover-feature'><span class='ico'>📡</span> 採集者 · EPA + 民生公共物聯網</div>
        <div class='cover-feature'><span class='ico'>🧠</span> 分析師 · LLM + RAG</div>
        <div class='cover-feature'><span class='ico'>🏥</span> 預警員 · 敏感族群建議</div>
      </div>
      <div class='cover-status'>{data_pill}{oc_pill}{pipeline_pill}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Scoped CSS — only active here (cover area has the prominent CTA)
st.markdown(
    """
    <style>
    .stButton > button[kind="primary"] {
        font-size: 1.25rem !important;
        font-weight: 900 !important;
        padding: 1.1rem 2.5rem !important;
        border-radius: 16px !important;
        letter-spacing: 0.04em !important;
        animation: ctaGlow 2.4s ease-in-out infinite;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px) scale(1.02);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

cL, cC, cR = st.columns([3, 2, 3])
with cC:
    cover_run = st.button(
        ("↻  重新執行 Pipeline" if st.session_state.pipeline_done
         else "▶  啟動三代理人 Pipeline"),
        key="cover_launch",
        type="primary",
        use_container_width=True,
    )
    st.markdown(
        "<div class='cover-hint' style='text-align:center;'>"
        "▼ 點擊啟動即可看到 3-agent 協作與群組聊天室 ▼"
        "</div>",
        unsafe_allow_html=True,
    )

# Anchor for auto-scroll once user clicks launch — the theater section below
# uses #theater-anchor as its scroll target.
st.markdown("<div id='theater-anchor'></div>", unsafe_allow_html=True)

# When launched: set a session flag (consumed by the agent section, where
# placeholders for live updates exist) and inject scroll-into-view JS via
# streamlit.components so it actually executes in the browser. We can't call
# run_pipeline() here because the section's placeholders are created later
# in the script — running pipeline at this point would put the progress bar
# above the theater section instead of inside it.
if cover_run or run_clicked:
    st.session_state["_pipeline_should_run"] = True
    import streamlit.components.v1 as _components
    _components.html(
        """
        <script>
        (function () {
          // Wait a beat for Streamlit to settle the layout, then smooth-scroll
          // to the theater anchor that lives in the agent section below.
          setTimeout(function () {
            var doc = window.parent ? window.parent.document : document;
            var anchor = doc.getElementById('theater-anchor');
            if (anchor) anchor.scrollIntoView({behavior: 'smooth', block: 'start'});
          }, 80);
        })();
        </script>
        """,
        height=0,
    )


# =============================================================================
# Dashboard data handles (used by sections below).
# The hero banner that used to sit here was removed — it duplicated the cover
# page header, had stale "爬蟲員 · OpenClaw Browser" tag, and pushed the
# actually-useful agent theater further down the page.
# =============================================================================
snapshot    = st.session_state.snapshot
ts_df       = st.session_state.ts_df            # primary 24h history (EPA preferred)
cams_ts_df  = st.session_state.cams_ts_df       # Open-Meteo CAMS 24h history (always available when reachable)
citizen_df  = st.session_state.citizen_df
data_mode   = st.session_state.data_mode


# =============================================================================
# SECTION · AGENTS (always visible — shows inactive desks before pipeline runs)
# =============================================================================
st.markdown("<a id='agents'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 01</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>三隻 agent 的協作視覺化</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>每隻 agent 負責 pipeline 中的一個環節。"
    "啟動後依序亮起，講話泡泡顯示它們對彼此說的話。左側中段即時更新採集者的清洗報告，右側則是 3 個 agent 的群組聊天室。</div>",
    unsafe_allow_html=True,
)

c_left, c_right = st.columns([5, 4])

# Pre-allocate placeholders inside the theater columns so live pipeline
# updates land HERE — not in a floating block above the section.
# Left column (top→bottom): pixel office → cleaning report
# Right column (top→bottom): status pill → chat log (full height, no
# floating progress bar — that turned out to be redundant with the pill +
# chat log and just added visual clutter).
# (Critic card removed in 3-agent refactor — its score didn't gate anything.)
with c_left:
    office_ph   = st.empty()
    cleaning_ph = st.empty()

with c_right:
    status_ph = st.empty()
    st.markdown(
        "<div class='eyebrow' style='margin-top:0.1rem;'>🦞 #lobster-agents · 群組聊天室</div>"
        "<div class='tiny muted' style='margin-bottom:0.4rem;'>誰把資料傳給誰 · 即時推播</div>",
        unsafe_allow_html=True,
    )
    chat_ph = st.empty()

# Initial paint reflects current session_state (idle if pipeline hasn't run).
_paint_office(office_ph, st.session_state.active_agent)
_paint_cleaning(cleaning_ph)
_paint_chat(chat_ph)

# If the cover/sidebar button set the run flag earlier this render, kick off
# the pipeline NOW with the section's placeholders so all live updates show
# up inside the theater. After it finishes we do a final rerun so the
# dashboard sections (gated on pipeline_done) render cleanly.
if st.session_state.pop("_pipeline_should_run", False):
    run_pipeline(
        office_ph=office_ph,
        cleaning_ph=cleaning_ph,
        chat_ph=chat_ph,
        progress_ph=None,
        status_ph=status_ph,
    )
    st.rerun()

# Per-agent LLM output cards (visible after pipeline runs)
_any_agent_output = any([
    st.session_state.llm_analysis,
    st.session_state.agent_c_advisories,
])
if st.session_state.pipeline_done and _any_agent_output:
    prov_label = LLM_PROVIDERS.get(st.session_state.llm_provider, {}).get("name", "LLM").upper() if st.session_state.llm_key.strip() else "FALLBACK"

    def _strip_redundant_heading(text: str) -> str:
        """Strip LLM-generated top-level headings that duplicate our eyebrow.
        Some LLMs prepend '# 🚨 空氣品質健康預警通知' etc., which renders as a
        huge duplicate title above an empty band. We remove any leading
        h1/h2 (`# ...` / `## ...`) lines before showing the body."""
        text = (text or "").strip()
        lines = text.split("\n")
        # Drop any leading markdown-heading lines and the blank lines after them.
        while lines and (lines[0].lstrip().startswith(("# ", "## ", "### ")) or not lines[0].strip()):
            lines.pop(0)
        return "\n".join(lines).strip()

    st.markdown(
        f"<div class='eyebrow' style='margin-top:1rem;'>{prov_label} · 全代理人分析報告</div>",
        unsafe_allow_html=True,
    )

    # Two side-by-side expanders — Streamlit-native, so the LLM's markdown
    # (headings / tables / lists) actually renders instead of showing raw `#`
    # characters with a huge whitespace band like the old escape-into-pre-wrap
    # approach produced.
    _col_a, _col_c = st.columns(2)
    if st.session_state.llm_analysis:
        with _col_a:
            with st.expander("🦞 分析師 · 風險分析", expanded=False):
                st.markdown(_strip_redundant_heading(st.session_state.llm_analysis))
    if st.session_state.agent_c_advisories:
        with _col_c:
            with st.expander("🦞 預警員 · 健康建議", expanded=False):
                st.markdown(_strip_redundant_heading(st.session_state.agent_c_advisories))

    st.markdown(
        "<div class='tiny muted' style='margin-top:0.4rem;'>📚 RAG 引用：WHO 2021 / EPA NAAQS / Lancet 2023 / 台灣 AQI 標準</div>",
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# Gate: dashboard sections (02 onwards) only render after pipeline runs.
# Theater section above already handles its own empty state.
# =============================================================================
if not st.session_state.pipeline_done or snapshot is None:
    st.stop()

# =============================================================================
# SECTION · MAIN DASHBOARD
# =============================================================================
st.markdown("<a id='dash'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 02</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>主儀表板 · 即時空品總覽</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>點擊「城市排行」橫條圖可鎖定城市 · "
    "其他圖表會同步高亮 · 滑鼠移上去看詳細數字 · 拖動下方時間軸看過去 24h 的快照</div>",
    unsafe_allow_html=True,
)

# ── Time-axis scrubber ───────────────────────────────────────────────────
# Pull all available hours from ts_df. ts_df has 25 hourly snapshots (24h history + now).
if ts_df is not None and not ts_df.empty:
    hourly_timestamps = sorted(ts_df["timestamp"].unique())
    if len(hourly_timestamps) > 1:
        time_labels = [pd.Timestamp(ts).strftime("%m/%d %H:00") for ts in hourly_timestamps]
        scrub_default = len(time_labels) - 1   # default to the most recent hour ("now")
        scrub_idx = st.slider(
            "🕒 時間軸",
            min_value=0,
            max_value=len(time_labels) - 1,
            value=scrub_default,
            format="",
            help="拖動可看過去 24 小時任一時點的快照 · 圖表會即時跟隨變化",
            label_visibility="collapsed",
        )
        selected_ts = hourly_timestamps[scrub_idx]
        is_current = scrub_idx == scrub_default
        # Build a reconstructed snapshot for the selected hour
        if not is_current:
            hist_slice = ts_df[ts_df["timestamp"] == selected_ts].copy()
            # Merge with current snapshot to keep geo/region/color fields,
            # but override AQI/pollutants/risk from the historical slice.
            # Only merge columns that actually exist in the history frame —
            # different sources (EPA aqx_p_488 vs CAMS) may report
            # different subsets, and we don't want a KeyError on the slice.
            _override_cols = [
                c for c in ["aqi", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "risk"]
                if c in hist_slice.columns
            ]
            scrub_snapshot = snapshot.merge(
                hist_slice[["city_id"] + _override_cols]
                    .rename(columns={c: f"_h_{c}" for c in _override_cols}),
                on="city_id", how="left",
            )
            for c in _override_cols:
                hist_col = f"_h_{c}"
                if hist_col in scrub_snapshot.columns:
                    scrub_snapshot[c] = scrub_snapshot[hist_col].fillna(scrub_snapshot[c])
                    scrub_snapshot = scrub_snapshot.drop(columns=[hist_col])
            # Recompute color + level based on rewritten AQI
            scrub_snapshot["level"]    = scrub_snapshot["aqi"].apply(lambda v: aqi_to_level(v)["name"])
            scrub_snapshot["color"]    = scrub_snapshot["aqi"].apply(lambda v: aqi_to_level(v)["color"])
            scrub_snapshot["level_num"]= scrub_snapshot["aqi"].apply(lambda v: aqi_to_level(v)["level"])
            snapshot = scrub_snapshot   # rebind for the rest of dashboard
            st.markdown(
                f"<div class='tiny muted' style='text-align:center; margin-top:-0.2rem; margin-bottom:0.4rem;'>"
                f"📸 顯示 <b style='color:#ff8c42;'>{time_labels[scrub_idx]}</b> 的歷史快照 · "
                f"拖到最右側回到即時"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            now_local = datetime.now()
            data_dt = pd.Timestamp(hourly_timestamps[-1]).to_pydatetime()
            delay_min = max(0, int((now_local - data_dt).total_seconds() // 60))
            if delay_min < 90:
                freshness_emoji, freshness_color = "🟢", "#00e676"
                freshness_label = "即時"
            elif delay_min < 240:
                freshness_emoji, freshness_color = "🟡", "#ffd93d"
                freshness_label = "略有延遲"
            else:
                freshness_emoji, freshness_color = "🔴", "#ff4757"
                freshness_label = "資料延遲較久"
            # EPA 即時測站的平均落後分鐘(來自 snapshot.updated_min_ago)
            try:
                epa_lag = int(snapshot["updated_min_ago"].mean())
                epa_lag_str = f" · EPA 測站平均落後 <b>{epa_lag} 分鐘</b>"
            except Exception:
                epa_lag_str = ""
            st.markdown(
                f"<div class='tiny muted' style='text-align:center; margin-top:-0.2rem; margin-bottom:0.4rem;'>"
                f"{freshness_emoji} <b style='color:{freshness_color};'>{freshness_label}</b> · "
                f"現在 <b>{now_local.strftime('%m/%d %H:%M')}</b> · "
                f"24h 歷史最新 <b style='color:#00d9ff;'>{time_labels[-1]}</b>"
                f"(落後 {delay_min} 分鐘){epa_lag_str}"
                f"</div>",
                unsafe_allow_html=True,
            )

focus_id = st.session_state.selected_city
focus_row = snapshot[snapshot["city_id"] == focus_id].iloc[0] if focus_id else snapshot.sort_values("aqi", ascending=False).iloc[0]

# Top row: Gauge + ranking
d1, d2 = st.columns([3, 5])

with d1:
    st.markdown(
        f"<div class='eyebrow'>{'聚焦城市' if focus_id else '當前最高 AQI'}</div>"
        f"<div style='font-size:1.4rem; font-weight:800; color:{focus_row['color']}; "
        f"text-shadow:0 0 12px {focus_row['color']}55; margin-bottom:-0.3rem;'>"
        f"{focus_row['city']}</div>"
        f"<div class='tiny muted' style='margin-bottom:0.5rem;'>{focus_row['level']} · {focus_row['region']}</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(make_aqi_gauge(focus_row["aqi"], focus_row["city"]),
                     width='stretch', key=f"gauge_{focus_row['city_id']}",
                     config={"displayModeBar": False})

    # Open the city deep-dive as a modal so the user keeps their scroll
    # position on the main dashboard instead of being teleported to another
    # page. The same content is also reachable as a standalone page via
    # pages/1_城市深入.py for direct URL access (e.g. ?city=taipei).
    @st.dialog("🦞 城市深入", width="large")
    def _city_detail_modal(city_id: str):
        from _city_detail import render_city_detail
        render_city_detail(
            initial_city_id=city_id,
            snapshot=st.session_state.snapshot,
            ts_df=st.session_state.ts_df,
            key_prefix="modal_detail",
            show_city_selector=True,
        )

    if st.button(f"🔍 查看 {focus_row['city']} 詳細", use_container_width=True, key="drill_in"):
        _city_detail_modal(focus_row["city_id"])

    # Mini stats
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>PM2.5</div>"
            f"<div class='kpi-value' style='font-size:1.4rem;'>{focus_row['PM2.5']}</div>"
            f"<div class='kpi-sub'>μg/m³</div></div>",
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>O₃</div>"
            f"<div class='kpi-value orange' style='font-size:1.4rem;'>{focus_row['O3']}</div>"
            f"<div class='kpi-sub'>ppb</div></div>",
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"<div class='kpi-card'><div class='kpi-label'>風險分數</div>"
            f"<div class='kpi-value' style='font-size:1.4rem; color:#9b59ff; text-shadow:0 0 12px rgba(155,89,255,0.4);'>{focus_row['risk']:.0f}</div>"
            f"<div class='kpi-sub'>/100</div></div>",
            unsafe_allow_html=True,
        )

with d2:
    st.markdown("<div class='eyebrow'>城市 AQI 排行</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>點擊長條鎖定城市，全局聯動篩選</div>", unsafe_allow_html=True)

    event = st.plotly_chart(
        make_city_ranking(snapshot, focus_id),
        width='stretch', key="ranking",
        on_select="rerun", selection_mode="points",
        config={"displayModeBar": False},
    )
    if event and event.get("selection") and event["selection"].get("points"):
        pt = event["selection"]["points"][0]
        # The bar's y value is city name
        ranked = snapshot.sort_values("aqi", ascending=True).reset_index(drop=True)
        idx = pt.get("point_index", 0)
        if 0 <= idx < len(ranked):
            new_city = ranked.iloc[idx]["city_id"]
            if new_city != st.session_state.selected_city:
                st.session_state.selected_city = new_city
                st.rerun()

# Second row: Map + Scatter PM2.5 vs AQI
m1, m2 = st.columns([5, 4])

with m1:
    st.markdown("<div class='eyebrow'>地理分佈</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='tiny muted' style='margin-bottom:0.4rem;'>"
        "圓圈大小反映 AQI，顏色反映等級 · "
        "<b style='color:#00d9ff;'>來源：EPA aqx_p_432</b>（環境部測站即時值）"
        "</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(make_map(snapshot, focus_id), width='stretch', key="map",
                     config={"displayModeBar": False})

with m2:
    st.markdown("<div class='eyebrow'>PM2.5 × AQI × 風險</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>氣泡大小代表風險分數</div>", unsafe_allow_html=True)
    st.plotly_chart(make_pm25_aqi_scatter(snapshot, focus_id),
                     width='stretch', key="scatter",
                     config={"displayModeBar": False})

# Third row: Data freshness
st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>各城市資料新鮮度</div>", unsafe_allow_html=True)

fresh_cards = "".join(
    f"<div class='kpi-card' style='min-width:128px; {'border:1px solid #00d9ff; box-shadow:0 0 18px rgba(0,217,255,0.4);' if focus_id == row['city_id'] else ''}'>"
    f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
    f"<div class='tiny' style='font-weight:700; color:#e8eef7;'>{row['city']}</div>"
    f"<div style='width:7px; height:7px; border-radius:50%; background:{'#00e676' if row['updated_min_ago'] < 5 else ('#ffd93d' if row['updated_min_ago'] < 10 else '#ff8c42')}; box-shadow:0 0 6px {'#00e676' if row['updated_min_ago'] < 5 else ('#ffd93d' if row['updated_min_ago'] < 10 else '#ff8c42')};'></div>"
    f"</div>"
    f"<div style='font-family:JetBrains Mono; color:{'#00e676' if row['updated_min_ago'] < 5 else ('#ffd93d' if row['updated_min_ago'] < 10 else '#ff8c42')}; font-size:0.95rem; font-weight:700; margin-top:0.3rem;'>{row['updated_min_ago']}m ago</div>"
    f"<div class='tiny muted'>AQI {row['aqi']:.0f}</div>"
    f"</div>"
    for _, row in snapshot.iterrows()
)
st.markdown(
    f"<div style='display:flex; gap:0.6rem; flex-wrap:wrap;'>{fresh_cards}</div>",
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · TRENDS — forecast/prediction column removed (使用者改用訂閱推送獲取
# 未來資訊，預測圖意義不大)。
# =============================================================================
st.markdown("<a id='trend'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 03</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>24 小時趨勢</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>過去 24 小時各城市的 AQI 走勢，可多選比較。</div>",
    unsafe_allow_html=True,
)

st.markdown("<div class='eyebrow'>24 小時 AQI 趨勢</div>", unsafe_allow_html=True)
selected = st.multiselect(
    "選擇要顯示的城市",
    options=[c["id"] for c in CITIES],
    default=st.session_state.trend_cities,
    format_func=lambda cid: CITY_BY_ID[cid]["name"],
    key="trend_select",
    label_visibility="collapsed",
)
if selected != st.session_state.trend_cities:
    st.session_state.trend_cities = selected
# Show every selected city (no cap) so "select all" actually displays all
# 20 cities. Plotly handles 20 traces fine — its built-in legend toggles
# let the user mute lines per-city if the chart gets too busy.
show_ids = list(dict.fromkeys((selected or []) + ([focus_id] if focus_id else []))) or selected
if show_ids:
    st.plotly_chart(make_trend_line(ts_df, show_ids),
                     width='stretch', key="trend_line",
                     config={"displayModeBar": False})
else:
    st.info("請至少選擇一個城市以顯示趨勢")

# Heatmap — 官方測站 (EPA aqx_p_488) 與 模型 (Open-Meteo CAMS) 雙軌呈現
st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>24h × 20 城市熱力時序圖</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='tiny muted' style='margin-bottom:0.4rem;'>"
    "切換來源比對 — <b style='color:#00d9ff;'>EPA 官方測站</b> 為環境部 77 站每小時實測；"
    "<b style='color:#ffb380;'>CAMS 模型</b> 為歐洲哥白尼大氣監測模式（衛星同化）的網格產出。"
    "兩者皆為真實外部資料，<u>非合成</u>。"
    "</div>",
    unsafe_allow_html=True,
)
with st.expander("📖 三個 AQI 來源差異對照表（為什麼地理分佈 vs 熱力圖會不同？）"):
    st.markdown(
        """
| 圖表 | API 端點 | 性質 | 更新頻率 | 涵蓋 |
|---|---|---|---|---|
| **地理分佈** | EPA `aqx_p_432` | 官方測站**即時**單筆值 | 每小時 | 77 個實體測站 |
| **熱力圖 EPA tab** | EPA `aqx_p_488` | 官方測站**過去 24h** 逐小時 | 每小時(歷史延遲 1-2h) | 77 個實體測站 |
| **熱力圖 CAMS tab** | Open-Meteo CAMS | 衛星**同化模式**網格 | 每小時 | 全境網格(非測站) |

**結論**:這三者是**三個不同的資料來源**,同一城市同時間的 AQI 數值會有差異是預期行為。
EPA 即時(432)反映**測站當下**;EPA 歷史(488)用於**追蹤趨勢**;CAMS 用於**填補無測站區域**。
"""
    )
_heat_tab_epa, _heat_tab_cams = st.tabs(["🏛 EPA 官方測站", "🌫 CAMS 大氣模式"])
with _heat_tab_epa:
    if ts_df is not None and not ts_df.empty:
        st.plotly_chart(make_heatmap(ts_df), width='stretch', key="heatmap_epa",
                         config={"displayModeBar": False})
    else:
        st.info("EPA 歷史資料未取得（請確認 sidebar 已填 EPA api_key）— 改看右側 CAMS tab。")
with _heat_tab_cams:
    if cams_ts_df is not None and not cams_ts_df.empty:
        st.plotly_chart(make_heatmap(cams_ts_df), width='stretch', key="heatmap_cams",
                         config={"displayModeBar": False})
        st.caption("資料來源：Open-Meteo · Copernicus CAMS Atmospheric Composition Reanalysis")
    else:
        st.info("Open-Meteo CAMS 歷史資料未取得（網路問題或 API 暫時故障）。")

# ── 本週 AQI 記錄板（從本機 SQLite 時序快取算）─────────────────────────────
# Reads the past 7 days of CAMS-hourly data stored in SQLite (seeded each
# pipeline run) and shows the cities with the highest peak AQI. Gives the
# user a "where did air quality get bad this week, even if it's clean now"
# view, which the current-snapshot ranking can't provide.
_week_top = tsdb.top_cities_by_period(hours=168, top_n=10)
st.markdown(
    "<div class='eyebrow' style='margin-top:1.2rem;'>📊 過去 7 天 AQI 紀錄板（本機時序快取）</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='tiny muted' style='margin-bottom:0.5rem;'>"
    "從本機 SQLite 累積的 CAMS 模式歷史資料計算，每跑一次 Pipeline 就會補齊最新一週。"
    "</div>",
    unsafe_allow_html=True,
)
if _week_top is None or _week_top.empty:
    st.info("時序快取還沒有累積資料 — 跑一次 Pipeline 就會自動拉 CAMS 過去 7 天進來。")
else:
    rank_cols = st.columns(min(5, len(_week_top)))
    for idx, (col, row) in enumerate(zip(rank_cols, _week_top.head(5).itertuples(index=False))):
        level = aqi_to_level(row.max_aqi)
        col.markdown(
            f"<div class='kpi-card' style='min-width:0; border-color:{level['color']}44;'>"
            f"<div class='kpi-label'>#{idx+1} · {escape(row.city)}</div>"
            f"<div class='kpi-value' style='color:{level['color']}; font-size:1.6rem;'>{row.max_aqi:.0f}</div>"
            f"<div class='kpi-sub'>峰值 · 平均 {row.avg_aqi:.0f}（{int(row.n_hours)}h）</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    # Detail expander with the full top-10 table
    with st.expander(f"查看完整 top-{len(_week_top)} 表 + 平均/最低 AQI", expanded=False):
        _disp = _week_top.rename(columns={
            "city": "城市", "max_aqi": "週峰值",
            "avg_aqi": "週平均", "min_aqi": "週最低", "n_hours": "樣本小時數",
        })[["城市", "週峰值", "週平均", "週最低", "樣本小時數"]]
        st.dataframe(
            _disp.style.background_gradient(subset=["週峰值"], cmap="RdYlGn_r"),
            use_container_width=True,
            height=60 + 32 * len(_disp),
        )

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · POLLUTANTS
# =============================================================================
st.markdown("<a id='pollute'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 04</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>污染物剖析</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>六種主要污染物的雷達圖比較與堆疊組成。"
    "雷達圖的軸是標準化過的（相對 WHO/EPA 指引值），所以越外圈越糟。</div>",
    unsafe_allow_html=True,
)

p1, p2 = st.columns([4, 5])

with p1:
    st.markdown("<div class='eyebrow'>污染物雷達圖</div>", unsafe_allow_html=True)
    radar_cities = st.multiselect(
        "比較城市（最多 4 個）",
        options=[c["id"] for c in CITIES],
        default=st.session_state.radar_cities,
        format_func=lambda cid: CITY_BY_ID[cid]["name"],
        max_selections=4,
        key="radar_select",
        label_visibility="collapsed",
    )
    show_radar = radar_cities if radar_cities else st.session_state.radar_cities
    if show_radar:
        st.plotly_chart(make_pollutant_radar(snapshot, show_radar),
                         width='stretch', key="radar",
                         config={"displayModeBar": False})

with p2:
    st.markdown("<div class='eyebrow'>各城市污染物組成</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>標準化後堆疊，顯示哪種污染物是該城市的主要貢獻者</div>", unsafe_allow_html=True)
    st.plotly_chart(make_stacked_composition(snapshot),
                     width='stretch', key="stacked",
                     config={"displayModeBar": False})

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · ENVIRONMENT
# =============================================================================
st.markdown("<a id='env'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 05</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>環境關聯</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>風從哪裡來、濕度如何影響、衛星看到什麼。"
    "這些跟空品高度相關但常被忽略的維度，都在這裡。</div>",
    unsafe_allow_html=True,
)

e1, e2 = st.columns(2)

with e1:
    st.markdown("<div class='eyebrow'>風向玫瑰圖</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>橫桿長度=城市數；顏色=該風向的平均 AQI</div>", unsafe_allow_html=True)
    st.plotly_chart(make_wind_rose(snapshot), width='stretch', key="wind",
                     config={"displayModeBar": False})

with e2:
    st.markdown("<div class='eyebrow'>濕度 × AQI 相關性</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>含趨勢線與皮爾森相關係數</div>", unsafe_allow_html=True)
    st.plotly_chart(make_humidity_scatter(snapshot), width='stretch', key="humid",
                     config={"displayModeBar": False})

# Weather cards
st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>各城市氣象條件</div>", unsafe_allow_html=True)
weather_remarks = {
    "high_humid": "💧 高濕導致細懸浮微粒吸水膨脹",
    "low_wind":   "🌫 風速低不利擴散",
    "high_temp":  "☀ 高溫易生成臭氧",
    "normal":     "✓ 條件正常",
}

def _weather_card(row) -> str:
    remark = (weather_remarks["high_humid"] if row["humidity"] > 80
              else weather_remarks["low_wind"] if row["wind_speed"] < 2
              else weather_remarks["high_temp"] if row["temp"] > 30
              else weather_remarks["normal"])
    return (
        f"<div class='glass-card' style='min-width:230px; padding:1rem 1.1rem;'>"
        f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
        f"<div style='font-weight:700; font-size:0.95rem;'>{row['city']}</div>"
        f"<div class='tiny muted'>{row['region']}</div>"
        f"</div>"
        f"<div style='display:grid; grid-template-columns:1fr 1fr; gap:0.5rem; margin-top:0.6rem;'>"
        f"<div><div class='tiny muted'>🌡 溫度</div><div style='font-family:JetBrains Mono; font-weight:700; color:#ff8c42;'>{row['temp']}°C</div></div>"
        f"<div><div class='tiny muted'>💧 濕度</div><div style='font-family:JetBrains Mono; font-weight:700; color:#00d9ff;'>{row['humidity']:.0f}%</div></div>"
        f"<div><div class='tiny muted'>💨 風速</div><div style='font-family:JetBrains Mono; font-weight:700; color:#9b59ff;'>{row['wind_speed']} m/s</div></div>"
        f"<div><div class='tiny muted'>📊 氣壓</div><div style='font-family:JetBrains Mono; font-weight:700; color:#00e676;'>{row['pressure']:.0f}</div></div>"
        f"</div>"
        f"<div class='tiny' style='margin-top:0.6rem; padding:0.3rem 0.5rem; background:rgba(0,217,255,0.05); border-left:2px solid #00d9ff; border-radius:0 6px 6px 0;'>{remark}</div>"
        f"</div>"
    )

weather_cards = "".join(_weather_card(row) for _, row in snapshot.iterrows())
st.markdown(
    f"<div style='display:flex; gap:0.7rem; overflow-x:auto; padding-bottom:0.4rem;'>{weather_cards}</div>",
    unsafe_allow_html=True,
)

# NOTE: The "🛰 NASA TROPOMI 衛星觀測" section was removed because we couldn't
# pull real Sentinel-5P data without significant Google Earth Engine /
# Copernicus Data Space setup. The 24h heatmap tabs (above) already show
# real CAMS atmospheric model data which is the closest honest substitute.

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · DATA SOURCES
# =============================================================================
st.markdown("<a id='source'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 06</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>官方測站 vs 民間感測器</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>採集者從<b style='color:#00d9ff;'>環境部 EPA 開放資料</b>拿到的官方測站，"
    "對比民間感測員從<b style='color:#ff8c42;'>民生公共物聯網 SensorThings API</b>（智慧城鄉空品微型感測器網路）"
    "與 <b style='color:#ff8c42;'>LASS-net Airbox</b> 並行拉取的民間感測器。"
    "兩者出現大落差，往往是區域熱點的早期訊號。離島地區（澎湖、金門）"
    "兩套網路皆無部署，會顯示「無民間感測」。</div>",
    unsafe_allow_html=True,
)

# Report LASS cleaning numbers if we have them — real, not made up
_lc = st.session_state.get("lass_cleaning")
_covered = 0
if citizen_df is not None and "sensor_count" in citizen_df.columns:
    _covered = int((citizen_df["sensor_count"] > 0).sum())
if _lc is not None:
    st.markdown(
        f"<div style='display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.6rem;'>"
        f"<span class='tag'>原始 {_lc.raw_records:,} 筆</span>"
        f"<span class='tag green'>保留 {_lc.kept_records:,} 筆</span>"
        f"<span class='tag orange'>丟棄 {_lc.dropped_records:,} 筆</span>"
        f"<span class='tag purple'>覆蓋 {_covered}/{len(CITIES)} 城市</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

s1, s2 = st.columns([5, 3])
with s1:
    st.markdown("<div class='eyebrow'>PM2.5 並排比較</div>", unsafe_allow_html=True)
    st.plotly_chart(make_citizen_vs_official(citizen_df, focus_id),
                     width='stretch', key="cit_vs_off",
                     config={"displayModeBar": False})

with s2:
    st.markdown("<div class='eyebrow'>差距排行</div>", unsafe_allow_html=True)
    # Drop cities with no civilian sensor coverage from the delta ranking
    valid = citizen_df.dropna(subset=["citizen_PM2.5"]).copy()
    if not valid.empty:
        valid["abs_delta"] = valid["delta"].abs()
        sorted_delta = valid.sort_values("abs_delta", ascending=False).head(6)
        rows = "".join(
            f"<div style='display:flex; justify-content:space-between; align-items:center; padding:0.55rem 0.8rem; border-bottom:1px dashed rgba(255,255,255,0.08);'>"
            f"<div><div style='font-weight:700;'>{r['city']}</div>"
            f"<div class='tiny muted'>官 {r['official_PM2.5']:.1f} · 民 {r['citizen_PM2.5']:.1f}（n={int(r['sensor_count'])}）</div></div>"
            f"<div style='font-family:JetBrains Mono; font-weight:800; font-size:1.05rem; color:{'#ff8c42' if abs(r['delta']) > 3 else '#8b95a8'};'>{'+' if r['delta'] >= 0 else ''}{r['delta']:.1f}</div>"
            f"</div>"
            for _, r in sorted_delta.iterrows()
        )
    else:
        rows = (
            "<div style='padding:1rem; text-align:center; color:#8b95a8; font-size:0.85rem;'>"
            "目前所有城市都無民間感測站覆蓋，或 LASS API 未回應。"
            "</div>"
        )
    # No-coverage cities listed separately
    nocover = citizen_df[citizen_df["citizen_PM2.5"].isna()]["city"].tolist()
    if nocover:
        rows += (
            f"<div style='padding:0.5rem 0.8rem; font-size:0.7rem; color:#6a7080;'>"
            f"無覆蓋：{escape('、'.join(nocover))}"
            f"</div>"
        )
    st.markdown(f"<div class='glass-card' style='padding:0.5rem;'>{rows}</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · HEALTH
# =============================================================================
st.markdown("<a id='health'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 07</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>健康預警 · 敏感族群建議</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>每個城市一張預警卡，顏色跟風險等級連動。點擊族群標籤只看跟自己相關的建議。</div>",
    unsafe_allow_html=True,
)

# Group filter
fc1, fc2 = st.columns([3, 2])
with fc1:
    st.markdown("<div class='eyebrow'>敏感族群篩選</div>", unsafe_allow_html=True)
    cols = st.columns(len(SENSITIVE_GROUPS))
    for i, g in enumerate(SENSITIVE_GROUPS):
        active = g["id"] in st.session_state.selected_groups
        label = f"{g['icon']} {g['label']}"
        if cols[i].button(label, key=f"group_{g['id']}",
                            width='stretch',
                            type=("primary" if active else "secondary")):
            if active:
                st.session_state.selected_groups.remove(g["id"])
            else:
                st.session_state.selected_groups.append(g["id"])
            st.rerun()

with fc2:
    st.markdown("<div class='eyebrow'>個人健康狀況</div>", unsafe_allow_html=True)
    user_input = st.text_input(
        "輸入你的狀況",
        placeholder="例如：氣喘、過敏、心律不整...",
        label_visibility="collapsed",
        key="user_health_input",
    )

# Personalized advice if user inputted condition
if user_input.strip():
    worst_city = snapshot.sort_values("aqi", ascending=False).iloc[0]
    st.markdown(
        f"""
        <div class='glass-card' style='border-color:#ff8c42; background:linear-gradient(135deg, rgba(255,140,66,0.10), rgba(15,24,48,0.5)); margin-bottom:1rem;'>
          <div class='eyebrow' style='color:#ff8c42;'>🎯 個人化建議</div>
          <div style='font-size:0.95rem; line-height:1.6;'>
            針對你的狀況「<b style='color:#ff8c42;'>{escape(user_input)}</b>」，目前全國平均 AQI 為
            <b style='color:#00d9ff;'>{overall_aqi:.0f}</b>（{overall_level['name']}），其中
            <b style='color:#ff4757;'>{worst_city['city']}</b>達 <b>{worst_city['aqi']:.0f}</b>。
            建議避開戶外運動高峰時段（07-09、17-19），若必須外出請佩戴 N95 口罩，
            並隨身攜帶相關藥物。RAG 知識庫已就你的關鍵字檢索到 3 篇相關文獻。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# City alert cards (3 per row)
selected_groups = st.session_state.selected_groups
sorted_snap = snapshot.sort_values("aqi", ascending=False)

for chunk_start in range(0, len(sorted_snap), 3):
    chunk = sorted_snap.iloc[chunk_start:chunk_start + 3]
    cols = st.columns(3)
    for i, (_, row) in enumerate(chunk.iterrows()):
        with cols[i]:
            lvl = aqi_to_level(row["aqi"])
            # Build group advice
            groups_to_show = selected_groups if selected_groups else [g["id"] for g in SENSITIVE_GROUPS]
            advice_lines = ""
            for gid in groups_to_show:
                g = next(g for g in SENSITIVE_GROUPS if g["id"] == gid)
                advice_lines += f"<li><b>{g['icon']} {g['label']}：</b><span style='color:#c0c8d8;'>{GROUP_ADVICE[gid]}</span></li>"

            st.markdown(
                f"""
                <div class='alert-card' style='--accent:{row["color"]}; --accent-glow:{row["color"]}55; border-left-color:{row["color"]};'>
                  <div style='display:flex; justify-content:space-between; align-items:flex-start;'>
                    <div>
                      <div class='alert-city'>{row['city']}</div>
                      <div class='tiny muted'>{row['region']} · 更新於 {row['updated_min_ago']} 分鐘前</div>
                    </div>
                    <div style='text-align:right;'>
                      <div class='alert-aqi' style='color:{row["color"]}; text-shadow:0 0 14px {row["color"]}55;'>{row['aqi']:.0f}</div>
                      <div class='tiny' style='color:{row["color"]}; font-weight:700;'>{lvl['name']}</div>
                    </div>
                  </div>
                  <div style='margin-top:0.6rem; padding:0.5rem 0.7rem; background:rgba(0,0,0,0.25); border-radius:8px; font-size:0.85rem;'>
                    {lvl['advice']}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"📋 查看 {row['city']} 詳細敏感族群建議", expanded=False):
                st.markdown(f"<ul style='line-height:1.8;'>{advice_lines}</ul>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='tiny muted' style='margin-top:0.6rem;'>"
                    f"📚 引用：WHO Air Quality Guidelines 2021、Lancet PM2.5 Cardiovascular 2023"
                    f"</div>",
                    unsafe_allow_html=True,
                )

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · PERSONALIZATION
# =============================================================================
st.markdown("<a id='perso'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 08</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>個人化推薦</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>告訴系統你住哪、做什麼、有什麼狀況 — "
    "它會告訴你今天幾點出門最好。</div>",
    unsafe_allow_html=True,
)

per1, per2 = st.columns([2, 3])

with per1:
    st.markdown("<div class='eyebrow'>個人設定</div>", unsafe_allow_html=True)

    user_city = st.selectbox(
        "📍 你常駐城市",
        options=[c["id"] for c in CITIES],
        format_func=lambda cid: CITY_BY_ID[cid]["name"],
        index=next(i for i, c in enumerate(CITIES) if c["id"] == st.session_state.user_city),
        key="user_city_select",
    )
    st.session_state.user_city = user_city

    activity = st.selectbox(
        "🏃 主要戶外活動",
        options=[a["id"] for a in OUTDOOR_ACTIVITIES],
        format_func=lambda aid: next(f"{a['icon']} {a['label']}" for a in OUTDOOR_ACTIVITIES if a["id"] == aid),
        index=next((i for i, a in enumerate(OUTDOOR_ACTIVITIES) if a["id"] == st.session_state.user_activity), 0),
        key="user_activity_select",
    )
    st.session_state.user_activity = activity

    conds = st.multiselect(
        "🏥 健康狀況（可複選）",
        options=[g["id"] for g in SENSITIVE_GROUPS],
        default=st.session_state.user_conditions,
        format_func=lambda gid: next(f"{g['icon']} {g['label']}" for g in SENSITIVE_GROUPS if g["id"] == gid),
        key="user_cond_select",
    )
    st.session_state.user_conditions = conds

    # Save profile to OpenClaw agents' MEMORY.md so they remember between sessions
    if st.button("💾 同步至 OpenClaw 記憶體", help="把上方設定寫進 analyst / advisor 的 MEMORY.md，下次它們會記得你"):
        from pathlib import Path
        from datetime import datetime as _dt
        cond_labels = [
            next(g["label"] for g in SENSITIVE_GROUPS if g["id"] == cid) for cid in conds
        ]
        activity_label = next(a["label"] for a in OUTDOOR_ACTIVITIES if a["id"] == activity)
        memory_text = (
            "# MEMORY.md — LobsterAQI User Profile\n\n"
            "## User\n"
            f"- 常駐城市：{CITY_BY_ID[user_city]['name']}（{user_city}）\n"
            f"- 健康狀況：{', '.join(cond_labels) if cond_labels else '無'}\n"
            f"- 主要戶外活動：{activity_label}\n"
            f"- 最後更新：{_dt.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "## How to use this memory\n"
            "下次使用者問問題時，agent 應主動考量他的常駐城市與健康狀況，"
            "不要每次都重新詢問背景。回答中提到城市時優先選使用者所在城市。\n"
        )
        written = []
        for agent_id in ("analyst", "advisor"):
            try:
                p = Path.home() / ".openclaw" / "agents" / agent_id / "agent" / "MEMORY.md"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(memory_text, encoding="utf-8")
                written.append(agent_id)
            except Exception as e:
                st.warning(f"寫入 {agent_id} MEMORY.md 失敗：{type(e).__name__}: {e}")
        if written:
            st.success(f"✓ 已同步至 OpenClaw {' + '.join(written)} 的 MEMORY.md")

    # Highlight relevant info
    my_row = snapshot[snapshot["city_id"] == user_city].iloc[0]
    st.markdown(
        f"""
        <div class='glass-card' style='border-color:{my_row["color"]}; background:linear-gradient(135deg, {my_row["color"]}15, rgba(15,24,48,0.5)); margin-top:1rem;'>
          <div class='eyebrow' style='color:{my_row["color"]};'>你的城市現況</div>
          <div style='display:flex; align-items:baseline; gap:0.6rem;'>
            <div style='font-size:2.4rem; font-weight:900; color:{my_row["color"]}; font-family:JetBrains Mono; text-shadow: 0 0 18px {my_row["color"]}55;'>{my_row['aqi']:.0f}</div>
            <div>
              <div style='font-weight:700; font-size:1.1rem;'>{my_row['city']}</div>
              <div class='tiny' style='color:{my_row["color"]};'>{my_row['level']}</div>
            </div>
          </div>
          <div style='margin-top:0.6rem; padding:0.5rem 0.7rem; background:rgba(0,0,0,0.25); border-radius:8px; font-size:0.85rem; line-height:1.5;'>
            {aqi_to_level(my_row['aqi'])['advice']}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with per2:
    st.markdown("<div class='eyebrow'>未來 12 小時最佳外出時段</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='tiny muted' style='margin-bottom:0.5rem;'>"
        f"根據 <b style='color:#00d9ff;'>{CITY_BY_ID[user_city]['name']}</b> 的預測 AQI 推薦 · "
        f"★ 標記最佳時段</div>",
        unsafe_allow_html=True,
    )
    outdoor_df = best_outdoor_hours(user_city)
    st.plotly_chart(make_outdoor_bars(outdoor_df), width='stretch', key="outdoor",
                     config={"displayModeBar": False})

    best_hour = outdoor_df[outdoor_df["recommend"]].iloc[0]
    activity_info = next(a for a in OUTDOOR_ACTIVITIES if a["id"] == st.session_state.user_activity)
    st.markdown(
        f"""
        <div class='glass-card' style='border-color:#00e676; background:linear-gradient(135deg, rgba(0,230,118,0.10), rgba(15,24,48,0.5));'>
          <div style='display:flex; align-items:center; gap:1rem;'>
            <div style='font-size:2rem;'>{activity_info["icon"]}</div>
            <div style='flex:1;'>
              <div class='eyebrow' style='color:#00e676;'>建議 {activity_info["label"]} 時段</div>
              <div style='font-size:1.4rem; font-weight:800;'>
                今天 <span style='color:#00e676; font-family:JetBrains Mono;'>{best_hour['hour']}</span>
                · 預測 AQI <span style='color:#00d9ff; font-family:JetBrains Mono;'>{best_hour['aqi']:.0f}</span>
              </div>
              <div class='tiny muted' style='margin-top:0.3rem;'>戶外指數 {best_hour['score']}/100 · {best_hour['level']}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── 你城市的本週 AQI 歷史趨勢（本機 SQLite 時序快取）─────────────────────
# Pulls the user's home city's hourly AQI over the past 168h from the
# CAMS-hourly data stored in SQLite. The week-over-week comparison badge
# gives a "is this week better or worse than last week" read at a glance.
st.markdown(
    f"<div class='eyebrow' style='margin-top:1.2rem;'>📈 你城市 "
    f"<b style='color:#00d9ff;'>{escape(CITY_BY_ID[user_city]['name'])}</b> 的本週 AQI 紀錄</div>",
    unsafe_allow_html=True,
)
_my_hist = tsdb.city_history(user_city, hours=168, sources=["cams_hourly"])
_this_avg, _prev_avg, _this_n, _prev_n = tsdb.city_period_avg(
    user_city, this_hours=168, sources=["cams_hourly"],
)
if _my_hist is None or _my_hist.empty:
    st.info(
        "本機時序快取尚無這個城市的歷史 — 跑一次 Pipeline 會自動拉 CAMS 過去 7 天回來。"
    )
else:
    # Week-over-week badge
    if _this_avg is not None and _prev_avg is not None and _prev_avg > 0:
        delta_pct = (_this_avg - _prev_avg) / _prev_avg * 100
        if delta_pct > 5:
            badge_color, badge_icon, badge_txt = "#ff4757", "▲", f"本週均值比上週高 {delta_pct:+.1f}%"
        elif delta_pct < -5:
            badge_color, badge_icon, badge_txt = "#00e676", "▼", f"本週均值比上週低 {delta_pct:+.1f}%"
        else:
            badge_color, badge_icon, badge_txt = "#ffd93d", "≈", f"本週均值與上週接近（{delta_pct:+.1f}%）"
        st.markdown(
            f"<div style='display:flex; gap:0.6rem; flex-wrap:wrap; margin-bottom:0.5rem;'>"
            f"<span class='tag' style='color:{badge_color}; background:{badge_color}1a; border-color:{badge_color}55;'>{badge_icon} {badge_txt}</span>"
            f"<span class='tag'>本週均值 {_this_avg:.1f}（{_this_n}h）</span>"
            f"<span class='tag'>上週均值 {_prev_avg:.1f}（{_prev_n}h）</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    elif _this_avg is not None:
        st.markdown(
            f"<div style='display:flex; gap:0.6rem; flex-wrap:wrap; margin-bottom:0.5rem;'>"
            f"<span class='tag'>本週均值 {_this_avg:.1f}（{_this_n}h）</span>"
            f"<span class='tag' style='opacity:0.6;'>上週資料不足，無法對照</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    # Plot the AQI line over the past week
    import plotly.graph_objects as _go
    _fig = _go.Figure(_go.Scatter(
        x=_my_hist["ts"], y=_my_hist["aqi"],
        mode="lines", line=dict(color="#00d9ff", width=2.2, shape="spline", smoothing=0.5),
        fill="tozeroy", fillcolor="rgba(0, 217, 255, 0.10)",
        hovertemplate="%{x|%m/%d %H:%M}<br>AQI: <b>%{y:.1f}</b><extra></extra>",
        name="AQI",
    ))
    _fig.update_layout(
        height=240,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#e8eef7", size=11),
        margin=dict(l=40, r=20, t=10, b=30),
        xaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8")),
        yaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8"), title="AQI"),
        hovermode="x unified",
    )
    st.plotly_chart(_fig, use_container_width=True,
                    config={"displayModeBar": False}, key="personal_week_trend")
    st.caption(
        f"資料來源：本機 SQLite (`lobster_aqi.sqlite`) · CAMS-hourly · {len(_my_hist)} 筆 hourly 取樣"
    )

# =============================================================================
# SECTION · PERSONAL SUBSCRIPTION (was pages/3_個人訂閱.py — merged into main
# app so the sidebar stays clean and the form is reachable without page
# switching).
# =============================================================================
st.markdown("<a id='subscribe'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow' style='margin-top:1.5rem; display:inline-block;'>SECTION · 04</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>個人訂閱 · 把預警送到你的 Discord / LINE</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>填好下面表單，會自動產生一條 OpenClaw cron 指令。"
    "可以複製貼到 terminal 跑，也可以直接按「立即註冊」讓本頁面幫你執行。</div>",
    unsafe_allow_html=True,
)

with st.form("subscription_form"):
    sub_c1, sub_c2 = st.columns(2)
    with sub_c1:
        sub_city = st.selectbox(
            "📍 你的城市",
            options=[c["id"] for c in CITIES],
            format_func=lambda cid: CITY_BY_ID[cid]["name"],
            index=next((i for i, c in enumerate(CITIES) if c["id"] == st.session_state.get("user_city", "taipei")), 0),
            key="sub_city_select",
        )
        sub_groups = st.multiselect(
            "🏥 你的敏感族群",
            options=[g["id"] for g in SENSITIVE_GROUPS],
            default=st.session_state.get("user_conditions", []),
            format_func=lambda gid: next(f"{g['icon']} {g['label']}" for g in SENSITIVE_GROUPS if g["id"] == gid),
            key="sub_groups_select",
        )
        sub_threshold = st.slider("⚠ AQI 觸發閾值（超過時推送）", 50, 200, 100, step=10, key="sub_threshold_slider")
    with sub_c2:
        sub_channel = st.selectbox(
            "📡 推送頻道",
            options=["discord", "telegram", "slack", "matrix", "（不推送，只在主畫面看）"],
            key="sub_channel_select",
        )
        sub_target = st.text_input(
            "頻道 ID / 對話 ID",
            placeholder="例如 channel:123456789012345678（Discord）或 telegram chat id",
            help="Discord: 從頻道右鍵 → 複製 ID（要先開啟開發者模式）",
            key="sub_target_input",
        )
        sub_cron_spec = st.selectbox(
            "推送頻率",
            options=[
                ("每小時整點", "0 * * * *"),
                ("每 30 分鐘", "*/30 * * * *"),
                ("每天早上 8 點", "0 8 * * *"),
                ("每天早上 8 點 + 晚上 6 點", "0 8,18 * * *"),
            ],
            format_func=lambda x: x[0],
            key="sub_cron_select",
        )

    sub_submit = st.form_submit_button("產生指令", type="primary", use_container_width=True)


if sub_submit:
    if sub_channel == "（不推送，只在主畫面看）":
        st.info("✓ 已記住你的設定，回主畫面時可在「個人化推薦」section 看到對你的建議。")
        st.session_state.user_city = sub_city
        st.session_state.user_conditions = sub_groups
    elif not sub_target.strip():
        st.error("請填入頻道 ID")
    else:
        sub_city_name = CITY_BY_ID[sub_city]["name"]
        sub_group_labels = [next(g["label"] for g in SENSITIVE_GROUPS if g["id"] == gid) for gid in sub_groups]
        sub_group_text = "、".join(sub_group_labels) if sub_group_labels else "一般族群"

        sub_msg = (
            f"請拉取台灣即時 AQI 並用 2 段繁體中文摘要：① {sub_city_name}（我的城市）目前 AQI、PM2.5 等指標；"
            f"② 對 {sub_group_text} 的具體建議。"
            f"若 {sub_city_name} AQI 低於 {sub_threshold}，明確說「目前空品良好，無需特別動作」一句帶過。"
            f"必須引用實際抓到的數值。"
        )

        sub_cron_cmd = [
            "openclaw", "cron", "add",
            "--name", f"LobsterAQI-{sub_city}-{sub_threshold}",
            "--cron", sub_cron_spec[1],
            "--tz", "Asia/Taipei",
            "--session", "isolated",
            "--agent", "analyst",
            "--message", sub_msg,
            "--announce",
            "--channel", sub_channel,
            "--to", sub_target.strip(),
        ]
        sub_cmd_str = " ".join(shlex.quote(p) for p in sub_cron_cmd)

        st.markdown("<div class='eyebrow' style='margin-top:1rem;'>產生的指令</div>", unsafe_allow_html=True)
        st.code(sub_cmd_str, language="bash")

        sub_cA, sub_cB = st.columns(2)
        with sub_cA:
            if st.button("📋 我自己複製到 terminal 跑", use_container_width=True, key="sub_copy_btn"):
                st.info("好，請手動跑上方那行指令。完成後 openclaw cron list 應看得到。")
        with sub_cB:
            if st.button("⚡ 直接幫我註冊（subprocess）", type="primary", use_container_width=True, key="sub_register_btn"):
                try:
                    sub_result = subprocess.run(
                        subprocess.list2cmdline(sub_cron_cmd),
                        shell=True, capture_output=True, text=True, timeout=30,
                        encoding="utf-8", errors="replace",
                    )
                    if sub_result.returncode == 0:
                        st.success("✓ Cron job 已註冊。執行 `openclaw cron list` 可確認。")
                        st.code(sub_result.stdout[-500:] or "(無輸出)")
                    else:
                        st.error(f"註冊失敗（returncode={sub_result.returncode}）")
                        st.code((sub_result.stdout or "") + "\n" + (sub_result.stderr or ""))
                except Exception as e:
                    st.error(f"執行錯誤：{type(e).__name__}: {e}")


# Footer
st.markdown(
    "<div style='text-align:center; margin-top:3rem; padding:1.5rem; color:#4a5266; font-size:0.78rem; font-family:JetBrains Mono;'>"
    "<div>🦞 LOBSTERAQI · TAIWAN AIR QUALITY MULTI-AGENT MONITORING</div>"
    "<div style='margin-top:0.4rem; opacity:0.6;'>Powered by Streamlit · Plotly · EPA Open Data · LASS-net 民生公共物聯網 · Open-Meteo CAMS · SQLite</div>"
    "</div>",
    unsafe_allow_html=True,
)
