"""Config file handling for the Inherent CLI."""

from __future__ import annotations

import json
import os
import secrets
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_URL = "http://localhost:18000"
DEFAULT_WORKSPACE_ID = "ws_local_001"
DEFAULT_USER_ID = "local-dev-user"


@dataclass(frozen=True)
class CLIConfig:
    """Resolved CLI connection settings."""

    url: str
    api_key: str
    workspace_id: str
    user_id: str
    engine_version: str


def config_dir() -> Path:
    """Return the per-user config directory."""
    root = os.getenv("INHERENT_HOME")
    if root:
        return Path(root).expanduser()
    return Path.home() / ".inherent"


def config_path() -> Path:
    """Return the TOML config path."""
    return config_dir() / "config.toml"


def compose_path() -> Path:
    """Return the extracted release compose file path."""
    return config_dir() / "docker-compose.release.yml"


def state_env_path() -> Path:
    """Return the env file consumed by Docker Compose."""
    return config_dir() / "stack.env"


def cursor_config_path() -> Path:
    """Return the Cursor MCP config path (honors ``CURSOR_HOME`` for tests)."""
    root = os.getenv("CURSOR_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".cursor"
    return base / "mcp.json"


def mcp_server_entry(config: CLIConfig) -> dict[str, Any]:
    """Build the Streamable HTTP MCP server entry for the local stack."""
    return {
        "url": f"{config.url}/mcp",
        "headers": {"X-API-Key": config.api_key},
    }


def write_cursor_mcp_config(config: CLIConfig) -> Path:
    """Merge an ``inherent`` MCP server into Cursor's ``mcp.json``.

    Existing servers are preserved; only the ``inherent`` entry is written so
    rerunning ``inherent connect cursor`` after ``inherent up`` refreshes the
    saved API key without clobbering the user's other MCP servers.
    """
    path = cursor_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            # A corrupt config is replaced rather than aborting the connect flow.
            data = {}

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    servers["inherent"] = mcp_server_entry(config)

    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def generate_api_key() -> str:
    """Generate a local API key with the engine's expected prefix."""
    return "ink_" + secrets.token_urlsafe(32)


def load_config() -> CLIConfig | None:
    """Load saved config, allowing env vars to override URL and key."""
    path = config_path()
    data: dict[str, object] = {}
    if path.exists():
        data = tomllib.loads(path.read_text(encoding="utf-8"))

    url = os.getenv("INHERENT_URL") or data.get("url")
    api_key = os.getenv("INHERENT_API_KEY") or data.get("api_key")
    if not url or not api_key:
        return None

    return CLIConfig(
        url=str(url).rstrip("/"),
        api_key=str(api_key),
        workspace_id=str(os.getenv("INHERENT_WORKSPACE_ID") or data.get("workspace_id") or ""),
        user_id=str(data.get("user_id") or DEFAULT_USER_ID),
        engine_version=str(data.get("engine_version") or "latest"),
    )


def write_config(config: CLIConfig) -> None:
    """Persist connection settings."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f'url = "{config.url}"',
                f'api_key = "{config.api_key}"',
                f'workspace_id = "{config.workspace_id}"',
                f'user_id = "{config.user_id}"',
                f'engine_version = "{config.engine_version}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def require_config() -> CLIConfig:
    """Return config or raise a user-facing error."""
    config = load_config()
    if config is None:
        raise RuntimeError(
            "No local stack config found. Run `inherent up`, or set "
            "INHERENT_URL and INHERENT_API_KEY."
        )
    return config
