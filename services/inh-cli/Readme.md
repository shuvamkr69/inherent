# Inherent CLI

`inherent` is the checkout-free command line for running and inspecting a local
Inherent stack from published images.

```bash
pip install inherent
inherent up
inherent status
inherent docs upload ./README.md
inherent search "what is inherent?"
inherent connect claude
```

`inherent up` extracts the release Compose file bundled in the wheel, starts the
local stack, runs the one-shot `bootstrap` service to seed a workspace and API
key, and saves the connection settings in `~/.inherent/config.toml`.

## Commands

| Command | Purpose |
| --- | --- |
| `inherent up [--version TAG] [--no-detach]` | Start the stack, seed it, save config. |
| `inherent down [--volumes]` | Stop the stack; `--volumes` also deletes local data. |
| `inherent status [--json]` | Show Compose service status. |
| `inherent logs [SERVICE] [-f]` | Stream stack or per-service logs. |
| `inherent doctor [--json]` | Probe `/health` and `/health/ready`. |
| `inherent whoami [--json]` | Show the current API identity and reachable workspaces. |
| `inherent docs list/show/upload/delete/refresh` | Manage documents through the REST API. |
| `inherent chunks DOC_ID [--json]` | List a document's chunks. |
| `inherent search "QUERY" [--mode hybrid\|keyword\|semantic]` | Test retrieval. |
| `inherent workspaces list [--json]` | List workspaces (local admin, else caller identity). |
| `inherent keys list [--json]` | List local API key metadata (never secrets). |
| `inherent connect claude/cursor [--print]` | Register the local MCP endpoint in an agent's config. |

`inherent connect claude` drives the `claude` CLI to register the MCP server;
`inherent connect cursor` merges an `inherent` server into `~/.cursor/mcp.json`
without disturbing existing entries. Add `--print` to print the config instead
of writing it.

## Pointing at a remote deployment

Environment variables override the saved config, so read commands work against
any deployment:

- `INHERENT_URL` — base URL (default `http://localhost:18000`).
- `INHERENT_API_KEY` — API key sent as `X-API-Key`.
- `INHERENT_WORKSPACE_ID` — workspace scope sent as `X-Workspace-Id`.

The read-only `inherent workspaces list` and `inherent keys list` commands call
the `/v1/admin/*` inventory endpoints, which the server exposes only when
`ADMIN_API_ENABLED=true` (the local Compose stacks set this). Against a hosted
deployment they fall back to the caller's own identity.
