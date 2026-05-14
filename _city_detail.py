"""
城市深入 (City Deep-Dive) 共用渲染模組
================================================

這個檔案提供「單一城市的詳細儀表板」UI,被以下兩個地方共用:

  - **app.py 的 modal dialog**:使用者在主畫面點「🔍 查看 X 詳細」按鈕時,
    透過 `@st.dialog` 開啟,不會跳離主畫面、保留捲動位置。
  - (歷史) `pages/1_城市深入.py`:已於 2026-05-13 刪除,作為獨立分頁的入口。
    如未來想恢復獨立網址(例:`?city=taipei`),只要把這個函式再次包進
    streamlit pages 即可。

檔名前綴的底線 `_` 是刻意設計 — Streamlit 的 `pages/` 自動探索機制不會把
以底線開頭的檔案列為可導航的分頁,避免在 sidebar 多出一個多餘的入口。
"""
from __future__ import annotations  # 啟用延後求值的型別註解(允許未來的型別語法)

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# 從 data 模組匯入:CITIES = 全部 20 個縣市清單;CITY_BY_ID = id → city dict 的快速查表;
# aqi_to_level = 把 AQI 數值轉成「良好 / 普通 / 對敏感族群不健康 ...」等級資訊
from data import (
    CITIES, CITY_BY_ID,
    aqi_to_level,
)
# 從 charts 模組匯入:make_aqi_gauge = AQI 圓形儀表板圖;PALETTE = 統一配色盤
from charts import (
    make_aqi_gauge, PALETTE,
)


def render_city_detail(
    initial_city_id: str,
    snapshot,
    ts_df,
    key_prefix: str = "city_detail",
    show_city_selector: bool = True,
) -> None:
    """渲染單一城市的深度儀表板。

    內容包含三大區塊:
      1. **Hero 區**:城市名 + AQI 數值 + 風險等級 + 4 個 KPI 卡片(PM2.5/O3/NO2/風險分數)
      2. **Row 1**:左側 AQI 儀表板 + 即時氣象小卡;右側 24h 六種污染物趨勢圖
      3. **Row 3**:預警員(LLM)給的個人化健康建議(若 Pipeline 已跑)
    (原 Row 2 的「6h 預測 + 最佳外出時段」已於 2026-05-13 移除)

    Parameters
    ----------
    initial_city_id : str
        要顯示哪一個城市的資料,例如 "taipei"、"kaohsiung"。
        若 show_city_selector=True 則 selectbox 預設停在這個城市。
    snapshot : pd.DataFrame
        20 個城市的「當下即時快照」DataFrame,由 run_pipeline 寫入 session_state,
        呼叫者(app.py / pages)從 session_state 取出後傳入。
    ts_df : pd.DataFrame
        24 小時逐小時的時序資料(long-format),欄位包含 city_id、timestamp、
        aqi、PM2.5、PM10、O3、NO2、SO2、CO 等。
    key_prefix : str
        widget key 的前綴,避免同一個函式在「主畫面 modal」與「獨立分頁」兩處
        被掛載時,兩處的 selectbox / chart key 撞鍵造成 Streamlit 報錯。
    show_city_selector : bool
        是否顯示城市切換 selectbox。獨立分頁通常 True、modal 則可關掉
        (因為使用者點按鈕時已經指定了城市)。

    Returns
    -------
    None
        直接把 UI 寫入 Streamlit 渲染樹,不回傳任何東西。
    """
    # ── 城市選擇器 (in-place) ────────────────────────────────────────────────
    # 顯示一個下拉式 selectbox 讓使用者切換要查看的城市。
    # `index=...` 計算出「initial_city_id 在 CITIES 清單中的位置」作為預設選項;
    # 若 initial_city_id 不在清單裡,fallback 到 0(第一個城市)。
    if show_city_selector:
        chosen = st.selectbox(
            "選擇城市",
            options=[c["id"] for c in CITIES],
            index=next((i for i, c in enumerate(CITIES) if c["id"] == initial_city_id), 0),
            format_func=lambda cid: CITY_BY_ID[cid]["name"],  # 顯示中文城市名而非 id
            label_visibility="collapsed",                       # 隱藏「選擇城市」這個 label,讓 UI 緊湊
            key=f"{key_prefix}_select",                         # 防止與其他 selectbox key 衝突
        )
    else:
        # 不顯示 selectbox 時,直接用傳入的 initial_city_id
        chosen = initial_city_id

    # 從 CITY_BY_ID 取出該城市的中繼資料(中文名、英文名、區域、經緯度、bias)
    city = CITY_BY_ID[chosen]
    # 從 snapshot 取出該城市這一列;若不存在(例:剛載入還沒跑 Pipeline)則顯示錯誤並退出
    row_df = snapshot[snapshot["city_id"] == chosen]
    if row_df.empty:
        st.error(f"找不到 {city['name']} 的資料")
        return
    row = row_df.iloc[0]              # 取第一列(實際上每個城市只會有 1 列)
    lvl = aqi_to_level(row["aqi"])    # 把 AQI 數值轉成 dict:{name, color, level, advice, max}

    # ── Hero 區:城市名 + AQI + 等級 + 4 個 KPI 卡片 ─────────────────────────
    # 整個 hero 區塊用一段 HTML 渲染,可以一次控制 flex 佈局、發光特效、KPI 卡片網格。
    # `text-shadow:0 0 20px {color}66` 中的 66 是 hex alpha(40% 透明度),
    # 加上跟風險等級顏色一致的發光,直覺傳達嚴重性。
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
        unsafe_allow_html=True,  # 允許 HTML 渲染(預設 Streamlit 為了安全會 escape)
    )

    # ── Row 1:AQI 儀表板 + 24h 六種污染物趨勢 ────────────────────────────────
    # 使用 st.columns([3, 5]) 分成左 3 右 5 的比例 — 趨勢圖較複雜需要更多橫向空間。
    c1, c2 = st.columns([3, 5])

    # 左欄:AQI 圓形儀表板 + 氣象 mini-card
    with c1:
        st.markdown("<div class='eyebrow'>AQI 即時儀表</div>", unsafe_allow_html=True)
        # make_aqi_gauge 回傳一個 Plotly Indicator(圓形量表),會根據 AQI 值自動上色
        st.plotly_chart(
            make_aqi_gauge(row["aqi"], row["city"]),
            use_container_width=True,                  # 圖表寬度跟著欄寬縮放
            key=f"{key_prefix}_gauge",                 # 防止 key 衝突
            config={"displayModeBar": False},          # 隱藏 Plotly 預設的工具列
        )
        # 即時氣象 mini-card — 用 2x2 grid 顯示溫度、濕度、風速、氣壓
        # 每個指標用不同顏色:橘=溫度、青=濕度、紫=風速、綠=氣壓,協助快速辨識
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

    # 右欄:24h 污染物趨勢圖(6 種污染物各畫一條線)
    with c2:
        st.markdown("<div class='eyebrow'>24h 六種污染物趨勢</div>", unsafe_allow_html=True)
        # 從 ts_df 篩出該城市的所有時點,按 timestamp 排序確保線條由左至右
        d = ts_df[ts_df["city_id"] == chosen].sort_values("timestamp")
        if d.empty:
            # 該城市可能因為 EPA / CAMS API 回應不完整而沒有時序資料
            st.info("該城市無時序資料")
        else:
            # 動態建立 Plotly Figure,for 迴圈把 6 種污染物各加一條 Scatter trace
            fig = go.Figure()
            for i, p in enumerate(["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]):
                fig.add_trace(go.Scatter(
                    x=d["timestamp"], y=d[p],
                    mode="lines+markers",                              # 同時畫線條 + 資料點
                    name=p,                                            # 在 legend 中顯示的名稱
                    line=dict(color=PALETTE[i % len(PALETTE)], width=2),  # 從 PALETTE 取色(modulo 避免越界)
                    marker=dict(size=4),
                    # hovertemplate:滑鼠懸停時顯示的格式;{{...}} 中的雙大括號是為了
                    # 在 f-string 裡 escape 出 Plotly 的單大括號語法
                    hovertemplate=f"<b>{p}</b><br>%{{x|%m/%d %H:%M}}<br>%{{y:.1f}}<extra></extra>",
                ))
            # 統一圖表外觀:透明背景、深色文字、青色淡格線、x 軸 unified hover
            fig.update_layout(
                height=380,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter, sans-serif", color="#e8eef7", size=11),
                margin=dict(l=40, r=20, t=20, b=40),
                xaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8")),
                yaxis=dict(gridcolor="rgba(0,217,255,0.08)", tickfont=dict(color="#8b95a8")),
                legend=dict(bgcolor="rgba(15,24,48,0.5)", bordercolor="rgba(0,217,255,0.2)", borderwidth=1, font=dict(color="#e8eef7")),
                hovermode="x unified",  # 滑鼠移到某個 x 位置時,同時顯示該時點所有 trace 的 y 值
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False},
                            key=f"{key_prefix}_pollutants")

    # ── Row 2:已移除 ────────────────────────────────────────────────────────
    # 原本是「未來 6 小時 AQI 預測 + 最佳外出時段」,於 2026-05-13 第三輪
    # 修復時刪除。原因:使用者已有訂閱推送功能可獲取未來資訊,且
    # `best_outdoor_hours()` 內部使用 `np.random` 合成資料,推薦時段並非
    # 真實預測,容易誤導使用者出門決策。

    # ── Row 3:預警員(LLM)給的個人化健康建議 ───────────────────────────────
    st.markdown("<div class='eyebrow' style='margin-top:1rem;'>🦞 預警員給此城市的建議</div>", unsafe_allow_html=True)
    # 從 session_state 取出預警員 LLM 的輸出;若 Pipeline 未跑或 LLM 失敗則為空字串
    advisory_text = st.session_state.get("agent_c_advisories", "")
    if advisory_text:
        # 已有 LLM 建議:用綠色 glass-card 渲染(對應預警員的主題色 #00e676)
        # `white-space:pre-wrap` 保留 LLM 輸出中的換行,讓段落格式不會被壓平
        st.markdown(
            f"<div class='glass-card' style='border-color:#00e67640; background:linear-gradient(135deg, rgba(0,230,118,0.12), rgba(15,24,48,0.5));'>"
            f"<div style='font-size:0.92rem; line-height:1.7; color:#c0c8d8; white-space:pre-wrap;'>{advisory_text}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        # 沒有 LLM 建議:顯示該 AQI 等級的通用 advice(來自 data.py 的 AQI_LEVELS),
        # 並附上提示告訴使用者怎麼啟用個人化建議
        st.markdown(
            f"<div class='glass-card'>"
            f"<div style='color:#c0c8d8;'>{lvl['advice']}</div>"
            f"<div class='tiny muted' style='margin-top:0.5rem;'>📚 提示：在主畫面執行 Pipeline 並連線 OpenClaw 預警員，可獲得針對前三高 AQI 城市的個人化建議。</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
