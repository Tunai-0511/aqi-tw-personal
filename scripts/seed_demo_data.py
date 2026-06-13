"""
期末 demo 用假資料灌庫工具 (Demo Data Seeder)
==============================================================================
讓 SECTION 08-10「個人化推薦以後」的區段，**一打開就有豐富內容**可秀，
不必在 demo 現場等 EPA / CAMS API、也不必手動逐日打卡。

灌入內容(全部明確標記為 demo,放在隔離的 source,可一鍵清除,不污染真實使用):
  1) 過去 ~16 天、每小時、20 城市的 AQI 歷史
       → 寫進 SQLite `aqi_snapshots`,**source='demo'**、data_mode='demo'
       → App 偵測到有 demo 資料時會自動改讀 source='demo'(見 tsdb.has_demo_data),
         所以**即使之後跑真實 Pipeline(寫 source='cams_hourly')也不會覆蓋 demo**
       → 點亮 SECTION 08 的「過去 7 天趨勢圖」與「比上週 ±X%」徽章
         (週對比需要 this 7 天 + prev 7 天 = 14 天,故灌 16 天保險)
  2) 常駐城市(預設台北)的 14 天「污染事件軌跡」覆寫
       → 每日平均 AQI 做出上週平穩、本週數次升高的形狀
       → 讓趨勢線有起伏、週對比徽章顯示明顯 ↑、散點 x 軸跨度夠
  (健康日誌「打卡紀錄」不在此灌入 —— 改由 App 進 SECTION 09 時即時回填,依該城市「當下
   生效的 AQI 來源」推導症狀,且不寫任何 demo 標記。跑本腳本後 App 會以 source='demo'
   對齊,散點點數較多;見 app.py 的 _ensure_demo_diary。)

⚠ 為何要標記 + 隔離:本專案一向強調「真實外部 API、無合成資料」,且使用者可能在
  demo 中途重跑真實 Pipeline(會寫 source='cams_hourly')。為避免互相覆蓋:
  - AQI:放在獨立的 **source='demo'** + data_mode='demo' —— 與真實 'cams_hourly'
         完全隔離(PK 是 (ts, city_id, source),source 不同就不會 UPSERT 互蓋)。
         App 偵測到 demo 資料就自動讀它(tsdb.has_demo_data)。
  - 日誌:由 App 端即時回填(本腳本不寫日誌);App 會自動對齊到 source='demo'。
  AQI 可用 `python seed_demo_data.py --clear` 一鍵移除(刪 data_mode='demo';一併清掉
  任何殘留的 [demo] 日誌列)。

個人健康檔案(年齡 / BMI / ICD-10 / 病歷)是 Streamlit session_state,無法由本
腳本預先灌入 —— 請在 App 封面「步驟① 個人健康檔案」展開表單自行填寫。

用法
-----
    python scripts/seed_demo_data.py            # 灌入 demo 資料
    python scripts/seed_demo_data.py --clear    # 清除所有 demo 資料
    python scripts/seed_demo_data.py --city kaohsiung   # 改常駐城市(預設 taipei)

(Windows 可直接雙擊 scripts/seed_demo_data.bat,會自動 activate venv)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 讓本腳本(放在 scripts/ 子目錄)能 import 專案根目錄的 data / tsdb 模組
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # noqa: E402  (第三方;與 data/tsdb 同段載入)
import data  # noqa: E402  (sys.path 調整後才能 import)
import tsdb  # noqa: E402

# Windows 主控台預設 codepage 可能是 cp950(繁中),無法輸出 ✓ / 🗑 等符號 → 強制
# 把 stdout/stderr 切成 utf-8(.bat 已 chcp 65001,但直接 python 跑時沒有)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

# demo 資料的識別標記
DEMO_DATA_MODE = "demo"        # aqi_snapshots.data_mode 用這個值區隔 demo 列(清除靠它)
DEMO_SOURCE    = "demo"        # 放在隔離的 source,真實 Pipeline 寫 'cams_hourly' 不會覆蓋
DEMO_DIARY_TAG = "[demo]"      # health_diary.note 前綴,清除時用 LIKE 比對

HISTORY_DAYS = 16              # 全城市每小時 AQI 灌幾天(>14 才夠週對比 this+prev 兩窗)
DIARY_DAYS = 14               # 常駐城市「污染事件」軌跡長度(每日均值設計成本週升高)

# 常駐城市過去 14 天的「每日平均 AQI」設計軌跡(oldest → newest,[0]=14 天前、[13]=昨天)。
# 刻意做成「上週平穩、本週數次污染事件」的形狀,一條軌跡同時餵三個視覺:
#   - SECTION 08 的 7 天趨勢線 → 有明顯起伏可看
#   - SECTION 08「比上週 ±X%」徽章 → 本週均值(~89)明顯高於上週(~52),≈ +70% ↑
#   - SECTION 09 散點 x 軸(每日平均 AQI)→ 跨度足夠(~42–115),配合 symptom 由同一條
#     軌跡推導,Pearson r 會明顯為正(且因 jitter 不等於 1.0,看起來寫實)
DAILY_TARGETS = [42, 48, 55, 50, 60, 52, 58,  70, 95, 115, 80, 105, 68, 90]

# 日夜倍率的 24 小時平均 — 把「設計每日均值」還原成逐時值時用它正規化,確保不改變當日平均
_MEAN_DIURNAL = sum(data._diurnal_factor(h) for h in range(24)) / 24.0


def _day_target_map(today) -> dict[str, float]:
    """{YYYY-MM-DD: 設計每日均值},涵蓋常駐城市過去 DIARY_DAYS 天(不含今天)。"""
    out: dict[str, float] = {}
    for idx in range(DIARY_DAYS, 0, -1):           # idx=14(最舊)… 1(昨天)
        day = today - timedelta(days=idx)
        out[day.isoformat()] = float(DAILY_TARGETS[DIARY_DAYS - idx])
    return out


def _pollutants_from_aqi(aqi: float):
    """由 AQI 用與 data.generate_current_snapshot 相同的比例推導各污染物 + 風險(無噪聲)。"""
    pm25 = max(2.0, aqi * 0.45)
    pm10 = max(5.0, pm25 * 1.6)
    o3   = max(5.0, 40 + (aqi - 60) * 0.3)
    no2  = max(2.0, 18 + aqi * 0.18)
    so2  = max(0.5, 4 + aqi * 0.03)
    co   = max(0.1, 0.4 + aqi * 0.006)
    risk = (0.40 * (pm25 / 35) + 0.20 * (aqi / 150) + 0.15 * (o3 / 100)
            + 0.10 * (no2 / 80) + 0.08 * (so2 / 30) + 0.07 * (co / 5)) * 100
    return pm25, pm10, o3, no2, so2, co, min(100.0, max(0.0, risk))


def seed_aqi_history() -> int:
    """灌入過去 HISTORY_DAYS 天、每小時、20 城市的 AQI 歷史(source='demo')。"""
    df = data.generate_time_series(hours_back=HISTORY_DAYS * 24)
    return tsdb.write_history_hourly(df, source=DEMO_SOURCE, data_mode=DEMO_DATA_MODE)


def seed_city_episode(city_id: str, today) -> int:
    """覆寫常駐城市過去 DIARY_DAYS 天的逐時 AQI,使每日均值貼合 DAILY_TARGETS。

    保留日夜形狀(_diurnal_factor / _MEAN_DIURNAL 正規化),只把「當日平均」拉到設計值,
    讓趨勢線 / 週對比 / 散點都有明顯且彼此一致的訊號。UPSERT 會覆蓋 seed_aqi_history()
    先前為該城市同 ts 寫入的列。
    """
    info = data.CITY_BY_ID[city_id]
    rows = []
    for day_str, target in _day_target_map(today).items():
        d = datetime.fromisoformat(day_str).date()
        for h in range(24):
            ts = datetime(d.year, d.month, d.day, h)
            # 設計均值 × (該小時日夜倍率 / 24h 平均倍率) → 當日 24 小時平均 ≈ target
            aqi = target * (data._diurnal_factor(h) / _MEAN_DIURNAL) + ((h % 5) - 2) * 0.8
            aqi = float(max(15.0, min(280.0, aqi)))
            pm25, pm10, o3, no2, so2, co, risk = _pollutants_from_aqi(aqi)
            rows.append({
                "timestamp": ts, "city_id": city_id,
                "city": info["name"], "region": info["region"],
                "aqi": round(aqi, 1), "PM2.5": round(pm25, 1), "PM10": round(pm10, 1),
                "O3": round(o3, 1), "NO2": round(no2, 1), "SO2": round(so2, 2),
                "CO": round(co, 2), "risk": round(risk, 1),
            })
    return tsdb.write_history_hourly(pd.DataFrame(rows), source=DEMO_SOURCE, data_mode=DEMO_DATA_MODE)


# 註:健康日誌(打卡紀錄)不再由本腳本灌入 —— 已改由 App 進 SECTION 09 時,依該城市
#     「當下生效的 AQI 來源」即時回填(見 app.py 的 _ensure_demo_diary):症狀分數由
#     當日平均 AQI 推導,且不寫任何 demo 標記(看起來就是本人累積的紀錄)。本腳本只負責
#     AQI 歷史 + 常駐城市的「污染事件軌跡」。跑完本腳本後,App 會自動以 source='demo'
#     對齊日誌,點數更多;不跑本腳本時,App 以真實 cams_hourly 對齊(約 7 天)。


def clear_demo() -> tuple[int, int]:
    """移除所有 demo 資料:aqi_snapshots(data_mode='demo')+ health_diary(note 含 [demo])。"""
    tsdb.init()              # 確保兩張表都存在
    tsdb._init_health_diary()
    with sqlite3.connect(tsdb.DB_PATH) as c:
        cur1 = c.execute("DELETE FROM aqi_snapshots WHERE data_mode = ?", (DEMO_DATA_MODE,))
        n_aqi = cur1.rowcount if cur1.rowcount is not None else 0
        cur2 = c.execute("DELETE FROM health_diary WHERE note LIKE ?", (f"%{DEMO_DIARY_TAG}%",))
        n_diary = cur2.rowcount if cur2.rowcount is not None else 0
    return n_aqi, n_diary


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentAQI 期末 demo 假資料灌庫工具")
    parser.add_argument("--clear", action="store_true", help="清除所有 demo 資料後結束")
    parser.add_argument("--city", default="taipei", help="污染事件軌跡要鋪在哪個常駐城市 id(預設 taipei)")
    args = parser.parse_args()

    print("=" * 60)
    print("  AgentAQI · 期末 demo 假資料灌庫工具")
    print(f"  資料庫:{tsdb.DB_PATH}")
    print("=" * 60)

    if args.clear:
        n_aqi, n_diary = clear_demo()
        print(f"  🗑  已清除 demo AQI 列:{n_aqi}")
        print(f"  🗑  已清除 demo 日誌列:{n_diary}")
        print("  ✓ demo 資料清除完成(真實資料不受影響)。")
        return

    city_id = args.city
    if city_id not in data.CITY_BY_ID:
        print(f"  [錯誤] 不認得的城市 id:{city_id}")
        print(f"        可用:{', '.join(c['id'] for c in data.CITIES)}")
        sys.exit(1)
    city_name = data.CITY_BY_ID[city_id]["name"]
    today = datetime.now().date()

    print(f"  ① 灌入過去 {HISTORY_DAYS} 天、每小時、20 城市 AQI 歷史 …")
    n_aqi = seed_aqi_history()
    print(f"     ✓ 寫入 {n_aqi} 列(source={DEMO_SOURCE}, data_mode={DEMO_DATA_MODE})")

    print(f"  ② 為常駐城市「{city_name}」鋪上 {DIARY_DAYS} 天污染事件軌跡(本週↑) …")
    n_ep = seed_city_episode(city_id, today)
    print(f"     ✓ 覆寫 {n_ep} 列(每日均值 42–115,本週均值高於上週)")

    print("-" * 60)
    print("  ✓ demo AQI 就緒!現在可以:")
    print("    - SECTION 08:看「7 天趨勢圖」起伏 +「比上週」明顯 ↑ 徽章")
    print("    - 封面步驟①:展開「個人健康檔案」自行填寫 persona(年齡 / 疾病 / AQI 閾值)")
    print("    - SECTION 09:打卡紀錄由 App 自動回填(依此 demo AQI 對齊),散點 + Pearson r 明顯為正")
    print("  清除:python scripts/seed_demo_data.py --clear")
    print("=" * 60)


if __name__ == "__main__":
    main()
