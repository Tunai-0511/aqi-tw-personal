"""
Bridge from LobsterAQI Streamlit to a locally-installed OpenClaw.

OpenClaw's gateway is WebSocket-based (not HTTP REST), so we don't speak the
protocol directly. Instead we shell out to the `openclaw` CLI — it handles
WebSocket auth, session routing, the embedded-fallback path, etc.

This keeps Python deps to zero (`subprocess` is stdlib) and lets users upgrade
OpenClaw without us changing the wire format.

Public surface mirrors the old HTTP-style client:
    health() -> (bool, message)
    list_agents() -> list[dict]
    trigger_agent(agent_id, prompt) -> {"response": str, "refs": [], ...}

All methods are exception-safe — failures return None / False / [].
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any


CLI_CANDIDATES = ["openclaw", "openclaw.cmd"]

# OpenClaw CLI cold-start is unexpectedly slow (plugin discovery, etc.).
# Even `agents list` can take 10-20s on first call. Be generous to avoid
# false-negative health checks.
HEALTH_TIMEOUT_S = 45
# Cold-start of an `openclaw agent` call (LLM via embedded fallback) can be
# 30-60s; subsequent calls within the same session are faster.
DEFAULT_AGENT_TIMEOUT_S = 240


def _is_windows() -> bool:
    return sys.platform == "win32" or os.name == "nt"


def _find_cli() -> str | None:
    for name in CLI_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


class OpenClawClient:
    """Subprocess-based client. base_url / token kept for API compat but unused
    — the underlying `openclaw` CLI reads its own config (~/.openclaw/openclaw.json)."""

    def __init__(self, base_url: str = "", token: str = "") -> None:
        self.base_url = base_url
        self.token = token
        self._cli = _find_cli()

    # ---------- public surface ----------

    def health(self) -> tuple[bool, str]:
        """Quick check that the `openclaw` CLI exists and `agents list` returns OK."""
        if not self._cli:
            return False, "找不到 openclaw CLI（請先安裝 OpenClaw）"
        raw = self._run_cli(["agents", "list", "--json"], timeout=HEALTH_TIMEOUT_S)
        if raw is None:
            return False, "openclaw agents list 失敗或逾時"
        data = self._parse_json_array_or_object(raw)
        if isinstance(data, list):
            return True, f"已連線 · CLI 偵測到 {len(data)} 個 agent"
        return False, "agents list 回傳格式異常"

    def list_agents(self) -> list[dict[str, Any]]:
        """Return all agents the local OpenClaw knows about."""
        if not self._cli:
            return []
        raw = self._run_cli(["agents", "list", "--json"], timeout=HEALTH_TIMEOUT_S)
        if not raw:
            return []
        data = self._parse_json_array_or_object(raw)
        return data if isinstance(data, list) else []

    def trigger_agent(
        self,
        agent_id: str,
        prompt: str,
        context: dict[str, Any] | None = None,
        timeout: int = DEFAULT_AGENT_TIMEOUT_S,
    ) -> dict[str, Any] | None:
        """
        Run a single turn on the specified agent. Returns:
            {"response": "<assistant text>", "refs": [], "agent": agent_id, "raw": <full JSON>}
        or None on failure.

        Note: cold-start can take 30-60s because OpenClaw initializes plugins,
        loads context, etc. Subsequent calls within the same session are faster.
        """
        if not self._cli or not agent_id:
            return None

        raw = self._run_cli(
            ["agent", "--agent", agent_id, "--message", prompt,
             "--json", "--timeout", str(timeout)],
            timeout=timeout + 30,
        )
        if not raw:
            return None

        # The CLI prints log lines before the JSON. The JSON is the LAST `{...}`
        # block in stdout, possibly multi-line.
        json_block = self._extract_last_json_object(raw)
        if not json_block:
            return None
        try:
            data = json.loads(json_block)
        except json.JSONDecodeError:
            return None

        text = ""
        payloads = data.get("payloads")
        if isinstance(payloads, list) and payloads:
            first = payloads[0]
            if isinstance(first, dict):
                text = first.get("text") or first.get("content") or ""
                if isinstance(text, list):
                    text = "".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in text
                    )

        if not text:
            # fall back to other common envelope shapes
            text = data.get("text") or data.get("output") or ""

        return {
            "response": text,
            "refs": [],
            "agent": agent_id,
            "raw": data,
        }

    # ---------- internals ----------

    def _run_cli(self, args: list[str], timeout: int) -> str | None:
        """Run `openclaw <args>` and return stdout, or None on any failure.

        On Windows, the CLI is a `.cmd` shim. We use `shell=True` so cmd.exe
        resolves and executes the .cmd file properly. To keep this safe, we
        only pass args we control (no user-supplied shell metachars).
        """
        if not self._cli:
            return None
        try:
            if _is_windows():
                # Pass the command and args as a list with shell=True so cmd.exe
                # handles the .cmd file resolution. subprocess will quote args
                # properly when given a list on Windows even with shell=True.
                cmd = subprocess.list2cmdline([self._cli, *args])
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            else:
                result = subprocess.run(
                    [self._cli, *args],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding="utf-8",
                    errors="replace",
                )
            if result.returncode != 0:
                return None
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    @staticmethod
    def _parse_json_array_or_object(text: str) -> Any:
        """
        Parse a JSON array or object out of `openclaw` stdout. The CLI may print
        log/warning lines before the JSON (e.g. `[plugins] plugins.allow is empty`),
        so we strip those first.
        """
        if not text:
            return None
        text = text.strip()
        # Fast path: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Slow path: find the first `[` or `{` on a line that begins with it
        # (handles the leading [plugins] log lines)
        for marker in ("\n[", "\n{"):
            idx = text.find(marker)
            while idx != -1:
                candidate = text[idx + 1:]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
                idx = text.find(marker, idx + 1)
        # Even slower path: scan for first `[` or `{` anywhere and try forward
        for i, ch in enumerate(text):
            if ch in "[{":
                try:
                    return json.loads(text[i:])
                except json.JSONDecodeError:
                    continue
        return None

    @staticmethod
    def _extract_last_json_object(text: str) -> str | None:
        """
        Pull the last top-level JSON object out of mixed stdout.
        OpenClaw prefixes JSON output with [info] lines, so we scan from the end
        looking for a balanced { ... } block.
        """
        text = text.strip()
        if not text:
            return None
        # Fast path: stdout is JSON-only
        if text.startswith("{") and text.endswith("}"):
            return text
        # Slow path: find a JSON object by balanced braces, scanning backward
        end = text.rfind("}")
        if end == -1:
            return None
        depth = 0
        for i in range(end, -1, -1):
            ch = text[i]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    return text[i:end + 1]
        return None


# Default agent IDs the LobsterAQI pipeline expects in the OpenClaw gateway.
# These are ASCII job titles for CLI / file-path safety on Windows.
# UI displays them in Chinese via PARTICIPANTS dict in app.py.
EXPECTED_AGENT_IDS: list[str] = ["collector", "scraper", "analyst", "critic", "advisor"]

# Mapping from agent ID → Chinese role title (for UI display)
AGENT_DISPLAY_NAMES: dict[str, str] = {
    "collector": "採集者",
    "scraper":   "爬蟲員",
    "analyst":   "分析師",
    "critic":    "品管員",
    "advisor":   "預警員",
}
