# zotero-headless-codex

Codex plugin for [zotero-headless](https://github.com/robinradx/zotero-headless) that packages MCP access, task-specific Zotero skills, focused Codex agents, and a lightweight startup status check.

## Prerequisites

- [zotero-headless](https://github.com/robinradx/zotero-headless) installed
- Zotero API key configured with `zhl setup account`
- Codex desktop or CLI with local plugins enabled

## Installation

```bash
zhl plugin install codex
```

That copies this bundle into `~/plugins/zotero-headless-codex`, refreshes its bundled MCP config from your local `zotero-headless` settings, and updates `~/.agents/plugins/marketplace.json`.

## Components

### MCP Server

Provides the `zotero-headless-mcp` server for structured library reads, mutations, sync, recovery, and local desktop interoperability.

### Skills

| Skill | Purpose |
|------|---------|
| `zotero-headless` | Core workflow guide and interface selection |
| `zotero-search` | Retrieval strategy: semantic, vector, keyword, direct reads |
| `zotero-sync` | Remote sync lifecycle and conflict handling |
| `zotero-recovery` | Snapshots, restore flows, backup repositories |
| `zotero-local` | Local Zotero desktop import and writeback safety |
| `zotero-setup` | Configuration and installation guidance |
| `zotero-status` | Health checks and environment status |

### Agents

| Agent | Purpose |
|------|---------|
| `library-researcher` | Deep multi-strategy exploration across Zotero libraries |
| `sync-resolver` | Diagnose sync failures and propose conflict resolution |

### Hooks

| Event | Purpose |
|------|---------|
| `SessionStart` | Show a quick `zotero-headless` availability/status line |

## Recommended Flow

1. Confirm health with the startup hook or `zotero-status`.
2. Pull remote state before exact reads or writes.
3. Use `zotero-search` guidance for retrieval strategy selection.
4. Snapshot before risky operations.
5. Use the `sync-resolver` agent when sync gets messy instead of retrying blindly.
