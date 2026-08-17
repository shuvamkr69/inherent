"""Read-only local admin visibility endpoints for the CLI."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.config import settings
from src.models.api_key import APIKeyInfo
from src.models.identity import APIKeySummary, WorkspaceSummary
from src.services.auth import get_api_key_info
from src.services.database import DatabaseService, get_database

router = APIRouter(prefix="/admin")


def _require_admin_enabled() -> None:
    """Hide the local inventory surface unless an operator explicitly enables it."""

    if not settings.admin_api_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.get("/workspaces", response_model=list[WorkspaceSummary])
async def list_workspaces(
    _key_info: Annotated[APIKeyInfo, Depends(get_api_key_info)],
    database: Annotated[DatabaseService, Depends(get_database)],
) -> list[WorkspaceSummary]:
    """List local workspace metadata without document or secret material."""

    _require_admin_enabled()
    return await database.list_admin_workspaces()


@router.get("/keys", response_model=list[APIKeySummary])
async def list_keys(
    _key_info: Annotated[APIKeyInfo, Depends(get_api_key_info)],
    database: Annotated[DatabaseService, Depends(get_database)],
) -> list[APIKeySummary]:
    """List API key metadata without key hashes or plaintext key values."""

    _require_admin_enabled()
    return await database.list_admin_api_keys()
