"""
Google Calendar MCP Server (read-only, stdio transport).

Exposes a handful of read-only tools against Google Calendar v3.
Refresh token is loaded from a JSON file (default: C:\\Users\\User\\.openclaw\\secrets\\google-cal.json).

This server is intentionally minimal: no writes, no event creation, no
deletion. If you need write access, add a separate MCP server with
calendar.events scope.

Environment variables:
  CALENDAR_SECRETS_PATH   path to the OAuth secrets JSON (default above)
  CALENDAR_TIMEZONE       IANA tz name for day boundaries (default: Asia/Taipei)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

# Force utf-8 on Windows consoles (cp950/cp936).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Suppress noisy googleapiclient / google.auth logs on stderr.
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")

DEFAULT_SECRETS_PATH = r"C:\Users\User\.openclaw\secrets\google-cal.json"
DEFAULT_TZ_OFFSET = timedelta(hours=8)  # Asia/Taipei, no DST


def _tz() -> timezone:
    return timezone(DEFAULT_TZ_OFFSET)


def _secrets_path() -> Path:
    return Path(os.environ.get("CALENDAR_SECRETS_PATH", DEFAULT_SECRETS_PATH))


def _load_credentials():  # -> google.oauth2.credentials.Credentials
    from google.oauth2.credentials import Credentials

    p = _secrets_path()
    data = json.loads(p.read_text(encoding="utf-8"))
    return Credentials(
        token=None,
        refresh_token=data["refresh_token"],
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data.get("scopes", ["https://www.googleapis.com/auth/calendar.readonly"]),
    )


def _get_service():
    from googleapiclient.discovery import build
    creds = _load_credentials()
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _day_window(date_str: str) -> tuple[str, str]:
    """Return (timeMin_iso, timeMax_iso) for a single calendar day in Asia/Taipei."""
    day = datetime.strptime(date_str, "%Y-%m-%d").date()
    start = datetime.combine(day, time.min, tzinfo=_tz())
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _simplify_event(ev: dict[str, Any]) -> dict[str, Any]:
    """Strip huge / nested fields; keep what's useful for an LLM digest."""
    start = ev.get("start", {})
    end = ev.get("end", {})
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary", "(no title)"),
        "description": ev.get("description"),
        "location": ev.get("location"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start and "dateTime" not in start,
        "status": ev.get("status"),
        "htmlLink": ev.get("htmlLink"),
        "attendees": [
            a.get("email") for a in (ev.get("attendees") or []) if a.get("email")
        ],
        "organizer": (ev.get("organizer") or {}).get("email"),
        "hangoutLink": ev.get("hangoutLink"),
        "conferenceData": (
            ev.get("conferenceData", {}).get("entryPoints", [])
            if ev.get("conferenceData")
            else None
        ),
    }


# --------------------------------------------------------------------------- #
# MCP server wiring
# --------------------------------------------------------------------------- #

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

app = Server("google-calendar")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_today_events",
            description=(
                "List Google Calendar events for TODAY (Asia/Taipei, 00:00 to 23:59:59). "
                "No parameters required. Returns a JSON array of events."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="list_tomorrow_events",
            description=(
                "List Google Calendar events for TOMORROW (Asia/Taipei, 00:00 to 23:59:59). "
                "No parameters required. Returns a JSON array of events."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="list_day_events",
            description=(
                "List Google Calendar events for a specific day in Asia/Taipei. "
                "date must be in YYYY-MM-DD format."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (Asia/Taipei).",
                    }
                },
                "required": ["date"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="list_events",
            description=(
                "List Google Calendar events in a custom time range. "
                "timeMin/timeMax must be ISO 8601 strings (e.g. 2026-06-10T00:00:00+08:00)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "timeMin": {"type": "string", "description": "ISO 8601 lower bound."},
                    "timeMax": {"type": "string", "description": "ISO 8601 upper bound."},
                    "maxResults": {
                        "type": "integer",
                        "default": 50,
                        "description": "Cap on returned events (default 50, max 250).",
                    },
                    "calendarId": {
                        "type": "string",
                        "default": "primary",
                        "description": "Calendar ID; default 'primary'.",
                    },
                },
                "required": ["timeMin", "timeMax"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_event",
            description="Fetch a single Google Calendar event by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "eventId": {"type": "string", "description": "Event ID from list_events."},
                    "calendarId": {
                        "type": "string",
                        "default": "primary",
                        "description": "Calendar ID; default 'primary'.",
                    },
                },
                "required": ["eventId"],
                "additionalProperties": False,
            },
        ),
    ]


def _call_list_today() -> list[dict[str, Any]]:
    now = datetime.now(_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return _fetch_range(start.isoformat(), end.isoformat())


def _call_list_tomorrow() -> list[dict[str, Any]]:
    now = datetime.now(_tz())
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = tomorrow + timedelta(days=1)
    return _fetch_range(tomorrow.isoformat(), end.isoformat())


def _call_list_day(date_str: str) -> list[dict[str, Any]]:
    tmin, tmax = _day_window(date_str)
    return _fetch_range(tmin, tmax)


def _call_list_range(
    time_min: str, time_max: str, max_results: int = 50, calendar_id: str = "primary"
) -> list[dict[str, Any]]:
    max_results = max(1, min(int(max_results), 250))
    return _fetch_range(time_min, time_max, max_results=max_results, calendar_id=calendar_id)


def _fetch_range(
    time_min: str,
    time_max: str,
    max_results: int = 50,
    calendar_id: str = "primary",
) -> list[dict[str, Any]]:
    service = _get_service()
    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = result.get("items", [])
    return [_simplify_event(e) for e in items]


def _call_get_event(event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
    service = _get_service()
    ev = (
        service.events()
        .get(calendarId=calendar_id, eventId=event_id)
        .execute()
    )
    return _simplify_event(ev)


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "list_today_events":
            payload = _call_list_today()
        elif name == "list_tomorrow_events":
            payload = _call_list_tomorrow()
        elif name == "list_day_events":
            payload = _call_list_day(arguments["date"])
        elif name == "list_events":
            payload = _call_list_range(
                arguments["timeMin"],
                arguments["timeMax"],
                arguments.get("maxResults", 50),
                arguments.get("calendarId", "primary"),
            )
        elif name == "get_event":
            payload = _call_get_event(
                arguments["eventId"],
                arguments.get("calendarId", "primary"),
            )
        else:
            payload = {"error": f"unknown tool: {name}"}
    except Exception as e:  # surface the error to the LLM
        payload = {"error": f"{type(e).__name__}: {e}"}
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
