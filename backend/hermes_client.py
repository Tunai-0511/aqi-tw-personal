"""Small client for the Hermes OpenAI-compatible API server."""
from __future__ import annotations

import hashlib
from typing import Any

import requests

from .config import settings


class HermesAPIError(RuntimeError):
    pass


def _conversation(user_id: str, channel: str) -> str:
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    return f"agentaqi-{channel}-{digest}"


def _extract_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()
    if isinstance(payload.get("response"), str):
        return payload["response"].strip()
    choices = payload.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        if isinstance(message.get("content"), str):
            return message["content"].strip()
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise HermesAPIError("Hermes 回應中沒有可顯示的文字")


def ask_hermes(user_id: str, message: str, *, channel: str = "web") -> str:
    if not settings.hermes_api_key:
        raise HermesAPIError("HERMES_API_KEY 尚未設定")
    response = requests.post(
        f"{settings.hermes_api_url}/v1/responses",
        headers={
            "Authorization": f"Bearer {settings.hermes_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "input": message,
            "conversation": _conversation(user_id, channel),
        },
        timeout=settings.hermes_api_timeout,
    )
    if response.status_code >= 400:
        raise HermesAPIError(f"Hermes API {response.status_code}: {response.text[:240]}")
    return _extract_text(response.json())
