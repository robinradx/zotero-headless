# zotero-headless-claude-code

Claude Code plugin for [zotero-headless](https://github.com/robinradx/zotero-headless) — search, sync, and manage Zotero libraries directly from Claude Code.

## Prerequisites

- [zotero-headless](https://github.com/robinradx/zotero-headless) installed (`pip install zotero-headless`)
- Zotero API key configured (`zhl setup account`)
- Claude Code

## Installation

```bash
# Test locally
claude --plugin-dir /path/to/zotero-headless-claude-code

# Or install MCP config via zotero-headless
zhl setup add claude-code --scope project
```

## Components

### MCP Server

Provides 41 native tools for library management, search, sync, and recovery via the `zotero-headless-mcp` server.

### Skills

| Skill | Type | Description |
|-------|------|-------------|
| `zotero-headless` | Knowledge | Core workflow guide — interface selection, anti-patterns |
| `zotero-search` | Knowledge | Search strategy — semantic vs keyword vs direct reads |
| `zotero-sync` | Knowledge | Sync lifecycle — discover, pull, push, conflict resolution |
| `zotero-recovery` | Knowledge | Snapshots, restore, backup repositories |
| `zotero-local` | Knowledge | Local desktop interop — import, plan-apply, apply |
| `zotero-setup` | User-invoked | `/zotero-setup` — guided configuration |
| `zotero-status` | User-invoked | `/zotero-status` — environment health check |

### Agents

| Agent | Triggers | Purpose |
|-------|----------|---------|
| `library-researcher` | Deep research queries about library contents | Autonomous multi-strategy search with synthesis |
| `sync-resolver` | Sync failures, conflict detection | Diagnose and resolve sync conflicts |

### Hooks

| Event | Purpose |
|-------|---------|
| `SessionStart` | Check zotero-headless availability and show status |

## Three Interfaces

The plugin leverages all three zotero-headless interfaces:

- **MCP tools** — structured CRUD, search, sync (native tool integration)
- **CLI** (`zhl` / `zhl raw`) — setup, diagnostics, admin, local SQL (via Bash)
- **HTTP API** — daemon lifecycle, background sync, metrics (when daemon runs)

## Quick Start

1. Install zotero-headless: `pip install zotero-headless`
2. Run setup: `zhl setup start`
3. Load plugin in Claude Code
4. Check status: `/zotero-status`
5. Search your library: "Find papers about X in my Zotero"
