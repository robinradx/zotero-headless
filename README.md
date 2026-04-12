# zotero-headless

<p align="center">
  <img src="./assets/zotero-headless.png" alt="zotero-headless logo" width="220" />
</p>

`zotero-headless` is a headless Zotero-compatible runtime with:

- a CLI for operators and scripts
- an HTTP API for apps and services
- an MCP server for agent tools
- a clean-room headless store
- Zotero web sync for user and group libraries
- local Zotero desktop interoperability
- qmd-backed semantic search that refreshes from library changes
- built-in recovery snapshots, restore flows, and backup repositories

It is built for two main deployment shapes:

- desktop interoperability: use an existing Zotero Desktop profile and optionally write supported changes back
- true headless runtime: run the daemon on a machine without Zotero Desktop and expose API or MCP to clients

## Quick Setup

### 1. Install the CLI

```text
uv tool install zotero-headless
```

or:

```text
pipx install zotero-headless
```

Main entrypoints:

```text
zotero-headless
zotero-headless-daemon
zotero-headless-mcp
```

Short aliases:

```text
zhl
zhl-daemon
zhl-mcp
```

### 2. Run guided setup

```text
zhl setup start
```

`setup start` tries autodiscovery first. On a normal desktop install it will usually find standard Zotero paths automatically, then prompt only for the missing pieces such as API credentials or remote-library selection.

### 3. Pick the common path that matches your use case

#### Codex plugin

Best if you want the richest Codex integration, not just raw MCP wiring.

```text
zhl plugin install codex
zhl plugin update codex
zhl plugin update all
```

This installs the local Codex plugin bundle with:

- bundled Zotero skills
- bundled research and sync agents
- bundled MCP config
- a startup status hook

#### Claude Code

Use the Claude Code plugin bundle.

```text
zhl plugin install claude-code
zhl plugin update claude-code
zhl plugin update all
```

This installs the repo-local Claude Code plugin bundle and refreshes its bundled `.mcp.json` from your local settings.

#### OpenClaw

Use OpenClaw's native plugin system plus the matching skill.

```text
zhl plugin install openclaw
zhl plugin update openclaw
zhl plugin update all
zhl skill install openclaw
```

`zhl plugin install openclaw` runs the real OpenClaw plugin install and enable flow against `./plugins/openclaw-plugin-zotero`.
`zhl plugin update ...` refreshes the installed plugin from the repo-local source bundle for the matching client. `zhl plugin update all` refreshes Codex, Claude Code, and OpenClaw in one pass.
The OpenClaw plugin source now builds through a package-manager-agnostic `prepare` lifecycle script, so linked installs work whether OpenClaw is configured to use `npm`, `pnpm`, or `bun`.

#### Codex or another client with plain MCP only

If you want raw MCP config without the full Codex plugin bundle:

```text
zhl setup add codex --scope user
```

Other supported setup targets include `cursor`, `claude-desktop`, `gemini`, `cline`, `antigravity`, and `windsurf`.

#### Headless daemon on a server

If this machine is the runtime host:

```text
zhl-daemon serve --host 0.0.0.0 --port 23119 --sync-interval 300
```

### 4. Smoke-test the install

```text
zhl capabilities
zhl daemon status
zhl setup list
```

If you need multiple isolated accounts on one machine, use named profiles:

```text
zhl --profile alice setup start
zhl --profile alice daemon serve --port 8787
zhl --profile bob setup start
zhl --profile bob daemon serve --port 8788
```

If you configured remote sync:

```text
zhl raw sync discover
```

## Most Common Workflows

### Search the library

```text
zhl qmd query "papers about retrieval augmented generation"
```

Use qmd-backed search for exploratory retrieval. Use exact MCP, API, or CLI reads for authoritative metadata.

### Pull and push a remote library

```text
zhl raw sync pull --library user:123456
zhl raw sync push --library user:123456
zhl raw sync conflicts --library user:123456
```

Always inspect conflicts before retrying a failed push.

### Import from local Zotero Desktop

```text
zhl local import
zhl local plan-apply --library local:1
zhl local apply --library local:1
```

Use `plan-apply` before any local writeback.

### Create a safety snapshot

```text
zhl recovery snapshot-create --reason "before bulk edits"
zhl recovery restore-plan --snapshot <snapshot_id> --library group:123
zhl recovery restore-execute --snapshot <snapshot_id> --library group:123 --confirm
```

## Which Interface To Use

### CLI

Use the CLI for:

- operator workflows
- shell scripts
- setup and diagnostics
- local administration

Human-facing commands live on the main surface such as `setup`, `doctor`, `version`, and `daemon`.

For strict machine-oriented automation, use:

```text
zhl raw ...
```

### HTTP API

Use the API for:

- app-to-app integration
- long-running services
- direct agent integrations without MCP
- runtime observability and job inspection

You can expose it with either:

```text
zhl api serve --host 127.0.0.1 --port 23119
```

or:

```text
zhl-daemon serve --host 127.0.0.1 --port 23119 --sync-interval 300
```

### MCP

Use MCP when your client already speaks MCP and you want native tool use inside:

- Codex
- Claude Code
- Cursor
- Gemini
- Cline
- Windsurf
- similar agent tools

Start the stdio MCP server directly with:

```text
zhl-mcp
```

## Typical Setup Recipes

### Desktop machine with Zotero installed and Codex as the client

```text
uv tool install zotero-headless
zhl setup start
zhl plugin install codex
```

Useful next commands:

```text
zhl local import
zhl qmd query "papers about transformers in NLP"
```

### Standalone headless server

```text
uv tool install zotero-headless
zhl setup start
zhl-daemon serve --host 0.0.0.0 --port 23119 --sync-interval 300
```

Useful next commands:

```text
curl -s http://127.0.0.1:23119/capabilities
zhl raw sync discover
```

### Claude Code on a project

```text
uv tool install zotero-headless
zhl setup start
zhl plugin install claude-code
```

### OpenClaw

```text
uv tool install zotero-headless
zhl setup start
zhl plugin install openclaw
zhl skill install openclaw
```

## Command Cheat Sheet

### Status and diagnostics

```text
zhl version
zhl update --check
zhl update
zhl doctor
zhl capabilities
zhl daemon status
zhl setup list
```

After a successful `zhl update`, `zotero-headless` automatically refreshes already-installed standalone skills and already-installed plugin targets using the packaged plugin bundles, with the current checkout used as an override when you are running from the repo.

### Client setup

```text
zhl plugin install codex
zhl plugin install claude-code
zhl plugin install openclaw
zhl plugin update codex
zhl plugin update claude-code
zhl plugin update openclaw
zhl plugin update all
zhl setup add codex --scope user
zhl skill install codex
zhl skill install openclaw
zhl skill export claude-desktop
zhl skill update all
```

### Local desktop interoperability

```text
zhl local libraries
zhl local import
zhl local poll
zhl local plan-apply --library local:1
zhl local apply --library local:1
```

### Remote sync

```text
zhl sync discover
zhl sync pull --library user:123456
zhl sync push --library user:123456
zhl sync conflicts --library user:123456
```

### Recovery

```text
zhl recovery repositories
zhl recovery snapshot-create --reason "before risky edit"
zhl recovery restore-plan --snapshot <snapshot_id> --library user:123456
zhl recovery restore-execute --snapshot <snapshot_id> --library user:123456 --confirm
```

## Status

This project is still early-stage, but it already includes:

- a headless SQLite store and change log
- the `zotero-headless` CLI
- the `zotero-headless-daemon` runtime
- the `zotero-headless-mcp` stdio server
- a local HTTP API
- Zotero web sync for user and group libraries
- local Zotero desktop import, polling, and narrow apply support
- remote attachment upload and download for the currently supported paths
- Better BibTeX-oriented citekey compatibility
- qmd export plus semantic search with automatic refresh
- MCP setup helpers and plugin installers for common agent tools
- runtime observability endpoints and background sync status
- recovery snapshots, restore planning, restore execution, and backup replication

Current compatibility baseline:

- Zotero `9.0` (released April 10, 2026) is the newest tracked desktop/runtime baseline for local schema assumptions
- Zotero 9 native citation-key fields are preserved on local reads and writes and attempted on remote writes with fallback behavior
- Zotero's browser-based account login does not replace the Web API key requirement for remote sync

## Repository Layout

- `src/zotero_headless/`: runtime, CLI, API, MCP, sync, and adapter code
- `tests/`: regression coverage across runtime and tooling surfaces
- `docs/`: deeper guides and architecture notes
- `plugins/`: repo-local plugin bundles for supported agent clients
- `desktop_helper/`: metadata and patch workflow for the optional external Zotero desktop-helper path

Local-only workspace material should live in ignored directories such as:

- `.codex/`
- `.agents/`
- `.notes/`
- `.tmp/`

## Desktop Helper Workflow

This repository no longer vendors a Zotero source snapshot.

The current architecture is a clean-room headless runtime with adapters around Zotero Desktop and Zotero web sync. When contributors need the optional desktop-helper path, the repo keeps a small helper workflow under `desktop_helper/` rather than an in-repo upstream mirror.

That workflow is intended to:

- pin an upstream Zotero commit or tag in `desktop_helper/metadata.json`
- keep helper deltas as explicit patch files under `desktop_helper/patches/`
- build or validate against an external upstream checkout

## Documentation

- [docs/README.md](./docs/README.md)
- [USE_CASES.md](./docs/USE_CASES.md)
- [CLI.md](./docs/CLI.md)
- [API_AND_MCP.md](./docs/API_AND_MCP.md)
- [LOCAL_DESKTOP.md](./docs/LOCAL_DESKTOP.md)
- [REMOTE_SYNC.md](./docs/REMOTE_SYNC.md)
- [RECOVERY.md](./docs/RECOVERY.md)
- [DESKTOP_HELPER.md](./docs/DESKTOP_HELPER.md)
- [ZOTERO_SOURCE_NOTES.md](./docs/ZOTERO_SOURCE_NOTES.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)

## References

- [Zotero Repository](https://github.com/zotero/zotero)
- [Zotero Web API Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)
- [Direct SQLite Database Access](https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access)
- [qmd README](https://github.com/tobi/qmd)
