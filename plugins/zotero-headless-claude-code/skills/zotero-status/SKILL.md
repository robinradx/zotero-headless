---
name: zotero-status
description: This skill should be used when the user asks to "check zotero status", "zotero status", "is zotero running", "library status", "daemon status", or wants a health check of their zotero-headless environment.
argument-hint: "[verbose]"
allowed-tools: ["Bash"]
---

# Zotero Headless Status Check

Perform a comprehensive health check of the zotero-headless environment and report findings.

## Standard Check

Run these commands and present a consolidated status report:

```bash
zhl daemon status
zhl capabilities
```

Report:
- Daemon: running or stopped, host/port if running
- Capabilities: available interfaces (CLI, API, MCP), qmd status, citation export status
- Libraries: list of configured libraries with sync state

## Verbose Check

When the user passes "verbose" or asks for detailed status, also run:

```bash
zhl doctor
zhl version
```

Additionally report:
- Version information
- Config file location and validity
- Data and state directory paths
- Local Zotero detection status
- API key configuration status
- qmd installation status

## Library Details

If libraries are available, list them with their state:

```bash
zhl raw core status
```

Report per library:
- Library ID and name
- Item and collection counts
- Last sync version
- Pending changes (if any)

## Presentation

Present the status as a concise summary table. Flag any issues prominently:
- Missing API key
- Daemon not running (if expected)
- Stale sync (last sync > 24h ago)
- qmd unavailable (search degraded)
- Pending unresolved conflicts
