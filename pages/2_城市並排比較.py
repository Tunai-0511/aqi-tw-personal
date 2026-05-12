"""
City side-by-side comparison.

Pick 2-3 cities → see them in a table + a shared radar chart + a 24h trend overlay.
Optional: ask the analyst agent (OpenClaw) to write a verbal comparison.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

from data import CITIES, CITY_BY_ID, aqi_to_level
from charts import make_pollutant_radar, make_trend_line
from styles import DARK_THEME_CSS, AGENT_STAGE_CSS
from data import LLM_PROVIDERS, call_llm_api


st.set_page_config(page_title="LobsterAQI · 城市比較", page_icon="🦞", layout="wide")
st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)
st.markdown(AGENT_STAGE_CSS, unsafe_allow_html=True)


snapshot = st.session_state.get("snapshot")
ts_df    = st.session_state.get("ts_df")
if snapshot is None or ts_df is None:
    st.warning("🦞 還沒有資料 — 請先回主畫面啟動 Pipeline。")
    if st.button("回主畫面", type="primary"):
        st.switch_page("app.py")
    st.stop()


col_back, col_pick = st.columns([1, 5])
with col_back:
    if st.button("← 回主畫面", use_container_width=True):
        st.switch_page("app.py")

st.markdown("<span class='eyebrow'>COMPARE · 城市並排</span>", unsafe_allow_html=True)
st.markdown("<div class='section-title'>挑 2-3 個城市並排看</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='section-sub'>同時比較 AQI、各種污染物、風險分數、氣象條件，並可請分析師寫一段話總結誰較適合戶外活動</div>",
    unsafe_allow_html=True,
)


default_cities = ["taipei", "kaohsiung", "hualien"]
chosen = st.multiselect(
    "選擇 2-3 個城市",
    options=[c["id"] for c in CITIES],
    default=default_cities,
    max_selections=3,
    format_func=lambda cid: CITY_BY_ID[cid]["name"],
)
if len(chosen) < 2:
    st.info("請至少選 2 個城市")
    st.stop()


# ── Side-by-side metric table ────────────────────────────────────────────
rows = []
for cid in chosen:
    r = snapshot[snapshot["city_id"] == cid]
    if r.empty:
        continue
    r = r.iloc[0]
    rows.append({
        "城市":      r["city"],
        "區域":      r["region"],
        "AQI":      r["aqi"],
        "等級":      r["level"],
        "PM2.5":    r["PM2.5"],
        "PM10":     r["PM10"],
        "O3":       r["O3"],
        "NO2":      r["NO2"],
        "SO2":      r["SO2"],
        "CO":       r["CO"],
        "溫度°C":    r["temp"],
        "濕度%":     r["humidity"],
        "風速":      r["wind_speed"],
        "風險分數":  r["risk"],
    })
cmp_df = pd.DataFrame(rows).set_index("城市")

st.markdown("<div class='eyebrow' style='margin-top:0.8rem;'>並排數值表</div>", unsafe_allow_html=True)
st.dataframe(
    cmp_df.style.background_gradient(subset=["AQI", "PM2.5", "風險分數"], cmap="RdYlGn_r"),
    use_container_width=True,
    height=160 + 32 * len(rows),
)


# ── Radar + 24h trend overlay ────────────────────────────────────────────
cL, cR = st.columns(2)
with cL:
    st.markdown("<div class='eyebrow'>污染物雷達（標準化）</div>", unsafe_allow_html=True)
    st.plotly_chart(
        make_pollutant_radar(snapshot, chosen),
        use_container_width=True,
        key="cmp_radar",
        config={"displayModeBar": False},
    )
with cR:
    st.markdown("<div class='eyebrow'>24h AQI 趨勢疊圖</div>", unsafe_allow_html=True)
    st.plotly_chart(
        make_trend_line(ts_df, chosen),
        use_container_width=True,
        key="cmp_trend",
        config={"displayModeBar": False},
    )


# ── Verbal comparison via direct LLM API ─────────────────────────────────
st.markdown("<div class='eyebrow' style='margin-top:1rem;'>🦞 請分析師寫一段比較</div>", unsafe_allow_html=True)

has_llm = bool(st.session_state.get("llm_key", "").strip())
prov_name = LLM_PROVIDERS.get(st.session_state.get("llm_provider", "anthropic"), {}).get("name", "LLM")

if not has_llm:
    st.info(f"⚠ 還沒填 LLM 金鑰 — 請回主畫面 sidebar 選擇 {prov_name} 並貼入 API Key。")
elif st.button("產生 AI 比較分析", type="primary", use_container_width=True):
    prompt_lines = ["以下是 {} 個台灣城市的即時空品快照：".format(len(chosen)), ""]
    for cid in chosen:
        r = snapshot[snapshot["city_id"] == cid].iloc[0]
        prompt_lines.append(
            f"- {r['city']}：AQI {r['aqi']:.0f}（{r['level']}），PM2.5 {r['PM2.5']} μg/m³，"
            f"O3 {r['O3']}，NO2 {r['NO2']}，風速 {r['wind_speed']} m/s，濕度 {r['humidity']:.0f}%"
        )
    prompt_lines.append("")
    prompt_lines.append(
        "請用 3 段繁體中文比較這幾個城市：① 整體空品哪個最好、最差 "
        "② 對戶外運動者的建議（誰最適合慢跑）③ 對敏感族群（氣喘/心血管）的建議。"
        "必須引用上方具體數值，不可編造其他城市。"
    )
    prompt = "\n".join(prompt_lines)
    with st.spinner(f"{prov_name} 分析中..."):
        answer = call_llm_api(
            st.session_state["llm_provider"],
            st.session_state["llm_key"],
            prompt,
            st.session_state.get("llm_model", ""),
            st.session_state.get("llm_base_url", ""),
            max_tokens=600,
            timeout=30,
        )
    if answer:
        st.markdown(
            f"<div class='glass-card' style='border-color:#9b59ff40; background:linear-gradient(135deg, rgba(155,89,255,0.10), rgba(15,24,48,0.5));'>"
            f"<div class='eyebrow' style='color:#9b59ff;'>🤖 分析師回覆</div>"
            f"<div style='font-size:0.95rem; line-height:1.75; color:#c0c8d8; white-space:pre-wrap;'>{answer}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.warning("LLM 沒回應或失敗 — 檢查 API key、網路、額度。")
