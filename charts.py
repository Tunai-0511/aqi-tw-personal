"""All Plotly chart factories. Every chart shares the same dark template and
returns a `go.Figure` ready to drop into `st.plotly_chart`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from data import AQI_LEVELS, POLLUTANTS, aqi_to_level

# ---------------------------------------------------------------------------
# Global theming
# ---------------------------------------------------------------------------

PAPER     = "rgba(0,0,0,0)"
PLOT      = "rgba(0,0,0,0)"
FONT      = dict(family="Inter, system-ui, sans-serif", color="#e8eef7", size=12)
GRID      = "rgba(0, 217, 255, 0.08)"
AXIS_LINE = "rgba(0, 217, 255, 0.25)"
TICK      = "#8b95a8"

CYAN   = "#00d9ff"
ORANGE = "#ff8c42"
GREEN  = "#00e676"
YELLOW = "#ffd93d"
RED    = "#ff4757"
PURPLE = "#9b59ff"

PALETTE = [CYAN, ORANGE, GREEN, YELLOW, PURPLE, RED, "#4eecff", "#ffb380", "#7af1bb", "#c4a5ff"]


def _base_layout(**kw) -> dict:
    """Return the default layout dict, merged with overrides."""
    base = dict(
        paper_bgcolor=PAPER,
        plot_bgcolor=PLOT,
        font=FONT,
        margin=dict(l=40, r=20, t=40, b=40),
        hoverlabel=dict(
            bgcolor="rgba(15, 24, 48, 0.95)",
            bordercolor=CYAN,
            font=dict(family="JetBrains Mono", color="#e8eef7", size=12),
        ),
        legend=dict(
            bgcolor="rgba(15, 24, 48, 0.5)",
            bordercolor="rgba(0, 217, 255, 0.2)",
            borderwidth=1,
            font=dict(color="#e8eef7"),
        ),
        xaxis=dict(
            gridcolor=GRID, zerolinecolor=AXIS_LINE,
            linecolor=AXIS_LINE, tickcolor=AXIS_LINE,
            tickfont=dict(color=TICK), title_font=dict(color="#c0c8d8"),
        ),
        yaxis=dict(
            gridcolor=GRID, zerolinecolor=AXIS_LINE,
            linecolor=AXIS_LINE, tickcolor=AXIS_LINE,
            tickfont=dict(color=TICK), title_font=dict(color="#c0c8d8"),
        ),
    )
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------


def make_aqi_gauge(aqi: float, city_name: str = "") -> go.Figure:
    lvl = aqi_to_level(aqi)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=aqi,
        number=dict(font=dict(size=44, color=lvl["color"], family="JetBrains Mono")),
        domain=dict(x=[0, 1], y=[0, 1]),
        gauge=dict(
            axis=dict(range=[0, 300], tickwidth=1, tickcolor=TICK,
                      tickfont=dict(color=TICK, size=10)),
            bar=dict(color=lvl["color"], thickness=0.28),
            bgcolor="rgba(255,255,255,0.03)",
            borderwidth=2, bordercolor="rgba(0, 217, 255, 0.3)",
            steps=[
                {"range": [0, 50],    "color": "rgba(0, 230, 118, 0.18)"},
                {"range": [50, 100],  "color": "rgba(255, 217, 61, 0.18)"},
                {"range": [100, 150], "color": "rgba(255, 140, 66, 0.20)"},
                {"range": [150, 200], "color": "rgba(255, 71, 87, 0.22)"},
                {"range": [200, 300], "color": "rgba(155, 89, 255, 0.22)"},
            ],
            threshold=dict(line=dict(color="#ffffff", width=3), thickness=0.85, value=aqi),
        ),
    ))
    fig.update_layout(**_base_layout(
        height=280, margin=dict(l=10, r=10, t=20, b=10),
    ))
    return fig


# ---------------------------------------------------------------------------
# Ranking bar
# ---------------------------------------------------------------------------


def make_city_ranking(df: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    s = df.sort_values("aqi", ascending=True).copy()
    colors = [
        ("#fff" if highlight == cid else c)
        for cid, c in zip(s["city_id"], s["color"])
    ]
    line_widths = [3 if highlight == cid else 0 for cid in s["city_id"]]

    fig = go.Figure(go.Bar(
        x=s["aqi"], y=s["city"], orientation="h",
        marker=dict(color=s["color"], line=dict(color=colors, width=line_widths)),
        text=[f"<b>{v:.0f}</b>" for v in s["aqi"]],
        textposition="outside",
        textfont=dict(color="#e8eef7", family="JetBrains Mono", size=12),
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
        margin=dict(l=70, r=30, t=20, b=30),
        xaxis_title="AQI",
        showlegend=False,
    ))
    return fig


# ---------------------------------------------------------------------------
# Scatter: PM2.5 vs AQI, bubble = risk
# ---------------------------------------------------------------------------


def make_pm25_aqi_scatter(df: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    sizes = (df["risk"] / df["risk"].max() * 50 + 12).clip(lower=10)
    opacity = [1.0 if (highlight is None or cid == highlight) else 0.35 for cid in df["city_id"]]
    line_width = [3 if cid == highlight else 1 for cid in df["city_id"]]

    fig = go.Figure(go.Scatter(
        x=df["PM2.5"], y=df["aqi"],
        mode="markers+text",
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


# ---------------------------------------------------------------------------
# 24h trend line
# ---------------------------------------------------------------------------


def make_trend_line(ts_df: pd.DataFrame, city_ids: list[str]) -> go.Figure:
    fig = go.Figure()
    for i, cid in enumerate(city_ids):
        d = ts_df[ts_df["city_id"] == cid].sort_values("timestamp")
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["timestamp"], y=d["aqi"],
            mode="lines+markers",
            name=d["city"].iloc[0],
            line=dict(color=PALETTE[i % len(PALETTE)], width=2.2, shape="spline", smoothing=0.6),
            marker=dict(size=5),
            hovertemplate="<b>%{fullData.name}</b><br>%{x|%m/%d %H:%M}<br>AQI: <b>%{y:.1f}</b><extra></extra>",
        ))
    fig.update_layout(**_base_layout(
        height=400,
        xaxis_title="時間",
        yaxis_title="AQI",
        hovermode="x unified",
    ))
    return fig


# ---------------------------------------------------------------------------
# Heatmap (hour × city)
# ---------------------------------------------------------------------------


def make_heatmap(ts_df: pd.DataFrame) -> go.Figure:
    pv = (ts_df.assign(hour=ts_df["timestamp"].dt.strftime("%m/%d %H:00"))
                .pivot_table(index="city", columns="hour", values="aqi"))
    fig = go.Figure(go.Heatmap(
        z=pv.values, x=pv.columns, y=pv.index,
        colorscale=[
            [0.00, "#00e676"], [0.16, "#ffd93d"], [0.33, "#ff8c42"],
            [0.50, "#ff4757"], [0.75, "#9b59ff"], [1.00, "#7f0000"],
        ],
        zmin=0, zmax=200,
        colorbar=dict(
            title=dict(text="AQI", font=dict(color="#c0c8d8")),
            tickfont=dict(color=TICK),
            outlinewidth=0, len=0.85,
        ),
        hovertemplate="<b>%{y}</b><br>%{x}<br>AQI: <b>%{z:.1f}</b><extra></extra>",
    ))
    fig.update_layout(**_base_layout(
        height=420,
        margin=dict(l=80, r=20, t=20, b=80),
    ))
    fig.update_xaxes(tickangle=-45, tickfont=dict(size=9))
    return fig


# ---------------------------------------------------------------------------
# Radar — pollutant profile
# ---------------------------------------------------------------------------


def make_pollutant_radar(snapshot: pd.DataFrame, city_ids: list[str]) -> go.Figure:
    fig = go.Figure()
    # Normalize each pollutant against a soft reference scale so all fit one chart.
    ref = {"PM2.5": 50, "PM10": 100, "O3": 100, "NO2": 80, "SO2": 30, "CO": 5}
    for i, cid in enumerate(city_ids):
        row = snapshot[snapshot["city_id"] == cid].iloc[0]
        vals = [min(100, row[p] / ref[p] * 100) for p in POLLUTANTS]
        fig.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=POLLUTANTS + [POLLUTANTS[0]],
            fill="toself",
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


# ---------------------------------------------------------------------------
# 6h forecast with confidence band
# ---------------------------------------------------------------------------


def make_forecast_chart(df: pd.DataFrame, city_name: str) -> go.Figure:
    hist = df[~df["is_forecast"]]
    fc   = df[df["is_forecast"]]
    fig = go.Figure()

    # Confidence band
    if not fc.empty:
        band_x = list(fc["timestamp"]) + list(fc["timestamp"][::-1])
        band_y = list(fc["upper"])      + list(fc["lower"][::-1])
        fig.add_trace(go.Scatter(
            x=band_x, y=band_y, fill="toself",
            fillcolor="rgba(255, 140, 66, 0.18)",
            line=dict(width=0), showlegend=False,
            name="信心區間",
            hoverinfo="skip",
        ))
    # Historic line (solid)
    fig.add_trace(go.Scatter(
        x=hist["timestamp"], y=hist["aqi"],
        mode="lines+markers", name="已觀測",
        line=dict(color=CYAN, width=3),
        marker=dict(size=6),
        hovertemplate="%{x|%m/%d %H:%M}<br>AQI: <b>%{y:.1f}</b><extra></extra>",
    ))
    # Forecast line (dashed)
    if not fc.empty:
        last = hist.iloc[[-1]]
        fc2 = pd.concat([last, fc])
        fig.add_trace(go.Scatter(
            x=fc2["timestamp"], y=fc2["aqi"],
            mode="lines+markers", name="預測",
            line=dict(color=ORANGE, width=3, dash="dash"),
            marker=dict(size=6, symbol="diamond"),
            hovertemplate="%{x|%m/%d %H:%M}<br>預測 AQI: <b>%{y:.1f}</b><extra></extra>",
        ))
    fig.update_layout(**_base_layout(
        height=380,
        title=dict(text=f"<b>{city_name}</b> · 過去 12h 與未來 6h",
                   font=dict(color="#e8eef7", size=14), x=0.02, y=0.95),
        xaxis_title=None, yaxis_title="AQI",
        hovermode="x unified",
    ))
    return fig


# ---------------------------------------------------------------------------
# Stacked pollutant composition
# ---------------------------------------------------------------------------


def make_stacked_composition(snapshot: pd.DataFrame) -> go.Figure:
    df = snapshot.copy()
    # Normalize each pollutant against a reference so they fit on one axis.
    ref = {"PM2.5": 50, "PM10": 100, "O3": 100, "NO2": 80, "SO2": 30, "CO": 5}
    for p in POLLUTANTS:
        df[f"{p}_norm"] = df[p] / ref[p] * 100
    colors = {"PM2.5": CYAN, "PM10": "#4eecff", "O3": YELLOW,
              "NO2": ORANGE, "SO2": PURPLE, "CO": RED}
    fig = go.Figure()
    for p in POLLUTANTS:
        fig.add_trace(go.Bar(
            x=df[f"{p}_norm"], y=df["city"], orientation="h",
            name=p, marker=dict(color=colors[p]),
            customdata=df[p],
            hovertemplate=f"<b>%{{y}}</b><br>{p}: %{{customdata}}<br>強度: %{{x:.1f}}%<extra></extra>",
        ))
    fig.update_layout(**_base_layout(
        height=420,
        barmode="stack",
        xaxis_title="標準化強度 (%)",
        margin=dict(l=70, r=30, t=20, b=30),
    ))
    return fig


# ---------------------------------------------------------------------------
# Wind rose
# ---------------------------------------------------------------------------


def make_wind_rose(snapshot: pd.DataFrame) -> go.Figure:
    # Center each bin on its cardinal direction by shifting -22.5°.
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    snapshot = snapshot.copy()
    shifted = (snapshot["wind_dir"] + 22.5) % 360
    bins = [0, 45, 90, 135, 180, 225, 270, 315, 360]  # 9 edges → 8 labels
    snapshot["dir_bin"] = pd.cut(shifted, bins=bins, labels=dirs,
                                  include_lowest=True, right=False)
    agg = snapshot.groupby("dir_bin", observed=True).agg(
        count=("aqi", "size"), mean_aqi=("aqi", "mean")).reset_index()
    fig = go.Figure(go.Barpolar(
        r=agg["count"],
        theta=agg["dir_bin"].astype(str),
        marker=dict(
            color=agg["mean_aqi"],
            colorscale=[[0, GREEN], [0.4, YELLOW], [0.7, ORANGE], [1, RED]],
            cmin=20, cmax=180,
            colorbar=dict(title=dict(text="平均 AQI", font=dict(color="#c0c8d8")),
                           tickfont=dict(color=TICK), len=0.7, outlinewidth=0),
            line=dict(color="#04060f", width=2),
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
                direction="clockwise", rotation=90,
                gridcolor=GRID, linecolor=AXIS_LINE,
                tickfont=dict(color="#c0c8d8", size=11),
            ),
        ),
    ))
    return fig


# ---------------------------------------------------------------------------
# Humidity vs AQI scatter with trendline
# ---------------------------------------------------------------------------


def make_humidity_scatter(snapshot: pd.DataFrame) -> go.Figure:
    x = snapshot["humidity"].values
    y = snapshot["aqi"].values
    if len(x) >= 2:
        m, b = np.polyfit(x, y, 1)
        r = float(np.corrcoef(x, y)[0, 1])
    else:
        m, b, r = 0, y.mean() if len(y) else 0, 0.0
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
    fig.add_trace(go.Scatter(
        x=line_x, y=line_y, mode="lines",
        line=dict(color=ORANGE, width=2, dash="dot"),
        name=f"趨勢線 (r={r:+.2f})",
        hoverinfo="skip",
    ))
    fig.update_layout(**_base_layout(
        height=380,
        xaxis_title="濕度 (%)",
        yaxis_title="AQI",
    ))
    fig.add_annotation(
        x=0.98, y=0.96, xref="paper", yref="paper",
        text=f"<b>相關係數 r = {r:+.2f}</b>",
        showarrow=False, align="right",
        font=dict(color=ORANGE, family="JetBrains Mono", size=13),
        bgcolor="rgba(15, 24, 48, 0.8)", bordercolor=ORANGE, borderwidth=1, borderpad=6,
    )
    return fig


# ---------------------------------------------------------------------------
# Citizen vs official comparison
# ---------------------------------------------------------------------------


def make_citizen_vs_official(df: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    cities = df["city"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=cities, y=df["official_PM2.5"],
        name="官方測站 (Agent A)",
        marker=dict(color=CYAN, line=dict(color="rgba(255,255,255,0.2)", width=1)),
        hovertemplate="<b>%{x}</b><br>官方: %{y} μg/m³<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=cities, y=df["citizen_PM2.5"],
        name="民間感測器 (Agent D)",
        marker=dict(color=ORANGE, line=dict(color="rgba(255,255,255,0.2)", width=1)),
        hovertemplate="<b>%{x}</b><br>民間: %{y} μg/m³<extra></extra>",
    ))
    fig.update_layout(**_base_layout(
        height=360,
        barmode="group",
        bargap=0.3,
        yaxis_title="PM2.5 (μg/m³)",
    ))
    return fig


# ---------------------------------------------------------------------------
# Map / scatter geo
# ---------------------------------------------------------------------------


def make_map(snapshot: pd.DataFrame, highlight: str | None = None) -> go.Figure:
    sizes = (snapshot["aqi"] / snapshot["aqi"].max() * 35 + 14)
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
            style="carto-darkmatter",
            center=dict(lat=24.0, lon=120.5),  # shifted west to fit 金門/馬祖/澎湖
            zoom=5.7,
        ),
        margin=dict(l=0, r=0, t=10, b=0),
    ))
    return fig


# ---------------------------------------------------------------------------
# Outdoor hours mini-bar
# ---------------------------------------------------------------------------


def make_outdoor_bars(df: pd.DataFrame) -> go.Figure:
    colors = [
        ORANGE if rec else "#3a4566"
        for rec in df["recommend"]
    ]
    fig = go.Figure(go.Bar(
        x=df["hour"], y=df["score"],
        marker=dict(color=df["color"],
                    line=dict(color=colors, width=[3 if r else 0 for r in df["recommend"]])),
        text=[f"<b>★</b>" if r else "" for r in df["recommend"]],
        textposition="outside",
        textfont=dict(color=ORANGE, size=14),
        customdata=np.stack([df["aqi"], df["level"]], axis=-1),
        hovertemplate="<b>%{x}</b><br>戶外指數: %{y}<br>AQI: %{customdata[0]:.1f}<br>等級: %{customdata[1]}<extra></extra>",
    ))
    fig.update_layout(**_base_layout(
        height=260,
        yaxis_title="戶外指數",
        showlegend=False,
        margin=dict(l=40, r=20, t=20, b=40),
    ))
    return fig


# NOTE: previously this file also exported `make_satellite_panel`, which
# rendered a synthetic "NASA TROPOMI" panel. The TROPOMI section has been
# removed because we cannot pull real Sentinel-5P data without significant
# Google Earth Engine / Copernicus Data Space setup. See data.py for the
# real-data fetchers that took over the rest of the dashboard.
