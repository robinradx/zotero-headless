---
name: zotero-setup
description: This skill should be used when the user asks to "setup zotero", "configure zotero-headless", "install zotero MCP", "connect Zotero account", "zotero API key", or wants to set up or reconfigure their zotero-headless installation.
argument-hint: "[account|libraries|local|mcp]"
allowed-tools: ["Bash", "Read", "Write", "Edit"]
---

# Zotero Headless Setup

Guide the user through configuring zotero-headless for their environment.

## Prerequisites Check

Run diagnostics first to assess current state:

```bash
zhl doctor
```

This reveals: installed version, config file location, API key status, data/state directories, local Zotero detection, qmd availability, and daemon status.

## Setup Flows

### Full Guided Setup

For first-time setup, run the interactive wizard:

```bash
zhl setup start
```

The wizard auto-discovers local Zotero installations, prompts for API key and user ID, and configures remote libraries.

### Account Configuration

Configure Zotero API credentials:

```bash
zhl setup account
```

Requires:
- **Zotero User ID** — found at https://www.zotero.org/settings/keys
- **API Key** — create at https://www.zotero.org/settings/keys/new (grant read/write access)

Alternatively, set via environment variables:
- `ZOTERO_HEADLESS_API_KEY`

### Library Configuration

Select which remote libraries to sync:

```bash
zhl setup libraries
```

### Local Desktop Path

Point to a local Zotero data directory:

```bash
zhl setup local
```

Standard paths: `~/Zotero` (macOS/Linux), `%USERPROFILE%\Zotero` (Windows).

### MCP Client Installation

Install MCP configuration for Claude Code:

```bash
zhl setup add claude-code --scope project
```

Scope options:
- `project` — writes to `.mcp.json` in project directory
- `user` — writes to user-level Claude Code config

List current MCP setups:

```bash
zhl setup list
```

## Verification

After setup, verify everything works:

```bash
zhl capabilities
zhl daemon status
```

If remote libraries are configured, test sync:

```bash
zhl raw sync discover
```

## Troubleshooting

- **"API key not configured"** — run `zhl setup account`
- **"No remote libraries"** — run `zhl setup libraries` after account setup
- **"Local Zotero not found"** — run `zhl setup local` with the correct path
- **"qmd not available"** — install the qmd CLI tool for semantic search support
- **MCP not connecting** — verify with `zhl setup list` and restart Claude Code session
