"""
oauth_calendar_write.py — One-time OAuth consent to get calendar.events scope.

Reuses client_id / client_secret from the existing read-only google-cal.json
(which backs the calendar MCP server — leave it alone!).

This script writes a NEW file: google-cal-write.json. The original is untouched
so the read-only MCP server keeps working.

Run once:
    python scripts\\oauth_calendar_write.py

It will:
  1. Open default browser to Google consent screen
  2. You log in + grant "Make changes to events" (calendar.events)
  3. Token is saved to C:\\Users\\.openclaw\\secrets\\google-cal-write.json

After this, you can use this file to insert/modify events via Google Calendar API.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Force utf-8 (Windows cp950/cp936 safe)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
SECRETS_PATH = Path(r"C:\Users\User\.openclaw\secrets\google-cal.json")
OUT_PATH = Path(r"C:\Users\User\.openclaw\secrets\google-cal-write.json")
PORT = 8089  # local HTTP server port (must be free)


def main() -> int:
    base = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    if not (base.get("client_id") and base.get("client_secret")):
        print("ERROR: google-cal.json missing client_id/client_secret", file=sys.stderr)
        return 1

    # Build a client_secrets-style dict for InstalledAppFlow
    client_config = {
        "installed": {
            "client_id": base["client_id"],
            "client_secret": base["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": base.get("token_uri", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # prompt="consent" forces the consent screen so we get a refresh_token
    # (otherwise Google may issue only an access_token for already-granted scopes)
    creds = flow.run_local_server(port=PORT, prompt="consent", open_browser=True)

    if not creds.refresh_token:
        print("ERROR: no refresh_token returned. Try again with prompt='consent'.",
              file=sys.stderr)
        return 1

    out = {
        "type": "authorized_user",
        "client_id": base["client_id"],
        "client_secret": base["client_secret"],
        "refresh_token": creds.refresh_token,
        "token_uri": base.get("token_uri", "https://oauth2.googleapis.com/token"),
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # Tighten ACL on Windows (best-effort, ignore if not on Windows)
    try:
        import subprocess
        subprocess.run(
            ["icacls", str(OUT_PATH), "/inheritance:r",
             "/grant:r", f"{__import__('os').getlogin()}:F", "SYSTEM:F", "Administrators:F"],
            check=False, capture_output=True,
        )
    except Exception:
        pass

    print(f"OK: wrote {OUT_PATH}")
    print(f"scopes:        {out['scopes']}")
    print(f"refresh_token: {out['refresh_token'][:12]}…  ({len(out['refresh_token'])} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
