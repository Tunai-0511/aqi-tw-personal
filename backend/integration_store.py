"""Supabase-backed storage for public messaging integrations.

The service-role key is used only by the backend.  A deliberately small
in-memory implementation is available in INTEGRATION_DEV_MODE so the complete
UI can be exercised locally before a Supabase project is configured.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any
import requests

from .config import settings


class IntegrationStoreError(RuntimeError):
    pass


class IntegrationStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._integrations: dict[tuple[str, str], dict[str, Any]] = {}

    @property
    def configured(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_service_role_key)

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method: str, table: str, *, params=None, payload=None, prefer=None):
        if not self.configured:
            raise IntegrationStoreError("Supabase service role 尚未設定")
        response = requests.request(
            method,
            f"{settings.supabase_url}/rest/v1/{table}",
            params=params,
            json=payload,
            headers=self._headers(prefer=prefer),
            timeout=12,
        )
        if response.status_code >= 400:
            raise IntegrationStoreError(f"Supabase {response.status_code}: {response.text[:300]}")
        if not response.content:
            return None
        return response.json()

    def list_integrations(self, user_id: str) -> list[dict[str, Any]]:
        if self.configured:
            rows = self._request(
                "GET", "agent_integrations",
                params={"user_id": f"eq.{user_id}", "select": "*", "order": "platform.asc"},
            )
            return rows or []
        self._require_dev()
        with self._lock:
            return [dict(row) for (uid, _), row in self._integrations.items() if uid == user_id]

    def upsert_integration(self, user_id: str, platform: str, **values: Any) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "user_id": user_id,
            "platform": platform,
            "status": values.pop("status", "connected"),
            "updated_at": now,
            **values,
        }
        if self.configured:
            rows = self._request(
                "POST", "agent_integrations",
                params={"on_conflict": "user_id,platform"},
                payload=row,
                prefer="resolution=merge-duplicates,return=representation",
            )
            return (rows or [row])[0]
        self._require_dev()
        with self._lock:
            previous = self._integrations.get((user_id, platform), {})
            row = {**previous, **row, "created_at": previous.get("created_at", now)}
            self._integrations[(user_id, platform)] = row
            return dict(row)

    def delete_integration(self, user_id: str, platform: str) -> None:
        if self.configured:
            self._request(
                "DELETE", "agent_integrations",
                params={"user_id": f"eq.{user_id}", "platform": f"eq.{platform}"},
            )
            return
        self._require_dev()
        with self._lock:
            self._integrations.pop((user_id, platform), None)

    @staticmethod
    def _require_dev() -> None:
        if not settings.integration_dev_mode:
            raise IntegrationStoreError("Supabase 尚未設定；本機測試可設 INTEGRATION_DEV_MODE=1")


store = IntegrationStore()
