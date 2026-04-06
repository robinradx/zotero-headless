# zotero-headless

<p align="center">
  <img src="./assets/zotero-headless.png" alt="zotero-headless logo" width="220" />
</p>

`zotero-headless` is an open-source headless Zotero-compatible runtime with:

- a CLI
- an HTTP API
- an MCP server
- a clean-room canonical store
- Zotero web sync
- local Zotero desktop interoperability
- qmd-backed semantic search over exported library content
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

This is still pre-release, but it is no longer just a sketch. The codebase already includes:

- canonical SQLite store plus change log
- `zotero-headless` CLI
- `zotero-headless-daemon` runtime
- `zotero-headless-mcp` stdio server
- local HTTP API
- Zotero web sync for user and group libraries
- local Zotero desktop import, polling, and narrow apply/writeback support
- remote attachment upload/download for the currently supported stored-file and snapshot-style paths
- Better BibTeX-oriented citekey compatibility
- qmd export and semantic search over Markdown derived from canonical state
- MCP setup helpers for common agent tools
- runtime observability endpoints and background sync status

## What It Is For

Typical end-user use cases:

- run a headless Zotero-compatible service on a server
- query or mutate libraries through CLI, API, or MCP
- sync against Zotero web libraries without requiring the Zotero GUI to be running
- work against a local desktop Zotero profile when local interoperability is needed
- export/query library content through qmd-backed semantic search flows

This repository also contains contribution and architecture material because the project is still evolving, but the repo is not meant only for contributors.

## Why The Repo Includes Vendored Zotero Code

This repository intentionally includes a vendored Zotero source snapshot under `vendor/`.

That is here for contributor visibility and debugging, not because the whole project is just a Zotero wrapper. The current architecture is a clean-room headless runtime with adapters around Zotero desktop and Zotero web sync, but understanding the upstream desktop/runtime behavior still matters for:

- local database interoperability
- daemon/bootstrap experiments
- sync semantics
- attachment handling
- reproducible debugging for contributors

For this project, keeping that context available is more useful than hiding it in a separate private mirror.

## Repository Layout

- `src/zotero_headless/`
  - main runtime, CLI, API, MCP, sync, and adapter code
- `tests/`
  - regression coverage for the runtime, sync, adapter, and tooling surfaces
- `docs/`
  - architecture notes and implementation planning
- `vendor/`
  - vendored Zotero source snapshot used for reference and compatibility work

Local-only workspace material should go in ignored directories such as:

- `.codex/`
- `.agents/`
- `.notes/`
- `.tmp/`

## Install

From source:

```bash
git clone https://github.com/<owner>/zotero-headless.git
cd zotero-headless
PYTHONPATH=src python3 -m zotero_headless capabilities
```

Main entrypoints:

```bash
zotero-headless
zotero-headless-daemon
zotero-headless-mcp
```

Short aliases:

```bash
zhl
zhl-daemon
zhl-mcp
```

## Quick Start

Run the setup flow:

```bash
zhl setup start
```

`setup start` tries autodiscovery first and then falls back to prompts for anything still missing.

Autodiscovery looks for:

- standard Zotero data directories such as `~/Zotero`
- common Zotero desktop binary locations
- already-saved API credentials and remote-library selections

Then the wizard will:

- ask for your local Zotero data directory
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

```bash
zhl config autodiscover
```

You can also reconfigure specific parts later:

```bash
zhl setup account
zhl setup libraries
zhl setup local
```

For non-interactive automation, you can still initialize configuration directly:

```bash
python -m zotero_headless config init \
  --data-dir "$HOME/Zotero" \
  --api-key "$ZOTERO_API_KEY" \
  --user-id 123456 \
  --remote-library-id user:123456 \
  --remote-library-id group:654321 \
  --default-library-id user:123456
```

Run the daemon runtime:

```bash
zhl-daemon serve --host 127.0.0.1 --port 8787 --sync-interval 300
```

Run the API directly without the daemon wrapper:

```bash
zhl api serve --host 127.0.0.1 --port 8787
```

Run the MCP server:

```bash
zhl-mcp
```

API exposure works in two modes:

- `zotero-headless api serve`
  - standalone HTTP API process
- `zotero-headless-daemon serve`
  - daemon runtime that hosts the same HTTP API plus runtime state and background sync

So no, the API is not only exposed on `zotero-headless-daemon`.

Inspect capabilities and daemon state:

```bash
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

```bash
zotero-headless local libraries
zotero-headless local import
zotero-headless local poll
zotero-headless local plan-apply --library local:1
zotero-headless local apply --library local:1
```

Remote sync:

```bash
zotero-headless sync canonical-discover
zotero-headless sync canonical-pull --library user:123456
zotero-headless sync canonical-push --library user:123456
zotero-headless sync conflicts --library user:123456
```

qmd flows:

```bash
zotero-headless qmd export
zotero-headless qmd query "retrieval augmented generation"
```

MCP/client setup:

```bash
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

```bash
zotero-headless skill install codex
zotero-headless skill install claude-code
zotero-headless skill install gemini-cli
zotero-headless skill install cline
zotero-headless skill install antigravity
zotero-headless skill install openclaw
zotero-headless skill install opencode
```

## What Is Implemented vs. What Is Still Narrow

Implemented:

- canonical headless store and mutation log
- runtime daemon, API, and MCP server
- Zotero web sync for remote libraries
- local desktop import and polling
- narrow local writeback/apply support for the supported item, collection, note, annotation, and attachment paths
- remote attachment handling for the currently supported stored-file and snapshot-style paths
- Better BibTeX-oriented citekey handling

Still intentionally narrow:

- some local desktop writeback edge cases
- full Zotero file-sync parity across every attachment mode and conflict case
- broader packaging/release polish

## Documentation

- [ARCHITECTURE.md](./docs/ARCHITECTURE.md)
- [IMPLEMENTATION_PLAN.md](./docs/IMPLEMENTATION_PLAN.md)
- [ZOTERO_SOURCE_NOTES.md](./docs/ZOTERO_SOURCE_NOTES.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)

## References

- [Zotero Repository](https://github.com/zotero/zotero)
- [Zotero Web API Syncing](https://www.zotero.org/support/dev/web_api/v3/syncing)
- [Direct SQLite Database Access](https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access)
- [qmd README](https://github.com/tobi/qmd)
