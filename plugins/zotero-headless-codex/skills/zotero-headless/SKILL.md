---
name: zotero-headless
description: Use this skill when the user is working with Zotero libraries, citations, academic references, zotero-headless MCP tools, or the `zhl` CLI from Codex. It establishes interface selection, core workflow ordering, and the main anti-patterns to avoid.
---

# Zotero Headless — Core Workflow Guide

Zotero-headless exposes three first-class interfaces for managing Zotero libraries without the Zotero GUI. Pick the interface that matches the job instead of forcing everything through one path.

## Interface Selection

### MCP Tools

Best for structured CRUD, search, sync, recovery, and local adapter operations when Codex already has the plugin installed.

Use MCP for:
- Listing libraries, items, and collections
- Getting exact item metadata
- Creating, updating, and deleting items or collections
- Pull, push, and conflict inspection
- Recovery snapshots and restore planning

### CLI (`zhl` / `zhl raw`)

Best for setup, diagnostics, daemon checks, local SQL, and explicit admin flows.

Use CLI for:
- Setup and configuration: `zhl setup start`, `zhl setup account`, `zhl setup libraries`
- Diagnostics: `zhl doctor`, `zhl capabilities`, `zhl version`
- Plugin installation: `zhl plugin install codex`
- Daemon status: `zhl daemon status`
- Local SQL: `zhl raw local sql "SELECT ..."`

Prefer `zhl raw` when you need machine-readable output.

### HTTP API

Best for daemon lifecycle, background jobs, health checks, and metrics when a running daemon is reachable.

Use HTTP when you need:
- `/health`
- `/daemon/status`
- `/daemon/jobs`
- `/metrics`

## Core Workflow

1. Assess runtime state with `zhl capabilities` or `zhl daemon status`.
2. Discover remote libraries before remote work.
3. Pull before exact reads if the current source of truth is zotero.org.
4. Use semantic or vector search for exploration and direct reads for exact metadata.
5. Snapshot before risky write flows.
6. Push after mutations, and inspect conflicts before any retry.

## Library ID Formats

- `user:123456` for a personal Zotero library
- `group:654321` for a group library
- `local:1` for a local Zotero desktop profile
- `headless:1` for a pure headless library

## Anti-Patterns

- Do not use semantic search for exact citation metadata.
- Do not write directly to the Zotero desktop database outside the supported local apply flow.
- Do not retry failed pushes blindly.
- Do not assume a remote library is fresh without a pull.

## Specialized Skills

Use the focused skills in this plugin when the task narrows:
- `zotero-search` for retrieval strategy
- `zotero-sync` for remote sync and conflicts
- `zotero-recovery` for snapshots and restore
- `zotero-local` for desktop interoperability
- `zotero-setup` for configuration
- `zotero-status` for health checks
