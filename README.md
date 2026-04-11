# zotero-headless

<p align="center">
  <img src="./assets/zotero-headless.png" alt="zotero-headless logo" width="220" />
</p>

`zotero-headless` is an open-source headless Zotero-compatible runtime with:

- a CLI
- an HTTP API
- an MCP server
- a clean-room headless store
- Zotero web sync
- local Zotero desktop interoperability
- qmd-backed semantic search that is automatically refreshed from library changes
- built-in recovery snapshots and restore tooling with optional external backup repositories
- compatibility with the agent tool of your choice through API or MCP

All three main interfaces are first-class:

- CLI
  - good for humans, scripts, and shell automation
- HTTP API
  - good for apps, services, agents, and direct integrations
- MCP
  - good for agent tools that already speak MCP

The project is built for two use cases:

- desktop interoperability
  - work against an existing local Zotero profile
  - import, poll, and apply the currently supported subset of changes back to the local desktop database
- headless/server runtime
  - run `zotero-headless-daemon` on a machine without the Zotero GUI
  - expose API and MCP for automation, retrieval, background sync jobs, and agent integrations

## Status

This project is still early-stage. The codebase already includes:

- headless SQLite store plus change log
- `zotero-headless` CLI
- `zotero-headless-daemon` runtime
- `zotero-headless-mcp` stdio server
- local HTTP API
- Zotero web sync for user and group libraries
- local Zotero desktop import, polling, and narrow apply/writeback support
- remote attachment upload/download for the currently supported stored-file and snapshot-style paths
- Better BibTeX-oriented citekey compatibility
- qmd export plus semantic search over Markdown derived from headless state, with automatic refresh on dataset changes
- MCP setup helpers for common agent tools
- runtime observability endpoints and background sync status
- recovery snapshots, restore planning, restore execution, and backup replication targets

Current upstream compatibility baseline:

- Zotero `9.0` (released April 10, 2026) is the newest tracked desktop/runtime baseline for local schema assumptions and the optional desktop-helper workflow
- native citation-key fields introduced in Zotero 9 are now preserved on local desktop reads/writes and attempted on remote writes with automatic fallback for older API behavior
- Zotero's new browser-based account login flow does not replace the Zotero Web API key required by `zotero-headless` for web sync

## What It Is For

Typical end-user use cases:

- run a headless Zotero-compatible service on a server
- query or mutate libraries through CLI, API, or MCP
- sync against Zotero web libraries without requiring the Zotero GUI to be running
- work against a local desktop Zotero profile when local interoperability is needed
- query library content through qmd-backed semantic search flows without manually rebuilding the qmd index after normal sync/write activity
- create safety snapshots before risky operations and restore whole state or a single library after a bad change

This repository also contains contribution and architecture material because the project is still evolving, but the repo is not meant only for contributors.

## Desktop Helper Workflow

This repository no longer vendors a Zotero source snapshot.

The current architecture is a clean-room headless runtime with adapters around Zotero desktop and Zotero web sync. When contributors need to work on the optional desktop-helper path, the repo keeps only a small helper workflow under `desktop_helper/` rather than a full upstream source mirror.

Understanding upstream desktop/runtime behavior still matters for:

- local database interoperability
- daemon/bootstrap experiments
- sync semantics
- attachment handling
- reproducible debugging for contributors

The intended workflow is:

- pin an upstream Zotero commit or tag in `desktop_helper/metadata.json`
- maintain the helper delta as explicit patch files under `desktop_helper/patches/`
- build or validate against an external upstream checkout instead of an in-repo vendored tree

## Repository Layout

- `src/zotero_headless/`
  - main runtime, CLI, API, MCP, sync, and adapter code
- `tests/`
  - regression coverage for the runtime, sync, adapter, and tooling surfaces
- `docs/`
  - branch guides and upstream Zotero notes
- `desktop_helper/`
  - metadata and patch workflow for the optional external Zotero desktop-helper path

Local-only workspace material should go in ignored directories such as:

- `.codex/`
- `.agents/`
- `.notes/`
- `.tmp/`

## Install

Recommended install methods:

```text
uv tool install zotero-headless
```

or

```text
pipx install zotero-headless
```

From source:

```text
git clone https://github.com/<owner>/zotero-headless.git
cd zotero-headless
PYTHONPATH=src python3 -m zotero_headless capabilities
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

## Quick Start

Run the setup flow:

```text
zhl setup start
```

`setup start` tries autodiscovery first, uses standard local Zotero paths automatically when it finds them, and only prompts for values that are still missing.

Interactive commands now default to human-readable output. If you want script-friendly payloads for setup, version, update, doctor, or daemon status commands, add `--json`.

The CLI is now split by audience:

- human/operator flows live on the main top-level commands like `setup`, `doctor`, `version`, and `daemon`
- strict programmatic CLI usage lives under `zhl raw ...`

Use `zhl raw ...` when you want non-interactive, automation-friendly command paths that mirror the underlying data operations closely.

## Recovery

`zotero-headless` now includes a built-in recovery subsystem for all library types.

It snapshots the full headless runtime boundary:

- canonical DB
- mirror DB
- cached files
- qmd export output
- citation export artifact

You can inspect configured repositories:

```text
zhl recovery repositories
```

Create a snapshot:

```text
zhl recovery snapshot-create --reason "before bulk edits"
```

Plan a rollback for one library:

```text
zhl recovery restore-plan --snapshot <snapshot_id> --library group:123
```

Execute a rollback:

```text
zhl recovery restore-execute --snapshot <snapshot_id> --library group:123 --confirm
```

Replicate a snapshot to an external repository:

```text
zhl recovery snapshot-push <snapshot_id> --repository s3-primary
zhl recovery snapshot-push <snapshot_id> --repository lab-rsync
```

See [docs/RECOVERY.md](./docs/RECOVERY.md) for configuration and API details.

Autodiscovery looks for:

- standard Zotero data directories such as `~/Zotero`
- common Zotero desktop binary locations
- already-saved API credentials and remote-library selections

Then the wizard will:

- tell you when it autodiscovers a standard local Zotero setup, and only ask for local desktop paths when it cannot infer them or when you explicitly reconfigure them
- use explicit confirmation prompts such as `[y/N]` and `[Y/n]` where a yes-or-no decision is needed
- ask for your Zotero API key only when web sync is needed
- discover your personal library and available group libraries
- let you choose which remote libraries to configure
- store a default remote library for later use

That means it also works for:

- a Linux server where this is the only Zotero-related install
- rerunning setup later to add or remove group libraries
- switching to a different Zotero account in true headless mode
- changing local Zotero paths without redoing the whole setup

You can inspect what autodiscovery sees without changing config:

```text
zhl config autodiscover
```

You can also reconfigure specific parts later:

```text
zhl setup account
zhl setup libraries
zhl setup local
```

### Example: Codex On A Desktop With Zotero Installed

Use this when you already have Zotero Desktop on your machine and want `zotero-headless` to interoperate with that local profile, while also making MCP and skills available in Codex.

1. Install the CLI:

```text
uv tool install zotero-headless
```

2. Run guided setup. On a standard desktop install, autodiscovery should usually find your Zotero data directory automatically:

```text
zhl setup start
```

3. Install the MCP server into Codex:

```text
zhl setup add codex --scope user
```

4. Install the Codex skill pack:

```text
zhl skill install codex
```

5. Start using whichever interface fits the task:

```text
zhl local import
zhl qmd query "papers about retrieval augmented generation"
zhl api serve --host 127.0.0.1 --port 8787
zhl-mcp
```

Typical result:

- local Zotero desktop data is imported and can be polled/applied
- Codex can connect through MCP
- Codex can also call the HTTP API directly when that is the better fit
- qmd-backed semantic search stays in sync automatically as headless data changes

### Example: Standalone Headless Linux Server

Use this when the machine does not run Zotero Desktop and `zotero-headless` is the only Zotero-related runtime on the box.

1. Install the CLI:

```text
uv tool install zotero-headless
```

2. Run guided setup. Autodiscovery will likely find little on a clean server, so the wizard will prompt for your Zotero API key and remote libraries:

```text
zhl setup start
```

3. Start the daemon runtime with background sync:

```text
zhl-daemon serve --host 0.0.0.0 --port 8787 --sync-interval 300
```

4. Use the API or MCP depending on the integration:

```text
curl -s http://127.0.0.1:8787/capabilities
zhl-mcp
```

5. If you want Codex or another agent client to connect to that server-hosted install, add MCP setup and install the matching skill pack on the client machine:

```text
zhl setup add codex --scope user
zhl skill install codex
```

Typical result:

- personal and group libraries sync from Zotero Web
- the daemon hosts API, MCP, background sync, and semantic search workflows
- agent clients can use either MCP or the HTTP API
- no local Zotero GUI or desktop profile is required

For non-interactive automation, you can still initialize configuration directly:

```text
python -m zotero_headless config init \
  --data-dir "$HOME/Zotero" \
  --api-key "$ZOTERO_API_KEY" \
  --user-id 123456 \
  --remote-library-id user:123456 \
  --remote-library-id group:654321 \
  --default-library-id user:123456
```

Run the daemon runtime:

```text
zhl-daemon serve --host 127.0.0.1 --port 8787 --sync-interval 300
```

Run the API directly without the daemon wrapper:

```text
zhl api serve --host 127.0.0.1 --port 8787
```

Run the MCP server:

```text
zhl-mcp
```

Check version and update:

```text
zhl version
zhl update --check
zhl update
zhl --json doctor
```

Release maintenance:

```text
make release VERSION=0.4.0
```

API exposure works in two modes:

- `zotero-headless api serve`
  - standalone HTTP API process
- `zotero-headless-daemon serve`
  - daemon runtime that hosts the same HTTP API plus runtime state and background sync

Strict machine-oriented CLI examples:

```text
zhl raw sync discover
zhl raw sync pull --library user:123456
zhl raw item create user:123456 '{"itemType":"note","note":"Hello"}'
zhl raw local import
```

So no, the API is not only exposed on `zotero-headless-daemon`.

Inspect capabilities and daemon state:

```text
zotero-headless capabilities
zotero-headless daemon status
zotero-headless doctor
```

## Choosing An Interface

Use the CLI if you want:

- terminal-first workflows
- shell scripts
- direct local administration

Use the HTTP API if you want:

- app-to-app integration
- service orchestration
- direct agent integrations without MCP
- long-running daemon deployments

Use MCP if you want:

- native tool use inside MCP-capable agent clients
- easy installation into Codex, Claude Code, Cursor, Gemini, Cline, Windsurf, and similar tools

## Current Command Surface

Local desktop interoperability:

```text
zotero-headless local libraries
zotero-headless local import
zotero-headless local poll
zotero-headless local plan-apply --library local:1
zotero-headless local apply --library local:1
```

Remote sync:

```text
zotero-headless sync discover
zotero-headless sync pull --library user:123456
zotero-headless sync push --library user:123456
zotero-headless sync conflicts --library user:123456
```

qmd flows:

```text
zotero-headless qmd export
zotero-headless qmd query "retrieval augmented generation"
```

MCP/client setup:

```text
zotero-headless setup list
zotero-headless setup add codex --scope user
zotero-headless setup add claude-code --scope project
zotero-headless setup add claude-desktop --scope user
zotero-headless setup add cursor --scope project
zotero-headless setup add gemini --scope user
zotero-headless setup add cline --scope user
zotero-headless setup add antigravity --scope user
zotero-headless setup add windsurf --scope user
```

Agent skill helpers:

```text
zotero-headless skill add claude-desktop
zotero-headless skill install codex
zotero-headless skill install claude-code
zotero-headless skill install gemini-cli
zotero-headless skill install cline
zotero-headless skill install antigravity
zotero-headless skill install openclaw
zotero-headless skill install opencode
```

`zotero-headless skill add claude-desktop` generates a Claude skill archive on your Desktop. Upload that archive in the Skills section of Claude Desktop or on claude.ai.

## Roadmap

Implemented:

- headless store and mutation log
- runtime daemon, API, and MCP server
- Zotero web sync for remote libraries
- local desktop import and polling
- narrow local writeback/apply support for the supported item, collection, note, annotation, and attachment paths
- remote attachment handling for the currently supported stored-file and snapshot-style paths
- Better BibTeX-oriented citekey handling

## Documentation

- [docs/README.md](./docs/README.md)
- [USE_CASES.md](./docs/USE_CASES.md)
- [CLI.md](./docs/CLI.md)
- [API_AND_MCP.md](./docs/API_AND_MCP.md)
- [LOCAL_DESKTOP.md](./docs/LOCAL_DESKTOP.md)
- [REMOTE_SYNC.md](./docs/REMOTE_SYNC.md)
- [DESKTOP_HELPER.md](./docs/DESKTOP_HELPER.md)
- [ZOTERO_SOURCE_NOTES.md](./docs/ZOTERO_SOURCE_NOTES.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)

## References

- [Zotero Repository](https://github.com/zotero/zotero)
- [Zotero Web API Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)
- [Direct SQLite Database Access](https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access)
- [qmd README](https://github.com/tobi/qmd)
