"""
aqi-live skill reader — 讀 AgentAQI 匯出的 latest_aqi.json,印出可貼進 Discord 的
繁中空品摘要(全國概況 / 指定城市 + 依 user_profile 個人化)。

這是「拉取模型」的 Hermes 端:AgentAQI 跑完 Pipeline 把結果寫進
hermes_export/latest_aqi.json,Hermes(Discord bot)呼叫本腳本(或內嵌等價邏輯)
讀那份 JSON 回答 —— 不需要任何外部 API key。

用法:
    python read_export.py            # 全國概況
    python read_export.py 台北市      # 指定城市 + 個人化提醒

路徑:預設讀 <專案根>/hermes_export/latest_aqi.json,可用環境變數 AGENTAQI_EXPORT 覆寫。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Windows 主控台預設可能是 cp950,無法輸出 emoji / 全形以外字元 → 強制 utf-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass


def export_path() -> Path:
    """latest_aqi.json 的路徑:優先用 AGENTAQI_EXPORT 環境變數,否則專案根的 hermes_export/。"""
    env = os.environ.get("AGENTAQI_EXPORT")
    if env:
        return Path(env)
    # 本檔在 hermes_skills/aqi-live/ → 專案根是上兩層
    return Path(__file__).resolve().parent.parent.parent / "hermes_export" / "latest_aqi.json"


def _persona_line(prof: dict | None) -> str:
    """依 user_profile 組一句個人化提醒;沒有 persona 回空字串。"""
    if not prof:
        return ""
    bits: list[str] = []
    if prof.get("age"):
        bits.append(f"{prof['age']} 歲")
    if prof.get("diagnoses"):
        bits.append("、".join(prof["diagnoses"]))
    elif prof.get("conditions"):
        bits.append("、".join(prof["conditions"]))
    if prof.get("bmi"):
        bits.append(f"BMI {prof['bmi']}")
    who = "、".join(bits) if bits else "你"
    return (
        f"🩺 給{who}的提醒:空品不佳時請依自身狀況減少戶外、必要時戴 N95;"
        "若有胸悶 / 喘鳴等不適儘速就醫。"
    )


def format_reply(data: dict, city_query: str | None = None) -> str:
    """把 latest_aqi.json 內容格式化成一段可貼進 Discord 的繁中回覆。"""
    mode = data.get("data_mode", "?")
    tag = "" if mode == "real" else f"（⚠ {mode} 資料）"
    lines: list[str] = []

    if city_query:
        match = None
        for c in data.get("cities", []):
            if city_query == c.get("city_id") or city_query in (c.get("city") or ""):
                match = c
                break
        if not match:
            return f"找不到「{city_query}」。可問「全國概況」或台北 / 高雄等城市名。{tag}"
        lines.append(f"📍 {match['city']} AQI {float(match['aqi']):.0f}（{match['level']}）{tag}")
        lines.append(
            f"   PM2.5 {match['pm25']} · PM10 {match['pm10']} · O3 {match['o3']} · NO2 {match['no2']}"
        )
        adv = (data.get("advisories") or {}).get(match["city"])
        if adv:
            lines.append(f"🏥 {adv}")
    else:
        nat = data.get("national") or {}
        worst = nat.get("worst") or {}
        best = nat.get("best") or {}
        lines.append(f"🇹🇼 全國平均 AQI {nat.get('avg_aqi', '—')}{tag}")
        lines.append(f"🔴 最高:{worst.get('city', '—')} {worst.get('aqi', '—')}（{worst.get('level', '')}）")
        lines.append(f"🟢 最低:{best.get('city', '—')} {best.get('aqi', '—')}（{best.get('level', '')}）")

    pl = _persona_line(data.get("user_profile"))
    if pl:
        lines.append(pl)
    lines.append(f"🕒 資料時間:{data.get('generated_at', '?')}")
    return "\n".join(lines)


def main() -> None:
    path = export_path()
    if not path.exists():
        print(
            f"找不到匯出檔:{path}\n"
            "請先在 AgentAQI 跑一次 Pipeline 產生 latest_aqi.json(或設 AGENTAQI_EXPORT)。"
        )
        sys.exit(1)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"讀取 / 解析失敗:{type(e).__name__}: {e}")
        sys.exit(1)
    city = sys.argv[1] if len(sys.argv) > 1 else None
    print(format_reply(data, city))


if __name__ == "__main__":
    main()
