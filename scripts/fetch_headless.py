#!/usr/bin/env python3
"""
無 UI 的資料抓取腳本 — 給排程器(GitHub Actions / Windows 工作排程器)定時呼叫。

不依賴任何 UI。直接呼叫 data.py 的純函式，抓 EPA / Open-Meteo / 民間感測器，
產出兩份 JSON:

  docs/data/latest_aqi.json  20 城市當下快照 + 全國摘要。沿用 build_agent_payload
                             的契約,所以同一份檔案靜態網站和現有 Agent Bot 都能讀。
  docs/data/history.json     24 小時逐時時序(每城市一條),給趨勢圖用。
                             latest_aqi.json 為了精簡沒帶時序,所以另存一份。

同一份 latest_aqi.json 也會寫到 agent_export/,維持現有聊天機器人原本讀的位置。

行為(刻意設計成不會用假資料蓋掉好資料):
  - EPA 抓得到真資料         → 覆寫,data_mode=real
  - EPA 抓不到、但已有舊資料  → 保留舊的,直接結束(不要用 mock 蓋掉)
  - EPA 抓不到、也沒有舊資料  → 才寫 mock,免得網站開天窗,並誠實標 data_mode=mock
  - AQI_FORCE_MOCK=1          → 強制 mock(本機測前端用,不必有 EPA 金鑰)

環境變數:
  EPA_KEY         環境部 Open Data 金鑰。沒有就拿不到 EPA 真實資料(時序仍可走 CAMS)。
  LLM_PROVIDER    選配。anthropic / gemini / openai / minimax / custom
  LLM_KEY         選配。有填才會烤一段「全國層級」的分析文字進 latest_aqi.json。
  LLM_MODEL       選配。留空用該 provider 預設。
  LLM_BASE_URL    選配。自訂 endpoint。
  AQI_FORCE_MOCK  選配。=1 強制用合成資料。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 台灣時間（UTC+8、無日光節約）。GitHub Actions 通常跑 UTC；輸出明確的 +08:00，
# 全球瀏覽器才能正確計算「N 分鐘前」。
TAIPEI = timezone(timedelta(hours=8))


def _now_taipei_iso() -> str:
    return datetime.now(TAIPEI).isoformat(timespec="seconds")

# 不論從哪個工作目錄被呼叫,都要能 import 到專案根的 data.py。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import data  # noqa: E402  truststore 在 import data 時注入,要保持在最前面

# ── 輸出位置 ────────────────────────────────────────────────────────────────
WEB_DATA_DIR = ROOT / "docs" / "data"   # 靜態網站讀這裡
AGENT_EXPORT = ROOT / "agent_export"    # 現有 Agent Bot 讀這裡
LATEST_NAME = "latest_aqi.json"
HISTORY_NAME = "history.json"


def _iso(value) -> str:
    """把 timestamp 轉成 ISO 字串(前端 new Date() 直接吃),不論它是 pandas 還是 str。"""
    if hasattr(value, "isoformat"):
        return value.isoformat(timespec="minutes")
    return str(value)


def _build_history(ts_df, hours: int = 24) -> dict:
    """把時序 DataFrame 轉成前端好用的「每城市一條序列」結構。

    只保留最後 `hours` 小時(時序來源有時會多帶幾小時),檔案才不會越長越肥 ——
    這份每小時會被 commit 一次,控制大小很重要。
    """
    cities: dict[str, dict] = {}
    if ts_df is None or getattr(ts_df, "empty", True):
        return {"cities": cities}
    import pandas as pd  # 區域 import:只有這裡需要,且 data 已把 pandas 帶進來
    df = ts_df.sort_values("timestamp")
    cutoff = pd.Timestamp(df["timestamp"].max()) - pd.Timedelta(hours=hours)
    df = df[df["timestamp"] >= cutoff]
    def _num(v, nd):
        # NaN / None → 0（注意：`NaN or 0` 不會過濾 NaN，因為 NaN 是 truthy）。
        return round(float(v), nd) if not pd.isna(v) else 0.0

    for cid, g in df.groupby("city_id"):
        head = g.iloc[0]
        points = []
        for _, row in g.iterrows():
            # CAMS 某些小時 us_aqi 為 null → NaN。跳過缺值，否則 json.dumps 會寫出裸 NaN，
            # 瀏覽器 JSON.parse 整包拒收、看板載入失敗。
            if pd.isna(row["aqi"]):
                continue
            points.append({
                "t": _iso(row["timestamp"]),
                "aqi": round(float(row["aqi"]), 1),
                "pm25": _num(row.get("PM2.5", 0), 1),
                "pm10": _num(row.get("PM10", 0), 1),
                "o3": _num(row.get("O3", 0), 1),
                "no2": _num(row.get("NO2", 0), 1),
                "so2": _num(row.get("SO2", 0), 2),
                "co": _num(row.get("CO", 0), 2),
            })
        cities[str(cid)] = {
            "city": str(head.get("city", cid)),
            "region": str(head.get("region", "")),
            "points": points,
        }
    return {"cities": cities}


def _maybe_analyst(payload: dict) -> str:
    """有設 LLM_KEY 才烤一段全國層級的分析文字(不含個人化)。失敗回空字串。"""
    key = os.environ.get("LLM_KEY", "").strip()
    if not key:
        return ""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip() or "anthropic"
    model = os.environ.get("LLM_MODEL", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()

    nat = payload.get("national", {}) or {}
    worst = nat.get("worst") or {}
    best = nat.get("best") or {}
    rows = "\n".join(
        f"{c['city']} AQI {c['aqi']}（{c['level']}）, PM2.5 {c['pm25']}"
        for c in payload.get("cities", [])
    )
    prompt = (
        "以下是台灣 20 縣市此刻的即時空氣品質。請寫一段 150-250 字的全國層級現況摘要,"
        "繁體中文,寫給一般民眾看。只能根據下面數據,不要編造。內容點出整體狀況、"
        "最差與最佳城市、以及一般民眾的活動建議。不要分點、不要前言。\n\n"
        f"全國平均 AQI {nat.get('avg_aqi')};最差 {worst.get('city')} {worst.get('aqi')};"
        f"最佳 {best.get('city')} {best.get('aqi')}。\n{rows}"
    )
    try:
        resp = data.call_llm_api(provider, key, prompt, model, base_url,
                                 max_tokens=1024, timeout=60)
        return (resp or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] LLM 分析失敗,略過: {exc}", file=sys.stderr)
        return ""


def _write(path: Path, obj: dict, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    kb = max(1, path.stat().st_size // 1024)
    print(f"[ok] 寫出 {path.relative_to(ROOT)}  ({kb} KB)")


def main() -> int:
    force_mock = os.environ.get("AQI_FORCE_MOCK", "") == "1"
    epa_key = os.environ.get("EPA_KEY", "").strip()

    snapshot = None
    if not force_mock:
        snapshot, msg = data.generate_real_snapshot(epa_key)
        print(f"[info] EPA 快照: {msg}")

    data_mode = "real"
    if snapshot is None or getattr(snapshot, "empty", True):
        # 拿不到真實資料。先看有沒有舊資料可以保留,不要用假資料蓋掉好的。
        if not force_mock and (WEB_DATA_DIR / LATEST_NAME).exists():
            print("[skip] 這次抓不到 EPA 真實資料,保留上一份(不用 mock 蓋掉好資料)。")
            return 0
        print("[info] 沒有可用的真實資料,改用合成資料(mock),讓網站不致開天窗。")
        snapshot = data.generate_current_snapshot()
        data_mode = "mock"

    # 24h 時序:真實優先(內部三層 fallback);整個失敗才退到純合成時序。
    try:
        ts = data.generate_real_timeseries(snapshot, hours_back=24, epa_key=epa_key)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 真實時序失敗,改用合成時序: {exc}", file=sys.stderr)
        ts = data.generate_time_series(hours_back=24)

    payload = data.build_agent_payload(
        snapshot,
        analysis="",
        advisories_raw="",
        data_mode=data_mode,
        user_city="taipei",
        threshold=100,
        user_profile=None,
        generated_at=_now_taipei_iso(),   # 明確 +08:00，避免跨時區新鮮度誤判
    )
    payload["analyst_summary"] = _maybe_analyst(payload)

    history = _build_history(ts)
    history["generated_at"] = payload["generated_at"]
    history["data_mode"] = data_mode

    _write(WEB_DATA_DIR / LATEST_NAME, payload)
    _write(WEB_DATA_DIR / HISTORY_NAME, history, compact=True)   # 時序較大,壓緊一點
    _write(AGENT_EXPORT / LATEST_NAME, payload)   # 同一份給現有 Agent Bot

    print(f"[done] data_mode={data_mode}  generated_at={payload['generated_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
