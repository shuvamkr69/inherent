"""Contract tests for CLI identity and local admin visibility endpoints (#275)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.models.api_key import APIKeyInfo
from src.models.identity import APIKeySummary, WhoAmIResponse, WorkspaceSummary
from src.services.auth import get_api_key_info
from src.services.database import get_database

pytestmark = [pytest.mark.contract]


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _user_key() -> APIKeyInfo:
    return APIKeyInfo(
        key_id="key-user",
        user_id="user-1",
        workspace_id=None,
        permissions=["read", "search"],
        rate_limit=100,
        status="active",
    )


async def test_whoami_returns_identity_and_authorized_workspaces(monkeypatch):
    """The endpoint resolves caller identity without leaking other workspaces."""
    import src.api.v1.identity as identity_mod

    monkeypatch.setattr(identity_mod.settings, "version", "9.9.9")
    db = AsyncMock()
    db.get_user_workspace_ids = AsyncMock(return_value=["ws-1"])
    db.get_workspace_summaries = AsyncMock(
        return_value=[WorkspaceSummary(id="ws-1", name="Workspace One", user_id="user-1")]
    )

    app = create_app()
    app.dependency_overrides[get_api_key_info] = _user_key
    app.dependency_overrides[get_database] = lambda: db

    async with _client(app) as client:
        response = await client.get("/v1/whoami", headers={"X-API-Key": "ink_test"})

    assert response.status_code == 200
    body = response.json()
    assert body["key_id"] == "key-user"
    assert body["workspace_id"] is None
    assert body["engine_version"] == "9.9.9"
    assert body["authorized_workspaces"] == [
        {"id": "ws-1", "name": "Workspace One", "user_id": "user-1"}
    ]
    WhoAmIResponse.model_validate(body)
    db.get_workspace_summaries.assert_awaited_once_with(["ws-1"])


async def test_admin_endpoints_are_hidden_when_disabled(single_workspace_db):
    """Disabled admin inventory returns 404, not an authorization hint."""
    app = create_app()
    app.dependency_overrides[get_api_key_info] = _user_key
    app.dependency_overrides[get_database] = lambda: single_workspace_db

    async with _client(app) as client:
        workspaces = await client.get("/v1/admin/workspaces", headers={"X-API-Key": "ink_test"})
        keys = await client.get("/v1/admin/keys", headers={"X-API-Key": "ink_test"})

    assert workspaces.status_code == 404
    assert keys.status_code == 404
    single_workspace_db.list_admin_workspaces.assert_not_called()
    single_workspace_db.list_admin_api_keys.assert_not_called()


async def test_admin_endpoints_return_metadata_when_enabled(monkeypatch):
    """Enabled admin inventory lists metadata only."""
    import src.api.v1.admin as admin_mod

    monkeypatch.setattr(admin_mod.settings, "admin_api_enabled", True)
    db = AsyncMock()
    db.list_admin_workspaces = AsyncMock(
        return_value=[WorkspaceSummary(id="ws-1", name="Workspace One", user_id="user-1")]
    )
    db.list_admin_api_keys = AsyncMock(
        return_value=[
            APIKeySummary(
                key_id="key-1",
                key_prefix="ink_abc...",
                user_id="user-1",
                workspace_id="ws-1",
                name="Local Key",
                status="active",
                permissions=["read", "search"],
                rate_limit=100,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]
    )

    app = create_app()
    app.dependency_overrides[get_api_key_info] = _user_key
    app.dependency_overrides[get_database] = lambda: db

    async with _client(app) as client:
        workspaces = await client.get("/v1/admin/workspaces", headers={"X-API-Key": "ink_test"})
        keys = await client.get("/v1/admin/keys", headers={"X-API-Key": "ink_test"})

    assert workspaces.status_code == 200
    assert workspaces.json()[0]["id"] == "ws-1"
    assert keys.status_code == 200
    key_body = keys.json()[0]
    assert key_body["key_prefix"] == "ink_abc..."
    assert "key_hash" not in key_body
