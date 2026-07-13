"""健康日誌：每天打卡（症狀分數 0–5 + 戶外分鐘）→ 對當日 AQI 算皮爾森相關 r。

用 tsdb.py（本機 SQLite）存日誌與 AQI 快照。打卡時順便把當下 20 城市
快照寫進 tsdb，之後 diary_with_aqi 才 join 得到「那天的 AQI」。相關性用你自己的資料
證明空污對你的敏感度——這是專案「用日誌驗證」那根支柱。
"""
from __future__ import annotations

import numpy as np

import tsdb

_SOURCE = "pipeline"  # 打卡時寫入的快照 source；讀取相關性時用同一個 source join


def log_entry(date: str, city_id: str, symptom_score: int, outdoor_min: int,
              note: str, snapshot_df=None) -> None:
    """寫一筆日誌；同時把當下快照寫進 tsdb（讓相關性有當日 AQI 可 join）。"""
    tsdb.upsert_diary_entry(date, city_id, int(symptom_score), int(outdoor_min), note or "")
    if snapshot_df is not None:
        try:
            tsdb.write_snapshot(snapshot_df, source=_SOURCE)
        except Exception:  # noqa: BLE001
            pass  # 快照寫入失敗不影響打卡本身


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def read_with_correlation(city_id: str, days: int = 30) -> dict:
    """回傳日誌 + 症狀↔AQI 皮爾森相關 r（資料不足回 None）。"""
    df = tsdb.diary_with_aqi(city_id, days=days, source=_SOURCE)
    entries, xs, ys = [], [], []
    for _, r in df.iterrows():
        avg = _clean(r.get("avg_aqi"))
        entries.append({
            "date": str(r["date"])[:10],
            "symptom_score": int(r["symptom_score"]),
            "outdoor_min": int(r["outdoor_min"]),
            "note": str(r.get("note") or ""),
            "avg_aqi": round(avg, 1) if avg is not None else None,
        })
        if avg is not None:
            xs.append(avg)
            ys.append(int(r["symptom_score"]))
    corr = None
    # 需要 ≥2 對、且兩軸都有變異，corrcoef 才有意義（否則回 nan）。
    if len(xs) >= 2 and len(set(xs)) > 1 and len(set(ys)) > 1:
        corr = round(float(np.corrcoef(xs, ys)[0, 1]), 2)
    return {"entries": entries, "correlation": corr, "n": len(entries), "n_paired": len(xs)}
