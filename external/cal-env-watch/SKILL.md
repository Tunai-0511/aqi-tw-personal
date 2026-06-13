---
name: cal-env-watch
description: Calendar × Weather × AQI proactive warning system for Telegram, with batch class-schedule insertion into Google Calendar. Use when Codex needs to (1) run or modify the `cal_env_watch` cron/script that warns about AQI/thunderstorm before upcoming Google Calendar events, (2) read the Google Calendar via the read-only MCP server (`calendar__list_*` tools), (3) batch-insert recurring weekly class schedules (or similar templates) into Google Calendar, or (4) handle the OAuth flow to get `calendar.events` write scope. Triggers: "cal_env_watch", "行程預警", "AQI 預警", "課表排入", "課表匯入", "Google Calendar 寫入", "calendar.events scope", "行事曆批次新增", "週課表", "recurring events".
---

# Cal Env Watch

Proactive warning system that pairs a user's Google Calendar with environmental data
(AQI from EPA / Open-Meteo weather) and pushes Telegram alerts before at-risk events.
Also bundles the write-side tools for batch-inserting recurring class schedules.

## When to use

Use this skill when the user asks about:

- **Running or modifying `cal_env_watch.py`** (the main watcher — see `scripts/cal_env_watch.py`)
- **Why a warning fired (or didn't)** — check thresholds, dedup state, location resolution
- **Adding a new class to the schedule** — `scripts/insert_class_schedule.py` template
- **Setting up write access to Google Calendar** — `scripts/oauth_calendar_write.py`
- **Reading calendar via MCP** — `scripts/calendar-mcp-server.py` exposes
  `calendar__list_today_events` / `calendar__list_tomorrow_events` /
  `calendar__list_day_events` / `calendar__list_events` / `calendar__get_event` tools

## Architecture

```
                    ┌─────────────────────────┐
                    │  Google Calendar (REST) │
                    └────────────┬────────────┘
                                 │ read (MCP)
                                 │
                    ┌────────────┴────────────┐
   heartbeat / cron │  cal_env_watch.py       │  outputs → Telegram
   ────────────────▶│  • 6h window scan       │──────────────────────▶
                    │  • AQI + weather lookup │
                    │  • threshold + dedup    │
                    │  • send or skip         │
                    └─────────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
      EPA AQI API          Open-Meteo          openclaw message
      (MOENV key)          (no key)            send --telegram
```

## Quick start (read side)

Read-only calendar access is already exposed via the `calendar__*` MCP tools. To use
in a script:

```python
from googleapiclient.discovery import build
# Calendar MCP server script: scripts/calendar-mcp-server.py
# Secrets: C:\Users\User\.openclaw\secrets\google-cal.json
# Scope:   https://www.googleapis.com/auth/calendar.readonly
```

## Quick start (write side)

To insert or modify events, you need `calendar.events` scope. The read-only token
in `google-cal.json` is bound to `calendar.readonly` only — do NOT add the new
scope to that file or the existing MCP server will need a re-consent.

**One-time setup** (5 seconds of user action):

```powershell
python scripts\oauth_calendar_write.py
```

This opens the browser, the user logs in, and a new file
`C:\Users\User\.openclaw\secrets\google-cal-write.json` is created with the
`calendar.events` refresh token. The original `google-cal.json` is untouched.

**Batch-insert a class schedule** (see `scripts/insert_class_schedule.py` for the
full template):

```powershell
# Preview
python scripts\insert_class_schedule.py --dry-run
# Execute
python scripts\insert_class_schedule.py
```

## Running the watcher

**Manual run**:

```powershell
python scripts\cal_env_watch.py              # 6h window, quiet hours respected
python scripts\cal_env_watch.py --window 12 # 12h window
python scripts\cal_env_watch.py --dry-run   # don't send to Telegram
python scripts\cal_env_watch.py --force     # ignore quiet hours (23:00-06:00)
```

**Cron** (recommended — runs every 30 min, 06:00-22:59 Asia/Taipei):

- session: `isolated` + `lightContext`
- delivery: `mode: none` (script sends its own Telegram)
- prompt: tell the agent "just run one python line and paste the result"

## Thresholds & policy

| Condition | Threshold | Telegram message | Notes |
|---|---|---|---|
| AQI | ≥ 50 | 🌫 info (numbers only, no advice) | Lower trigger so snapshot arrives before event |
| AQI | ≥ 100 | 😷 + `建議戴口罩/減少戶外` | Health-specific advice is OK |
| AQI | ≥ 150 | ⚠️ + `建議戴口罩/減少戶外` | Same advice, higher urgency emoji |
| Weather code | 95–99 | ⛈ factual only (no "改期/室內") | Real hazard, factual tone |
| ~~rain prob ≥ 30%~~ | — | — | Removed: user dislikes umbrella nagging |
| ~~temp ≥ 33°C~~ | — | — | Removed: user dislikes "多喝水" nagging |
| ~~temp ≤ 12°C~~ | — | — | Removed: user dislikes jacket nagging |

Dedup: same `(event_id, warning_type)` is suppressed for 24h. State file:
`memory/cal-warn-state.json`.

## Location resolution

`cal_env_watch.py` matches the event `location` field against a keyword set:

| Keywords | Lat / Lon | Label |
|---|---|---|
| 中科大 / 中臺 / 台中科大 / 臺中科大 / ntcust / ntcu | 24.1108, 120.6156 | 台中科大 |
| 西屯 | 24.1614, 120.6057 | 西屯 |
| 北屯 | 24.1826, 120.6865 | 北屯 |
| 逢甲 / fcu | 24.1786, 120.6467 | 逢甲大學 |
| 東海 / thu | 24.1810, 120.6030 | 東海大學 |
| 中興 / nchu | 24.1210, 120.6768 | 中興大學 |
| 中國醫 / cmuh | 24.1495, 120.6845 | 中國醫藥大學 |
| 台中車站 / 中區 | 24.1370, 120.6868 | 台中車站 |
| 新光三越 / 中港 / 老虎城 | 24.1650, 120.6390 | 新光三越/老虎城 |
| 勤美 / 草悟道 / 國美館 / 西區 | 24.1423, 120.6630 | 勤美/草悟道 |

Default: 台中中區 (24.1469, 120.6476).

**Tip**: when inserting class events, set `location` to
`"臺中科技大學 (台中科大) 教室XXXX"` — the `"台中科大"` substring matches the
keyword set automatically.

## Secrets layout

| File | Scope | Used by | Notes |
|---|---|---|---|
| `secrets/google-cal.json` | `calendar.readonly` | `calendar-mcp-server.py`, `cal_env_watch.py` | Read-only refresh token. Do NOT add write scope here. |
| `secrets/google-cal-write.json` | `calendar.events` | `insert_class_schedule.py`, manual inserts | Created by `oauth_calendar_write.py`. |
| `secrets/moenv.json` | n/a (file-based) | `cal_env_watch.py` (AQI API) | Has `moenv_api_key` field. Provider: `moenvfile`. |

ACL on these files should be locked down (`icacls /inheritance:r`). For
non-OpenClaw credential surfaces, scripts read the file directly.

## Known pitfalls

See [references/pitfalls.md](references/pitfalls.md) for full list. Top three:

1. **Cron PATH**: cron environment may not have npm-global in PATH. The script
   uses `shutil.which('openclaw')` first, then falls back to
   `%APPDATA%\npm\openclaw.cmd`.
2. **Emoji encoding**: `subprocess.run` for `openclaw message send` must set
   `encoding='utf-8', errors='replace'` to avoid cp950/cp936 crashes on emoji.
3. **LLM agent on cron**: when using cron + LLM agent, set `--no-deliver` so
   the LLM's prose response is NOT sent as a Telegram message.

## References

- [references/thresholds.md](references/thresholds.md) — full threshold table + version history
- [references/locations.md](references/locations.md) — LOCATION_KEYWORDS + how to add new
- [references/secrets.md](references/secrets.md) — OAuth flow + secret file structure
- [references/pitfalls.md](references/pitfalls.md) — gotchas encountered in production
