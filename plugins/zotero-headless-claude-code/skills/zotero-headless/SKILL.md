---
name: zotero-headless
description: This skill should be used when the user mentions "Zotero", "references", "citations", "academic papers", "research library", "bibliography", "BibTeX", or asks about managing a reference library. Also triggers when zotero-headless MCP tools, CLI commands (`zhl`), or HTTP API endpoints are referenced.
---

# Zotero Headless — Core Workflow Guide

Zotero-headless provides three first-class interfaces for managing Zotero libraries without the Zotero GUI. Each interface has a sweet spot — select the right one for each operation.

## Interface Selection

### MCP Tools (41 tools via `zotero-headless` MCP server)

Best for structured CRUD operations, search, and sync — native tool integration with typed parameters and responses.

Use MCP tools for:
- Listing libraries, items, collections
- Getting/creating/updating/deleting items and collections
- Search operations (semantic, vector, keyword)
- Sync pull/push and conflict inspection
- Recovery snapshots and restore operations

### CLI (`zhl` / `zhl raw`)

Best for setup, diagnostics, admin tasks, and operations requiring formatted output or interactive guidance. Execute via Bash tool.

Use CLI for:
- Setup and configuration: `zhl setup start`, `zhl setup account`, `zhl setup libraries`
- Diagnostics: `zhl doctor`, `zhl capabilities`, `zhl version`
- MCP client installation: `zhl setup add claude-code --scope project`
- Local SQL queries: `zhl raw local sql "SELECT ..."`
- Updates: `zhl update --check`, `zhl update`
- Daemon management: `zhl daemon status`, `zhl daemon command`

Prefer `zhl raw` for machine-parseable JSON output when piping or processing results programmatically.

### HTTP API (daemon at default port 23119)

Best for persistent operations, background sync, and observability. Use when the daemon is running.

Use HTTP API for:
- Daemon runtime state: `GET /daemon/status`, `GET /daemon/runtime`
- Background job monitoring: `GET /daemon/jobs`
- Prometheus metrics: `GET /metrics`
- Health checks: `GET /health`

## Core Workflow

1. **Assess runtime state** — run `zhl capabilities` or `zhl daemon status` to understand what is available.
2. **Discover remote libraries** — use MCP `zotero_sync_discover` or `zhl raw sync discover` before accessing remote data.
3. **Pull before reading** — run `zotero_sync_pull` for a library before querying its items to ensure fresh state.
4. **Search with the right tool** — use qmd semantic search (`zotero_qmd_query`) for exploratory topic retrieval; use direct MCP reads (`zotero_get_item`, `zotero_list_items`) for exact authoritative metadata.
5. **Write then sync** — create/update items via MCP mutation tools, then push with `zotero_sync_push`.
6. **On failure, check conflicts** — inspect `zotero_sync_conflicts` before retrying any failed write or push.

## Library ID Formats

- `user:123456` — personal Zotero library
- `group:654321` — group library
- `local:1` — local Zotero desktop profile
- `headless:1` — pure headless library

## Citation Export

Citation keys are auto-detected from Zotero 9 native fields with Better BibTeX fallback. Check export status with `zotero_capabilities` or `zhl citations status`. Enable auto-export with `zhl citations enable`. Export a library with `zhl citations export --library <id>`.

## Anti-Patterns

- **Do not** use qmd semantic search for exact metadata lookups — use direct MCP reads instead.
- **Do not** mutate the local Zotero desktop database directly — use the supported local apply flow only.
- **Do not** retry failed remote writes blindly — always inspect conflicts first.
- **Do not** assume libraries are synced — pull before reading remote data.

## Additional Resources

For specialized workflows, consult the dedicated skills:
- **zotero-search** — semantic vs keyword vs direct lookup guidance
- **zotero-sync** — sync workflow, conflict resolution strategies
- **zotero-recovery** — snapshots, restore, backup repositories
- **zotero-local** — local desktop import, poll, plan-apply, apply
