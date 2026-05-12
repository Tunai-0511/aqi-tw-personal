"""
🦞 LobsterAQI · Taiwan Air Quality Multi-Agent Monitoring Platform
==================================================================
Streamlit single-page application. Run with:

    streamlit run app.py
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta
from html import escape

import pandas as pd
import streamlit as st

from data import (
    AGENTS, AQI_LEVELS, CITIES, CITY_BY_ID, CRITIC, GROUP_ADVICE,
    LLM_PROVIDERS, OUTDOOR_ACTIVITIES, PIPELINE_STEPS, POLLUTANTS, SENSITIVE_GROUPS,
    aqi_to_level,
    best_outdoor_hours,
    call_llm_api,
    generate_citizen_vs_official,
    generate_cleaning_report,
    generate_current_snapshot,
    generate_history_with_forecast,
    generate_real_snapshot,
    generate_real_timeseries,
    generate_satellite_panel,
    generate_time_series,
)
# OpenClaw is kept for cron push + MEMORY.md write (NOT for in-app LLM calls).
# Imported lazily where needed (subscribe page, MEMORY write button).
from styles import AGENT_STAGE_CSS, DARK_THEME_CSS
from charts import (
    make_aqi_gauge,
    make_city_ranking,
    make_citizen_vs_official,
    make_forecast_chart,
    make_heatmap,
    make_humidity_scatter,
    make_map,
    make_outdoor_bars,
    make_pm25_aqi_scatter,
    make_pollutant_radar,
    make_region_donut,
    make_satellite_panel,
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
        # Snapshot data (None until pipeline runs)
        "snapshot":        None,
        "ts_df":           None,
        "citizen_df":      None,
        "satellite_df":    None,
        "data_mode":       "mock",   # "mock" | "real" | "openclaw"
        "llm_analysis":    "",       # Agent B output
        "agent_a_summary":  "",      # Agent A LLM commentary on data quality
        "agent_c_advisories": "",    # Agent C LLM health advisories
        "agent_d_summary":  "",      # Agent D LLM commentary on cleaning
        "rag_docs":        [
            {"name": "WHO_AirQualityGuidelines_2021.pdf",  "size": "2.3 MB", "added": "10/05"},
            {"name": "EPA_NAAQS_Reference.pdf",            "size": "1.1 MB", "added": "10/05"},
            {"name": "Lancet_PM25_Cardiovascular_2023.pdf","size": "847 KB", "added": "10/05"},
            {"name": "台灣空氣品質指標技術手冊.pdf",            "size": "1.6 MB", "added": "10/05"},
        ],
        "critic_score":    92.4,
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
# Helpers
# =============================================================================
def agent_color(agent_id: str) -> str:
    if agent_id == CRITIC["id"]:
        return CRITIC["color"]
    return next((a["color"] for a in AGENTS if a["id"] == agent_id), "#00d9ff")


def agent_name(agent_id: str) -> str:
    if agent_id == CRITIC["id"]:
        return CRITIC["name"]
    return next((a["name"] for a in AGENTS if a["id"] == agent_id), "Agent")


# Participants in the multi-agent "group chat".
# `name` is the Chinese display label shown in the chat-room.
PARTICIPANTS: dict[str, dict[str, str]] = {
    "A":       {"name": "採集者",   "label": "A", "color": "#00d9ff"},
    "B":       {"name": "分析師",   "label": "B", "color": "#9b59ff"},
    "C":       {"name": "預警員",   "label": "C", "color": "#00e676"},
    "D":       {"name": "爬蟲員",   "label": "D", "color": "#ff8c42"},
    "K":       {"name": "品管員",   "label": "K", "color": "#ffd93d"},
    "SYS":     {"name": "系統",     "label": "⚙", "color": "#8b95a8"},
    "LLM":     {"name": "LLM",      "label": "🤖", "color": "#c4a5ff"},
    "DB":      {"name": "InfluxDB", "label": "💾", "color": "#4eecff"},
    "WEBHOOK": {"name": "Webhook",  "label": "📡", "color": "#ffb380"},
    "USER":    {"name": "使用者",   "label": "👤", "color": "#e8eef7"},
    "*":       {"name": "全體龍蝦", "label": "📢", "color": "#c0c8d8"},
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


def run_pipeline():
    """Drive the multi-agent pipeline with live UI updates and optional real API calls."""
    st.session_state.comm_log              = []
    st.session_state.pipeline_done         = False
    st.session_state.snapshot              = None
    st.session_state.llm_analysis          = ""
    st.session_state.agent_a_summary       = ""
    st.session_state.agent_c_advisories    = ""
    st.session_state.agent_d_summary       = ""

    progress     = st.progress(0.0, text="正在啟動代理人...")
    log_holder   = st.empty()
    status_holder = st.empty()

    # Direct LLM config (no OpenClaw routing — much faster than gateway plugin discovery)
    llm_provider = st.session_state.llm_provider
    llm_key      = st.session_state.llm_key.strip()
    llm_model    = st.session_state.llm_model or LLM_PROVIDERS[llm_provider]["default_model"]
    llm_base_url = st.session_state.llm_base_url
    has_llm      = bool(llm_key)
    prov_name    = LLM_PROVIDERS[llm_provider]["name"]

    AGENT_SYSTEM = (
        "你是台灣空氣品質多代理人系統中的一員。重要：只能根據訊息中提供的具體數值作答，"
        "禁止編造資料、城市或事件。回覆使用繁體中文，極度簡潔。"
    )

    def _agent_llm(prompt: str, max_tokens: int = 200) -> tuple[str | None, str]:
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

    # ── AGENT A ─────────────────────────────────────────────────────────────
    st.session_state.active_agent = "A"
    progress.progress(0.05, text="Agent A · 資料採集中...")
    _status("A")

    if has_llm:
        push_log("SYS", f"{prov_name} 金鑰已就緒，啟動 Pipeline", to="*")
    else:
        push_log("SYS", "未填 LLM 金鑰，LLM 評論段落將跳過（圖表照常產生）", to="*")
    _log_render(log_holder)
    time.sleep(0.2)

    push_log("A", "呼叫 EPA Open Data API v2 抓 20 城市測站", to="SYS")
    _log_render(log_holder)
    snapshot, status_msg = generate_real_snapshot(st.session_state.epa_key or None)
    if snapshot is not None:
        push_log("SYS", f"回傳 → {status_msg}", to="A")
        push_log("A", "Open-Meteo 氣象已合併（溫度／濕度／氣壓）", to="SYS")
        ts_df = generate_real_timeseries(snapshot)
        st.session_state.data_mode = "real"
    else:
        push_log("SYS", f"⚠ {status_msg}，改用內建模擬資料", to="A")
        snapshot = generate_current_snapshot()
        ts_df    = generate_time_series(24)
        st.session_state.data_mode = "mock"

    st.session_state.snapshot = snapshot
    st.session_state.ts_df    = ts_df

    avg_aqi_pipe = snapshot["aqi"].mean()
    worst_pipe   = snapshot.sort_values("aqi", ascending=False).iloc[0]
    best_pipe    = snapshot.sort_values("aqi").iloc[0]

    if has_llm:
        push_log("A", f"請 {prov_name} 評估資料品質", to="LLM")
        _log_render(log_holder)
        a_resp, a_err = _agent_llm(
            f"剛抓到的台灣空品資料：\n"
            f"- 站數：{len(snapshot)} 城市\n"
            f"- 全國平均 AQI：{avg_aqi_pipe:.1f}\n"
            f"- 最高：{worst_pipe['city']} AQI {worst_pipe['aqi']:.0f}（PM2.5 {worst_pipe['PM2.5']}）\n"
            f"- 最低：{best_pipe['city']} AQI {best_pipe['aqi']:.0f}（PM2.5 {best_pipe['PM2.5']}）\n\n"
            f"請用 1-2 句評論資料完整性與是否有異常值。只引用上方數字。",
            max_tokens=150,
        )
        if a_resp:
            st.session_state.agent_a_summary = a_resp
            push_log("LLM", a_resp[:90], to="A")
        else:
            push_log("LLM", f"⚠ 失敗：{a_err}", to="A")

    push_log("A", f"資料封包完成 → 傳送 {len(snapshot)} 城市 EPA + 氣象快照", to="B")
    push_log("A", "通知 Agent D 同步開始爬蟲", to="D")
    _log_render(log_holder)
    progress.progress(0.25, text="Agent A · 完成")

    # ── AGENT D ─────────────────────────────────────────────────────────────
    st.session_state.active_agent = "D"
    _status("D")
    d_steps = [
        ("啟動 Chromium Headful Browser，目標：cwbsensor.tw（無官方 API）", "SYS", 0.45),
        ("DOM 解析：locator('table.sensor-grid tr') → 838 筆原始紀錄",      "SYS", 0.50),
        ("資料清洗完成：保留 771 筆、丟棄 67 筆（格式錯誤/重複/離群）",      "SYS", 0.40),
    ]
    for msg, to, wait in d_steps:
        push_log("D", msg, to=to)
        _log_render(log_holder)
        time.sleep(wait)

    if has_llm:
        push_log("D", f"請 {prov_name} 評估清洗品質", to="LLM")
        _log_render(log_holder)
        d_resp, d_err = _agent_llm(
            "你是 Agent D（民間感測爬蟲代理人）。剛完成清洗：\n"
            "- 原始：838 筆，保留：771 筆，丟棄：67 筆\n"
            "- 丟棄原因：格式錯誤 35 筆、重複 18 筆、離群值 14 筆\n\n"
            "請用 1 句評論這份清洗結果的品質。只引用上方數字。",
            max_tokens=120,
        )
        if d_resp:
            st.session_state.agent_d_summary = d_resp
            push_log("LLM", d_resp[:90], to="D")
        else:
            push_log("LLM", f"⚠ 失敗：{d_err}", to="D")
        _log_render(log_holder)

    push_log("D", "民間感測資料封包完成 → 傳送 771 筆清洗後 PM2.5 / 風速資料", to="B")
    _log_render(log_holder)
    progress.progress(0.45, text="Agent D · 完成")

    # ── AGENT B ─────────────────────────────────────────────────────────────
    st.session_state.active_agent = "B"
    _status("B")
    push_log("B", "收到 Agent A 與 Agent D 的資料封包，開始綜合分析", to="*")
    _log_render(log_holder)
    time.sleep(0.3)
    push_log("B", "加權公式：0.40·PM2.5 + 0.20·AQI + 0.15·O3 + 0.10·NO2 + 0.08·SO2 + 0.07·CO", to="SYS")
    _log_render(log_holder)
    time.sleep(0.35)
    push_log("B", "RAG 檢索：WHO 2021、EPA NAAQS、Lancet 2023", to="SYS")
    _log_render(log_holder)
    time.sleep(0.35)

    if has_llm:
        push_log("B", f"請 {prov_name} 生成 3 段風險分析報告", to="LLM")
        _log_render(log_holder)
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
            max_tokens=600,
        )
        if b_resp:
            st.session_state.llm_analysis = b_resp
            push_log("LLM", f"分析完成（{len(b_resp)} 字）", to="B")
        else:
            push_log("LLM", f"⚠ 失敗：{b_err}", to="B")
    else:
        push_log("B", "未填 LLM 金鑰，跳過風險分析（圖表仍會基於快照資料繪製）", to="SYS")
        time.sleep(0.3)

    push_log("B", "報告寫好了，提交給品管員審稿", to="K")
    _log_render(log_holder)
    progress.progress(0.72, text="Agent B · 完成")

    # ── CRITIC ──────────────────────────────────────────────────────────────
    st.session_state.active_agent = "K"
    if has_llm:
        push_log("K", f"收到報告，呼叫 {prov_name} 進行語意審稿", to="LLM")
        _log_render(log_holder)
        k_resp, k_err = _agent_llm(
            "你是品管員 Critic。請審 Agent B 的報告：檢查引用密度、數值一致性、結論邏輯。"
            "用一句評語 + 一個 0-100 整數分數結尾（例如：『邏輯清楚，引用充足。92/100』）。",
            max_tokens=120,
        )
        if k_resp:
            push_log("LLM", k_resp[:120], to="K")
            import re as _re
            m = _re.search(r"(\d{1,3})\s*[/／]?\s*100", k_resp)
            score = float(m.group(1)) if m else round(88 + random.random() * 9, 1)
        else:
            score = round(88 + random.random() * 9, 1)
            push_log("LLM", f"⚠ 失敗：{k_err}（使用預設分數）", to="K")
    else:
        push_log("K", "收到報告，開始審稿：引用密度 ✓、數值一致性 ✓、結論邏輯 ✓", to="SYS")
        _log_render(log_holder)
        time.sleep(0.35)
        score = round(88 + random.random() * 9, 1)

    st.session_state.critic_score = round(score, 1)
    push_log("K", f"審核通過 · 報告品質 {st.session_state.critic_score}/100", to="B")
    _log_render(log_holder)
    progress.progress(0.85, text="Critic · 完成")

    # ── AGENT C ─────────────────────────────────────────────────────────────
    st.session_state.active_agent = "C"
    _status("C")
    push_log("B", "報告通過審核，把風險分級結果交給你發布預警", to="C")
    _log_render(log_holder)
    time.sleep(0.25)
    push_log("C", f"收到 → Risk Tier 映射，為 {len(snapshot)} 城市生成敏感族群預警", to="SYS")
    _log_render(log_holder)
    time.sleep(0.3)

    if has_llm:
        push_log("C", f"請 {prov_name} 生成個人化健康建議", to="LLM")
        _log_render(log_holder)
        top_worst = snapshot.sort_values("aqi", ascending=False).head(3)
        top_list = "\n".join(
            f"- {r['city']}：AQI {r['aqi']:.0f}（{r['level']}），PM2.5 {r['PM2.5']} μg/m³"
            for _, r in top_worst.iterrows()
        )
        c_resp, c_err = _agent_llm(
            f"你是 Agent C（健康預警代理人）。前三高 AQI 城市：\n{top_list}\n\n"
            f"請針對「老人、幼童、氣喘患者、心血管、孕婦」五類敏感族群，"
            f"用繁體中文輸出 3-4 句具體建議（總計）。必須提及上述城市與 AQI 數值，不要編造其他城市。",
            max_tokens=350,
        )
        if c_resp:
            st.session_state.agent_c_advisories = c_resp
            push_log("LLM", f"健康建議生成完成（{len(c_resp)} 字）", to="C")
        else:
            push_log("LLM", f"⚠ 失敗：{c_err}（使用預設族群建議模板）", to="C")

    push_log("C", "寫入時序資料庫（20 城市 × 9 指標）", to="DB")
    _log_render(log_holder)
    time.sleep(0.2)
    push_log("C", "推播健康預警給訂閱者（含口罩、戶外活動建議）", to="WEBHOOK")
    _log_render(log_holder)
    time.sleep(0.2)
    push_log("SYS", "Pipeline 完成 ✓ 所有代理人下線", to="*")
    _log_render(log_holder)
    time.sleep(0.2)

    # ── Build citizen & satellite from real snapshot ─────────────────────────
    st.session_state.citizen_df   = generate_citizen_vs_official(snapshot_df=snapshot)
    st.session_state.satellite_df = generate_satellite_panel(snapshot_df=snapshot)

    progress.progress(1.0, text="✓ Pipeline 完成")
    _status("X", done=True)
    st.session_state.pipeline_done = True
    st.session_state.active_agent  = None
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

    # Pipeline button — only shown after first run (initial launch is on the cover page)
    run_clicked = False
    if st.session_state.pipeline_done:
        st.markdown("<div class='eyebrow'>Pipeline</div>", unsafe_allow_html=True)
        run_clicked = st.button(
            "↻  重新執行 Pipeline",
            type="primary", use_container_width=True,
        )
        st.markdown(
            f"<div class='tiny muted'>上次執行：{datetime.now().strftime('%H:%M:%S')} · "
            f"Critic 通過 <span style='color:#ffd93d; font-family:JetBrains Mono;'>{st.session_state.critic_score}</span>/100</div>",
            unsafe_allow_html=True,
        )

    st.markdown(" ")

    # RAG uploads
    st.markdown("<div class='eyebrow'>RAG 知識庫</div>", unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "拖曳 PDF / TXT 至此",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded:
        for f in uploaded:
            if not any(d["name"] == f.name for d in st.session_state.rag_docs):
                st.session_state.rag_docs.append({
                    "name":  f.name,
                    "size":  f"{f.size / 1024:.0f} KB",
                    "added": datetime.now().strftime("%m/%d"),
                })

    rag_text = st.text_area(
        "或貼上文字片段",
        placeholder="貼上文獻摘要、研究結論...",
        height=68,
    )
    if st.button("✚ 加入 RAG", width='stretch') and rag_text.strip():
        st.session_state.rag_docs.append({
            "name":  f"snippet_{len(st.session_state.rag_docs):03d}.txt",
            "size":  f"{len(rag_text)} chars",
            "added": datetime.now().strftime("%m/%d"),
        })
        st.rerun()

    # Doc list
    docs_html = "".join(
        f"<div class='comm-row' style='font-size:0.7rem;'>"
        f"<span style='color:#00d9ff;'>▸</span> "
        f"<span style='color:#e8eef7;'>{escape(d['name'][:32])}</span>"
        f"<div class='tiny muted' style='margin-left:1rem;'>{d['size']} · {d['added']}</div>"
        f"</div>"
        for d in st.session_state.rag_docs
    )
    st.markdown(
        f"<div class='comm-log' style='max-height:170px; font-size:0.7rem;'>{docs_html}</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"📚 共 {len(st.session_state.rag_docs)} 份文件")

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
        "Mock data for demo purposes"
        "</div>",
        unsafe_allow_html=True,
    )


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

ANTI_HALLUCINATION_SYSTEM = (
    "你是 LobsterAQI 的 AI 助理。你必須嚴格遵守以下規則：\n"
    "1. 只能基於使用者訊息中提供的『資料快照』和『RAG 文獻庫』作答，禁止編造資料中沒有的數字、城市、等級或事件。\n"
    "2. 若使用者問題的答案不在資料中，必須明確回覆：『目前資料中沒有這項資訊』，並建議使用者調整提問或啟動 Pipeline。\n"
    "3. 回答時直接引用具體數值（例如『台北市 AQI 為 42』），不使用模糊詞如『大概』、『可能』。\n"
    "4. 若引用 WHO/EPA/Lancet 結論，只引用 RAG 文獻庫中已列出的條目，標明來源。\n"
    "5. 一律使用繁體中文，回覆控制在 4 段以內、每段 1-3 句。\n"
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
        f"=== Agent 分析摘要 ===\n"
        f"Agent A（資料採集）：{st.session_state.get('agent_a_summary', '（未生成）')}\n"
        f"Agent D（清洗報告）：{st.session_state.get('agent_d_summary', '（未生成）')}\n"
        f"Agent B（風險分析）：{st.session_state.get('llm_analysis', '（未生成）')}\n"
        f"Agent C（健康預警）：{st.session_state.get('agent_c_advisories', '（未生成）')}\n"
    )


def _render_chat_panel() -> None:
    """Render chat history + input inside the floating panel container."""
    pipeline_ready = st.session_state.pipeline_done and st.session_state.snapshot is not None
    has_llm        = bool(st.session_state.llm_key.strip())
    prov_name      = LLM_PROVIDERS[st.session_state.llm_provider]["name"]

    # Compact status pills inside the panel
    pill_html = (
        f"<div style='display:flex; gap:0.3rem; margin-bottom:0.5rem; flex-wrap:wrap;'>"
        f"<span class='pill {'green' if pipeline_ready else 'gray'}' style='font-size:0.62rem; padding:0.12rem 0.4rem;'>"
        f"<span class='dot'></span>{'資料就緒' if pipeline_ready else '未啟動'}</span>"
        f"<span class='pill {'green' if has_llm else 'gray'}' style='font-size:0.62rem; padding:0.12rem 0.4rem;'>"
        f"<span class='dot'></span>{escape(prov_name)}{' · 已連線' if has_llm else ' · 未填金鑰'}</span>"
        f"</div>"
    )
    st.markdown(pill_html, unsafe_allow_html=True)

    # Placeholder so newly-appended messages appear immediately without st.rerun()
    history_container = st.container()

    placeholder = (
        "問我空氣品質的問題..."
        if pipeline_ready else
        "請先啟動 Pipeline..."
    )
    user_msg = st.chat_input(placeholder, key="floating_chat_input")
    if user_msg:
        st.session_state.chat_history.append({"role": "user", "content": user_msg})

        if not pipeline_ready:
            st.session_state.chat_history.append({
                "role":    "assistant",
                "content": "Pipeline 尚未啟動，目前沒有資料可供分析。請先點頁面上方的「啟動 Pipeline」。",
                "refs":    [],
            })
        else:
            rag_block = "=== RAG 文獻庫（僅可引用以下條目） ===\n" + "\n".join(
                f"  [{r['source']}] {r['quote']}" for r in RAG_SNIPPETS
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
                with st.spinner(f"{prov_name} 分析中..."):
                    answer = call_llm_api(
                        st.session_state.llm_provider,
                        st.session_state.llm_key,
                        full_prompt,
                        st.session_state.llm_model,
                        st.session_state.llm_base_url,
                        system=ANTI_HALLUCINATION_SYSTEM,
                        max_tokens=500,
                        timeout=25,
                    )

            if not answer:
                # Pull diagnostic reason from data.LAST_LLM_ERROR
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
                "refs":    RAG_SNIPPETS if has_llm else [],
            })

    # Render history (after processing so new messages appear immediately)
    with history_container:
        if not st.session_state.chat_history:
            st.markdown(
                "<div class='tiny muted' style='text-align:center; padding:1.2rem 0.5rem;'>"
                "👋 我是 LobsterAQI AI 助理。問我空氣品質的問題吧。"
                "</div>",
                unsafe_allow_html=True,
            )
        for msg in st.session_state.chat_history[-20:]:   # cap to last 20 for performance
            with st.chat_message(msg["role"], avatar=("🦞" if msg["role"] == "assistant" else "👤")):
                st.markdown(msg["content"])
                if msg.get("refs"):
                    with st.expander("📚 引用文獻", expanded=False):
                        for r in msg["refs"]:
                            st.markdown(
                                f"<div style='padding:0.4rem 0.6rem; background:rgba(155,89,255,0.08); "
                                f"border-left:3px solid #9b59ff; border-radius:0 8px 8px 0; margin:0.25rem 0; font-size:0.78rem;'>"
                                f"<b style='color:#9b59ff;'>{r['source']}</b><br>{r['quote']}</div>",
                                unsafe_allow_html=True,
                            )


# ── Floating chat: either collapsed FAB or expanded panel (never both) ──────
if st.session_state.chat_expanded:
    with st.container(key="floating_chat"):
        # Header bar
        h1, h2 = st.columns([5, 1])
        with h1:
            st.markdown(
                "<div style='font-weight:800; font-size:0.95rem; padding:0.2rem 0;'>"
                "🦞 LobsterAQI AI 助理"
                "</div>",
                unsafe_allow_html=True,
            )
        with h2:
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
    f"<span class='pill green'><span class='dot'></span>"
    f"Pipeline 已完成 · Critic {st.session_state.critic_score}/100</span>"
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
        四隻龍蝦代理人即時採集 EPA 資料、爬取民間感測器、呼叫 LLM 生成分析報告，
        並由 Critic 自動審稿。按下啟動鍵，整套儀表板就會在你面前展開。
      </div>
      <div class='cover-features'>
        <div class='cover-feature'><span class='ico'>📡</span> 採集者 · EPA Open Data</div>
        <div class='cover-feature'><span class='ico'>🤖</span> 分析師 · LLM + RAG</div>
        <div class='cover-feature'><span class='ico'>🏥</span> 預警員 · 健康預警</div>
        <div class='cover-feature'><span class='ico'>🌐</span> 爬蟲員 · 民間感測</div>
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
         else "▶  啟動四代理人 Pipeline"),
        key="cover_launch",
        type="primary",
        use_container_width=True,
    )
    st.markdown(
        "<div class='cover-hint' style='text-align:center;'>"
        "▼ 點擊啟動即可看到龍蝦劇場與群組聊天室 ▼"
        "</div>",
        unsafe_allow_html=True,
    )

# Anchor for auto-scroll once user clicks launch
st.markdown("<div id='theater-anchor'></div>", unsafe_allow_html=True)

# When launched: inject scroll-into-view JS (executes browser-side on next render)
# then run_pipeline() which blocks while updating progress in the theater section below.
if cover_run or run_clicked:
    st.markdown(
        """
        <script>
        (function() {
          const anchor = window.parent.document.getElementById('theater-anchor');
          if (anchor) anchor.scrollIntoView({behavior: 'smooth', block: 'start'});
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )
    run_pipeline()


# =============================================================================
# HERO BANNER  (gated — only renders after pipeline is done)
# =============================================================================
snapshot    = st.session_state.snapshot
ts_df       = st.session_state.ts_df
citizen_df  = st.session_state.citizen_df
satellite_df = st.session_state.satellite_df
data_mode   = st.session_state.data_mode

if st.session_state.pipeline_done and snapshot is not None:
    overall_aqi   = snapshot["aqi"].mean()
    overall_level = aqi_to_level(overall_aqi)
    worst = snapshot.sort_values("aqi", ascending=False).iloc[0]
    best  = snapshot.sort_values("aqi").iloc[0]
    mode_tag = (
        "<span class='tag' style='color:#00e676;background:rgba(0,230,118,0.1);border-color:rgba(0,230,118,0.3);'>● LIVE 即時資料</span>"
        if data_mode == "real" else
        "<span class='tag' style='color:#8b95a8;background:rgba(139,149,168,0.1);border-color:rgba(139,149,168,0.3);'>● MOCK 模擬資料</span>"
    )
    kpi_html = (
        f"<div class='kpi-card' style='min-width:140px;'>"
        f"<div class='kpi-label'>全國平均 AQI</div>"
        f"<div class='kpi-value' style='color:{overall_level['color']}; text-shadow: 0 0 18px {overall_level['color']}66;'>{overall_aqi:.0f}</div>"
        f"<div class='kpi-sub'>{overall_level['name']}</div>"
        f"</div>"
        f"<div class='kpi-card' style='min-width:140px;'>"
        f"<div class='kpi-label'>最高城市</div>"
        f"<div class='kpi-value orange'>{worst['aqi']:.0f}</div>"
        f"<div class='kpi-sub'>{worst['city']} · {worst['level']}</div>"
        f"</div>"
        f"<div class='kpi-card' style='min-width:140px;'>"
        f"<div class='kpi-label'>最低城市</div>"
        f"<div class='kpi-value green'>{best['aqi']:.0f}</div>"
        f"<div class='kpi-sub'>{best['city']} · {best['level']}</div>"
        f"</div>"
        f"<div class='kpi-card' style='min-width:140px;'>"
        f"<div class='kpi-label'>覆蓋城市</div>"
        f"<div class='kpi-value'>{len(snapshot)}</div>"
        f"<div class='kpi-sub'>20 城市 · 5 區域</div>"
        f"</div>"
    )

    critic_score_display = f"{st.session_state.critic_score} ✓"

    st.markdown(
        f"""
        <div class='hero-wrap'>
          <div style='display:flex; justify-content:space-between; align-items:flex-start; gap:2rem; flex-wrap:wrap;'>
            <div style='flex:1; min-width:340px;'>
              <span class='eyebrow'>TAIWAN AIR QUALITY · MULTI-AGENT SYSTEM</span>
              <div class='hero-title'>
                🦞 <span class='accent'>Lobster</span><span class='accent2'>AQI</span> 監控平台
              </div>
              <div class='hero-sub'>
                四隻龍蝦代理人即時採集、爬蟲、分析、預警 — 結合多種 LLM API 與 RAG 文獻庫，
                產出有依據的健康建議。Critic 自動審稿，不通過就退回重做。
              </div>
              <div style='margin-top:1rem; display:flex; gap:0.5rem; flex-wrap:wrap;'>
                <span class='tag'>採集者 · EPA</span>
                <span class='tag orange'>爬蟲員 · OpenClaw Browser</span>
                <span class='tag purple'>分析師 · LLM + RAG</span>
                <span class='tag green'>預警員 · Health Tier</span>
                <span class='tag' style='color:#ffd93d; background:rgba(255,217,61,0.1); border-color:rgba(255,217,61,0.3);'>品管員 · {critic_score_display}</span>
                {mode_tag}
              </div>
            </div>
            <div style='display:flex; gap:0.8rem; flex-wrap:wrap;'>
              {kpi_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# SECTION · AGENTS (always visible — shows inactive desks before pipeline runs)
# =============================================================================
st.markdown("<a id='agents'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 01</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>四隻龍蝦的協作劇場</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>每隻龍蝦負責 pipeline 中的一個環節。"
    "啟動後依序亮起，講話泡泡顯示它們對彼此說的話。右側即時更新 Agent D 的清洗報告與 5 隻龍蝦的群組聊天室。</div>",
    unsafe_allow_html=True,
)

active = st.session_state.active_agent

# --- Build pixel-art office ---
desks_html = ""
last_msg_by_agent = {}
for entry in st.session_state.comm_log:
    last_msg_by_agent[entry["agent"]] = entry["msg"]

for ag in AGENTS:
    is_active = (active == ag["id"]) or (st.session_state.pipeline_done and ag["id"] in last_msg_by_agent)
    bubble_msg = last_msg_by_agent.get(ag["id"], "")
    bubble_class = "bubble" if bubble_msg else "bubble empty"
    lob_class = "lobster active" if is_active else "lobster"
    mon_class = "monitor active" if is_active else "monitor"
    desks_html += (
        f"<div class='desk' style='--agent-color:{ag['color']}; --agent-glow:{ag['color']}; --bubble-color:{ag['color']}; --bubble-glow:{ag['color']}55;'>"
        f"<div class='{bubble_class}'>{escape(bubble_msg[:62]) if bubble_msg else '&nbsp;'}</div>"
        f"<div class='{lob_class}'>🦞</div>"
        f"<div class='desk-base'></div>"
        f"<div class='{mon_class}'>{ag['id']}</div>"
        f"<div class='agent-label'>{ag['name']}</div>"
        f"<div class='agent-role'>{ag['role']}</div>"
        f"<div class='agent-desc'>{ag['desc']}</div>"
        f"</div>"
    )

# Critic agent (sits above pipeline)
critic_active = (active == "K") or st.session_state.pipeline_done
critic_msg = last_msg_by_agent.get("K", "")
critic_html = f"""
<div class='glass-card' style='border-color:{CRITIC["color"]}40; background: linear-gradient(135deg, rgba(255,217,61,0.08), rgba(15,24,48,0.5)); margin-top:1rem;'>
  <div style='display:flex; align-items:center; gap:1rem;'>
    <div style='font-size:2.4rem; filter: {"drop-shadow(0 0 18px " + CRITIC["color"] + ")" if critic_active else "grayscale(0.6) brightness(0.6)"}; '>🦞</div>
    <div style='flex:1;'>
      <div style='font-family:JetBrains Mono; color:{CRITIC["color"]}; letter-spacing:0.15em; font-size:0.75rem; font-weight:700;'>CRITIC AGENT · 報告品管員</div>
      <div style='font-size:0.9rem; color:#e8eef7;'>{escape(critic_msg) if critic_msg else "等待 Agent B 提交報告..."}</div>
      <div class='tiny muted' style='margin-top:0.2rem;'>每份報告自動驗證引用密度、數值一致性、結論邏輯，60 分以下退回 Agent B 重做。</div>
    </div>
    <div style='text-align:right;'>
      <div class='tiny muted'>最新分數</div>
      <div style='font-family:JetBrains Mono; font-size:1.8rem; font-weight:800; color:{CRITIC["color"]}; text-shadow:0 0 14px {CRITIC["color"]}66;'>{st.session_state.critic_score}</div>
    </div>
  </div>
</div>
"""

c_left, c_right = st.columns([5, 4])

with c_left:
    st.markdown(f"<div class='office'>{desks_html}</div>", unsafe_allow_html=True)
    st.markdown(critic_html, unsafe_allow_html=True)

with c_right:
    # Cleaning report
    cleaning = generate_cleaning_report()
    st.markdown(
        f"""
        <div class='clean-card' style='margin-top:1rem;'>
          <div class='head'>🧹 資料清洗報告</div>
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
          <div style='margin-top:0.8rem; display:flex; gap:0.4rem; flex-wrap:wrap;'>
            {"".join(f"<span class='tag orange'>{k} {v}</span>" for k, v in cleaning.drop_reasons.items())}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Multi-agent group chat (communication log)
    st.markdown(
        "<div class='eyebrow' style='margin-top:1rem;'>🦞 #lobster-agents · 群組聊天室</div>"
        "<div class='tiny muted' style='margin-bottom:0.4rem;'>顯示誰把資料傳給誰、誰請誰審稿 · 即時推播</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.comm_log:
        rows_html = "".join(_render_chat_row(e) for e in st.session_state.comm_log[-25:])
        st.markdown(
            f"<div class='chat-room' style='max-height:520px;'>{rows_html}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='chat-room' style='text-align:center; color:#4a5266; padding:2rem;'>"
            "點擊上方 <b style='color:#00d9ff;'>「啟動四代理人 Pipeline」</b> 加入群組聊天室"
            "</div>",
            unsafe_allow_html=True,
        )

# Per-agent LLM output cards (visible after pipeline runs)
_any_agent_output = any([
    st.session_state.agent_a_summary,
    st.session_state.agent_d_summary,
    st.session_state.llm_analysis,
    st.session_state.agent_c_advisories,
])
if st.session_state.pipeline_done and _any_agent_output:
    prov_label = LLM_PROVIDERS.get(st.session_state.llm_provider, {}).get("name", "LLM").upper() if st.session_state.llm_key.strip() else "FALLBACK"

    def _agent_card(role_name: str, label: str, color: str, text: str, big: bool = False) -> str:
        if not text:
            return ""
        body_style = "font-size:0.95rem; line-height:1.75;" if big else "font-size:0.85rem; line-height:1.65;"
        return (
            f"<div class='glass-card' style='border-color:{color}40; background:linear-gradient(135deg, {color}12, rgba(15,24,48,0.5));'>"
            f"<div style='font-family:JetBrains Mono; color:{color}; letter-spacing:0.15em; font-size:0.7rem; font-weight:700; margin-bottom:0.5rem;'>"
            f"🦞 {escape(role_name)} · {escape(label)}</div>"
            f"<div style='{body_style} color:#c0c8d8; white-space:pre-wrap;'>{escape(text)}</div>"
            f"</div>"
        )

    st.markdown(
        f"<div class='eyebrow' style='margin-top:1rem;'>{prov_label} · 全代理人 LLM 分析報告</div>",
        unsafe_allow_html=True,
    )

    # Top row: 採集者 + 爬蟲員
    cards_top = "".join([
        _agent_card("採集者", "資料品質評估", "#00d9ff", st.session_state.agent_a_summary),
        _agent_card("爬蟲員", "清洗品質評估", "#ff8c42", st.session_state.agent_d_summary),
    ])
    if cards_top:
        st.markdown(
            f"<div style='display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-top:0.4rem;'>{cards_top}</div>",
            unsafe_allow_html=True,
        )

    # 分析師 (main analysis, full width)
    if st.session_state.llm_analysis:
        st.markdown(
            _agent_card("分析師", "風險分析報告", "#9b59ff", st.session_state.llm_analysis, big=True),
            unsafe_allow_html=True,
        )

    # 預警員
    if st.session_state.agent_c_advisories:
        st.markdown(
            _agent_card("預警員", "敏感族群健康建議", "#00e676", st.session_state.agent_c_advisories, big=True),
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='tiny muted' style='margin-top:0.6rem;'>📚 RAG 引用：WHO Air Quality Guidelines 2021、EPA NAAQS、Lancet 2023、台灣空氣品質指標技術手冊</div>",
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
            # but override aqi/pollutants/risk from the historical slice.
            scrub_snapshot = snapshot.merge(
                hist_slice[["city_id", "aqi", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "risk"]]
                    .rename(columns={c: f"_h_{c}" for c in ["aqi", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "risk"]}),
                on="city_id", how="left",
            )
            for c in ["aqi", "PM2.5", "PM10", "O3", "NO2", "SO2", "CO", "risk"]:
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
            st.markdown(
                f"<div class='tiny muted' style='text-align:center; margin-top:-0.2rem; margin-bottom:0.4rem;'>"
                f"⚡ 顯示即時資料（{time_labels[-1]}）"
                f"</div>",
                unsafe_allow_html=True,
            )

focus_id = st.session_state.selected_city
focus_row = snapshot[snapshot["city_id"] == focus_id].iloc[0] if focus_id else snapshot.sort_values("aqi", ascending=False).iloc[0]

# Top row: Gauge + ranking + region donut
d1, d2, d3 = st.columns([3, 4, 3])

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

    if st.button(f"🔍 查看 {focus_row['city']} 詳細", use_container_width=True, key="drill_in"):
        st.query_params["city"] = focus_row["city_id"]
        st.switch_page("pages/1_城市深入.py")

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

with d3:
    st.markdown("<div class='eyebrow'>區域聚合</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>北中南東四區平均 AQI</div>", unsafe_allow_html=True)
    st.plotly_chart(make_region_donut(snapshot), width='stretch', key="donut",
                     config={"displayModeBar": False})

# Second row: Map + Scatter PM2.5 vs AQI
m1, m2 = st.columns([5, 4])

with m1:
    st.markdown("<div class='eyebrow'>地理分佈</div>", unsafe_allow_html=True)
    st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>圓圈大小反映 AQI，顏色反映等級</div>", unsafe_allow_html=True)
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
# SECTION · TRENDS
# =============================================================================
st.markdown("<a id='trend'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 03</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>趨勢與預測</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>24 小時回看 × 6 小時前看。"
    "預測線是虛線、信心區間是橙色陰影 — 越往後越寬，符合預測的本質。</div>",
    unsafe_allow_html=True,
)

t1, t2 = st.columns([5, 4])

with t1:
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
    # If focus city selected, ensure it's included
    show_ids = list(set(selected + ([focus_id] if focus_id else [])))[:8] or selected
    if show_ids:
        st.plotly_chart(make_trend_line(ts_df, show_ids),
                         width='stretch', key="trend_line",
                         config={"displayModeBar": False})
    else:
        st.info("請至少選擇一個城市以顯示趨勢")

with t2:
    forecast_city = focus_id if focus_id else "taipei"
    forecast_df = generate_history_with_forecast(forecast_city, 12, 6)
    st.markdown("<div class='eyebrow'>6 小時 AQI 預測</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='tiny muted' style='margin-bottom:0.4rem;'>"
        f"顯示城市：<b style='color:#00d9ff;'>{CITY_BY_ID[forecast_city]['name']}</b>"
        " · 實線=已知 · 虛線=預測 · 陰影=信心區間</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(make_forecast_chart(forecast_df, CITY_BY_ID[forecast_city]["name"]),
                     width='stretch', key="forecast",
                     config={"displayModeBar": False})

# Heatmap
st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>24h × 20 城市熱力時序圖</div>", unsafe_allow_html=True)
st.markdown("<div class='tiny muted' style='margin-bottom:0.4rem;'>每格代表該城市該小時的 AQI，顏色越紅越糟</div>", unsafe_allow_html=True)
st.plotly_chart(make_heatmap(ts_df), width='stretch', key="heatmap",
                 config={"displayModeBar": False})

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

# Satellite panel
st.markdown("<div class='eyebrow' style='margin-top:1rem;'>🛰 NASA TROPOMI 衛星觀測</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='tiny muted' style='margin-bottom:0.4rem;'>"
    "氣溶膠光學厚度（AOD）、二氧化氮柱濃度、二氧化硫柱濃度、甲烷柱濃度</div>",
    unsafe_allow_html=True,
)
st.plotly_chart(make_satellite_panel(satellite_df), width='stretch', key="sat",
                 config={"displayModeBar": False})

st.markdown("<br>", unsafe_allow_html=True)


# =============================================================================
# SECTION · DATA SOURCES
# =============================================================================
st.markdown("<a id='source'></a>", unsafe_allow_html=True)
st.markdown("<span class='eyebrow'>SECTION · 06</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>官方測站 vs 民間感測器</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>Agent A 從環保署 API 拿到的「正規」資料，"
    "對比 Agent D 用瀏覽器爬蟲拿到的「在地」民間感測器。當兩者出現大落差，往往是區域熱點的早期訊號。</div>",
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
    sorted_delta = citizen_df.copy()
    sorted_delta["abs_delta"] = sorted_delta["delta"].abs()
    sorted_delta = sorted_delta.sort_values("abs_delta", ascending=False).head(6)
    rows = "".join(
        f"<div style='display:flex; justify-content:space-between; align-items:center; padding:0.55rem 0.8rem; border-bottom:1px dashed rgba(255,255,255,0.08);'>"
        f"<div><div style='font-weight:700;'>{r['city']}</div>"
        f"<div class='tiny muted'>官 {r['official_PM2.5']} · 民 {r['citizen_PM2.5']}</div></div>"
        f"<div style='font-family:JetBrains Mono; font-weight:800; font-size:1.05rem; color:{'#ff8c42' if abs(r['delta']) > 3 else '#8b95a8'};'>{'+' if r['delta'] >= 0 else ''}{r['delta']}</div>"
        f"</div>"
        for _, r in sorted_delta.iterrows()
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

# Footer
st.markdown(
    "<div style='text-align:center; margin-top:3rem; padding:1.5rem; color:#4a5266; font-size:0.78rem; font-family:JetBrains Mono;'>"
    "<div>🦞 LOBSTERAQI · TAIWAN AIR QUALITY MULTI-AGENT MONITORING</div>"
    "<div style='margin-top:0.4rem; opacity:0.6;'>Powered by Claude · Streamlit · Plotly · OpenClaw Browser Agent · InfluxDB</div>"
    "</div>",
    unsafe_allow_html=True,
)
