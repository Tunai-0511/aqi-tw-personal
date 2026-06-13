#!/usr/bin/env python3
"""Record a chat-platform `feel 1~5` check-in into AgentAQI's health diary.

Platform-agnostic (Discord / Telegram / LINE / Slack…). This script is
intentionally small and endpoint-free: chat users reply with `feel 4`, then the
bot (or you) runs this helper to persist the score into the same SQLite
`health_diary` table used by Streamlit SECTION · 09.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tsdb
from data import CITY_BY_ID

_SCORE_RE = re.compile(r"^\s*(?:feel\s*[:：]?\s*)?([1-5])\s*$", re.IGNORECASE)


def parse_score(text: str) -> int:
    """Parse `feel 4`, `Feel: 2`, or bare `5` into an integer 1..5."""
    match = _SCORE_RE.match(text or "")
    if not match:
        raise ValueError("請輸入 `feel 1` 到 `feel 5`，例如：feel 4")
    return int(match.group(1))


def record_feel(
    score: int,
    city_id: str = "taichung",
    outdoor_min: int = 0,
    note: str = "feel 指令打卡",
    entry_date: date | None = None,
) -> dict[str, object]:
    """Write one feel score into tsdb.health_diary and return the saved values."""
    score = int(score)
    if score < 1 or score > 5:
        raise ValueError("score must be between 1 and 5")
    if city_id not in CITY_BY_ID:
        valid = ", ".join(sorted(CITY_BY_ID))
        raise ValueError(f"unknown city_id={city_id!r}; valid: {valid}")

    when = entry_date or date.today()
    date_str = when.isoformat()
    tsdb.upsert_diary_entry(
        date=date_str,
        city_id=city_id,
        symptom_score=score,
        outdoor_min=int(outdoor_min),
        note=note,
    )
    return {
        "date": date_str,
        "city_id": city_id,
        "city": CITY_BY_ID[city_id]["name"],
        "symptom_score": score,
        "outdoor_min": int(outdoor_min),
        "note": note,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record chat-platform feel check-in into AgentAQI health_diary")
    parser.add_argument("text", help="`feel 1`..`feel 5` or bare `1`..`5`")
    parser.add_argument("--city", default="taichung", choices=sorted(CITY_BY_ID), help="city_id for health_diary")
    parser.add_argument("--outdoor-min", type=int, default=0, help="outdoor exposure minutes; default 0 for quick chat check-in")
    parser.add_argument("--note", default="feel 指令打卡", help="note saved in health_diary")
    parser.add_argument("--date", dest="entry_date", help="YYYY-MM-DD; defaults to today")
    args = parser.parse_args(argv)

    try:
        score = parse_score(args.text)
        entry_date = datetime.strptime(args.entry_date, "%Y-%m-%d").date() if args.entry_date else None
        saved = record_feel(
            score=score,
            city_id=args.city,
            outdoor_min=args.outdoor_min,
            note=args.note,
            entry_date=entry_date,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"已記錄 {saved['date']} {saved['city']}："
        f"體感 {saved['symptom_score']}/5，戶外 {saved['outdoor_min']} 分鐘"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
