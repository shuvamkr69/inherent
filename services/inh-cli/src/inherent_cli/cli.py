"""Typer command surface for the Inherent CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .compose import (
    compose_capture,
    compose_command,
    ensure_docker,
    install_compose_file,
    write_stack_env,
)
from .config import (
    CLIConfig,
    DEFAULT_URL,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
    generate_api_key,
    mcp_server_entry,
    require_config,
    write_config,
    write_cursor_mcp_config,
)
from .rest import request, upload_document

app = typer.Typer(help="Run and inspect Inherent.")
docs_app = typer.Typer(help="Document commands.")
workspaces_app = typer.Typer(help="Workspace visibility commands.")
keys_app = typer.Typer(help="API key visibility commands.")
app.add_typer(docs_app, name="docs")
app.add_typer(workspaces_app, name="workspaces")
app.add_typer(keys_app, name="keys")
console = Console()


def _print(data: object, *, as_json: bool) -> None:
    if as_json:
        console.print_json(json.dumps(data))
    else:
        console.print(data)


def _wait_ready(config: CLIConfig, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            body = request(config, "GET", "/health/ready", workspace=False)
            if body.get("status") in {"healthy", "degraded"}:
                return
        except Exception:
            time.sleep(2)
    raise RuntimeError("Timed out waiting for the public API readiness probe.")


@app.command()
def version() -> None:
    """Print CLI version."""
    console.print(__version__)


@app.command()
def up(
    engine_version: Annotated[
        str, typer.Option("--version", help="Engine image tag.")
    ] = __version__,
    detach: Annotated[bool, typer.Option("--detach/--no-detach")] = True,
) -> None:
    """Start the local release stack, seed it, and save CLI config."""
    docker_version = ensure_docker()
    api_key = generate_api_key()
    config = CLIConfig(
        url=DEFAULT_URL,
        api_key=api_key,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=DEFAULT_USER_ID,
        engine_version=engine_version,
    )
    install_compose_file()
    write_stack_env(config, engine_version=engine_version)
    write_config(config)

    console.print(f"[green]✓[/green] {docker_version} found")
    args = ["up", "--pull", "always"]
    if detach:
        args.append("-d")
    args.append("--wait")
    compose_command(*args)
    compose_command("--profile", "bootstrap", "run", "--rm", "bootstrap")
    _wait_ready(config)
    console.print("[green]✓[/green] Stack healthy")
    console.print(f"[green]✓[/green] Workspace ready: {config.workspace_id}")
    console.print("Connect your agent:")
    console.print("  inherent connect claude --print")


@app.command()
def down(
    volumes: Annotated[bool, typer.Option("--volumes", help="Delete local volumes.")] = False
) -> None:
    """Stop the local stack."""
    args = ["down"]
    if volumes:
        args.append("-v")
    compose_command(*args)


@app.command()
def status(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show Docker Compose service status."""
    result = compose_capture("ps", "--format", "json")
    if as_json:
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        _print(rows, as_json=True)
        return
    console.print(result.stdout or result.stderr)


@app.command()
def logs(
    service: Annotated[str | None, typer.Argument()] = None,
    follow: Annotated[bool, typer.Option("-f", "--follow")] = False,
) -> None:
    """Show stack or service logs."""
    args = ["logs"]
    if follow:
        args.append("-f")
    if service:
        args.append(service)
    compose_command(*args)


@app.command()
def doctor(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Run lightweight health probes."""
    config = require_config()
    checks: list[dict[str, object]] = []
    for path in ("/health", "/health/ready"):
        try:
            body = request(config, "GET", path, workspace=False)
            checks.append({"path": path, "ok": True, "status": body.get("status", "ok")})
        except Exception as exc:
            checks.append({"path": path, "ok": False, "error": str(exc)})
    if as_json:
        _print(checks, as_json=True)
        return
    table = Table("Probe", "OK", "Detail")
    for check in checks:
        table.add_row(
            str(check["path"]),
            str(check["ok"]),
            str(check.get("status") or check.get("error")),
        )
    console.print(table)


@app.command()
def whoami(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show the current API identity."""
    body = request(require_config(), "GET", "/v1/whoami", workspace=False)
    if as_json:
        _print(body, as_json=True)
        return
    table = Table("Field", "Value")
    for key in ("key_id", "user_id", "workspace_id", "permissions", "engine_version"):
        table.add_row(key, json.dumps(body[key]) if isinstance(body[key], list) else str(body[key]))
    console.print(table)


@app.command()
def search(
    query: Annotated[str, typer.Argument()],
    mode: Annotated[str, typer.Option("--mode")] = "hybrid",
    limit: Annotated[int, typer.Option("--limit")] = 5,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Search indexed documents."""
    body = request(
        require_config(),
        "POST",
        "/v1/search",
        json={"query": query, "search_mode": mode, "limit": limit},
    )
    if as_json:
        _print(body, as_json=True)
        return
    table = Table("Score", "Document", "Content")
    for row in body.get("results", []):
        table.add_row(
            f"{row.get('score', 0):.3f}",
            row.get("document_name", ""),
            row.get("content", "")[:120],
        )
    console.print(table)


@docs_app.command("upload")
def docs_upload(path: Annotated[Path, typer.Argument(exists=True)]) -> None:
    """Upload one document."""
    body = upload_document(require_config(), path)
    console.print_json(json.dumps(body))


@docs_app.command("list")
def docs_list(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List documents."""
    body = request(require_config(), "GET", "/v1/documents")
    if as_json:
        _print(body, as_json=True)
        return
    table = Table("ID", "Name", "Status", "Chunks")
    for doc in body.get("documents", []):
        table.add_row(doc["id"], doc["name"], doc["status"], str(doc["chunk_count"]))
    console.print(table)


@docs_app.command("show")
def docs_show(document_id: str, as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show document metadata."""
    _print(request(require_config(), "GET", f"/v1/documents/{document_id}"), as_json=as_json)


@docs_app.command("delete")
def docs_delete(document_id: str) -> None:
    """Delete a document."""
    request(require_config(), "DELETE", f"/v1/documents/{document_id}")
    console.print(f"Deleted {document_id}")


@docs_app.command("refresh")
def docs_refresh(document_id: str) -> None:
    """Refresh a document."""
    console.print_json(
        json.dumps(request(require_config(), "POST", f"/v1/documents/{document_id}/refresh"))
    )


@app.command()
def chunks(document_id: str, as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List chunks for a document."""
    body = request(require_config(), "GET", f"/v1/chunks/{document_id}")
    if as_json:
        _print(body, as_json=True)
        return
    table = Table("Index", "Tokens", "Content")
    for chunk in body:
        table.add_row(str(chunk["chunk_index"]), str(chunk["token_count"]), chunk["content"][:140])
    console.print(table)


@workspaces_app.command("list")
def workspaces_list(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List local workspaces, falling back to the caller identity remotely."""
    config = require_config()
    try:
        body = request(config, "GET", "/v1/admin/workspaces", workspace=False)
    except Exception:
        body = request(config, "GET", "/v1/whoami", workspace=False)["authorized_workspaces"]
    _print(body, as_json=as_json)


@keys_app.command("list")
def keys_list(as_json: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List local API key metadata."""
    body = request(require_config(), "GET", "/v1/admin/keys", workspace=False)
    _print(body, as_json=as_json)


def _claude_add_command(config: CLIConfig) -> str:
    """Render the `claude mcp add` command that registers the local stack."""
    return (
        f"claude mcp add --transport http inherent {config.url}/mcp "
        f'--header "X-API-Key: {config.api_key}"'
    )


@app.command()
def connect(
    agent: Annotated[str, typer.Argument(help="Agent to configure: claude or cursor.")],
    print_only: Annotated[
        bool, typer.Option("--print", help="Print the config instead of writing it.")
    ] = False,
) -> None:
    """Register the local MCP endpoint in an agent's config."""
    config = require_config()
    if agent not in {"claude", "cursor"}:
        raise typer.BadParameter("agent must be claude or cursor")

    if agent == "claude":
        # Claude Code owns its own config store, so we drive its CLI rather than
        # editing files it manages. `--print` just shows the command instead.
        command = _claude_add_command(config)
        if print_only:
            console.print(command)
            return
        if shutil.which("claude") is None:
            console.print(
                "[yellow]![/yellow] claude CLI not found. Run this to register the server:"
            )
            console.print(f"  {command}")
            return
        subprocess.run(
            [
                "claude",
                "mcp",
                "add",
                "--transport",
                "http",
                "inherent",
                f"{config.url}/mcp",
                "--header",
                f"X-API-Key: {config.api_key}",
            ],
            check=True,
        )
        console.print("[green]✓[/green] Registered Inherent with Claude.")
        return

    # Cursor reads a JSON config file, so we merge our entry into it directly.
    if print_only:
        console.print_json(json.dumps({"mcpServers": {"inherent": mcp_server_entry(config)}}))
        return
    target = write_cursor_mcp_config(config)
    console.print(f"[green]✓[/green] Wrote Inherent MCP server to {target}")


def main() -> None:
    """Console-script entrypoint."""
    try:
        app()
    except subprocess.CalledProcessError as exc:
        raise typer.Exit(exc.returncode or 1) from exc
    except RuntimeError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
