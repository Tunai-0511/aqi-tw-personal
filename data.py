"""
資料層 (Data Layer) — LobsterAQI 的核心資料模組
============================================================

本檔案包含三大類功能:

1. **靜態參考資料 (Static Reference Data)**
   - `CITIES`:台灣 20 個縣市的基礎資料(中英文名、區域、經緯度、AQI bias 係數)
   - `AQI_LEVELS`:6 個 AQI 等級的閾值、中文名、顏色、健康建議
   - `POLLUTANTS`:6 種主要污染物清單
   - `SENSITIVE_GROUPS` / `GROUP_ADVICE` / `OUTDOOR_ACTIVITIES`:UI 配置

2. **合成資料生成器 (Synthetic Generators)** — Mock fallback
   - `generate_current_snapshot()`:整批 20 城市的當下 AQI 模擬
   - `generate_time_series()`:24h 時序模擬
   - 這些函式只在 EPA API 失敗時被呼叫做 fallback,
     使用 `np.random` 加 `_diurnal_factor` (日夜峰值模型) 產生合理的假資料

3. **真實 API 抓取器 (Real API Fetchers)**
   - `fetch_epa_realtime()`:環境部 EPA aqx_p_432 即時資料
   - `fetch_epa_historical()`:環境部 EPA aqx_p_488 24h 歷史
   - `fetch_open_meteo_*()`:Open-Meteo 氣象 + CAMS 大氣化學模式(免金鑰)
   - `fetch_citizen_sensors()`:民生公共物聯網 + LASS-net Airbox 民間感測器
   - `generate_real_snapshot()`:整合上述 API 產出真實的「當下快照」
   - `generate_real_timeseries()`:整合產出真實的「24h 時序」
   - `call_llm_api()`:呼叫各家 LLM(Anthropic / Gemini / MiniMax / OpenAI / 自訂)
   - `send_discord_webhook()`:Pipeline 完成後推送摘要到 Discord

備註: 此檔案早期是純 mock 生成器(docstring 寫的就是這樣),後來逐步加入
真實 API 後,mock 變成「fallback 安全網」而非主要路徑。`app.py:603-609`
顯示了切換邏輯:EPA 成功 → real;失敗 → mock,並在 UI 標示 'MOCK 模擬資料'。
"""

from __future__ import annotations

# 使用作業系統的憑證儲存區(Windows certmgr / macOS Keychain),而非 certifi 內建的 CA 清單。
# 在 OpenSSL 3.5+ 環境下,certifi 的 CA 對某些憑證(例:台灣 MOENV 的 TWCA)會因為
# 缺少 Subject Key Identifier extension 而被拒。改用 OS 憑證可避開此問題。
# 必須在 `import requests` 之前執行,因為 urllib3 在 import 時就會固定 SSL context。
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    # truststore 套件選裝;裝失敗就 fallback 到 certifi 預設行為
    pass

import json
import math
import random
import time
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

# ─── 靜態參考資料 (Static Reference Data) ─────────────────────────────────
# 以下三個常數是整個系統的基礎事實來源 — 對其他模組是 read-only。
# 變更這些值需確認上下游(charts.py / app.py / _city_detail.py)的對應邏輯。
# ─────────────────────────────────────────────────────────────────────────

# 台灣 20 縣市清單(含本島 17 + 離島 3)。
# 每個 dict 的欄位:
#   id     英文 slug,作為 DataFrame 的 city_id 主鍵
#   name   中文名,顯示給使用者看
#   en     英文官方名
#   region 北/中/南/東/離島 — 用於區域聚合與統計
#   lat,lon 地圖標點座標(EPSG:4326)
#   bias   AQI 模擬時的城市偏差係數 — 工業城市較高、東部 / 離島較低,
#          僅在 mock fallback 時使用。
CITIES: list[dict[str, Any]] = [
    # 北部
    {"id": "taipei",     "name": "台北市", "en": "Taipei",     "region": "北部", "lat": 25.03, "lon": 121.57, "bias": 0.95},
    {"id": "new_taipei", "name": "新北市", "en": "New Taipei", "region": "北部", "lat": 25.01, "lon": 121.46, "bias": 1.00},
    {"id": "taoyuan",    "name": "桃園市", "en": "Taoyuan",    "region": "北部", "lat": 24.99, "lon": 121.31, "bias": 1.10},
    {"id": "hsinchu",    "name": "新竹市", "en": "Hsinchu",    "region": "北部", "lat": 24.81, "lon": 120.97, "bias": 0.90},
    {"id": "keelung",    "name": "基隆市", "en": "Keelung",    "region": "北部", "lat": 25.13, "lon": 121.74, "bias": 0.80},
    {"id": "yilan",      "name": "宜蘭縣", "en": "Yilan",      "region": "北部", "lat": 24.76, "lon": 121.75, "bias": 0.55},
    # 中部
    {"id": "miaoli",     "name": "苗栗縣", "en": "Miaoli",     "region": "中部", "lat": 24.56, "lon": 120.82, "bias": 1.00},
    {"id": "taichung",   "name": "台中市", "en": "Taichung",   "region": "中部", "lat": 24.15, "lon": 120.68, "bias": 1.30},
    {"id": "changhua",   "name": "彰化縣", "en": "Changhua",   "region": "中部", "lat": 24.08, "lon": 120.54, "bias": 1.25},
    {"id": "nantou",     "name": "南投縣", "en": "Nantou",     "region": "中部", "lat": 23.96, "lon": 120.97, "bias": 0.85},
    {"id": "yunlin",     "name": "雲林縣", "en": "Yunlin",     "region": "中部", "lat": 23.71, "lon": 120.43, "bias": 1.45},  # 麥寮六輕
    {"id": "chiayi",     "name": "嘉義市", "en": "Chiayi",     "region": "中部", "lat": 23.48, "lon": 120.45, "bias": 1.20},
    # 南部
    {"id": "tainan",     "name": "台南市", "en": "Tainan",     "region": "南部", "lat": 22.99, "lon": 120.21, "bias": 1.25},
    {"id": "kaohsiung",  "name": "高雄市", "en": "Kaohsiung",  "region": "南部", "lat": 22.63, "lon": 120.30, "bias": 1.40},
    {"id": "pingtung",   "name": "屏東縣", "en": "Pingtung",   "region": "南部", "lat": 22.67, "lon": 120.49, "bias": 1.15},
    # 東部
    {"id": "hualien",    "name": "花蓮縣", "en": "Hualien",    "region": "東部", "lat": 23.99, "lon": 121.61, "bias": 0.55},
    {"id": "taitung",    "name": "台東縣", "en": "Taitung",    "region": "東部", "lat": 22.76, "lon": 121.14, "bias": 0.45},
    # 離島
    {"id": "penghu",     "name": "澎湖縣", "en": "Penghu",     "region": "離島", "lat": 23.57, "lon": 119.58, "bias": 0.50},
    {"id": "kinmen",     "name": "金門縣", "en": "Kinmen",     "region": "離島", "lat": 24.45, "lon": 118.38, "bias": 1.20},  # 受陸源影響
    {"id": "matsu",      "name": "連江縣", "en": "Matsu",      "region": "離島", "lat": 26.16, "lon": 119.95, "bias": 1.05},
]

# id → city dict 的快速查表;遠比每次 `next(c for c in CITIES if c["id"]==x)` 快
CITY_BY_ID = {c["id"]: c for c in CITIES}

# 6 種主要污染物的標準順序 — 用於雷達圖、堆疊圖、表格欄位順序的單一來源
POLLUTANTS = ["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]

# AQI 6 級分級表(對齊台灣 EPA / US EPA 國際標準的 0-500 制)。
# 順序很重要 — aqi_to_level() 從上往下找第一個 aqi <= max 的等級。
# 每級包含:
#   max    該級的 AQI 上限
#   name   中文等級名(顯示用)
#   color  Hex 色碼(全應用統一)
#   level  數字級別 1-6(便於排序 / 篩選)
#   advice 短文字健康建議(LLM 失敗時的 fallback)
AQI_LEVELS = [
    {"max":  50, "name": "良好",            "color": "#00e676", "level": 1, "advice": "空氣品質良好，適合戶外活動"},
    {"max": 100, "name": "普通",            "color": "#ffd93d", "level": 2, "advice": "極少數族群可能輕微不適，可正常活動"},
    {"max": 150, "name": "對敏感族群不健康", "color": "#ff8c42", "level": 3, "advice": "敏感族群應減少長時間或激烈戶外活動"},
    {"max": 200, "name": "對所有族群不健康", "color": "#ff4757", "level": 4, "advice": "所有人應減少戶外活動，敏感族群避免外出"},
    {"max": 300, "name": "非常不健康",       "color": "#9b59ff", "level": 5, "advice": "所有族群應留在室內並關閉門窗"},
    {"max": 999, "name": "危害",            "color": "#7f0000", "level": 6, "advice": "緊急狀態，所有人應留在室內"},
]


def aqi_to_level(aqi: float) -> dict[str, Any]:
    """把 AQI 數值轉成對應的等級 dict(含中文名、顏色、健康建議)。

    線性掃描 AQI_LEVELS,回傳第一個 aqi <= lvl["max"] 的等級;
    超過 300 直接回傳最後一級「危害」。

    為什麼用線性掃描而非二分?因為只有 6 級,線性 O(6) 還比 bisect 的
    overhead 更快,且程式碼直覺易讀。
    """
    for lvl in AQI_LEVELS:
        if aqi <= lvl["max"]:
            return lvl
    return AQI_LEVELS[-1]


# ─── 時間感知的合成生成器 (Time-aware Synthetic Generators) ──────────────
# 這個區段的所有函式都是「mock fallback」 — 當 EPA API 失敗時才會被呼叫。
# 它們不是真實資料,但用合理的數學模型(日夜雙峰、城市偏差、高斯噪聲)
# 產生視覺上「看起來合理」的數值,確保即使無法連到 API 也能展示 UI。
# ─────────────────────────────────────────────────────────────────────────


def _diurnal_factor(hour: int) -> float:
    """日夜雙峰模型 — 模擬 AQI 一天內的兩個尖峰(早 8 點 + 晚 6 點)。

    用兩個 Gaussian 鐘形曲線疊加,代表早晚通勤造成的空污尖峰。
    回傳值介於約 0.7(深夜低谷)到 1.6(尖峰),用乘法套用到 base AQI 上。

    為什麼是 8am 與 6pm?台灣交通尖峰時間;PM 與 NOx 排放在這兩段大幅增加。
    """
    morning = math.exp(-((hour - 8) ** 2) / 8)     # 早 8 點為中心的鐘形,寬度 ~2.8h
    evening = math.exp(-((hour - 18) ** 2) / 10)   # 晚 6 點為中心的鐘形,寬度 ~3.2h
    return 0.7 + 0.45 * (morning + evening)


def _seed_for(city_id: str, ts: datetime) -> int:
    """為「特定城市 + 特定小時」產生穩定的隨機種子。

    用途:讓同一個城市在同一小時內,不管程式跑幾次,看到的「合成 AQI」
    都是同一個數字 — 避免使用者每次 rerun 看到完全不同的值,造成困惑。

    hash 後 AND 0xFFFFFFFF 確保結果為 32-bit unsigned int(NumPy rng 要求)。
    """
    return hash((city_id, ts.strftime("%Y-%m-%d-%H"))) & 0xFFFFFFFF


def generate_current_snapshot(now: datetime | None = None) -> pd.DataFrame:
    """產生 20 城市的合成「當下快照」(mock fallback)。

    回傳一個 DataFrame,每個城市一列,欄位包括:
      city_id, city, en, region, lat, lon                  ← 城市靜態資料
      aqi, PM2.5, PM10, O3, NO2, SO2, CO                   ← 污染物
      wind_dir, wind_speed, humidity, temp, pressure       ← 氣象
      risk                                                  ← 加權風險分數 (0-100)
      level, level_num, color                              ← AQI 分級資訊
      updated_min_ago                                       ← 假的「X 分鐘前更新」(1-11)

    ⚠ 此函式產出的所有數值都是合成 — 僅在 EPA API 失敗時用於 UI fallback。
    呼叫者(app.py:637)會同步 set `data_mode='mock'` 讓 UI 標示「MOCK 模擬資料」。
    """
    now = now or datetime.now()
    hour = now.hour
    diurnal = _diurnal_factor(hour)   # 取得「目前小時的日夜倍率」(0.7~1.6)

    rows: list[dict[str, Any]] = []
    for city in CITIES:
        # 每個城市 + 該小時 的種子,確保「同一小時不會看到完全不同的值」
        rng = np.random.default_rng(_seed_for(city["id"], now))

        # ── AQI 計算 ──
        # 基準 55 × 城市偏差(雲林 1.45 / 台東 0.45)× 日夜倍率,再加 N(0, 10) 噪聲
        # 最後 clip 在 [15, 280] 範圍,避免出現負值或極端高(>300 應該是真實事件,不該被假資料模擬)
        base_aqi = 55 * city["bias"] * diurnal + rng.normal(0, 10)
        aqi = float(max(15, min(280, base_aqi)))

        # ── 各污染物 ──
        # 每個污染物都用「以 AQI 為基準的線性回歸 + 噪聲」做,模擬實際相關性
        # PM2.5 大約是 AQI 的 0.45 倍(以美國 NowCast 換算約略對齊)
        pm25 = max(2.0, aqi * 0.45 + rng.normal(0, 4))
        pm10 = max(5.0, pm25 * 1.6 + rng.normal(0, 6))            # PM10 通常是 PM2.5 的 1.5-1.8 倍
        o3   = max(5.0, 40 + (aqi - 60) * 0.3 + rng.normal(0, 8)) # O3 與 AQI 弱正相關
        no2  = max(2.0, 18 + aqi * 0.18 + rng.normal(0, 4))       # NO2 主要來自交通
        so2  = max(0.5, 4 + aqi * 0.03 + rng.normal(0, 1.5))      # SO2 在台灣已很低(燃煤管制)
        co   = max(0.1, 0.4 + aqi * 0.006 + rng.normal(0, 0.1))   # CO 同樣已普遍偏低

        # ── 氣象 ──
        wind_dir = float(rng.uniform(0, 360))                      # 風向 0-360°
        wind_speed = float(max(0.2, 3 + rng.normal(0, 1.4)))       # 風速 m/s
        humidity = float(max(30, min(95, 70 + rng.normal(0, 8))))  # 濕度 30-95%
        # 溫度模型:22°C 為均值,加上一天內的正弦波(早 6 點最冷 / 下午 2 點最熱),再加噪聲
        temperature = float(22 + 6 * math.sin((hour - 6) * math.pi / 12) + rng.normal(0, 1.2))
        pressure = float(1010 + rng.normal(0, 3))                   # 氣壓 hPa(海平面均壓 1013)

        # ── 風險分數(綜合 0-100) ──
        # 加權公式:PM2.5 權重最高(健康影響最大),CO 最低(已普遍很低)
        # 每個污染物先除以其「參考門檻」(PM2.5 用 35 對齊 EPA 24h 標準),再加權平均
        risk = 0.40 * (pm25 / 35) + 0.20 * (aqi / 150) + 0.15 * (o3 / 100) \
             + 0.10 * (no2 / 80)  + 0.08 * (so2 / 30) + 0.07 * (co / 5)
        # 乘 100 變成 0-100 分制,再 clip 邊界
        risk = float(min(100, max(0, risk * 100)))

        rows.append({
            "city_id": city["id"],
            "city":     city["name"],
            "en":       city["en"],
            "region":   city["region"],
            "lat":      city["lat"],
            "lon":      city["lon"],
            "aqi":      round(aqi, 1),
            "PM2.5":    round(pm25, 1),
            "PM10":     round(pm10, 1),
            "O3":       round(o3, 1),
            "NO2":      round(no2, 1),
            "SO2":      round(so2, 2),
            "CO":       round(co, 2),
            "wind_dir":   round(wind_dir, 0),
            "wind_speed": round(wind_speed, 1),
            "humidity":   round(humidity, 0),
            "temp":       round(temperature, 1),
            "pressure":   round(pressure, 0),
            "risk":       round(risk, 1),
            "level":      aqi_to_level(aqi)["name"],
            "level_num":  aqi_to_level(aqi)["level"],
            "color":      aqi_to_level(aqi)["color"],
            "updated_min_ago": int(rng.integers(1, 12)),
        })
    return pd.DataFrame(rows)


def generate_time_series(hours_back: int = 24, now: datetime | None = None) -> pd.DataFrame:
    """合成過去 N 小時 × 20 城市的逐小時時序資料(long-format)。

    內部會對每個小時呼叫一次 `generate_current_snapshot(ts)` 並把結果展平成
    長表(每列一個城市 × 一個時點)。這是 EPA / CAMS 都掛掉時的最後 fallback。

    Returns
    -------
    pd.DataFrame
        欄位:timestamp, city_id, city, region, aqi, PM2.5, PM10, O3, NO2, SO2, CO, risk
    """
    now = now or datetime.now()
    rows: list[dict[str, Any]] = []
    # range(hours_back, -1, -1) = 從最舊到最新依序產生(包含 0,即現在)
    for h in range(hours_back, -1, -1):
        # 對齊到整點(分秒歸零),確保時序的 x 軸刻度是漂亮的小時點
        ts = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
        df = generate_current_snapshot(ts)
        for _, r in df.iterrows():
            rows.append({
                "timestamp": ts,
                "city_id":   r["city_id"],
                "city":      r["city"],
                "region":    r["region"],
                "aqi":       r["aqi"],
                "PM2.5":     r["PM2.5"],
                "PM10":      r["PM10"],
                "O3":        r["O3"],
                "NO2":       r["NO2"],
                "SO2":       r["SO2"],
                "CO":        r["CO"],
                "risk":      r["risk"],
            })
    return pd.DataFrame(rows)


# ─── 輔助面板資料 (Auxiliary Panels) ──────────────────────────────────────


def generate_citizen_vs_official(
    snapshot_df: pd.DataFrame,
    lass_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """整合「官方 EPA」與「民間 LASS-net」的 PM2.5 對比表。

    輸出每個城市的:
      - official_PM2.5:來自 snapshot(EPA aqx_p_432 即時值)
      - citizen_PM2.5: 來自 LASS Airbox 的城市中位數(若有覆蓋)
      - delta:民間 - 官方(正值代表民間更高 — 通常在街角 / 住家陽台量測)
      - sensor_count:該城市的民間感測器數量

    若 LASS 抓取失敗(`lass_df` 為 None / empty),所有城市的 citizen_PM2.5
    填 NaN,UI 端會顯示「無民間感測站覆蓋」。
    """
    # 從 snapshot 取需要的欄位,並把 PM2.5 改名 official_PM2.5 以便和民間版區分
    df = snapshot_df[["city", "city_id", "PM2.5"]].copy()
    df = df.rename(columns={"PM2.5": "official_PM2.5"})

    if lass_df is not None and not lass_df.empty:
        # left join — 保留所有官方城市,民間沒覆蓋的城市為 NaN
        df = df.merge(
            lass_df[["city_id", "citizen_PM2.5", "sensor_count"]],
            on="city_id",
            how="left",
        )
    else:
        # LASS 抓取整體失敗時的 fallback,讓 UI 不會 KeyError
        df["citizen_PM2.5"] = float("nan")
        df["sensor_count"]  = 0

    # 計算差異(round 到 1 位小數方便顯示)
    df["delta"] = (df["citizen_PM2.5"] - df["official_PM2.5"]).round(1)
    return df[["city", "city_id", "official_PM2.5", "citizen_PM2.5", "delta", "sensor_count"]]


@dataclass
class CleaningReport:
    """清洗報告的不可變資料結構 — 整批 ETL 處理的統計結果。

    用途:UI 上「採集者」顯示「原始 X 筆 → 保留 Y 筆」的清洗摘要。
    被 `fetch_citizen_sensors()` 等真實 ETL 函式使用。
    """
    raw_records:    int                  # 從 API 拉到的原始筆數
    kept_records:   int                  # 經清洗後保留的筆數
    dropped_records: int                 # 被丟棄的筆數
    drop_reasons:   dict[str, int]       # 各種丟棄原因的計數,例:{"格式錯誤": 25, "重複資料": 12}

    @property
    def keep_rate(self) -> float:
        """保留率 = kept / max(1, raw),max 防止除以零。"""
        return self.kept_records / max(1, self.raw_records)


# ─── 健康建議 (Health Advisory) — UI 配置 ────────────────────────────────
# 以下三個常數是純 UI 配置,不是「資料」也不是「合成生成器」。
# 用於 sidebar 訂閱表單、個人化推薦頁面。
# ─────────────────────────────────────────────────────────────────────────

# 5 類敏感族群 — 與台灣 EPA / WHO 標準一致
# 每個 dict 提供 emoji icon + 中文標籤,供 multiselect 元件顯示
SENSITIVE_GROUPS = [
    {"id": "elderly",       "label": "老人",     "icon": "👴"},
    {"id": "children",      "label": "幼童",     "icon": "🧒"},
    {"id": "asthma",        "label": "氣喘患者", "icon": "🫁"},
    {"id": "cardiovascular","label": "心血管",   "icon": "❤️"},
    {"id": "pregnant",      "label": "孕婦",     "icon": "🤰"},
]

# 每類敏感族群的通用健康建議 — LLM 失敗時的 fallback
# 內容引用 WHO / EPA / Lancet 等文獻的共識
GROUP_ADVICE = {
    "elderly":        "避免清晨與傍晚交通尖峰時段外出，外出佩戴 N95 口罩，注意血壓變化。",
    "children":       "暫停戶外體育課與遊戲，改為室內活動，留意是否出現咳嗽或喘鳴。",
    "asthma":         "隨身攜帶吸入器，避免長時間戶外活動，若出現胸悶請立即就醫。",
    "cardiovascular": "減少劇烈運動，PM2.5 與心血管事件高度相關，留意胸痛與心悸。",
    "pregnant":       "盡量待在室內並開啟空氣清淨機，研究顯示 PM2.5 暴露與低出生體重相關。",
}

# 戶外活動類型 — 個人化推薦時供使用者選擇「我關心哪種活動」
OUTDOOR_ACTIVITIES = [
    {"id": "running",  "label": "慢跑",     "icon": "🏃"},
    {"id": "cycling",  "label": "自行車",   "icon": "🚴"},
    {"id": "walking",  "label": "散步",     "icon": "🚶"},
    {"id": "hiking",   "label": "登山",     "icon": "🥾"},
    {"id": "commute",  "label": "通勤",     "icon": "🚗"},
    {"id": "outdoor_work", "label": "戶外工作", "icon": "👷"},
]


# ─── 3-agent Pipeline 設定 (Agent Pipeline Configuration) ──────────────────


# Pipeline 中 3 個 agent 的排列順序(同時也是儀表板的視覺顯示順序,左到右)
# 執行流程:A 採集者 → B 分析師 → C 預警員
#
# 歷史:早期有 5 個 agent(採集者 / 爬蟲員 / 分析師 / 品管員 Critic / 預警員)。
# 「爬蟲員」與「採集者」工作重疊(都是 HTTP fetch),合併成單一採集者;
# 「品管員 Critic」原本給分析報告打 0-100 分,但低分並未真的觸發 retry,
# 等於不影響流程,因此移除。3-agent 重構讓邏輯更清晰、debug 更容易。
AGENTS = [
    {"id": "A", "name": "採集者", "role": "資料採集",   "color": "#00d9ff",
     "desc": "EPA + Open-Meteo + 民生公共物聯網 / LASS（並行清洗，無 LLM）"},
    {"id": "B", "name": "分析師", "role": "風險分析",   "color": "#9b59ff",
     "desc": "加權公式 + RAG 文獻檢索 + LLM 風險報告"},
    {"id": "C", "name": "預警員", "role": "健康預警",   "color": "#00e676",
     "desc": "風險等級 → 5 類敏感族群建議"},
]




# =============================================================================
# 即時資料 API Helper 區段 (Real-time API Helpers)
# =============================================================================
# 以下函式呼叫實際的外部 API,是「真實資料」的主要來源。
# 失敗時呼叫者(`generate_real_snapshot`)會 fallback 到上方的合成生成器。
# =============================================================================

# 環境部 EPA 回傳的「縣市中文名稱」對應到我們專案內的 city_id slug。
# 兩個 key 是為了處理「臺北市」與「台北市」這類「臺/台」異體字共存的情況。
COUNTY_TO_CITY_ID: dict[str, str] = {
    "臺北市": "taipei",    "台北市": "taipei",
    "新北市": "new_taipei",
    "桃園市": "taoyuan",
    "新竹市": "hsinchu",   "新竹縣": "hsinchu",
    "基隆市": "keelung",
    "宜蘭縣": "yilan",
    "苗栗縣": "miaoli",
    "臺中市": "taichung",  "台中市": "taichung",
    "彰化縣": "changhua",
    "南投縣": "nantou",
    "雲林縣": "yunlin",
    "嘉義市": "chiayi",    "嘉義縣": "chiayi",
    "臺南市": "tainan",    "台南市": "tainan",
    "高雄市": "kaohsiung",
    "屏東縣": "pingtung",
    "花蓮縣": "hualien",
    "臺東縣": "taitung",   "台東縣": "taitung",
    "澎湖縣": "penghu",
    "金門縣": "kinmen",
    "連江縣": "matsu",
}

# One representative city per region for weather fetching (limits Open-Meteo calls to 5)
_REGION_REPR: dict[str, str] = {
    "北部": "taipei",
    "中部": "taichung",
    "南部": "kaohsiung",
    "東部": "hualien",
    "離島": "penghu",
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    """安全地把任何值轉成 float;失敗或 NaN 都回 default。

    用於處理 API 回應中可能是 string / None / "ND"(EPA 用「ND」代表「測不到」)
    的數值欄位,避免 float("ND") 直接炸掉整支程式。
    """
    try:
        f = float(v)
        # NaN 不等於自己,math.isnan 是最可靠的偵測方式
        return f if not math.isnan(f) else default
    except (TypeError, ValueError):
        return default


def fetch_epa_realtime(api_key: str | None = None) -> pd.DataFrame | None:
    """從環境部 Open Data v2(moenv.gov.tw,前身為 epa.gov.tw)抓取即時 AQI。

    端點:`https://data.moenv.gov.tw/api/v2/aqx_p_432`(每小時更新一次)
    認證:需在 moenv.gov.tw 註冊帳號取得免費 api_key

    為什麼程式碼這麼防禦性?MOENV API 的回傳格式在實務中觀察到至少 4 種變形,
    可能是後端不同代版本並存。本函式對 4 種格式都能 parse:
      - {"records": [...], "total": N}        ← 較舊的格式
      - [{...}, {...}]                        ← 較新的純陣列
      - {"data": [...]}                       ← 某些 endpoint
      - {"result": {"records": [...]}}        ← 被包裝的格式

    Returns
    -------
    pd.DataFrame | None
        失敗時回 None — 呼叫者必須處理 None 的情況(切換到 mock fallback)
    """
    # limit=1000 一次取所有 77 個測站(實務上不到 80 筆,但留 buffer);format=JSON 而非 CSV
    params: dict[str, Any] = {"limit": 1000, "format": "JSON", "offset": 0}
    if api_key and api_key.strip():
        params["api_key"] = api_key.strip()
    try:
        r = requests.get(
            "https://data.moenv.gov.tw/api/v2/aqx_p_432",
            params=params, timeout=15,    # 15 秒夠長,Taiwan 主機通常 < 3s
        )
        r.raise_for_status()
        # 認證失敗時 MOENV 會回 HTTP 200 + 純文字錯誤訊息(而非 4xx),
        # 因此額外檢查 Content-Type 確認真的是 JSON
        ct = r.headers.get("Content-Type", "")
        if "json" not in ct.lower():
            return None
        body = r.json()
        records: list | None = None
        # 依序嘗試 4 種已知的格式;or 短路求值找到第一個非空的就停
        if isinstance(body, list):
            records = body
        elif isinstance(body, dict):
            records = (body.get("records")
                       or body.get("data")
                       or body.get("rows")
                       or (body.get("result", {}) or {}).get("records"))
        if not isinstance(records, list) or not records:
            return None
        return pd.DataFrame(records)
    except Exception:
        # 任何例外都回 None(網路斷線、JSON parse 失敗、Timeout 等)
        # 呼叫者會 fallback 到 mock
        return None


def fetch_weather_current(lat: float, lon: float) -> dict[str, float]:
    """從 Open-Meteo 抓取單點即時氣象(免金鑰、免註冊)。

    Open-Meteo 是歐洲氣象資料整合服務,提供免費的天氣 API,
    台灣氣象資料來源主要是 ECMWF + 各國氣象局的混合模型。

    失敗時不會炸,而是回一組「合理的台灣春夏典型值」(25°C / 70% / 3 m/s),
    確保 UI 即使在無網路情況下也能顯示完整的氣象卡片。
    """
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,surface_pressure",
                "timezone": "Asia/Taipei",
            },
            timeout=8,
        )
        r.raise_for_status()
        c = r.json().get("current", {})
        return {
            "temp":       float(c.get("temperature_2m", 25.0)),
            "humidity":   float(c.get("relative_humidity_2m", 70.0)),
            "wind_speed": float(c.get("wind_speed_10m", 3.0)),
            "wind_dir":   float(c.get("wind_direction_10m", 180.0)),
            "pressure":   float(c.get("surface_pressure", 1013.0)),
        }
    except Exception:
        return {"temp": 25.0, "humidity": 70.0, "wind_speed": 3.0, "wind_dir": 180.0, "pressure": 1013.0}


def _resolve_col(df: pd.DataFrame, *candidates: str) -> str | None:
    """First column name in `candidates` that exists in `df` (case-insensitive)."""
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None


def generate_real_snapshot(epa_key: str | None = None) -> tuple[pd.DataFrame | None, str]:
    """整合 EPA + Open-Meteo 產出「真實」的 20 城市當下快照。

    這是 `generate_current_snapshot()` 的真實資料版本。當 EPA API 成功
    回應時,app.py 會優先用這個函式;失敗才 fallback 到合成版本。

    處理流程:
      1. 呼叫 `fetch_epa_realtime()` 取得 EPA 77 個測站的當下值
      2. 用 `_resolve_col` 容錯處理欄位命名(舊 EPA / 新 MOENV v2 兩種命名共存)
      3. 為「每個區域的代表城市」呼叫一次 Open-Meteo 氣象 API(共 5 次,
         不是 20 次,因為氣象變化區域內差異小,可共用)
      4. 對每個 city,從 EPA 資料 group_by 縣市並取「測站平均」作該城市的代表值
      5. 計算 `updated_min_ago`(EPA publishtime 距現在的分鐘數),取代合成版的隨機值

    Returns
    -------
    tuple[pd.DataFrame | None, str]
        (df, status_msg)
        df = None 時表示失敗,status_msg 解釋失敗原因
        df 成功時,status_msg 是「成功取得 X 城市即時資料」摘要
    """
    raw = fetch_epa_realtime(epa_key)
    if raw is None or raw.empty:
        return None, "EPA API 無回應或無資料，請確認網路或 API 金鑰"

    # 預先解析所有欄位名稱(舊 EPA 用「PM2.5」、新 MOENV 用「pm25」,要兩個都接得起來)
    # 用 _resolve_col 一次找出實際存在的欄位名,後面就不用每次 try 多種寫法
    cols = {
        "county":      _resolve_col(raw, "County", "county", "縣市"),
        "aqi":         _resolve_col(raw, "AQI", "aqi"),
        "pm25":        _resolve_col(raw, "PM2.5", "pm2.5", "pm25", "PM25"),
        "pm10":        _resolve_col(raw, "PM10", "pm10"),
        "o3":          _resolve_col(raw, "O3", "o3"),
        "no2":         _resolve_col(raw, "NO2", "no2"),
        "so2":         _resolve_col(raw, "SO2", "so2"),
        "co":          _resolve_col(raw, "CO", "co"),
        "wind_dir":    _resolve_col(raw, "WindDirec", "winddirec", "wind_direc", "wind_direction"),
        "publishtime": _resolve_col(raw, "publishtime", "PublishTime", "datacreationdate"),
    }
    if cols["county"] is None or cols["aqi"] is None:
        return None, f"資料欄位無法識別（缺 County 或 AQI）。實際欄位：{list(raw.columns)[:12]}"

    # Pre-fetch weather for one city per region (5 calls total)
    weather_by_region: dict[str, dict[str, float]] = {}
    for region, rep_id in _REGION_REPR.items():
        rep = CITY_BY_ID[rep_id]
        weather_by_region[region] = fetch_weather_current(rep["lat"], rep["lon"])

    rows: list[dict[str, Any]] = []
    for city in CITIES:
        county_keys = [k for k, v in COUNTY_TO_CITY_ID.items() if v == city["id"]]
        sdf = raw[raw[cols["county"]].isin(county_keys)]
        if sdf.empty:
            continue

        def col_mean(key: str) -> float:
            real = cols.get(key)
            if real is None:
                return 0.0
            vals = pd.to_numeric(sdf[real], errors="coerce").dropna()
            return float(vals.mean()) if len(vals) > 0 else 0.0

        aqi = col_mean("aqi")
        if aqi <= 0:
            continue

        pm25 = max(0.0, col_mean("pm25"))
        pm10 = max(0.0, col_mean("pm10"))
        o3   = max(0.0, col_mean("o3"))
        no2  = max(0.0, col_mean("no2"))
        so2  = max(0.0, col_mean("so2"))
        co   = max(0.0, col_mean("co"))
        wind_dir = col_mean("wind_dir")

        # Compute minutes-since-publish from EPA's publishtime/datacreationdate
        # so the "資料新鮮度" cards reflect actual EPA station update lag,
        # rather than displaying "0 分鐘前" for every city.
        publish_col = cols.get("publishtime")
        if publish_col is not None and publish_col in sdf.columns:
            pub_dt = pd.to_datetime(sdf[publish_col], errors="coerce").max()
            if pd.notna(pub_dt):
                # EPA timestamps are in UTC+8 without timezone tag — strip tz from now
                delta_min = max(0, int((datetime.now() - pub_dt.to_pydatetime()).total_seconds() // 60))
                updated_min = min(delta_min, 999)
            else:
                updated_min = 0
        else:
            updated_min = 0

        w = weather_by_region.get(city["region"], {"temp": 25.0, "humidity": 70.0, "wind_speed": 3.0, "pressure": 1013.0})

        risk = (0.40 * (pm25 / 35) + 0.20 * (aqi / 150) + 0.15 * (o3 / 100)
              + 0.10 * (no2 / 80)  + 0.08 * (so2 / 30) + 0.07 * (co / 5))
        risk = float(min(100, max(0, risk * 100)))

        rows.append({
            "city_id":    city["id"],
            "city":       city["name"],
            "en":         city["en"],
            "region":     city["region"],
            "lat":        city["lat"],
            "lon":        city["lon"],
            "aqi":        round(aqi, 1),
            "PM2.5":      round(pm25, 1),
            "PM10":       round(pm10, 1),
            "O3":         round(o3, 1),
            "NO2":        round(no2, 1),
            "SO2":        round(so2, 2),
            "CO":         round(co, 2),
            "wind_dir":   round(wind_dir, 0),
            "wind_speed": round(w["wind_speed"], 1),
            "humidity":   round(w["humidity"], 0),
            "temp":       round(w["temp"], 1),
            "pressure":   round(w["pressure"], 0),
            "risk":       round(risk, 1),
            "level":      aqi_to_level(aqi)["name"],
            "level_num":  aqi_to_level(aqi)["level"],
            "color":      aqi_to_level(aqi)["color"],
            "updated_min_ago": updated_min,
        })

    if not rows:
        return None, "EPA 資料中找不到對應城市，可能 API 格式已變更"
    df = pd.DataFrame(rows)
    return df, f"成功取得 {len(rows)} 城市即時資料（EPA + Open-Meteo）"


def generate_real_timeseries(
    snapshot: pd.DataFrame,
    hours_back: int = 24,
    epa_key: str | None = None,
) -> pd.DataFrame:
    """產出 24 小時的歷史 DataFrame,使用三層 fallback 策略確保總有資料可顯示。

    優先順序(依次降級):
      1. **EPA aqx_p_488** — 環境部官方測站每小時實測歷史(真實資料,最權威)
      2. **Open-Meteo CAMS** — 歐洲哥白尼大氣化學模式網格(真實模型,涵蓋全境)
      3. **日夜模式重建** — 用 snapshot 當下 AQI 為錨點,用 `_diurnal_factor`
         反推 24 小時前的變化曲線(合成,僅當前兩者都失敗時的最後手段)

    為什麼 fallback 也要錨定到當下 AQI?讓圖表的「右邊(現在)」一定對得起來,
    使用者看到的「現在 AQI」與時序圖最右端一致;只有歷史那段是猜的。

    Returns
    -------
    pd.DataFrame
        欄位:timestamp, city_id, city, region, aqi, PM2.5, PM10, O3, NO2, SO2, CO, risk
        無論走哪一條路徑,都會回傳同樣 schema 的 DataFrame
    """
    # 1. EPA 歷史測站(最權威)
    if epa_key:
        epa_hist = fetch_epa_historical(epa_key, hours_back=hours_back)
        if epa_hist is not None and not epa_hist.empty:
            return epa_hist

    # 2. CAMS 大氣化學模式(免金鑰,涵蓋全境)
    # 注意:CAMS 一次回 past_days + forecast_days 的資料,因此要 filter 出 <= now 的歷史段
    cams = fetch_open_meteo_aq_batch(CITIES, past_days=1, forecast_days=0)
    if cams is not None and not cams.empty:
        return cams[cams["timestamp"] <= pd.Timestamp(datetime.now())].copy()

    # 3. Fallback:用日夜模式重建歷史曲線(以當下 AQI 為錨點)
    now = datetime.now()
    rows: list[dict[str, Any]] = []
    for _, city_row in snapshot.iterrows():
        cid = city_row["city_id"]
        real_aqi = float(city_row["aqi"])
        current_diurnal = max(0.01, _diurnal_factor(now.hour))
        for h in range(hours_back, -1, -1):
            ts = (now - timedelta(hours=h)).replace(minute=0, second=0, microsecond=0)
            ratio = _diurnal_factor(ts.hour) / current_diurnal
            base = real_aqi * ratio
            rng = np.random.default_rng(_seed_for(cid + "_rt", ts))
            aqi = float(max(10, base + rng.normal(0, real_aqi * 0.06)))
            pm25 = max(2.0, aqi * 0.45)
            rows.append({
                "timestamp": ts,
                "city_id":   cid,
                "city":      city_row["city"],
                "region":    city_row["region"],
                "aqi":       round(aqi, 1),
                "PM2.5":     round(pm25, 1),
                "PM10":      round(pm25 * 1.6, 1),
                "O3":        round(max(0, 40 + (aqi - 60) * 0.3), 1),
                "NO2":       round(max(0, 18 + aqi * 0.18), 1),
                "SO2":       round(max(0, 4 + aqi * 0.03), 2),
                "CO":        round(max(0, 0.4 + aqi * 0.006), 2),
                "risk":      float(city_row["risk"]),
            })
    return pd.DataFrame(rows)


# =============================================================================
# 真實資料抓取器 (Real-data Fetchers) — 完全取代上面合成生成器的「正式」資料路徑
# =============================================================================
# 本區段是整個系統的「資料心臟」 — 所有真實外部 API 都集中在這。
# 失敗時呼叫者(主要是 app.py)會自動 fallback 到上方的合成版本。
#
# 資料來源層級:
#   1. EPA (環境部 Open Data)        ← 官方測站,77 站,每小時更新,需 API key
#   2. Open-Meteo CAMS               ← 衛星同化模型,網格產出,免金鑰
#   3. 民生公共物聯網 (Civil IoT)    ← 政府 micro sensor 網路,~10,000 個感測器
#   4. LASS-net Airbox               ← 社群 / 學術感測器,~500 個,離島覆蓋好
# =============================================================================

# LASS-net 社群 Airbox 入口 — 公開 JSON,免金鑰
LASS_AIRBOX_URL    = "https://pm25.lass-net.org/data/last-all-airbox.json"
# EPA 24h 歷史值 endpoint(aqx_p_488 = "全國空氣品質監測小時值"資料集)
EPA_HIST_URL       = "https://data.moenv.gov.tw/api/v2/aqx_p_488"
# Open-Meteo 空氣品質 API(CAMS 來源),免金鑰
OPEN_METEO_AQ_URL  = "https://air-quality-api.open-meteo.com/v1/air-quality"

# 民生公共物聯網 (Civil IoT Taiwan) — 智慧城鄉空品微型感測器計畫的官方資料服務。
# 用 OGC SensorThings API 標準,中央研究院 colife.org.tw 鏡像入口。
# 涵蓋約 10,000+ 個由政府佈建的 PM2.5 微型感測器,覆蓋工業 / 都市 / 農業區密集。
CIVIL_IOT_STA_URL  = "https://sta.colife.org.tw/STA_AirQuality_EPAIoT/v1.0/Datastreams"

# 民間感測器匹配的「半徑」(km)。離島(澎湖/金門/馬祖)與東部(花蓮/台東)
# 民間感測器較稀疏,需要拉大半徑才能找到至少 1 個感測器代表該城市。
_OFFSHORE_REGIONS = {"離島", "東部"}


def _haversine_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Vectorised haversine distance from one point to many (km)."""
    r_lat1 = math.radians(lat1); r_lon1 = math.radians(lon1)
    r_lat2 = np.radians(lat2);   r_lon2 = np.radians(lon2)
    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1
    a = np.sin(dlat / 2) ** 2 + math.cos(r_lat1) * np.cos(r_lat2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def _fetch_civil_iot_one_city(city_id: str, top: int = 200) -> list[dict]:
    """Pull civilian PM2.5 sensors for ONE city from 民生公共物聯網 SensorThings.

    Critical detail: CivilIoT stores city names in the legacy traditional
    form (e.g. 臺北市, 臺中市, 臺南市, 臺東縣), while our internal `CITIES`
    list uses the everyday form (台北市, 台中市, ...). We build the OData
    $filter with **every alias** that maps to this `city_id` in
    `COUNTY_TO_CITY_ID`, so the 臺/台 variant doesn't drop entire cities.

    The API's default @iot.id ordering biases globally toward early
    sensor deployments (Taoyuan / Yunlin pilot zones), so a global query
    truncated at any reasonable N misses most of Taiwan. Per-city queries
    with the alias-OR filter guarantee representative coverage everywhere.
    """
    aliases = [k for k, v in COUNTY_TO_CITY_ID.items() if v == city_id]
    if not aliases:
        return []
    city_filter = " or ".join(f"Thing/properties/city eq '{a}'" for a in aliases)
    filter_q = f"name eq 'PM2.5' and ({city_filter})"
    try:
        r = requests.get(
            CIVIL_IOT_STA_URL,
            params={
                "$filter": filter_q,
                "$expand": "Observations($orderby=phenomenonTime desc;$top=1),Thing($expand=Locations)",
                "$top":    top,
            },
            timeout=20,
        )
        r.raise_for_status()
        body = r.json()
    except Exception:
        return []
    rows: list[dict] = []
    for ds in body.get("value") or []:
        obs = ds.get("Observations") or []
        if not obs:
            continue
        pm25 = obs[0].get("result")
        thing = ds.get("Thing") or {}
        locs  = thing.get("Locations") or []
        coords = (locs[0].get("location") or {}).get("coordinates") if locs else None
        if not coords or len(coords) < 2:
            continue
        # SensorThings uses GeoJSON ordering: [lon, lat]
        lon, lat = coords[0], coords[1]
        site = (thing.get("properties") or {}).get("stationID") or thing.get("name") or ""
        rows.append({"site": site, "pm25": pm25, "lat": lat, "lon": lon})
    return rows


def _fetch_civil_iot_raw() -> tuple[list[dict] | None, str]:
    """Pull civilian PM2.5 readings from 民生公共物聯網 SensorThings API,
    one HTTP request per city, in parallel.

    Returns (list of dicts with site/pm25/lat/lon, status_msg). The
    SensorThings endpoint exposes ~10,000+ 智慧城鄉空品微型感測器
    (Smart City micro-sensors); we cap per-city at 120 sensors which is
    plenty for a median-aggregation per district.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    rows: list[dict] = []
    failed_cities: list[str] = []
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(_fetch_civil_iot_one_city, city["id"]): city["name"]
                for city in CITIES
            }
            for fut in as_completed(futures, timeout=40):
                city_name = futures[fut]
                try:
                    rows.extend(fut.result())
                except Exception:
                    failed_cities.append(city_name)
    except Exception as e:
        if not rows:
            return None, f"CivilIoT API 失敗：{type(e).__name__}: {str(e)[:80]}"

    if not rows:
        return None, "CivilIoT 全部 20 城市查詢無回應"

    suffix = f"（{len(failed_cities)} 個城市查詢失敗）" if failed_cities else ""
    return rows, f"CivilIoT 取得 {len(rows)} 筆原始紀錄{suffix}"


def _fetch_lass_raw() -> tuple[list[dict] | None, str]:
    """Fallback civilian PM2.5 source - LASS-net community Airbox portal.
    Returns same shape as `_fetch_civil_iot_raw`."""
    try:
        r = requests.get(LASS_AIRBOX_URL, timeout=15)
        r.raise_for_status()
        feeds = (r.json() or {}).get("feeds", []) or []
    except Exception as e:
        return None, f"LASS API 失敗：{type(e).__name__}: {str(e)[:80]}"
    rows: list[dict] = []
    for entry in feeds:
        if not isinstance(entry, dict):
            continue
        ab = entry.get("AirBox") if isinstance(entry.get("AirBox"), dict) else entry
        rows.append({
            "site": ab.get("SiteName") or ab.get("device_id") or ab.get("name") or "",
            "pm25": ab.get("s_d0"),
            "lat":  ab.get("gps_lat") or ab.get("lat"),
            "lon":  ab.get("gps_lon") or ab.get("lon"),
        })
    return rows, f"LASS 取得 {len(rows)} 筆原始紀錄"


def fetch_citizen_sensors() -> tuple[pd.DataFrame | None, "CleaningReport | None", str]:
    """Fetch civilian PM2.5 sensors and aggregate per city.

    Pulls from TWO complementary sources in parallel and merges:
      1. 民生公共物聯網 SensorThings API (sta.colife.org.tw · STA_AirQuality_EPAIoT)
         — official government-curated 智慧城鄉空品微型感測器 network
         (~10,000 sensors; strong on industrial / urban / agricultural belts)
      2. LASS-net Airbox community portal (pm25.lass-net.org)
         — community / academic Airbox sensors (~500 currently online;
         strong on outlying islands 澎湖/金門/馬祖 where the official
         programme has no deployment)

    Both are honest "民生公共物聯網成員" data sources: LASS sensors feed
    into the 民生公共物聯網 platform via SensorThings as well, but the
    community portal exposes a simpler all-in-one snapshot endpoint.

    The returned status_message names both sources and their record
    counts. CleaningReport fields are real (computed from live data, not
    random).

    Cleaning steps:
      1. Drop rows where PM2.5 is missing or out of plausible range (0-500 μg/m³).
      2. Drop rows whose lat/lon fall outside the Taiwan bounding box.
      3. De-duplicate by site/device id (keep first).
      4. For each of our 20 cities, take the median PM2.5 of sensors within
         a radius (5 km inland, 20 km offshore / eastern).
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        ft_civil = pool.submit(_fetch_civil_iot_raw)
        ft_lass  = pool.submit(_fetch_lass_raw)
        civil_rows, civil_status = ft_civil.result()
        lass_rows,  lass_status  = ft_lass.result()

    civil_rows = civil_rows or []
    lass_rows  = lass_rows or []
    rows = civil_rows + lass_rows
    if not rows:
        return None, None, f"{civil_status} ｜ {lass_status}"

    parts = []
    if civil_rows:
        parts.append(f"民生公共物聯網 {len(civil_rows)} 筆")
    if lass_rows:
        parts.append(f"LASS-net {len(lass_rows)} 筆")
    source_label = " + ".join(parts) if parts else "未知來源"

    df = pd.DataFrame(rows)
    raw_count = len(df)

    # 1. PM2.5 in plausible range
    df["pm25"] = pd.to_numeric(df["pm25"], errors="coerce")
    bad_pm = df["pm25"].isna() | (df["pm25"] <= 0) | (df["pm25"] >= 500)
    df = df[~bad_pm].copy()
    dropped_pm = int(bad_pm.sum())

    # 2. lat/lon in Taiwan bounding box (119-123 E, 21-26.5 N — covers offshore islands)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    in_taiwan = df["lat"].between(21.0, 26.5) & df["lon"].between(119.0, 123.0)
    pre_geo = len(df)
    df = df[in_taiwan].copy()
    dropped_geo = pre_geo - len(df)

    # 3. de-dup by site/device id
    pre_dup = len(df)
    df = df.drop_duplicates(subset=["site"], keep="first")
    dropped_dup = pre_dup - len(df)

    if df.empty:
        return None, CleaningReport(
            raw_records=raw_count, kept_records=0, dropped_records=raw_count,
            drop_reasons={"PM2.5 異常": dropped_pm, "地理範圍外": dropped_geo, "重複": dropped_dup},
        ), f"{source_label}: 清洗後無有效資料"

    # 4. aggregate per city
    sensor_lat = df["lat"].to_numpy()
    sensor_lon = df["lon"].to_numpy()
    sensor_pm  = df["pm25"].to_numpy()

    per_city = []
    for city in CITIES:
        radius_km = 20.0 if city["region"] in _OFFSHORE_REGIONS else 5.0
        d = _haversine_km(city["lat"], city["lon"], sensor_lat, sensor_lon)
        mask = d <= radius_km
        if mask.any():
            per_city.append({
                "city_id":       city["id"],
                "city":          city["name"],
                "citizen_PM2.5": round(float(np.median(sensor_pm[mask])), 1),
                "sensor_count":  int(mask.sum()),
            })
        else:
            per_city.append({
                "city_id":       city["id"],
                "city":          city["name"],
                "citizen_PM2.5": float("nan"),
                "sensor_count":  0,
            })

    cleaning = CleaningReport(
        raw_records=raw_count,
        kept_records=len(df),
        dropped_records=raw_count - len(df),
        drop_reasons={
            "PM2.5 異常": dropped_pm,
            "地理範圍外": dropped_geo,
            "重複":      dropped_dup,
        },
    )
    return pd.DataFrame(per_city), cleaning, f"{source_label}: 取得 {len(df)} 個有效感測器"



def fetch_epa_historical(api_key: str | None, hours_back: int = 24) -> pd.DataFrame | None:
    """Pull EPA aqx_p_488 (hourly history). Returns a long-format DataFrame
    with columns: timestamp, city_id, aqi, PM2.5, PM10, O3, NO2, SO2, CO.
    None on failure.

    We grab 2 pages (limit=1000, offset=0/1000) sorted by datacreationdate desc
    to cover ~24 h × 77 stations ≈ 1800 records.
    """
    if not api_key or not api_key.strip():
        return None
    records: list[dict] = []
    try:
        for offset in (0, 1000):
            params = {
                "api_key": api_key.strip(),
                "limit":   1000,
                "offset":  offset,
                "sort":    "datacreationdate desc",
                "format":  "JSON",
            }
            r = requests.get(EPA_HIST_URL, params=params, timeout=20)
            r.raise_for_status()
            body = r.json()
            page = (body.get("records") if isinstance(body, dict) else None) or []
            if not page:
                break
            records.extend(page)
    except Exception:
        return None
    if not records:
        return None

    raw = pd.DataFrame(records)
    cols = {
        "county": _resolve_col(raw, "county", "County", "縣市"),
        "ts":     _resolve_col(raw, "datacreationdate", "DataCreationDate", "publishtime", "PublishTime"),
        "aqi":    _resolve_col(raw, "aqi", "AQI"),
        "pm25":   _resolve_col(raw, "pm2.5", "PM2.5", "pm25"),
        "pm10":   _resolve_col(raw, "pm10", "PM10"),
        "o3":     _resolve_col(raw, "o3", "O3"),
        "no2":    _resolve_col(raw, "no2", "NO2"),
        "so2":    _resolve_col(raw, "so2", "SO2"),
        "co":     _resolve_col(raw, "co", "CO"),
    }
    if cols["county"] is None or cols["ts"] is None or cols["aqi"] is None:
        return None

    raw["_ts"] = pd.to_datetime(raw[cols["ts"]], errors="coerce")
    raw = raw.dropna(subset=["_ts"])
    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=hours_back + 1)
    raw = raw[raw["_ts"] >= cutoff]

    rows: list[dict] = []
    for county, sdf in raw.groupby(cols["county"]):
        city_id = COUNTY_TO_CITY_ID.get(str(county))
        if not city_id:
            continue
        for ts, hdf in sdf.groupby(sdf["_ts"].dt.floor("h")):
            def m(key):
                c = cols.get(key)
                if c is None: return None
                v = pd.to_numeric(hdf[c], errors="coerce").dropna()
                return float(v.mean()) if len(v) else None
            aqi = m("aqi")
            if aqi is None or aqi <= 0:
                continue
            rows.append({
                "timestamp": ts.to_pydatetime(),
                "city_id":   city_id,
                "city":      CITY_BY_ID[city_id]["name"],
                "region":    CITY_BY_ID[city_id]["region"],
                "aqi":       round(aqi, 1),
                "PM2.5":     round(m("pm25") or 0, 1),
                "PM10":      round(m("pm10") or 0, 1),
                "O3":        round(m("o3") or 0, 1),
                "NO2":       round(m("no2") or 0, 1),
                "SO2":       round(m("so2") or 0, 2),
                "CO":        round(m("co") or 0, 2),
                "risk":      0.0,
            })
    return pd.DataFrame(rows) if rows else None


def fetch_open_meteo_aq_batch(
    cities: list[dict],
    past_days: int = 1,
    forecast_days: int = 1,
) -> pd.DataFrame | None:
    """Fetch hourly air quality from Open-Meteo (Copernicus CAMS model)
    for many cities in a single request. Returns a long-format DataFrame
    with columns: timestamp, city_id, aqi, PM2.5, PM10, O3, NO2, SO2, CO,
    is_forecast (bool), source='cams'. Free, no key required."""
    if not cities:
        return None
    lats = ",".join(f"{c['lat']:.4f}" for c in cities)
    lons = ",".join(f"{c['lon']:.4f}" for c in cities)
    try:
        r = requests.get(
            OPEN_METEO_AQ_URL,
            params={
                "latitude":      lats,
                "longitude":     lons,
                "hourly":        "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi",
                "past_days":     past_days,
                "forecast_days": forecast_days,
                "timezone":      "Asia/Taipei",
            },
            timeout=20,
        )
        r.raise_for_status()
        body = r.json()
    except Exception:
        return None

    # Single-location response is a dict; batch is a list. Normalize.
    locations = body if isinstance(body, list) else [body]
    if len(locations) != len(cities):
        # Mismatch — fall back to whatever we got, paired by index
        cities = cities[:len(locations)]
    now_naive = datetime.now()
    rows: list[dict] = []
    for city, loc in zip(cities, locations):
        h = (loc.get("hourly") or {})
        times    = h.get("time") or []
        pm25_arr = h.get("pm2_5") or []
        pm10_arr = h.get("pm10") or []
        o3_arr   = h.get("ozone") or []
        no2_arr  = h.get("nitrogen_dioxide") or []
        so2_arr  = h.get("sulphur_dioxide") or []
        co_arr   = h.get("carbon_monoxide") or []
        aqi_arr  = h.get("us_aqi") or []
        for i, t in enumerate(times):
            try:
                ts = datetime.fromisoformat(t)
            except (ValueError, TypeError):
                continue
            def at(arr, i):
                try:
                    v = arr[i]
                    return float(v) if v is not None else None
                except (IndexError, TypeError, ValueError):
                    return None
            aqi = at(aqi_arr, i)
            pm25 = at(pm25_arr, i)
            if aqi is None and pm25 is None:
                continue
            # Quick risk score using the same weighted blend that EPA-real
            # snapshots use (PM2.5 dominates). Keeps the column shape in
            # parity with EPA history so downstream code (e.g. the time
            # scrubber merge in app.py) doesn't break when CAMS is the
            # ts_df source.
            pm25_v = pm25 or 0.0
            pm10_v = at(pm10_arr, i) or 0.0
            o3_v   = at(o3_arr, i)   or 0.0
            no2_v  = at(no2_arr, i)  or 0.0
            so2_v  = at(so2_arr, i)  or 0.0
            co_v   = (at(co_arr, i) or 0.0) / 1000
            aqi_v  = aqi or 0.0
            _risk = (
                0.40 * (pm25_v / 35) + 0.20 * (aqi_v / 150)
                + 0.15 * (o3_v / 100) + 0.10 * (no2_v / 80)
                + 0.08 * (so2_v / 30) + 0.07 * (co_v / 5)
            )
            _risk = min(100.0, max(0.0, _risk * 100))
            rows.append({
                "timestamp":   ts,
                "city_id":     city["id"],
                "city":        city["name"],
                "region":      city["region"],
                "aqi":         round(aqi, 1) if aqi is not None else None,
                "PM2.5":       round(pm25, 1) if pm25 is not None else None,
                "PM10":        round(pm10_v, 1),
                "O3":          round(o3_v, 1),
                "NO2":         round(no2_v, 1),
                "SO2":         round(so2_v, 2),
                "CO":          round(co_v, 2),
                "risk":        round(_risk, 1),
                "is_forecast": ts > now_naive,
                "source":      "cams",
            })
    return pd.DataFrame(rows) if rows else None


def send_discord_webhook(
    url: str,
    snapshot: pd.DataFrame,
    critic_score: float | None,
    data_mode: str = "real",
) -> tuple[bool, str]:
    """Pipeline 跑完後,把摘要 POST 到 Discord channel webhook。

    Discord embed 是一種美觀的卡片訊息格式,比純文字 message 更專業。
    包含的欄位:
      - 全國平均 AQI(突出顯示)
      - 最高 / 最低 AQI 的城市
      - Critic 評分(舊版功能,3-agent refactor 後通常為 None,顯示 「—」)
      - 資料來源標籤(LIVE / MOCK)

    Webhook URL 是使用者自己在 Discord 頻道設定中產生的,例:
      `https://discord.com/api/webhooks/{channel_id}/{token}`

    Returns
    -------
    tuple[bool, str]
        (success, status_msg) — UI 顯示 status_msg 讓使用者知道有沒有成功
    """
    url = (url or "").strip()
    if not url:
        return False, "未填 Discord webhook URL"
    if snapshot is None or snapshot.empty:
        return False, "Snapshot 為空"

    try:
        avg   = float(snapshot["aqi"].mean())
        worst = snapshot.sort_values("aqi", ascending=False).iloc[0]
        best  = snapshot.sort_values("aqi").iloc[0]
    except Exception as e:
        return False, f"Snapshot parse: {type(e).__name__}"

    mode_tag = "LIVE" if data_mode == "real" else "MOCK"
    score_str = f"{critic_score:.1f}/100" if isinstance(critic_score, (int, float)) else "—"
    embed = {
        "title": "🦞 LobsterAQI Pipeline 摘要",
        "description": f"資料來源：{mode_tag} · 覆蓋 {len(snapshot)} 城市",
        "color": 0x00d9ff,
        "fields": [
            {"name": "全國平均 AQI", "value": f"**{avg:.1f}**",
             "inline": True},
            {"name": "最高城市", "value": f"{worst['city']} ({worst['aqi']:.0f})",
             "inline": True},
            {"name": "最低城市", "value": f"{best['city']} ({best['aqi']:.0f})",
             "inline": True},
            {"name": "Critic 評分", "value": score_str, "inline": True},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "LobsterAQI · Taiwan Multi-Agent Air Quality Platform"},
    }
    try:
        r = requests.post(url, json={"embeds": [embed]}, timeout=8)
        ok = r.status_code in (200, 204)
        return ok, f"HTTP {r.status_code}" + ("" if ok else f" · {r.text[:120]}")
    except requests.exceptions.Timeout:
        return False, "Webhook 逾時"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:80]}"


# =============================================================================
# 直接呼叫多家 LLM 的 helper (Multi-provider LLM Helpers)
# =============================================================================
# 設計取捨:OpenClaw gateway 統一管理 LLM 雖然優雅,但每次呼叫多 30-60 秒
# 的插件冷啟,對「使用者按鈕後幾秒內要看到結果」的 UI 太慢。因此本專案
# 採「混合架構」:
#   - **Pipeline 內的 LLM 呼叫**(分析師 / 預警員 / 右下角助理 / 城市比較)
#     → 直接呼叫各家 provider 的 HTTP API,毫秒級延遲
#   - **OpenClaw 仍保留用於**:cron 排程推送、Discord/LINE 綁定、
#     MEMORY.md 跨會話記憶 — 這些不需即時回應
# =============================================================================

# 所有支援的 LLM 提供商配置 — 加新家只要在這加一筆即可。
# 每筆配置包含:
#   name           顯示在 UI selectbox 的中文名
#   placeholder    輸入框的 placeholder(讓使用者知道 key 的格式)
#   default_model  該家的預設模型(留空表示使用者必填)
#   base_url       自訂 endpoint(留空使用 anthropic / openai 等的官方預設)
# 全部都用 OpenAI-format API contract — 因為 Gemini / MiniMax / OpenAI 都支援。
# Anthropic 的格式略有不同,在 call_llm_api 內會分支處理。
LLM_PROVIDERS: dict[str, dict[str, str]] = {
    "anthropic": {
        "name":          "Anthropic (Claude)",
        "placeholder":   "sk-ant-...",
        "default_model": "claude-sonnet-4-6",
        "base_url":      "",
    },
    # Google Gemini exposes an OpenAI-compatible endpoint at
    # /v1beta/openai/chat/completions — same request shape as everything
    # below, so it slots right into the generic OpenAI-format branch.
    # Get an API key at https://aistudio.google.com/apikey (free tier).
    "gemini": {
        "name":          "Google Gemini",
        "placeholder":   "AIza...",
        "default_model": "gemini-2.5-flash",
        "base_url":      "https://generativelanguage.googleapis.com/v1beta/openai",
    },
    # MiniMax (international, where M1 / M2 / abab models live). Sign up at
    # platform.minimaxi.chat; the China platform (api.minimax.chat) is a
    # separate account system and we don't ship that switch here anymore.
    "minimax": {
        "name":          "MiniMax (國際版)",
        "placeholder":   "eyJ...",
        "default_model": "MiniMax-M2.7",
        "base_url":      "https://api.minimaxi.chat/v1",
    },
    "openai": {
        "name":          "OpenAI",
        "placeholder":   "sk-...",
        "default_model": "gpt-4o-mini",
        "base_url":      "https://api.openai.com/v1",
    },
    "custom": {
        "name":          "自訂 API（OpenAI 格式）",
        "placeholder":   "...",
        "default_model": "",
        "base_url":      "",
    },
}


# 診斷用全域變數:每次 call_llm_api 失敗都更新這個,
# 呼叫者(app.py)可以讀取此值告訴使用者「為什麼失敗」(timeout / HTTP 4xx / parse 失敗 等)
LAST_LLM_ERROR: str = ""


# 有些 LLM 會把內部推理思考過程暴露在 <thinking>...</thinking> 或
# <think>...</think> 標籤中(Claude extended thinking、DeepSeek-R1、Qwen-QwQ、
# 部份 MiniMax 模型)。這對使用者沒幫助,還會顯得雜亂,因此在顯示前濾掉。
import re as _re

# 完整配對:<thinking>...</thinking>(也接受 think / reasoning / analysis / reflection)
_REASONING_TAG_RE = _re.compile(
    r"<\s*(thinking|think|reasoning|analysis|reflection)\s*>"
    r"[\s\S]*?"     # 非貪婪匹配,確保不會誤吃多個 block
    r"<\s*/\s*\1\s*>",
    _re.IGNORECASE,
)
# 模型被截斷時可能只開了 <thinking> 沒關閉;這種情況把從開標籤到結尾全砍掉
_DANGLING_OPEN_RE = _re.compile(
    r"<\s*(thinking|think|reasoning|analysis|reflection)\s*>[\s\S]*$",
    _re.IGNORECASE,
)


def clean_llm_output(text: str | None) -> str:
    """清理 LLM 原始輸出,移除思考標籤、空白、不必要的 markdown 圍欄。

    處理步驟:
      1. 移除所有 `<thinking>...</thinking>` 等推理標籤區塊
      2. 處理「半開」的標籤(模型輸出被 token limit 截斷時)
      3. trim 前後空白
      4. 如果整段被 ```...``` 包圍,把圍欄拿掉(只保留內容)

    為什麼 LLM 會吐出推理區塊?某些 reasoning model 預設會回傳:
        <thinking>
        Let me analyze the AQI...
        </thinking>
        台北市的 AQI 為...
    我們不希望使用者看到「Let me analyze」之類的英文 internal monologue,
    因此在顯示前一律清掉。
    """
    if not text:
        return ""
    out = _REASONING_TAG_RE.sub("", text)
    # If the model started a reasoning block but never closed it (truncated),
    # cut everything from the opening tag to the end.
    out = _DANGLING_OPEN_RE.sub("", out)
    out = out.strip()
    # Drop wrapping ```markdown ... ``` fences if they wrap the whole output
    if out.startswith("```") and out.endswith("```"):
        lines = out.splitlines()
        if len(lines) >= 2:
            out = "\n".join(lines[1:-1]).strip()
    return out


def call_llm_api(
    provider: str,
    api_key: str,
    prompt: str,
    model: str,
    base_url: str = "",
    system: str = "你是台灣空氣品質監測專家，根據 AQI 數據提供準確、有依據的健康建議。回覆請使用繁體中文。",
    # 預設 4096 token 上限(夠長,給長報告用)。呼叫者可傳更高;
    # 不刻意強制短回應,因為使用者多次反映希望 LLM 講清楚不要被截斷。
    max_tokens: int = 4096,
    timeout: int = 30,
) -> str | None:
    """直接呼叫指定 LLM 提供商的 HTTP API,回傳純文字(已清理 reasoning 標籤)。

    支援的 provider:
      - **anthropic**:走 Anthropic Messages API (不同於 OpenAI 格式)
      - **gemini / openai / minimax / custom**:走 OpenAI-format /chat/completions

    失敗處理:
      - 任何例外都回 None
      - `LAST_LLM_ERROR` 全域變數會被設成短診斷訊息(HTTP status / timeout 等)
      - 對 429/500/502/503/504 等 transient 錯誤會自動重試一次
        (Gemini 在尖峰時段常出現 503 UNAVAILABLE)

    Parameters
    ----------
    provider : str
        要使用哪一家('anthropic' / 'gemini' / 'minimax' / 'openai' / 'custom')
    api_key : str
        該家的金鑰;空白會直接回 None
    prompt : str
        使用者問題或 Pipeline 中組好的 context+question
    model : str
        模型名;若空字串會用該 provider 的 default_model
    base_url : str
        custom provider 時用,其他家會 fallback 到 LLM_PROVIDERS 內定義的 endpoint
    system : str
        system prompt,預設限制 LLM 用繁體中文 + 強調有依據的建議
    max_tokens : int
        最大輸出 token 數
    timeout : int
        單次 HTTP 請求 timeout(秒)

    Returns
    -------
    str | None
        清理後的純文字回應;失敗時為 None(呼叫者必須處理)
    """
    global LAST_LLM_ERROR
    LAST_LLM_ERROR = ""

    if not api_key or not api_key.strip():
        LAST_LLM_ERROR = "API key 空白"
        return None
    key = api_key.strip()
    mdl = (model or "").strip() or LLM_PROVIDERS.get(provider, {}).get("default_model", "")

    # HTTP statuses commonly transient — worth one quick retry. Gemini in
    # particular returns 503 UNAVAILABLE during peak demand.
    _RETRYABLE = {429, 500, 502, 503, 504}

    def _short_err_message(text: str) -> str:
        """Pull a human-readable message out of a JSON error body."""
        try:
            body = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text[:180]
        if isinstance(body, list) and body:
            body = body[0]
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                msg = err.get("message") or err.get("status") or ""
                if msg:
                    return str(msg)[:180]
        return text[:180]

    try:
        if provider == "anthropic":
            r = None
            for attempt in (1, 2):
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": mdl or "claude-sonnet-4-6",
                        "max_tokens": max_tokens,
                        "system": system,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=timeout,
                )
                if r.status_code in _RETRYABLE and attempt == 1:
                    time.sleep(1.5)
                    continue
                break
            if r.status_code >= 400:
                LAST_LLM_ERROR = f"Anthropic HTTP {r.status_code} · {_short_err_message(r.text)}"
                return None
            data = r.json()
            try:
                return clean_llm_output(data["content"][0]["text"])
            except (KeyError, IndexError, TypeError) as e:
                LAST_LLM_ERROR = f"Anthropic 回應解析失敗（{type(e).__name__}）：{str(data)[:200]}"
                return None
        else:
            url = ((base_url or "").strip()
                   or LLM_PROVIDERS.get(provider, {}).get("base_url", "")).rstrip("/")
            if not url:
                LAST_LLM_ERROR = f"{provider} 沒設定 base_url"
                return None
            r = None
            for attempt in (1, 2):
                r = requests.post(
                    f"{url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": mdl,
                        "max_tokens": max_tokens,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user",   "content": prompt},
                        ],
                    },
                    timeout=timeout,
                )
                if r.status_code in _RETRYABLE and attempt == 1:
                    time.sleep(1.5)
                    continue
                break
            if r.status_code >= 400:
                LAST_LLM_ERROR = f"{provider} HTTP {r.status_code} · {_short_err_message(r.text)}"
                return None
            data = r.json()
            try:
                return clean_llm_output(data["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError) as e:
                LAST_LLM_ERROR = f"{provider} 回應解析失敗（{type(e).__name__}）：{str(data)[:200]}"
                return None
    except requests.exceptions.Timeout:
        LAST_LLM_ERROR = f"逾時 >{timeout}s"
        return None
    except requests.exceptions.ConnectionError as e:
        LAST_LLM_ERROR = f"連線失敗：{str(e)[:120]}"
        return None
    except Exception as e:
        LAST_LLM_ERROR = f"{type(e).__name__}: {str(e)[:150]}"
        return None
