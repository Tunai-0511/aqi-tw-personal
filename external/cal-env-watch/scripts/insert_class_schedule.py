"""
insert_class_schedule.py — Batch-insert class schedule
as weekly recurring events, ending 2026-06-26.

Source data: hard-coded below.
OAuth: uses secrets/google-cal-write.json (calendar.events scope).

Usage:
    python scripts\\insert_class_schedule.py --dry-run   # preview only
    python scripts\\insert_class_schedule.py             # actually insert
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

SECRETS_PATH = Path(r"C:\Users\User\.openclaw\secrets\google-cal-write.json")
TZ = timezone(timedelta(hours=8))  # Asia/Taipei

# Last class day = 2026-06-26 (Friday). RRULE UNTIL uses UTC, so 6/26 23:59:59 +08
# = 6/26 15:59:59Z. Google wants YYYYMMDDTHHMMSSZ (no dashes/colons).
UNTIL_UTC = "20260626T155959Z"

# 7 = Peacock (cyan/teal) — easy to spot among work/personal events
COLOR_ID_CLASS = "7"

# 15-min popup reminder (in-person class, no link to join)
REMINDERS = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 15}]}

# Class schedule template. Replace with your actual schedule.
CLASSES: list[dict] = [
    {
        "summary": "範例課程 A",
        "first_date": "2026-06-15",  # Mon
        "start_time": "09:10", "end_time": "12:00",
        "classroom": "101",
    },
    {
        "summary": "範例課程 B",
        "first_date": "2026-06-16",  # Tue
        "start_time": "13:30", "end_time": "16:20",
        "classroom": "202",
    },
]


# --------------------------------------------------------------------------- #
# Build event payload
# --------------------------------------------------------------------------- #

def build_event_body(cls: dict) -> dict:
    """Build a Google Calendar v3 event resource for one class."""
    first_date = datetime.strptime(cls["first_date"], "%Y-%m-%d").date()
    sh, sm = map(int, cls["start_time"].split(":"))
    eh, em = map(int, cls["end_time"].split(":"))
    start_dt = datetime(first_date.year, first_date.month, first_date.day, sh, sm, tzinfo=TZ)
    end_dt = datetime(first_date.year, first_date.month, first_date.day, eh, em, tzinfo=TZ)

    title = cls["summary"]
    classroom = cls.get("classroom")
    description_parts = []
    if classroom:
        description_parts.append(f"教室 {classroom}")
        # cal-env-watch LOCATION_KEYWORDS match: substring search on lowercased location
        # "台中科大" is in the keyword set
        location = f"臺中科技大學 (台中科大) 教室{classroom}"
    else:
        location = "臺中科技大學 (台中科大)"

    description_parts.append("週課表自動匯入")
    description_parts.append("學期結束：2026-06-26")

    body: dict = {
        "summary": f"【課】{title}",
        "location": location,
        "description": "\n".join(description_parts),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Taipei"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Taipei"},
        "recurrence": [f"RRULE:FREQ=WEEKLY;UNTIL={UNTIL_UTC}"],
        "colorId": COLOR_ID_CLASS,
        "reminders": REMINDERS,
    }
    return body


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print events, don't insert")
    args = ap.parse_args()

    if not args.dry_run:
        if not SECRETS_PATH.exists():
            print(f"ERROR: {SECRETS_PATH} not found.", file=sys.stderr)
            print("Run `python scripts\\oauth_calendar_write.py` first.", file=sys.stderr)
            return 1

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        creds = Credentials(
            token=None,  # will be auto-refreshed
            refresh_token=data["refresh_token"],
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=data.get("scopes", ["https://www.googleapis.com/auth/calendar.events"]),
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    print("=" * 70)
    print(f"  NTCUST 課表匯入預覽  ({len(CLASSES)} 個 events, 每週重複至 2026-06-26)")
    print("=" * 70)
    print()

    created = 0
    failed = 0
    for cls in CLASSES:
        body = build_event_body(cls)
        # Print human-readable summary
        wd = ["一", "二", "三", "四", "五", "六", "日"][
            datetime.strptime(cls["first_date"], "%Y-%m-%d").weekday()
        ]
        loc_short = body["location"]
        print(f"  [{wd}] {cls['first_date']}  {cls['start_time']}-{cls['end_time']}"
              f"  【課】{cls['summary']:<14}  @ {loc_short}")

        if args.dry_run:
            continue

        try:
            result = service.events().insert(calendarId="primary", body=body).execute()
            created += 1
            print(f"      → created event id={result.get('id')[:20]}… "
                  f"htmlLink={result.get('htmlLink')[:50]}…")
        except HttpError as e:
            failed += 1
            print(f"      → FAILED ({e.resp.status}): {e._get_reason() if hasattr(e, '_get_reason') else e}")

    print()
    print("=" * 70)
    if args.dry_run:
        print(f"  DRY-RUN: 0 寫入、{len(CLASSES)} 個預覽完成")
    else:
        print(f"  完成: {created} 個 events 寫入、{failed} 個失敗")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())