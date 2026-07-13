"""Narrow, non-interactive Hermes profile provisioner.

No user input is ever interpolated into a shell string. Profile names are
derived from a SHA-256 digest and subprocesses run without shell=True.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass

from .config import settings


@dataclass(frozen=True)
class ProvisionResult:
    profile: str
    status: str
    detail: str


def profile_name(user_id: str) -> str:
    return f"aqi-{hashlib.sha256(user_id.encode('utf-8')).hexdigest()[:16]}"


def provision_profile(user_id: str) -> ProvisionResult:
    name = profile_name(user_id)
    mode = settings.hermes_provision_mode
    if mode == "disabled":
        return ProvisionResult(name, "connected", "Hermes 自動佈建尚未啟用")
    if mode not in {"cli", "docker"}:
        return ProvisionResult(name, "error", f"不支援的 HERMES_PROVISION_MODE：{mode}")

    base = [settings.hermes_cli]
    if mode == "docker":
        base = ["docker", "exec", settings.hermes_container, settings.hermes_cli]
    command = [*base, "profile", "create", name]
    if settings.hermes_template_profile:
        command.extend(["--clone-from", settings.hermes_template_profile])
    else:
        command.append("--clone")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.hermes_provision_timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ProvisionResult(name, "error", f"Hermes 佈建失敗：{exc}")

    output = (completed.stdout or completed.stderr or "").strip()[-500:]
    if completed.returncode == 0:
        return ProvisionResult(name, "ready", output or "Hermes Profile 已建立")
    if "already exists" in output.lower() or "已存在" in output:
        return ProvisionResult(name, "ready", "Hermes Profile 已存在")
    return ProvisionResult(name, "error", output or f"Hermes CLI 結束碼 {completed.returncode}")
