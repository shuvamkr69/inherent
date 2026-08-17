"""Unit tests for the Inherent CLI command surface."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from inherent_cli import __version__
from inherent_cli.cli import app
from inherent_cli.config import CLIConfig, write_config

runner = CliRunner()


def _save_local_config(tmp_path) -> None:
    """Write a minimal saved config so read commands resolve a stack."""
    write_config(CLIConfig("http://localhost:18000", "ink_test", "ws-1", "user-1", "0.3.0"))


def test_whoami_json_uses_saved_config(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    monkeypatch.setattr(
        "inherent_cli.cli.request",
        lambda config, method, path, workspace=True, json=None: {
            "key_id": "key-1",
            "user_id": "user-1",
            "workspace_id": "ws-1",
            "permissions": ["read"],
            "rate_limit": 100,
            "status": "active",
            "engine_version": "0.3.0",
            "authorized_workspaces": [{"id": "ws-1", "name": "Local", "user_id": "user-1"}],
        },
    )
    write_config(CLIConfig("http://localhost:18000", "ink_test", "ws-1", "user-1", "0.3.0"))

    result = runner.invoke(app, ["whoami", "--json"])

    assert result.exit_code == 0
    assert '"key_id": "key-1"' in result.stdout


def test_workspaces_list_falls_back_to_whoami(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    calls: list[str] = []

    def fake_request(config, method, path, workspace=True, json=None):
        calls.append(path)
        if path == "/v1/admin/workspaces":
            raise RuntimeError("hidden")
        return {"authorized_workspaces": [{"id": "ws-1", "name": "Local", "user_id": "user-1"}]}

    monkeypatch.setattr("inherent_cli.cli.request", fake_request)
    write_config(CLIConfig("http://localhost:18000", "ink_test", "ws-1", "user-1", "0.3.0"))

    result = runner.invoke(app, ["workspaces", "list", "--json"])

    assert result.exit_code == 0
    assert calls == ["/v1/admin/workspaces", "/v1/whoami"]
    assert '"id": "ws-1"' in result.stdout


def test_connect_claude_prints_streamable_http_config(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    write_config(CLIConfig("http://localhost:18000", "ink_test", "ws-1", "user-1", "0.3.0"))

    result = runner.invoke(app, ["connect", "claude", "--print"])

    assert result.exit_code == 0
    assert "http://localhost:18000/mcp" in result.stdout
    assert "X-API-Key: ink_test" in result.stdout


def test_version_matches_package(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_connect_rejects_unknown_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    _save_local_config(tmp_path)

    result = runner.invoke(app, ["connect", "vscode", "--print"])

    assert result.exit_code != 0


def test_connect_cursor_print_emits_mcp_server_block(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    _save_local_config(tmp_path)

    result = runner.invoke(app, ["connect", "cursor", "--print"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mcpServers"]["inherent"]["url"] == "http://localhost:18000/mcp"
    assert payload["mcpServers"]["inherent"]["headers"]["X-API-Key"] == "ink_test"


def test_connect_cursor_merges_existing_config(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    cursor_home = tmp_path / "cursor"
    monkeypatch.setenv("CURSOR_HOME", str(cursor_home))
    cursor_home.mkdir()
    (cursor_home / "mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"url": "http://example/mcp"}}}),
        encoding="utf-8",
    )
    _save_local_config(tmp_path)

    result = runner.invoke(app, ["connect", "cursor"])

    assert result.exit_code == 0
    saved = json.loads((cursor_home / "mcp.json").read_text(encoding="utf-8"))
    # The pre-existing server is preserved and the inherent entry is added.
    assert saved["mcpServers"]["other"]["url"] == "http://example/mcp"
    assert saved["mcpServers"]["inherent"]["headers"]["X-API-Key"] == "ink_test"


def test_doctor_reports_probe_results(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    _save_local_config(tmp_path)

    def fake_request(config, method, path, workspace=True, json=None):
        return {"status": "healthy"}

    monkeypatch.setattr("inherent_cli.cli.request", fake_request)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    checks = json.loads(result.stdout)
    assert [c["path"] for c in checks] == ["/health", "/health/ready"]
    assert all(c["ok"] for c in checks)


def test_docs_list_renders_rows(monkeypatch, tmp_path):
    monkeypatch.setenv("INHERENT_HOME", str(tmp_path))
    _save_local_config(tmp_path)

    monkeypatch.setattr(
        "inherent_cli.cli.request",
        lambda config, method, path, workspace=True, json=None: {
            "documents": [
                {"id": "doc-1", "name": "notes.txt", "status": "ready", "chunk_count": 3}
            ]
        },
    )

    result = runner.invoke(app, ["docs", "list", "--json"])

    assert result.exit_code == 0
    assert '"id": "doc-1"' in result.stdout
