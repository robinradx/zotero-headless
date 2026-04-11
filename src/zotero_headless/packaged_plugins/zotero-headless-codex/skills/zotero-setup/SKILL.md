---
name: zotero-setup
description: Use this skill when the user wants to install, configure, or troubleshoot zotero-headless, including account setup, library selection, local profile setup, or Codex plugin installation.
---

# Zotero Headless Setup

Guide the user through configuring zotero-headless for the environment they are actually using.

## Diagnostics First

Start with:

```bash
zhl doctor
```

This checks version, config location, API key state, data directories, local Zotero detection, qmd availability, and daemon status.

## Setup Flows

### Full Guided Setup

```bash
zhl setup start
```

Use this for first-time setup.

### Account Configuration

```bash
zhl setup account
```

Requires:
- Zotero user ID
- Zotero API key with the required permissions

### Library Configuration

```bash
zhl setup libraries
```

### Local Desktop Path

```bash
zhl setup local
```

### Codex Plugin Installation

```bash
zhl plugin install codex
```

This installs the local Codex plugin bundle. For raw MCP config only, `zhl setup add codex --scope user` still exists, but the plugin path is the richer install.

## Verification

After setup:

```bash
zhl capabilities
zhl daemon status
zhl setup list
```

If remote libraries are configured:

```bash
zhl raw sync discover
```

## Troubleshooting

- Missing API key: run `zhl setup account`
- Missing libraries: run `zhl setup libraries`
- Missing local Zotero path: run `zhl setup local`
- Degraded search: install qmd and re-check capabilities
- Codex plugin not appearing: restart Codex or refresh plugins after `zhl plugin install codex`
