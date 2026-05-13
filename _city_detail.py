"""
Shared rendering for the "city deep-dive" view.

This module is imported by two callers:
  - `pages/1_城市深入.py`  — full-page entry (also reachable via URL `?city=...`)
  - `app.py`               — opens it inside an `st.dialog` modal so the user
                              never leaves the main dashboard and keeps scroll
                              position.

The leading underscore in the filename keeps Streamlit's pages auto-discovery
from listing this file as a navigable page.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import (
    CITIES, CITY_BY_ID,
    aqi_to_level, best_outdoor_hours,
)
from charts import (
    make_aqi_gauge, make_outdoor_bars, PALETTE,
)


def render_city_detail(
    initial_city_id: str,
    snapshot,
    ts_df,
    key_prefix: str = "city_detail",
    show_city_selector: bool = True,
) -> None:
    """Render a city's deep-dive UI (hero + gauge + 24h pollutants + 6h
    forecast + best outdoor hours + advisory).

    Parameters
    ----------
    initial_city_id : str
        Which city to land on. The selectbox (if shown) starts here.
    snapshot, ts_df : pd.DataFrame
        Pulled from session_state by the caller.
    key_prefix : str
        Disambiguates widget keys when the same function is mounted in two
        contexts (page + dialog) in the same Streamlit session.
    show_city_selector : bool
        Whether to render the in-place selectbox. The page entry shows it;
        the dialog hides it because the click already specified the city
        (but you can flip this on if you want city switching inside the
        modal).
    """
    # ── City picker (in-place) ──────────────────────────────────────────────
    if show_city_selector:
        chosen = st.selectbox(
            "選擇城市",
            options=[c["id"] for c in CITIES],
            index=next((i for i, c in enumerate(CITIES) if c["id"] == initial_city_id), 0),
            format_func=lambda cid: CITY_BY_ID[cid]["name"],
            label_visibility="collapsed",
            key=f"{key_prefix}_select",
        )
    else:
        chosen = initial_city_id

    city = CITY_BY_ID[chosen]
    row_df = snapshot[snapshot["city_id"] == chosen]
    if row_df.empty:
        st.error(f"找不到 {city['name']} 的資料")
        return
    row = row_df.iloc[0]
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
            key=f"{key_prefix}_gauge",
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
        d = ts_df[ts_df["city_id"] == chosen].sort_values("timestamp")
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
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False},
                            key=f"{key_prefix}_pollutants")

    # ── Row 2: removed — 6h forecast + best outdoor hours both removed per
    # 使用者偏好(已改用訂閱推送獲取未來資訊，且原 best_outdoor_hours 是合成資料)。

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
