"""
cal_env_watch.py — Calendar × Weather × AQI proactive warning

For each upcoming event in the next LOOKAHEAD_HOURS hours:
  - Look up AQI from the nearest EPA station
  - Look up weather (precipitation probability, temperature, weather code) from Open-Meteo
  - Compare against thresholds → decide warning(s)
  - Send new warnings to Telegram (deduped via state file)
  - Send nothing if all clean

Usage:
  python cal_env_watch.py              # normal run (reads calendar, may send telegram)
  python cal_env_watch.py --dry-run    # never sends telegram, prints what would be sent
  python cal_env_watch.py --window 8   # custom lookahead (default 6 hours)

Exit codes:
  0  OK
  1  Critical error (auth, network down, etc.)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Force utf-8 output (Windows cp950/cp936 safe).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

WORKSPACE = Path(r"C:\Users\User\.openclaw\workspace")
SCRIPTS_DIR = WORKSPACE / "scripts"
MEMORY_DIR = WORKSPACE / "memory"

GOOGLE_CAL_SECRETS = Path(r"C:\Users\User\.openclaw\secrets\google-cal.json")
MOENV_SECRETS = Path(r"C:\Users\User\.openclaw\secrets\moenv.json")

STATE_PATH = MEMORY_DIR / "cal-warn-state.json"
RAW_AQI_PATH = MEMORY_DIR / "aqi_raw_latest.json"

# Telegram delivery (must match other cron jobs)
TG_CHANNEL = "telegram"
TG_TARGET = os.environ.get("TG_TARGET", "YOUR_TELEGRAM_CHAT_ID")

# Lookahead window in hours
DEFAULT_LOOKAHEAD_HOURS = 6

# Default location (台中市中區/西區) — used when event has no location field
DEFAULT_LAT = 24.1469
DEFAULT_LON = 120.6476
DEFAULT_LOCATION_LABEL = "台中 (default)"

# Quiet hours (Asia/Taipei) — no proactive checks between these hours
QUIET_START_HOUR = 23
QUIET_END_HOUR = 6

# AQI station priority by name (closer to 台中科技大學 is better).
# Used for matching keyword-based location strings.
LOCATION_KEYWORDS: list[tuple[set[str], tuple[float, float], str]] = [
    ({"中科大", "中臺", "台中科大", "臺中科大", "ntcust", "ntcu"}, (24.1108, 120.6156), "台中科大"),
    ({"西屯"}, (24.1614, 120.6057), "西屯"),
    ({"北屯"}, (24.1826, 120.6865), "北屯"),
    ({"逢甲", "fcu", "fcu.edu"}, (24.1786, 120.6467), "逢甲大學"),
    ({"東海", "thu"}, (24.1810, 120.6030), "東海大學"),
    ({"中興", "nchu"}, (24.1210, 120.6768), "中興大學"),
    ({"中國醫", "cmuh", "中醫大"}, (24.1495, 120.6845), "中國醫藥大學"),
    ({"台中車站", "臺中車站", "台中火車站", "中區"}, (24.1370, 120.6868), "台中車站"),
    ({"新光三越", "中港", "老虎城"}, (24.1650, 120.6390), "新光三越/老虎城"),
    ({"勤美", "草悟道", "國美館", "西區"}, (24.1423, 120.6630), "勤美/草悟道"),
]

# Thresholds
# v2 (2026-06-09, per user feedback): drop "bring umbrella / wear jacket /
# drink water" chatter. AQI is the primary deliverable — lower the trigger so the
# snapshot lands before the event, not only at AQI>=100. Thunderstorm stays as a
# real hazard (factual, not naggy).
# v2.1 (2026-06-09 23:13, user 改回來): AQI >= 100 / >= 150 重新附上
# 「建議戴口罩/減少戶外」勸告。AQI 50 info 仍只給數字不建議。
AQI_INFO = 50             # >= 50   → info-only AQI snapshot (numbers, no advice)
AQI_UNHEALTHY_SENS = 100  # >= 100  → mask emoji + 建議戴口罩/減少戶外
AQI_UNHEALTHY = 150       # >= 150  → warning emoji + 建議戴口罩/減少戶外
DEDUP_HOURS = 24          # same (event_id, warning_type) within 24h → skip

# Weather codes (WMO) we care about for severe weather
# https://open-meteo.com/en/docs
WMO_SEVERE = {95, 96, 99}  # thunderstorm


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr)


def http_get_json(url: str, timeout: int = 20) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-cal-watch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8-sig"))


def taipei_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def in_quiet_hours(now: datetime) -> bool:
    h = now.hour
    if QUIET_START_HOUR > QUIET_END_HOUR:
        return h >= QUIET_START_HOUR or h < QUIET_END_HOUR
    return QUIET_END_HOUR <= h < QUIET_START_HOUR


# --------------------------------------------------------------------------- #
# Google Calendar
# --------------------------------------------------------------------------- #

def fetch_calendar_events(time_min_iso: str, time_max_iso: str) -> list[dict[str, Any]]:
    """Read events from Google Calendar using the same OAuth file as the MCP server."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    data = json.loads(GOOGLE_CAL_SECRETS.read_text(encoding="utf-8"))
    creds = Credentials(
        token=None,
        refresh_token=data["refresh_token"],
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data.get("scopes", ["https://www.googleapis.com/auth/calendar.readonly"]),
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            maxResults=50,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = result.get("items", [])

    out: list[dict[str, Any]] = []
    for ev in items:
        if ev.get("status") == "cancelled":
            continue
        start = ev.get("start", {}) or {}
        end = ev.get("end", {}) or {}
        all_day = "date" in start and "dateTime" not in start
        if all_day:
            continue  # skip all-day events (birthday reminders etc)
        out.append({
            "id": ev.get("id"),
            "summary": ev.get("summary", "(no title)"),
            "location": ev.get("location"),
            "start": start.get("dateTime"),
            "end": end.get("dateTime"),
            "htmlLink": ev.get("htmlLink"),
            "hangoutLink": (ev.get("hangoutLink") or None),
        })
    return out


# --------------------------------------------------------------------------- #
# AQI
# --------------------------------------------------------------------------- #

def fetch_aqi_all() -> list[dict[str, Any]]:
    api_key = json.loads(MOENV_SECRETS.read_text(encoding="utf-8"))["moenv_api_key"]
    url = (
        f"https://data.moenv.gov.tw/api/v2/aqx_p_432"
        f"?api_key={api_key}&limit=1000&format=JSON"
    )
    data = http_get_json(url)
    records = data["value"] if isinstance(data, dict) and "value" in data else data
    # cache raw
    try:
        RAW_AQI_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"warn: could not cache aqi raw: {e}")
    return records


def to_float(v: Any) -> float | None:
    try:
        s = str(v).strip()
        return float(s) if s else None
    except (ValueError, TypeError):
        return None


def nearest_station(records: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    """Pick nearest station by simple lat/lon (EPA exposes lat/lon in newer datasets)."""
    def d(rec: dict[str, Any]) -> float:
        try:
            return ((float(rec.get("latitude", 0)) - lat) ** 2 +
                    (float(rec.get("longitude", 0)) - lon) ** 2) ** 0.5
        except Exception:
            return 9999.0
    valid = [r for r in records if r.get("latitude") and r.get("longitude") and r.get("aqi")]
    if not valid:
        return None
    return min(valid, key=d)


def aqi_summary(records: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    s = nearest_station(records, lat, lon)
    if not s:
        return None
    return {
        "site": s.get("sitename"),
        "county": s.get("county"),
        "aqi": to_float(s.get("aqi")),
        "pm25": to_float(s.get("pm2.5")),
        "pm25_avg": to_float(s.get("pm2.5_avg")),
        "status": s.get("status"),
        "publish": s.get("publishtime"),
    }


# --------------------------------------------------------------------------- #
# Weather (Open-Meteo, no key required)
# --------------------------------------------------------------------------- #

def fetch_weather_forecast(lat: float, lon: float) -> dict[str, Any] | None:
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code,precipitation",
        "forecast_days": 2,
        "timezone": "Asia/Taipei",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    try:
        return http_get_json(url)
    except Exception as e:
        log(f"warn: open-meteo failed: {e}")
        return None


def weather_at(forecast: dict[str, Any], iso_dt: str) -> dict[str, Any] | None:
    """Extract the hourly forecast slice closest to iso_dt (Asia/Taipei)."""
    if not forecast:
        return None
    target = datetime.fromisoformat(iso_dt)
    hourly = forecast.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return None
    # times look like '2026-06-09T15:00' (Asia/Taipei from open-meteo tz=Asia/Taipei)
    best = None
    best_diff = None
    for t in times:
        try:
            d = datetime.fromisoformat(t)
        except ValueError:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=target.tzinfo)
        diff = abs((d - target).total_seconds())
        if best is None or diff < best_diff:
            best = t
            best_diff = diff
    if best is None:
        return None
    idx = times.index(best)
    return {
        "time": best,
        "temperature_2m": (hourly.get("temperature_2m") or [None])[idx],
        "precipitation_probability": (hourly.get("precipitation_probability") or [None])[idx],
        "weather_code": (hourly.get("weather_code") or [None])[idx],
    }


# --------------------------------------------------------------------------- #
# Location resolution
# --------------------------------------------------------------------------- #

def resolve_location(event: dict[str, Any]) -> tuple[float, float, str]:
    """Return (lat, lon, label) for an event."""
    loc = (event.get("location") or "").strip()
    if loc:
        for keywords, coord, label in LOCATION_KEYWORDS:
            if any(k.lower() in loc.lower() for k in keywords):
                return coord[0], coord[1], label
        # unknown string — keep default but mention
        return DEFAULT_LAT, DEFAULT_LON, f"{loc} → default"
    return DEFAULT_LAT, DEFAULT_LON, DEFAULT_LOCATION_LABEL


# --------------------------------------------------------------------------- #
# Warning decision
# --------------------------------------------------------------------------- #

def decide_warnings(
    event: dict[str, Any],
    aqi: dict[str, Any] | None,
    wx: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Return [(type, message)] for each triggered warning.

    v2 (2026-06-09): drop "bring umbrella / wear jacket / drink water" — the user
    wants factual info, not nagging. Thunderstorm stays as a real hazard.
    v2.1 (2026-06-09 23:13): AQI >= 100 / >= 150 重新加回「建議戴口罩/減少戶外」。
    AQI 50 info 仍只給數字不建議。
    """
    out: list[tuple[str, str]] = []
    summary = event.get("summary", "")
    loc_label = event.get("__loc_label", "")
    when = event.get("start", "")

    # Severe weather (factual, not advice-y)
    if wx:
        code = wx.get("weather_code")
        if code in WMO_SEVERE:
            out.append((
                "thunder",
                f"⛈ {when[11:16]}「{summary}」@ {loc_label}：預報雷雨",
            ))

    # AQI snapshot — primary deliverable
    if aqi and aqi.get("aqi") is not None:
        a = aqi["aqi"]
        site = aqi.get("site") or "?"
        status = aqi.get("status") or ""
        pm25 = aqi.get("pm25")
        pm25_str = f", PM2.5 {pm25:.0f}" if pm25 is not None else ""
        if a >= AQI_UNHEALTHY:        # >= 150
            out.append((
                "aqi_bad",
                f"⚠️ {when[11:16]}「{summary}」@ {loc_label}：AQI {a:.0f}（{status}）@ {site}{pm25_str}\n建議戴口罩/減少戶外",
            ))
        elif a >= AQI_UNHEALTHY_SENS: # >= 100
            out.append((
                "aqi_mid",
                f"😷 {when[11:16]}「{summary}」@ {loc_label}：AQI {a:.0f}（{status}）@ {site}{pm25_str}\n建議戴口罩/減少戶外",
            ))
        elif a >= AQI_INFO:           # >= 50 — info-only, no advice
            out.append((
                "aqi_info",
                f"🌫 {when[11:16]}「{summary}」@ {loc_label}：AQI {a:.0f}（{status}）@ {site}{pm25_str}",
            ))

    return out


# --------------------------------------------------------------------------- #
# State & dedup
# --------------------------------------------------------------------------- #

def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"warn: state file corrupt, ignoring: {e}")
    return {"version": 1, "sent": {}, "updated_at": None}


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Prune entries older than 7 days
    cutoff = int(datetime.now(timezone.utc).timestamp()) - 7 * 86400
    pruned: dict[str, dict[str, int]] = {}
    for ev_id, types in state.get("sent", {}).items():
        pruned[ev_id] = {t: ts for t, ts in types.items() if ts >= cutoff}
    state["sent"] = pruned
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def should_send(state: dict[str, Any], event_id: str, warn_type: str) -> bool:
    sent = state.get("sent", {}).get(event_id, {})
    last_ts = sent.get(warn_type)
    if last_ts is None:
        return True
    age = int(datetime.now(timezone.utc).timestamp()) - last_ts
    return age > DEDUP_HOURS * 3600


def mark_sent(state: dict[str, Any], event_id: str, warn_type: str) -> None:
    state.setdefault("sent", {}).setdefault(event_id, {})[warn_type] = int(
        datetime.now(timezone.utc).timestamp()
    )


# --------------------------------------------------------------------------- #
# Telegram delivery
# --------------------------------------------------------------------------- #

def send_telegram(message: str, dry_run: bool) -> bool:
    if dry_run:
        log(f"[dry-run] would send to telegram {TG_TARGET}: {message[:80]}…")
        return True
    # Locate the openclaw executable (PATH may be minimal in cron env on Windows)
    import shutil
    oc = shutil.which("openclaw")
    if not oc:
        # Try the npm-global shim location
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "npm" / "openclaw.cmd",
            Path(os.environ.get("APPDATA", "")) / "npm" / "openclaw.ps1",
            Path(os.environ.get("APPDATA", "")) / "npm" / "openclaw",
        ]
        for c in candidates:
            if c.exists():
                oc = str(c)
                break
    if not oc:
        log("ERROR: openclaw executable not found in PATH or %APPDATA%\\npm")
        return False
    try:
        result = subprocess.run(
            [oc, "message", "send",
             "--channel", TG_CHANNEL,
             "--target", TG_TARGET,
             "--message", message],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode != 0:
            log(f"openclaw message send failed (rc={result.returncode}): {result.stderr.strip()[:200]}")
            return False
        log(f"sent: {message[:60]}…")
        return True
    except Exception as e:
        log(f"openclaw message send exception: {e}")
        return False


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="don't actually send telegram")
    ap.add_argument("--window", type=int, default=DEFAULT_LOOKAHEAD_HOURS,
                    help=f"lookahead hours (default {DEFAULT_LOOKAHEAD_HOURS})")
    ap.add_argument("--force", action="store_true", help="ignore quiet hours")
    args = ap.parse_args()

    now = taipei_now()
    if in_quiet_hours(now) and not args.force:
        log(f"quiet hours ({QUIET_START_HOUR:02d}:00-{QUIET_END_HOUR:02d}:00), skipping")
        return 0

    time_min = now.isoformat()
    time_max = (now + timedelta(hours=args.window)).isoformat()

    log(f"window: {time_min} → {time_max} ({args.window}h)")

    # 1) Calendar
    try:
        events = fetch_calendar_events(time_min, time_max)
        log(f"events: {len(events)}")
    except Exception as e:
        log(f"ERROR fetching calendar: {e}")
        return 1

    if not events:
        log("no events in window; nothing to do")
        return 0

    # 2) AQI
    try:
        aqi_records = fetch_aqi_all()
        log(f"aqi stations: {len(aqi_records)}")
    except Exception as e:
        log(f"ERROR fetching AQI: {e}")
        aqi_records = []

    # 3) For each event, fetch weather + decide
    state = load_state()
    triggered = 0
    sent = 0

    for ev in events:
        lat, lon, label = resolve_location(ev)
        ev["__loc_label"] = label

        aqi = aqi_summary(aqi_records, lat, lon) if aqi_records else None
        forecast = fetch_weather_forecast(lat, lon)
        wx = weather_at(forecast, ev["start"]) if forecast else None

        warnings = decide_warnings(ev, aqi, wx)
        if not warnings:
            log(f"  - {ev['start'][11:16]} {ev['summary'][:30]} @ {label}: clean")
            continue

        log(f"  - {ev['start'][11:16]} {ev['summary'][:30]} @ {label}: {len(warnings)} candidate")
        for warn_type, msg in warnings:
            if not should_send(state, ev["id"], warn_type):
                log(f"      dedup skip: {warn_type}")
                continue
            if args.dry_run:
                # In dry-run, print the would-be message to stdout (utf-8) so user can verify
                print(f"[DRY-RUN] {msg}", flush=True)
            triggered += 1
            ok = send_telegram(msg, args.dry_run)
            if ok:
                mark_sent(state, ev["id"], warn_type)
                sent += 1

    save_state(state)
    log(f"done: {triggered} new warnings triggered, {sent} sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
