"""
Plotly 圖表工廠模組 (Chart Factories)
============================================

本檔案集中所有的圖表生成函式,每個 `make_*()` 函式回傳一個 `plotly.graph_objects.Figure`
物件,呼叫者只需把它丟給 `st.plotly_chart(fig, ...)` 即可顯示。

設計原則:
  1. **統一主題**:所有圖表共用 `_base_layout()` 提供的深色背景、青色格線、Inter 字體
  2. **無副作用**:函式只接受 DataFrame 與參數,不讀 / 寫 session_state — 方便單元測試
  3. **互動化**:每張圖都設定 `hovertemplate`,滑鼠懸停時顯示中文化的資訊提示
  4. **顏色語意**:`color` 欄位由 data.py 的 `aqi_to_level()` 決定(綠=好/紅=差),
     全應用統一這個顏色映射,確保使用者建立穩定的「顏色→風險等級」心智模型
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# 從 data.py 引入 AQI 等級資料(顏色 / 等級名 / 建議),共用同一份事實來源
from data import AQI_LEVELS, POLLUTANTS, aqi_to_level

# ─── 全域主題參數 ────────────────────────────────────────────────────────────
# 這些常數定義整個應用程式的視覺基準色,變更這裡就會影響所有圖表。

PAPER     = "rgba(0,0,0,0)"                                      # 圖表外框背景(透明,跟著 app 背景)
PLOT      = "rgba(0,0,0,0)"                                      # 圖表繪圖區背景(透明)
FONT      = dict(family="Inter, system-ui, sans-serif",          # 主字體 Inter,fallback 到系統字體
                 color="#e8eef7", size=12)                       # 字色採高對比的偏白色
GRID      = "rgba(0, 217, 255, 0.08)"                            # 格線:極淡的青色,不搶眼但可定位
AXIS_LINE = "rgba(0, 217, 255, 0.25)"                            # 軸線:稍深的青色
TICK      = "#8b95a8"                                             # 軸上刻度數字的顏色(中灰)

# 主題色 — 對應 AQI 等級的視覺強度
CYAN   = "#00d9ff"   # 青色:主題色 / 「正常 / 資訊」
ORANGE = "#ff8c42"   # 橘色:警告 / 對敏感族群不健康
GREEN  = "#00e676"   # 綠色:良好
YELLOW = "#ffd93d"   # 黃色:普通
RED    = "#ff4757"   # 紅色:對所有族群不健康
PURPLE = "#9b59ff"   # 紫色:非常不健康

# 通用配色盤,用於多 trace 圖表(例:24h 趨勢、雷達)的城市顏色循環使用
PALETTE = [CYAN, ORANGE, GREEN, YELLOW, PURPLE, RED, "#4eecff", "#ffb380", "#7af1bb", "#c4a5ff"]


def _base_layout(**kw) -> dict:
    """回傳每張圖的預設 layout dict,允許呼叫者用 kwargs 覆寫個別屬性。

    用法範例:
    ```python
    fig.update_layout(**_base_layout(height=380, xaxis_title="時間"))
    ```

    為什麼用 dict 而不是直接 fig.update_layout?
      - dict 易於合併 / 覆寫個別 key(`base.update(kw)`)
      - 同一份 base 可以在多個 `make_*` 函式中重用,確保視覺一致
    """
    base = dict(
        paper_bgcolor=PAPER,
        plot_bgcolor=PLOT,
        font=FONT,
        margin=dict(l=40, r=20, t=40, b=40),       # 預設邊距,主要圖表用這個
        hoverlabel=dict(                            # 滑鼠懸停 tooltip 樣式
            bgcolor="rgba(15, 24, 48, 0.95)",       # 深藍背景,稍微透明
            bordercolor=CYAN,                       # 青色邊框,與主題一致
            font=dict(family="JetBrains Mono", color="#e8eef7", size=12),  # 等寬字便於數字對齊
        ),
        legend=dict(                                # 圖例樣式
            bgcolor="rgba(15, 24, 48, 0.5)",
            bordercolor="rgba(0, 217, 255, 0.2)",
            borderwidth=1,
            font=dict(color="#e8eef7"),
        ),
        xaxis=dict(                                 # x 軸樣式(可被 update_xaxes 進一步覆寫)
            gridcolor=GRID, zerolinecolor=AXIS_LINE,
            linecolor=AXIS_LINE, tickcolor=AXIS_LINE,
            tickfont=dict(color=TICK), title_font=dict(color="#c0c8d8"),
        ),
        yaxis=dict(                                 # y 軸樣式
            gridcolor=GRID, zerolinecolor=AXIS_LINE,
            linecolor=AXIS_LINE, tickcolor=AXIS_LINE,
            tickfont=dict(color=TICK), title_font=dict(color="#c0c8d8"),
        ),
    )
    base.update(kw)   # 把呼叫端傳入的 kwargs 合併進來(覆寫上面的預設值)
    return base


# ─── AQI 圓形儀表板 (Gauge) ──────────────────────────────────────────────────


def make_aqi_gauge(aqi: float, city_name: str = "") -> go.Figure:
    """AQI 圓形儀表板 — 以 0-300 為軸,目前數值用大字 + 顏色顯示。

    特色:
      - 背景按 AQI 區段塗上對應的淡色(綠/黃/橘/紅/紫),提供「分級感」
      - 白色 threshold 線指向當前 AQI,精確標示位置
      - 數字大小 44pt + 等寬字,確保使用者第一眼看到的就是數值

    Parameters
    ----------
    aqi : float
        當前 AQI 數值(0-300+)
    city_name : str
        城市名(目前未顯示在儀表板上,保留供未來標題用)
    """
    lvl = aqi_to_level(aqi)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",                                   # 顯示模式:儀表 + 數字
        value=aqi,
        number=dict(font=dict(size=44, color=lvl["color"],     # 大字數值,顏色跟 AQI 等級對應
                              family="JetBrains Mono")),       # 等寬字防止數字寬度跳動
        domain=dict(x=[0, 1], y=[0, 1]),                       # 圖在容器內佔滿
        gauge=dict(
            axis=dict(range=[0, 300], tickwidth=1, tickcolor=TICK,
                      tickfont=dict(color=TICK, size=10)),
            bar=dict(color=lvl["color"], thickness=0.28),       # 主指針顏色 = 風險等級色
            bgcolor="rgba(255,255,255,0.03)",                   # 弱化儀表內部背景
            borderwidth=2, bordercolor="rgba(0, 217, 255, 0.3)",
            steps=[                                              # 5 段分級背景色(淡色)
                {"range": [0, 50],    "color": "rgba(0, 230, 118, 0.18)"},   # 良好(綠)
                {"range": [50, 100],  "color": "rgba(255, 217, 61, 0.18)"},  # 普通(黃)
                {"range": [100, 150], "color": "rgba(255, 140, 66, 0.20)"},  # 對敏感族群不健康(橘)
                {"range": [150, 200], "color": "rgba(255, 71, 87, 0.22)"},   # 對所有族群不健康(紅)
                {"range": [200, 300], "color": "rgba(155, 89, 255, 0.22)"},  # 非常不健康(紫)
            ],
            # threshold 是一條白色細線,精確指向當前 AQI 位置 — 額外的視覺強調
            threshold=dict(line=dict(color="#ffffff", width=3), thickness=0.85, value=aqi),
        ),
    ))
    fig.update_layout(**_base_layout(
        height=280, margin=dict(l=10, r=10, t=20, b=10),       # 儀表型不需要太大邊距
    ))
    return fig


# ─── 城市 AQI 排名(橫向長條) ───────────────────────────────────────────────


def make_city_ranking(df: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    """20 個城市的 AQI 橫向長條圖,由低到高排序。

    支援「聚焦城市」功能:傳入 `highlight=city_id` 時,該城市會加上白色粗框,
    其餘維持原色,使用者一眼可看到自己關心的城市排在哪裡。

    Parameters
    ----------
    df : pd.DataFrame
        snapshot DataFrame,需包含 city_id, city, aqi, color, level, PM2.5, risk
    highlight : str | None
        要加白邊的城市 id;None 表示沒有任何聚焦
    """
    # 由低到高排序 — 因為 Plotly 橫向長條圖預設 y 軸由下往上,
    # 排序後最高的會在最上面,符合「壞的在頂上」直覺
    s = df.sort_values("aqi", ascending=True).copy()
    # 為每個城市計算邊框色:被聚焦的用白色,其餘維持原色(實際上會被 width=0 覆蓋掉)
    colors = [
        ("#fff" if highlight == cid else c)
        for cid, c in zip(s["city_id"], s["color"])
    ]
    # 邊框寬度:聚焦城市為 3,其餘為 0(不顯示邊框)
    line_widths = [3 if highlight == cid else 0 for cid in s["city_id"]]

    fig = go.Figure(go.Bar(
        x=s["aqi"], y=s["city"], orientation="h",          # 橫向長條:x = AQI 值,y = 城市
        marker=dict(color=s["color"], line=dict(color=colors, width=line_widths)),
        text=[f"<b>{v:.0f}</b>" for v in s["aqi"]],         # 條形外顯示 AQI 數字
        textposition="outside",
        textfont=dict(color="#e8eef7", family="JetBrains Mono", size=12),
        # customdata 把多個欄位塞進 hover 用,要用 np.stack 把多列拼成 2D 陣列
        customdata=np.stack([s["level"], s["PM2.5"], s["risk"], s["city_id"]], axis=-1),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "AQI: <b>%{x:.1f}</b><br>"
            "等級: %{customdata[0]}<br>"
            "PM2.5: %{customdata[1]} μg/m³<br>"
            "風險分數: %{customdata[2]}<extra></extra>"
        ),
    ))
    fig.update_layout(**_base_layout(
        height=420,
        margin=dict(l=70, r=30, t=20, b=30),  # 左邊留多一點空間放城市名
        xaxis_title="AQI",
        showlegend=False,
    ))
    return fig


# ─── PM2.5 vs AQI 散點(氣泡大小 = 風險分數) ────────────────────────────────


def make_pm25_aqi_scatter(df: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    """PM2.5 對 AQI 的散點圖,氣泡大小代表風險分數。

    用途:檢視 PM2.5 與 AQI 的關係(理論上應正相關),同時用氣泡大小
    顯示「綜合風險分數」是否與單一污染物一致。

    Parameters
    ----------
    df : pd.DataFrame
        snapshot,需包含 PM2.5, aqi, risk, color, city_id, city, level
    highlight : str | None
        聚焦城市 id;非聚焦城市會降為 35% 不透明度
    """
    # 把 risk 標準化成 12-62 的氣泡半徑;clip(lower=10) 避免 risk=0 時氣泡消失
    sizes = (df["risk"] / df["risk"].max() * 50 + 12).clip(lower=10)
    # 不透明度:聚焦城市 1.0,其餘 0.35(灰化)
    opacity = [1.0 if (highlight is None or cid == highlight) else 0.35 for cid in df["city_id"]]
    # 邊框寬度:聚焦 3px,其餘 1px(輕量邊框讓氣泡看起來更立體)
    line_width = [3 if cid == highlight else 1 for cid in df["city_id"]]

    fig = go.Figure(go.Scatter(
        x=df["PM2.5"], y=df["aqi"],
        mode="markers+text",                            # 同時顯示氣泡 + 城市名標籤
        text=df["city"],
        textposition="top center",
        textfont=dict(color="#c0c8d8", size=10),
        marker=dict(
            size=sizes, color=df["color"],
            opacity=opacity,
            line=dict(width=line_width, color="rgba(255,255,255,0.6)"),
            symbol="circle",
        ),
        customdata=np.stack([df["city"], df["risk"], df["level"]], axis=-1),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "PM2.5: %{x:.1f} μg/m³<br>"
            "AQI: %{y:.1f}<br>"
            "風險分數: %{customdata[1]}<br>"
            "等級: %{customdata[2]}<extra></extra>"
        ),
    ))
    fig.update_layout(**_base_layout(
        height=420,
        xaxis_title="PM2.5 (μg/m³)",
        yaxis_title="AQI",
        showlegend=False,
    ))
    return fig


# ─── 24h AQI 趨勢線 ──────────────────────────────────────────────────────────


def make_trend_line(ts_df: pd.DataFrame, city_ids: list[str]) -> go.Figure:
    """多城市的 24h AQI 趨勢線圖,使用者可多選比較。

    每個城市畫一條曲線(`shape="spline"` + `smoothing=0.6` 做平滑曲線),
    顏色由 PALETTE 循環指派。Plotly 內建 legend 點擊可隱藏/顯示特定線。

    Parameters
    ----------
    ts_df : pd.DataFrame
        時序資料,需包含 city_id, city, timestamp, aqi
    city_ids : list[str]
        要顯示的城市 id 清單;可長可短(實測 20 條也順)
    """
    fig = go.Figure()
    for i, cid in enumerate(city_ids):
        # 篩出該城市的資料並按時間排序
        d = ts_df[ts_df["city_id"] == cid].sort_values("timestamp")
        if d.empty:
            continue   # 該城市可能沒有時序資料,跳過避免空 trace
        fig.add_trace(go.Scatter(
            x=d["timestamp"], y=d["aqi"],
            mode="lines+markers",
            name=d["city"].iloc[0],                              # 取出該城市的中文名
            # spline + smoothing 0.6 = 適度平滑(0=完全折線,1=過度平滑失真)
            line=dict(color=PALETTE[i % len(PALETTE)], width=2.2, shape="spline", smoothing=0.6),
            marker=dict(size=5),
            hovertemplate="<b>%{fullData.name}</b><br>%{x|%m/%d %H:%M}<br>AQI: <b>%{y:.1f}</b><extra></extra>",
        ))
    fig.update_layout(**_base_layout(
        height=400,
        xaxis_title="時間",
        yaxis_title="AQI",
        hovermode="x unified",   # 滑鼠到某時點時,顯示所有城市在該時點的 AQI(便於對比)
    ))
    return fig


# ─── 熱力時序圖(小時 × 城市) ──────────────────────────────────────────────


def make_heatmap(ts_df: pd.DataFrame) -> go.Figure:
    """24h × 20 城市的 AQI 熱力圖。

    座標軸:x = 每小時時點、y = 城市名、z(色階)= AQI 數值
    色階從 0(綠)到 200(紫紅),與 AQI 等級色階對齊,使用者可一眼看出
    「哪個城市在哪個時段最差」。

    Parameters
    ----------
    ts_df : pd.DataFrame
        24h × 20 城市的長表;需包含 city, timestamp, aqi
    """
    # pivot_table:把 long 表格轉成 wide 矩陣(city × hour),儲存格值是 aqi
    pv = (ts_df.assign(hour=ts_df["timestamp"].dt.strftime("%m/%d %H:00"))
                .pivot_table(index="city", columns="hour", values="aqi"))
    fig = go.Figure(go.Heatmap(
        z=pv.values, x=pv.columns, y=pv.index,
        # 自訂色階,跟 AQI 分級色對齊(0=綠、50=黃、100=橘、150=紅、200=紫、300=深紫紅)
        colorscale=[
            [0.00, "#00e676"], [0.16, "#ffd93d"], [0.33, "#ff8c42"],
            [0.50, "#ff4757"], [0.75, "#9b59ff"], [1.00, "#7f0000"],
        ],
        zmin=0, zmax=200,    # 固定色階範圍,確保跨時間對比一致
        colorbar=dict(
            title=dict(text="AQI", font=dict(color="#c0c8d8")),
            tickfont=dict(color=TICK),
            outlinewidth=0, len=0.85,
        ),
        hovertemplate="<b>%{y}</b><br>%{x}<br>AQI: <b>%{z:.1f}</b><extra></extra>",
    ))
    fig.update_layout(**_base_layout(
        height=420,
        margin=dict(l=80, r=20, t=20, b=80),    # 左留城市名空間,下留時間刻度
    ))
    # x 軸標籤斜 -45 度,避免時間字串太擠
    fig.update_xaxes(tickangle=-45, tickfont=dict(size=9))
    return fig


# ─── 污染物雷達圖 ────────────────────────────────────────────────────────────


def make_pollutant_radar(snapshot: pd.DataFrame, city_ids: list[str]) -> go.Figure:
    """多城市的「6 種污染物」雷達圖比較。

    每個污染物對應一個軸(PM2.5/PM10/O3/NO2/SO2/CO),每個城市畫一個多邊形。
    為了讓 6 種單位完全不同的污染物畫在同一張圖,先把每個值用「參考標準」
    (例:PM2.5 用 50 μg/m³)標準化成 0-100% 的相對強度。

    Parameters
    ----------
    snapshot : pd.DataFrame
        當下快照
    city_ids : list[str]
        要比較的城市清單
    """
    fig = go.Figure()
    # 每個污染物對應的「參考門檻」(略嚴於 EPA 標準,讓圖表變化更明顯)
    # 例:PM2.5 = 50 μg/m³ 表示「達到 50 時占 100%」
    ref = {"PM2.5": 50, "PM10": 100, "O3": 100, "NO2": 80, "SO2": 30, "CO": 5}
    for i, cid in enumerate(city_ids):
        row = snapshot[snapshot["city_id"] == cid].iloc[0]
        # 標準化每個污染物到 0-100%,並 cap 在 100(避免雷達圖被單一極端值撐爆)
        vals = [min(100, row[p] / ref[p] * 100) for p in POLLUTANTS]
        fig.add_trace(go.Scatterpolar(
            # 雷達圖要把第一個點再加到最後,線才會自動封口
            r=vals + [vals[0]],
            theta=POLLUTANTS + [POLLUTANTS[0]],
            fill="toself",                                # 填滿多邊形內部(視覺更明顯)
            name=row["city"],
            line=dict(color=PALETTE[i % len(PALETTE)], width=2),
            opacity=0.55,
            hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{r:.1f}%<extra></extra>",
        ))
    fig.update_layout(**_base_layout(
        height=440,
        polar=dict(
            bgcolor="rgba(15, 24, 48, 0.4)",
            radialaxis=dict(
                visible=True, range=[0, 100],
                gridcolor=GRID, linecolor=AXIS_LINE,
                tickfont=dict(color=TICK, size=9),
            ),
            angularaxis=dict(
                gridcolor=GRID, linecolor=AXIS_LINE,
                tickfont=dict(color="#c0c8d8", size=11),
            ),
        ),
    ))
    return fig


# ─── 堆疊式污染物組成 ───────────────────────────────────────────────────────


def make_stacked_composition(snapshot: pd.DataFrame) -> go.Figure:
    """20 個城市的堆疊長條圖,顯示各污染物對總強度的貢獻。

    用法:看「哪個城市的 AQI 主要是哪幾種污染物推起來的」。例如:
      - 雲林可能 PM2.5 / PM10 比例高(六輕影響)
      - 都會區可能 NO2 / O3 比例高(交通排放)
    """
    df = snapshot.copy()
    # 跟雷達圖同一份標準化規則,確保視覺一致
    ref = {"PM2.5": 50, "PM10": 100, "O3": 100, "NO2": 80, "SO2": 30, "CO": 5}
    for p in POLLUTANTS:
        df[f"{p}_norm"] = df[p] / ref[p] * 100
    # 每個污染物對應一個顏色(與其他圖表保持一致)
    colors = {"PM2.5": CYAN, "PM10": "#4eecff", "O3": YELLOW,
              "NO2": ORANGE, "SO2": PURPLE, "CO": RED}
    fig = go.Figure()
    for p in POLLUTANTS:
        fig.add_trace(go.Bar(
            x=df[f"{p}_norm"], y=df["city"], orientation="h",
            name=p, marker=dict(color=colors[p]),
            customdata=df[p],   # 同時把「實際數值(非標準化)」帶進 hover
            hovertemplate=f"<b>%{{y}}</b><br>{p}: %{{customdata}}<br>強度: %{{x:.1f}}%<extra></extra>",
        ))
    fig.update_layout(**_base_layout(
        height=420,
        barmode="stack",                       # 堆疊模式 — 累加每個污染物的貢獻
        xaxis_title="標準化強度 (%)",
        margin=dict(l=70, r=30, t=20, b=30),
    ))
    return fig


# ─── 風玫瑰圖(風向頻率 + 平均 AQI) ────────────────────────────────────────


def make_wind_rose(snapshot: pd.DataFrame) -> go.Figure:
    """8 方位風玫瑰圖:每個方位的城市數量(r)、平均 AQI(色階)。

    觀察重點:
      - 哪個方位的風城市較多?(地形 / 季風的影響)
      - 哪個方位的風常伴隨高 AQI?(可能來自外部污染源)
    """
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    snapshot = snapshot.copy()
    # 把風向 0° (=北)對齊到 8 分箱的中心點;+22.5 後 mod 360 等於把箱位置調整
    shifted = (snapshot["wind_dir"] + 22.5) % 360
    bins = [0, 45, 90, 135, 180, 225, 270, 315, 360]   # 9 個邊界 → 8 個區間
    snapshot["dir_bin"] = pd.cut(shifted, bins=bins, labels=dirs,
                                  include_lowest=True, right=False)
    # groupby 各方位:count = 城市數、mean = 平均 AQI
    agg = snapshot.groupby("dir_bin", observed=True).agg(
        count=("aqi", "size"), mean_aqi=("aqi", "mean")).reset_index()
    fig = go.Figure(go.Barpolar(
        r=agg["count"],                                              # 半徑 = 該方位的城市數
        theta=agg["dir_bin"].astype(str),                            # 角度 = 方位名
        marker=dict(
            color=agg["mean_aqi"],                                   # 色階 = 平均 AQI
            colorscale=[[0, GREEN], [0.4, YELLOW], [0.7, ORANGE], [1, RED]],
            cmin=20, cmax=180,                                       # 固定色階範圍
            colorbar=dict(title=dict(text="平均 AQI", font=dict(color="#c0c8d8")),
                           tickfont=dict(color=TICK), len=0.7, outlinewidth=0),
            line=dict(color="#04060f", width=2),                    # 黑色邊框讓扇形更分明
        ),
        hovertemplate="<b>%{theta}</b><br>城市數: %{r}<br>平均 AQI: %{marker.color:.1f}<extra></extra>",
    ))
    fig.update_layout(**_base_layout(
        height=420,
        polar=dict(
            bgcolor="rgba(15, 24, 48, 0.4)",
            radialaxis=dict(visible=True, gridcolor=GRID, linecolor=AXIS_LINE,
                            tickfont=dict(color=TICK, size=9)),
            angularaxis=dict(
                direction="clockwise", rotation=90,    # 順時針方向(地圖慣例),北朝上
                gridcolor=GRID, linecolor=AXIS_LINE,
                tickfont=dict(color="#c0c8d8", size=11),
            ),
        ),
    ))
    return fig


# ─── 濕度 vs AQI 散點 + 趨勢線 ──────────────────────────────────────────────


def make_humidity_scatter(snapshot: pd.DataFrame) -> go.Figure:
    """濕度與 AQI 的散點圖 + 線性回歸 + Pearson 相關係數。

    研究問題:濕度高的城市 AQI 是否較低?(理論上濕度高有助於 PM 沉降)
    本圖用簡單線性回歸 + 相關係數量化兩者關係,圖上會顯示 r 值。
    """
    x = snapshot["humidity"].values
    y = snapshot["aqi"].values
    if len(x) >= 2:
        # np.polyfit 用最小平方法回歸,deg=1 = 線性
        m, b = np.polyfit(x, y, 1)
        r = float(np.corrcoef(x, y)[0, 1])   # Pearson 相關係數
    else:
        # 不到 2 個點時,fallback 到「水平直線=均值」並用 r=0
        m, b, r = 0, y.mean() if len(y) else 0, 0.0
    # 趨勢線延伸到資料邊界外 2 單位,讓視覺上看起來不會被截
    line_x = np.array([x.min() - 2, x.max() + 2])
    line_y = m * line_x + b

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers+text",
        text=snapshot["city"],
        textposition="top center",
        textfont=dict(size=10, color="#c0c8d8"),
        marker=dict(size=14, color=snapshot["color"],
                    line=dict(width=1, color="rgba(255,255,255,0.5)")),
        customdata=np.stack([snapshot["city"], snapshot["humidity"], snapshot["aqi"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>濕度: %{x:.0f}%<br>AQI: %{y:.1f}<extra></extra>",
        showlegend=False, name="cities",
    ))
    # 趨勢線(橘色虛線,跟資料點顏色形成對比)
    fig.add_trace(go.Scatter(
        x=line_x, y=line_y, mode="lines",
        line=dict(color=ORANGE, width=2, dash="dot"),
        name=f"趨勢線 (r={r:+.2f})",
        hoverinfo="skip",   # 趨勢線不需要 hover,避免遮擋資料點
    ))
    fig.update_layout(**_base_layout(
        height=380,
        xaxis_title="濕度 (%)",
        yaxis_title="AQI",
    ))
    # 右上角 annotation 顯眼地秀出相關係數
    fig.add_annotation(
        x=0.98, y=0.96, xref="paper", yref="paper",
        text=f"<b>相關係數 r = {r:+.2f}</b>",
        showarrow=False, align="right",
        font=dict(color=ORANGE, family="JetBrains Mono", size=13),
        bgcolor="rgba(15, 24, 48, 0.8)", bordercolor=ORANGE, borderwidth=1, borderpad=6,
    )
    return fig


# ─── 民間 vs 官方測站對比 ───────────────────────────────────────────────────


def make_citizen_vs_official(df: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    """並排長條圖:每個城市的「官方測站 PM2.5」vs「民間感測器 PM2.5」。

    用途:檢視兩種資料來源的一致性。理論上應接近,但民間感測器精度較差、
    放置位置(如住家陽台)可能更貼近實際呼吸環境,差異本身就是分析價值。

    Parameters
    ----------
    df : pd.DataFrame
        需包含 city, official_PM2.5, citizen_PM2.5
    """
    cities = df["city"]
    fig = go.Figure()
    # 官方測站:青色,代表權威 / 標準
    fig.add_trace(go.Bar(
        x=cities, y=df["official_PM2.5"],
        name="官方測站 (Agent A)",
        marker=dict(color=CYAN, line=dict(color="rgba(255,255,255,0.2)", width=1)),
        hovertemplate="<b>%{x}</b><br>官方: %{y} μg/m³<extra></extra>",
    ))
    # 民間感測器:橘色,代表 grass-roots / 草根資料
    fig.add_trace(go.Bar(
        x=cities, y=df["citizen_PM2.5"],
        name="民間感測器 (Agent D)",
        marker=dict(color=ORANGE, line=dict(color="rgba(255,255,255,0.2)", width=1)),
        hovertemplate="<b>%{x}</b><br>民間: %{y} μg/m³<extra></extra>",
    ))
    fig.update_layout(**_base_layout(
        height=360,
        barmode="group",     # group 模式 — 同一城市的兩個 bar 並排(對比用)
        bargap=0.3,
        yaxis_title="PM2.5 (μg/m³)",
    ))
    return fig


# ─── 地理分佈圖(scatter mapbox) ───────────────────────────────────────────


def make_map(snapshot: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    """20 個城市在台灣地圖上的散點分佈圖。

    特色:
      - 圓點大小 = AQI 相對值(視覺一目了然哪邊空品差)
      - 圓點顏色 = AQI 等級色(綠/黃/橘/紅/紫)
      - 聚焦城市保持不透明,其餘 55%(略灰化)讓使用者更容易找
      - 底圖用 carto-darkmatter 風格,與整體深色主題一致

    Parameters
    ----------
    snapshot : pd.DataFrame
        需包含 lat, lon, aqi, color, city, PM2.5, level, city_id
    highlight : str | None
        聚焦城市 id,非聚焦城市不透明度降為 55%
    """
    # 氣泡大小:14-49 之間(min=14 確保最低 AQI 城市也看得見、max~49 避免太大)
    sizes = (snapshot["aqi"] / snapshot["aqi"].max() * 35 + 14)
    # 不透明度:聚焦城市 1.0,其餘 0.55(灰化但仍可辨識)
    opacity = [1.0 if (highlight is None or cid == highlight) else 0.55
               for cid in snapshot["city_id"]]
    fig = go.Figure(go.Scattermapbox(
        lat=snapshot["lat"], lon=snapshot["lon"],
        mode="markers+text",
        text=snapshot["city"],
        textposition="top right",
        textfont=dict(color="#e8eef7", size=11),
        marker=dict(
            size=sizes,
            color=snapshot["color"],
            opacity=opacity,
        ),
        customdata=np.stack([snapshot["city"], snapshot["aqi"], snapshot["PM2.5"], snapshot["level"]], axis=-1),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "AQI: <b>%{customdata[1]}</b><br>"
            "PM2.5: %{customdata[2]} μg/m³<br>"
            "等級: %{customdata[3]}<extra></extra>"
        ),
    ))
    fig.update_layout(**_base_layout(
        height=460,
        mapbox=dict(
            style="carto-darkmatter",                    # 免 token 的深色底圖
            center=dict(lat=24.0, lon=120.5),            # 中心點稍偏西 — 把金門/澎湖/馬祖納入畫面
            zoom=5.7,
        ),
        margin=dict(l=0, r=0, t=10, b=0),                # 地圖佔滿整個容器
    ))
    return fig


# NOTE: 早期版本還有 `make_outdoor_bars` 與 `make_satellite_panel`,
# 已分別於 2026-05-16(隨 SECTION · 08 outdoor 區塊移除)與更早期移除。
# 真實的 Sentinel-5P / CAMS 衛星資料需要 Google Earth Engine / Copernicus
# 帳號,作為個人專案 demo 太複雜。其他部分都改用真實 API(EPA / Open-Meteo
# / LASS) — 見 data.py。
