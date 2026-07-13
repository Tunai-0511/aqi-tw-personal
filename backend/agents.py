"""三個專職 agent。

  採集者 (collector) — 純 ETL，不呼叫 LLM。直接用 data.py 抓真實資料，失敗退 mock。
  分析師 (analyst)   — 全國三段風險分析（RAG 文獻直接注入 prompt）。
  預警員 (advisor)   — 單一城市 × 個人化建議（依診斷檢索 RAG 後注入 prompt）。

分析師/預警員用 llm.complete（供應商中性：anthropic / minimax / openai / gemini / custom），
所以換成 MiniMax 也照樣跑。
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd

import data
from . import llm, rag
from .personalize import UserProfile, profile_block

Event = Callable[[str, dict], None]

# 系統提示（逐字沿用）
ANALYST_SYSTEM = (
    "你是台灣空氣品質多代理人系統中的一員。重要：只能根據訊息中提供的具體數值作答，"
    "禁止編造資料、城市或事件。回覆使用繁體中文，不限制長度——把該講的講完整。"
)
ADVISOR_SYSTEM = (
    "你是台灣空氣品質系統的健康預警員。重要:只能根據訊息中提供的具體數值與文獻作答,"
    "禁止編造資料、城市或事件。回覆使用繁體中文。"
)


def _emit(on_event: Event | None, kind: str, **payload) -> None:
    if on_event:
        on_event(kind, payload)


def national_summary(snapshot: pd.DataFrame) -> dict:
    """全國摘要（平均 / 最差 / 最佳），欄位對齊 build_agent_payload 的 national。"""
    w = snapshot.sort_values("aqi", ascending=False).iloc[0]
    b = snapshot.sort_values("aqi").iloc[0]
    return {
        "avg_aqi": round(float(snapshot["aqi"].mean()), 1),
        "worst": {"city": str(w["city"]), "aqi": round(float(w["aqi"]), 1), "level": str(w["level"])},
        "best": {"city": str(b["city"]), "aqi": round(float(b["aqi"]), 1), "level": str(b["level"])},
    }


# ── 採集者：純 ETL ───────────────────────────────────────────────────────────
def run_collector(epa_key: str, on_event: Event | None = None):
    """回傳 (snapshot_df, ts_df, data_mode, national)。EPA 失敗自動退合成資料。"""
    _emit(on_event, "agent_start", agent="collector", name="採集者")
    snapshot, msg = data.generate_real_snapshot(epa_key or None)
    data_mode = "real"
    if snapshot is None or getattr(snapshot, "empty", True):
        _emit(on_event, "agent_note", agent="collector", text=f"EPA 無資料，改用模擬：{msg}")
        snapshot = data.generate_current_snapshot()
        data_mode = "mock"
    else:
        _emit(on_event, "agent_note", agent="collector", text=msg)
    try:
        ts = data.generate_real_timeseries(snapshot, hours_back=24, epa_key=epa_key or None)
    except Exception as exc:  # noqa: BLE001
        _emit(on_event, "agent_note", agent="collector", text=f"時序抓取失敗，改用合成：{exc}")
        ts = data.generate_time_series(hours_back=24)
    national = national_summary(snapshot)
    _emit(on_event, "agent_done", agent="collector", cities=int(len(snapshot)))
    return snapshot, ts, data_mode, national


# ── 分析師：全國三段分析（RAG 直接注入）─────────────────────────────────────
def run_analyst(snapshot: pd.DataFrame, national: dict, profile: UserProfile,
                on_event: Event | None = None, override: dict | None = None) -> str:
    _emit(on_event, "agent_start", agent="analyst", name="分析師")
    prof = profile_block(profile)
    prof_section = (prof + "\n") if prof else ""
    worst, best = national["worst"], national["best"]
    w_row = snapshot.sort_values("aqi", ascending=False).iloc[0]
    b_row = snapshot.sort_values("aqi").iloc[0]
    user_prompt = (
        prof_section
        + f"台灣即時空品快報（{datetime.now().strftime('%Y-%m-%d %H:%M')}）：\n"
        f"- 全國平均 AQI：{national['avg_aqi']:.1f}\n"
        f"- 最高：{worst['city']} AQI {worst['aqi']:.0f}（{worst['level']}），PM2.5 {w_row['PM2.5']} μg/m³\n"
        f"- 最低：{best['city']} AQI {best['aqi']:.0f}（{best['level']}），PM2.5 {b_row['PM2.5']} μg/m³\n"
        f"- 覆蓋城市：{len(snapshot)}\n\n"
        "RAG 文獻可引用：\n"
        "- WHO 2021：PM2.5 年均 ≤ 5 μg/m³，24h ≤ 15 μg/m³\n"
        "- EPA NAAQS：PM2.5 24h ≤ 35 μg/m³\n"
        "- Lancet 2023：高 PM2.5 下劇烈運動，肺部沉積量 ↑3-5x\n\n"
        "請用 3 段繁體中文輸出：① 現況摘要 ② 健康建議 ③ 未來 6 小時研判。"
        "每段 2-3 句，必須引用上方數值，不可編造其他城市或數字。"
        + (
            "若上方有使用者設定，第 ② 段請依已提供的敏感程度、活動、門檻或健康因素"
            "給 1-2 句量身建議；不得推測未提供的疾病。"
            if prof else ""
        )
    )
    text = llm.complete(ANALYST_SYSTEM, user_prompt, max_tokens=4096, override=override)
    _emit(on_event, "agent_done", agent="analyst", chars=len(text))
    return text


# ── 預警員：單城市 × 個人化建議（依診斷檢索 RAG 後注入）──────────────────────
def run_advisor(snapshot: pd.DataFrame, national: dict, city_id: str, profile: UserProfile,
                on_event: Event | None = None, override: dict | None = None) -> str | None:
    """回傳該城市的個人化建議純文字；使用者沒填個人檔案回 None。"""
    if not profile.is_filled:
        return None
    _emit(on_event, "agent_start", agent="advisor", name="預警員")
    match = snapshot[snapshot["city_id"] == city_id]
    if match.empty:
        # 請求城市不在快照（真實資料偶爾某縣市當下無測站）。退回台北（幾乎必有），
        # 再退回第一列——刻意不退到「最差城市」，以免建議內容與標籤城市不符。
        fallback = snapshot[snapshot["city_id"] == "taipei"]
        match = fallback if not fallback.empty else snapshot.head(1)
    row = match.iloc[0]
    rank = int((snapshot["aqi"] > row["aqi"]).sum()) + 1
    avg_aqi = float(snapshot["aqi"].mean())
    prof = profile_block(profile)
    over = float(row["aqi"]) > int(profile.threshold)

    # 個人 RAG：用診斷標籤 + 城市當 query 檢索，把文獻直接注入 prompt（原 app 的做法）。
    diag_labels = [d["label"] for d in data.USER_ICD10_OPTIONS if d["code"] in profile.diagnoses]
    picked = rag.retrieve("個人健康建議 " + " ".join(diag_labels) + " " + str(row["city"]), top_k=5)
    rag_block = rag.format_block(picked)

    personal_focus = (
        "引用其年齡、已診斷疾病與已提供病史" if profile.has_health_profile
        else "引用其空氣敏感程度、主要活動與提醒門檻；不得推測疾病"
    )
    warning_focus = (
        "出現哪些症狀該中止活動或就醫（對應已提供病史）" if profile.has_health_profile
        else "出現哪些不適應中止活動，必要時尋求醫療協助（不得推測病史）"
    )
    user_prompt = (
        prof + "\n"
        f"你是空品健康預警員。只針對「{row['city']}」這一個城市,為上面這位使用者寫一份**詳細**的個人化健康建議。\n\n"
        f"=== {row['city']} 即時數據 ===\n"
        f"AQI {row['aqi']:.0f}({row['level']})· PM2.5 {row['PM2.5']} μg/m³ · PM10 {row['PM10']} · "
        f"O3 {row['O3']} · NO2 {row['NO2']} · SO2 {row['SO2']} · CO {row['CO']}\n"
        f"全國脈絡:全國平均 AQI {avg_aqi:.0f};{row['city']} 在 20 城市中第 {rank} 高。\n"
        f"對照使用者自設閾值:目前 AQI {row['aqi']:.0f} "
        f"{'已超過' if over else '未超過'}使用者設定的 {int(profile.threshold)} — 建議必須回應這一點。\n"
        + rag_block
        + "\n=== 輸出格式(繁體中文,總長 250-450 字,依下列小節,不要其他前言)===\n"
        f"【現況風險】2-3 句:此刻對這位使用者的主要風險與原因，{personal_focus}\n"
        "【外出建議】2-3 句:今天適不適合出門、建議的活動強度/時段/時長\n"
        "【防護裝備】1-2 句:口罩等級、是否開空氣清淨機、其他防護\n"
        f"【症狀警訊】1-2 句:{warning_focus}\n"
        "【一句總結】20 字內的行動指令\n"
        "規則:只引用上面提供的數值、偏好與文獻，不可編造或推測未提供的健康資訊。"
    )
    text = llm.complete(ADVISOR_SYSTEM, user_prompt, max_tokens=3072, override=override)
    _emit(on_event, "agent_done", agent="advisor", chars=len(text))
    return text
