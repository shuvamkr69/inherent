"""Identity endpoint for CLI and agent clients."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.config import settings
from src.models.api_key import APIKeyInfo
from src.models.identity import WhoAmIResponse, WorkspaceSummary
from src.services.auth import get_api_key_info, get_authorized_workspace_ids
from src.services.database import DatabaseService, get_database

router = APIRouter()


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(
    key_info: Annotated[APIKeyInfo, Depends(get_api_key_info)],
    database: Annotated[DatabaseService, Depends(get_database)],
) -> WhoAmIResponse:
    """Return the current key's resolved identity and reachable workspaces."""

    workspace_ids = await get_authorized_workspace_ids(key_info, database)
    workspaces = await database.get_workspace_summaries(workspace_ids)
    known = {workspace.id: workspace for workspace in workspaces}

    return WhoAmIResponse(
        key_id=key_info.key_id,
        user_id=key_info.user_id,
        workspace_id=key_info.workspace_id,
        permissions=list(key_info.permissions),
        rate_limit=key_info.rate_limit,
        status=key_info.status,
        engine_version=settings.version,
        authorized_workspaces=[
            known.get(workspace_id, WorkspaceSummary(id=workspace_id))
            for workspace_id in workspace_ids
        ],
    )
