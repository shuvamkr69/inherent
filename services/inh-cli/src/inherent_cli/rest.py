"""HTTP client helpers for the Inherent CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .config import CLIConfig


def _headers(config: CLIConfig, *, workspace: bool = True) -> dict[str, str]:
    headers = {"X-API-Key": config.api_key}
    if workspace and config.workspace_id:
        headers["X-Workspace-Id"] = config.workspace_id
    return headers


def request(
    config: CLIConfig,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    workspace: bool = True,
) -> Any:
    """Send a JSON API request and return the decoded response."""
    with httpx.Client(base_url=config.url, timeout=30.0) as client:
        response = client.request(
            method, path, headers=_headers(config, workspace=workspace), json=json
        )
    response.raise_for_status()
    if response.status_code == 204:
        return None
    return response.json()


def upload_document(config: CLIConfig, path: Path) -> Any:
    """Upload one document through the public API."""
    with path.open("rb") as handle:
        files = {"file": (path.name, handle)}
        with httpx.Client(base_url=config.url, timeout=120.0) as client:
            response = client.post("/v1/documents", headers=_headers(config), files=files)
    response.raise_for_status()
    return response.json()
