"""Authenticate frontend requests with a Supabase access token."""
from __future__ import annotations

from dataclasses import dataclass

import requests
from fastapi import Header, HTTPException

from .config import settings


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str = ""


def current_user(
    authorization: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None),
) -> AuthUser:
    if settings.integration_dev_mode and x_demo_user:
        safe = "".join(ch for ch in x_demo_user if ch.isalnum() or ch in "-_")[:64]
        if safe:
            return AuthUser(id=f"demo-{safe}", email="demo@local.invalid")

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Supabase Auth 尚未設定")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="請先登入")

    token = authorization.split(" ", 1)[1].strip()
    try:
        response = requests.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="暫時無法驗證登入狀態") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="登入已過期，請重新登入")
    data = response.json()
    return AuthUser(id=str(data["id"]), email=str(data.get("email") or ""))
