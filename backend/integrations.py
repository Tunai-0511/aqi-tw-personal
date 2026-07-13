"""Discord account linking and Hermes provisioning API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Literal
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .config import settings
from .hermes_control import provision_profile
from .hermes_client import HermesAPIError, ask_hermes
from .integration_auth import AuthUser, current_user
from .integration_store import IntegrationStoreError, store


router = APIRouter(prefix="/api/integrations", tags=["integrations"])
class HermesMessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


def _public_status(row: dict) -> dict:
    return {
        key: row.get(key)
        for key in (
            "platform", "status", "platform_user_name", "platform_space_name",
            "hermes_profile", "provision_detail", "created_at", "updated_at",
        )
    }


def _state_secret() -> bytes:
    secret = settings.integration_state_secret
    if not secret and settings.integration_dev_mode:
        secret = "local-development-only-state-secret"
    if len(secret) < 24:
        raise HTTPException(status_code=503, detail="INTEGRATION_STATE_SECRET 尚未安全設定")
    return secret.encode("utf-8")


def _make_state(user_id: str) -> str:
    payload = json.dumps(
        {"sub": user_id, "iat": int(time.time()), "nonce": secrets.token_urlsafe(10)},
        separators=(",", ":"),
    ).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(_state_secret(), body, hashlib.sha256).digest()
    return f"{body.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _read_state(value: str) -> str:
    try:
        body_text, signature_text = value.split(".", 1)
        body = body_text.encode("ascii")
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        expected = hmac.new(_state_secret(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4)))
        if int(time.time()) - int(payload["iat"]) > 600:
            raise ValueError("expired")
        return str(payload["sub"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Discord 授權狀態無效或已過期") from exc


def _provision_and_record(user_id: str, platform: str) -> None:
    result = provision_profile(user_id)
    try:
        store.upsert_integration(
            user_id,
            platform,
            status=result.status,
            hermes_profile=result.profile,
            provision_detail=result.detail,
        )
    except IntegrationStoreError:
        return


@router.get("/config")
def integration_config() -> dict:
    return {
        "enabled": store.configured or settings.integration_dev_mode,
        "auth_enabled": bool(settings.supabase_url and settings.supabase_anon_key),
        "dev_mode": settings.integration_dev_mode,
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
        "discord_enabled": bool(settings.discord_client_id and settings.discord_client_secret),
        "hermes_mode": settings.hermes_provision_mode,
    }


@router.get("")
def list_integrations(user: AuthUser = Depends(current_user)) -> dict:
    try:
        rows = store.list_integrations(user.id)
    except IntegrationStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    mapped = {row["platform"]: _public_status(row) for row in rows}
    return {"integrations": mapped}


@router.post("/discord/connect")
def discord_connect(user: AuthUser = Depends(current_user)) -> dict:
    if not settings.discord_client_id or not settings.discord_client_secret:
        raise HTTPException(status_code=503, detail="Discord OAuth 尚未設定")
    query = urlencode({
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify guilds bot applications.commands",
        "permissions": settings.discord_permissions,
        "state": _make_state(user.id),
        "prompt": "consent",
    })
    return {"authorization_url": f"https://discord.com/oauth2/authorize?{query}"}


@router.get("/discord/callback")
def discord_callback(
    background_tasks: BackgroundTasks,
    code: str = Query(min_length=3),
    state: str = Query(min_length=20),
    guild_id: str | None = None,
):
    user_id = _read_state(state)
    token_response = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": settings.discord_client_id,
            "client_secret": settings.discord_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.discord_redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=12,
    )
    if token_response.status_code >= 400:
        raise HTTPException(status_code=400, detail="Discord 授權交換失敗")
    token = token_response.json().get("access_token")
    identity = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {token}"}, timeout=10,
    )
    if identity.status_code != 200:
        raise HTTPException(status_code=400, detail="無法取得 Discord 使用者資料")
    discord_user = identity.json()
    try:
        store.upsert_integration(
            user_id,
            "discord",
            status="provisioning",
            platform_user_id=str(discord_user["id"]),
            platform_user_name=str(discord_user.get("global_name") or discord_user.get("username") or "Discord user"),
            platform_space_id=guild_id,
            platform_space_name="Discord Server" if guild_id else "Direct Message",
            metadata={"scope": token_response.json().get("scope", "")},
        )
    except IntegrationStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    background_tasks.add_task(_provision_and_record, user_id, "discord")
    return RedirectResponse(f"{settings.public_app_url}/integrations.html?connected=discord", status_code=303)


@router.post("/hermes/chat")
def hermes_chat(body: HermesMessageIn, user: AuthUser = Depends(current_user)) -> dict:
    try:
        return {"answer": ask_hermes(user.id, body.message, channel="web")}
    except HermesAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/discord/demo-connect")
def discord_demo_connect(
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(current_user),
) -> dict:
    if not settings.integration_dev_mode:
        raise HTTPException(status_code=404, detail="Not found")
    store.upsert_integration(
        user.id, "discord", status="provisioning",
        platform_user_id=f"discord-{user.id}", platform_user_name="本機 Discord 測試者",
        platform_space_name="Discord Demo",
    )
    background_tasks.add_task(_provision_and_record, user.id, "discord")
    return {"ok": True}


@router.delete("/{platform}")
def disconnect(
    platform: Literal["discord"],
    user: AuthUser = Depends(current_user),
) -> dict:
    try:
        store.delete_integration(user.id, platform)
    except IntegrationStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{platform}/provision")
def retry_provision(
    platform: Literal["discord"],
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(current_user),
) -> dict:
    rows = store.list_integrations(user.id)
    if not any(row.get("platform") == platform for row in rows):
        raise HTTPException(status_code=404, detail="請先完成平台綁定")
    store.upsert_integration(user.id, platform, status="provisioning")
    background_tasks.add_task(_provision_and_record, user.id, platform)
    return {"ok": True, "status": "provisioning"}
