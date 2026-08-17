"""Identity and local admin visibility response models."""

from datetime import datetime

from pydantic import BaseModel


class WorkspaceSummary(BaseModel):
    """Workspace metadata safe to expose to the owning caller or local admin."""

    id: str
    name: str | None = None
    user_id: str | None = None


class APIKeySummary(BaseModel):
    """API key metadata without secret material."""

    key_id: str
    key_prefix: str
    user_id: str
    workspace_id: str | None = None
    name: str
    status: str
    permissions: list[str]
    rate_limit: int
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class WhoAmIResponse(BaseModel):
    """Resolved identity for the current API key."""

    key_id: str
    user_id: str
    workspace_id: str | None = None
    permissions: list[str]
    rate_limit: int
    status: str
    engine_version: str
    authorized_workspaces: list[WorkspaceSummary]
