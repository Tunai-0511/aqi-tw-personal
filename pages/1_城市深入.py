"""
City detail page — drill-down view for any one of the 20 cities.

Reads `?city=<id>` from URL params (set by the main dashboard when user clicks
a row in the ranking chart) OR shows a selectbox if the param is missing.

Streamlit treats this file as a sub-page because it lives in `pages/`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable so we can reuse data.py / charts.py / styles.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import CITIES, CITY_BY_ID, aqi_to_level, best_outdoor_hours
from charts import (
    make_aqi_gauge, make_forecast_chart, make_outdoor_bars, make_trend_line,
    PALETTE,
)
from styles import DARK_THEME_CSS, AGENT_STAGE_CSS

st.set_page_config(
    page_title="LobsterAQI · 城市深入",
    page_icon="🦞",
    layout="wide",
)
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)
st.markdown(AGENT_STAGE_CSS, unsafe_allow_html=True)


# ── Resolve the target city ──────────────────────────────────────────────
snapshot = st.session_state.get("snapshot")
ts_df    = st.session_state.get("ts_df")

if snapshot is None or ts_df is None:
    st.warning(
        "🦞 還沒有資料 — 請先回主畫面點擊「啟動四代理人 Pipeline」載入即時 AQI 資料。"
    )
    if st.button("回主畫面", type="primary"):
        st.switch_page("app.py")
    st.stop()

# Read ?city=xxx from URL, fall back to selectbox
qparam_city = st.query_params.get("city")
if qparam_city and qparam_city in CITY_BY_ID:
    default_city = qparam_city
else:
    default_city = snapshot.sort_values("aqi", ascending=False).iloc[0]["city_id"]

col_back, col_pick, col_pad = st.columns([1, 4, 1])
with col_back:
    if st.button("← 回主畫面", use_container_width=True):
        st.switch_page("app.py")
with col_pick:
    chosen = st.selectbox(
        "選擇城市",
        options=[c["id"] for c in CITIES],
        index=next((i for i, c in enumerate(CITIES) if c["id"] == default_city), 0),
        format_func=lambda cid: CITY_BY_ID[cid]["name"],
        label_visibility="collapsed",
    )
    if chosen != qparam_city:
        st.query_params["city"] = chosen
        default_city = chosen

city = CITY_BY_ID[default_city]
row  = snapshot[snapshot["city_id"] == default_city]
if row.empty:
    st.error(f"找不到 {city['name']} 的資料")
    st.stop()
row = row.iloc[0]
lvl = aqi_to_level(row["aqi"])


# ── Hero strip: city name + AQI gauge + level + key stats ────────────────
st.markdown(
    f"""
    <div class='hero-wrap' style='padding:1.4rem 2rem; margin-bottom:1rem;'>
      <div style='display:flex; justify-content:space-between; align-items:center; gap:1.6rem; flex-wrap:wrap;'>
        <div>
          <div class='eyebrow'>CITY · {row['region']}</div>
          <div style='font-size:2.6rem; font-weight:900; color:{row["color"]}; text-shadow:0 0 20px {row["color"]}66; letter-spacing:-0.04em; line-height:1.05;'>
            {row['city']}
          </div>
          <div style='font-size:1.05rem; color:#c0c8d8; margin-top:0.3rem;'>
            AQI <b style='color:{row["color"]};'>{row['aqi']:.0f}</b> ·
            <span style='color:{row["color"]};'>{row['level']}</span> ·
            更新於 {row['updated_min_ago']} 分鐘前
          </div>
        </div>
        <div style='display:flex; gap:0.7rem; flex-wrap:wrap;'>
          <div class='kpi-card' style='min-width:110px;'>
            <div class='kpi-label'>PM2.5</div>
            <div class='kpi-value' style='font-size:1.5rem;'>{row['PM2.5']}</div>
            <div class='kpi-sub'>μg/m³</div>
          </div>
          <div class='kpi-card' style='min-width:110px;'>
            <div class='kpi-label'>O₃</div>
            <div class='kpi-value orange' style='font-size:1.5rem;'>{row['O3']}</div>
            <div class='kpi-sub'>ppb</div>
          </div>
          <div class='kpi-card' style='min-width:110px;'>
            <div class='kpi-label'>NO₂</div>
            <div class='kpi-value' style='font-size:1.5rem; color:#9b59ff;'>{row['NO2']}</div>
            <div class='kpi-sub'>ppb</div>
          </div>
          <div class='kpi-card' style='min-width:110px;'>
            <div class='kpi-label'>風險分數</div>
            <div class='kpi-value' style='font-size:1.5rem; color:#ff8c42;'>{row['risk']:.0f}</div>
            <div class='kpi-sub'>/100</div>
          </div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Row 1: AQI gauge + 24h pollutant trends ──────────────────────────────
c1, c2 = st.columns([3, 5])

with c1:
    st.markdown("<div class='eyebrow'>AQI 即時儀表</div>", unsafe_allow_html=True)
    st.plotly_chart(
        make_aqi_gauge(row["aqi"], row["city"]),
        use_container_width=True,
        key="city_gauge",
        config={"displayModeBar": False},
    )
    # Weather mini-card
    st.markdown(
        f"""
        <div class='glass-card'>
          <div class='eyebrow'>即時氣象</div>
          <div style='display:grid; grid-template-columns:1fr 1fr; gap:0.6rem; margin-top:0.4rem;'>
            <div><div class='tiny muted'>🌡 溫度</div><div style='font-family:JetBrains Mono; font-weight:700; color:#ff8c42; font-size:1.2rem;'>{row['temp']}°C</div></div>
            <div><div class='tiny muted'>💧 濕度</div><div style='font-family:JetBrains Mono; font-weight:700; color:#00d9ff; font-size:1.2rem;'>{row['humidity']:.0f}%</div></div>
            <div><div class='tiny muted'>💨 風速</div><div style='font-family:JetBrains Mono; font-weight:700; color:#9b59ff; font-size:1.2rem;'>{row['wind_speed']} m/s</div></div>
            <div><div class='tiny muted'>📊 氣壓</div><div style='font-family:JetBrains Mono; font-weight:700; color:#00e676; font-size:1.2rem;'>{row['pressure']:.0f}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown("<div class='eyebrow'>24h 六種污染物趨勢</div>", unsafe_allow_html=True)
    d = ts_df[ts_df["city_id"] == default_city].sort_values("timestamp")
    if d.empty:
        st.info("該城市無時序資料")
    else:
        fig = go.Figure()
        for i, p in enumerate(["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]):
            fig.add_trace(go.Scatter(
                x=d["timestamp"], y=d[p],
                mode="lines+markers",
                name=p,
                line=dict(color=PALETTE[i % len(PALETTE)], width=2),
                marker=dict(size=4),
                hovertemplate=f"<b>{p}</b><br>%{{x|%m/%d %H:%M}}<br>%{{y:.1f}}<extra></extra>",
            ))
        fig.update_layout(
            height=380,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", color="#e8eef7", size=11),
            margin=dict(l=40, r=20, t=20, b=40),
            xaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8")),
            yaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8")),
            legend=dict(bgcolor="rgba(15,24,48,0.5)", bordercolor="rgba(0,217,255,0.2)", borderwidth=1, font=dict(color="#e8eef7")),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="city_pollutants")


# ── Row 2: 6h forecast + best outdoor hours ──────────────────────────────
c3, c4 = st.columns([5, 4])

with c3:
    st.markdown("<div class='eyebrow'>未來 6 小時 AQI 預測</div>", unsafe_allow_html=True)
    from data import generate_history_with_forecast
    fdf = generate_history_with_forecast(default_city, history_hours=12, ahead=6)
    st.plotly_chart(
        make_forecast_chart(fdf, row["city"]),
        use_container_width=True,
        key="city_forecast",
        config={"displayModeBar": False},
    )

with c4:
    st.markdown("<div class='eyebrow'>最佳外出時段（12h）</div>", unsafe_allow_html=True)
    outdoor_df = best_outdoor_hours(default_city)
    st.plotly_chart(
        make_outdoor_bars(outdoor_df),
        use_container_width=True,
        key="city_outdoor",
        config={"displayModeBar": False},
    )
    # Show best hour as a callout
    best_hour = outdoor_df[outdoor_df["recommend"]].iloc[0]
    st.markdown(
        f"<div style='padding:0.6rem 0.8rem; background:rgba(0,230,118,0.10); border-left:3px solid #00e676; border-radius:0 8px 8px 0; margin-top:0.4rem;'>"
        f"<div class='tiny muted'>建議外出時段</div>"
        f"<div style='font-size:1.1rem; font-weight:800; color:#00e676; font-family:JetBrains Mono;'>"
        f"{best_hour['hour']} · 預測 AQI {best_hour['aqi']:.0f}"
        f"</div></div>",
        unsafe_allow_html=True,
    )


# ── Row 3: Personalized advisory (from advisor agent if available) ───────
st.markdown("<div class='eyebrow' style='margin-top:1rem;'>🦞 預警員給此城市的建議</div>", unsafe_allow_html=True)
advisory_text = st.session_state.get("agent_c_advisories", "")
if advisory_text:
    st.markdown(
        f"<div class='glass-card' style='border-color:#00e67640; background:linear-gradient(135deg, rgba(0,230,118,0.12), rgba(15,24,48,0.5));'>"
        f"<div style='font-size:0.92rem; line-height:1.7; color:#c0c8d8; white-space:pre-wrap;'>{advisory_text}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"<div class='glass-card'>"
        f"<div style='color:#c0c8d8;'>{lvl['advice']}</div>"
        f"<div class='tiny muted' style='margin-top:0.5rem;'>📚 提示：在主畫面執行 Pipeline 並連線 OpenClaw 預警員，可獲得針對前三高 AQI 城市的個人化建議。</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
