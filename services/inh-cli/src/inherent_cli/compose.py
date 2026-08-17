"""Docker Compose orchestration helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

from .config import CLIConfig, compose_path, state_env_path


def ensure_docker() -> str:
    """Return the Docker version string or raise an actionable error."""
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker was not found. Install Docker Desktop and retry.")
    result = subprocess.run(
        [docker, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def install_compose_file() -> Path:
    """Extract the bundled release compose file into the user state directory."""
    target = compose_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    source = resources.files("inherent_cli").joinpath("data/docker-compose.release.yml")
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def write_stack_env(config: CLIConfig, *, engine_version: str) -> Path:
    """Write the env file used by the local release stack."""
    path = state_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "INHERENT_VERSION": engine_version,
        "POSTGRES_PASSWORD": os.getenv("INHERENT_POSTGRES_PASSWORD", config.api_key),
        "WEAVIATE_API_KEY": os.getenv("INHERENT_WEAVIATE_API_KEY", config.api_key),
        "INGESTION_API_KEY": os.getenv("INHERENT_INGESTION_API_KEY", config.api_key),
        "API_KEY": config.api_key,
        "USER_ID": config.user_id,
        "WORKSPACE_ID": config.workspace_id,
        "KEY_NAME": "Local CLI Key",
        "WORKSPACE_NAME": "Local CLI Workspace",
        "SEED_PRINCIPAL_B": "1",
    }
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    return path


def compose_command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Docker Compose against the bundled release compose file."""
    command = [
        "docker",
        "compose",
        "--env-file",
        str(state_env_path()),
        "-f",
        str(compose_path()),
        *args,
    ]
    return subprocess.run(command, check=check, text=True)


def compose_capture(*args: str) -> subprocess.CompletedProcess[str]:
    """Run Docker Compose and capture stdout for display commands."""
    command = [
        "docker",
        "compose",
        "--env-file",
        str(state_env_path()),
        "-f",
        str(compose_path()),
        *args,
    ]
    return subprocess.run(command, check=False, capture_output=True, text=True)
