---
name: zotero-status
description: Use this skill when the user wants a zotero-headless health check, environment summary, daemon status review, or library status report.
---

# Zotero Headless Status Check

Perform a concise but useful health check of the user's zotero-headless environment.

## Standard Check

Run:

```bash
zhl daemon status
zhl capabilities
```

Report:
- Whether the daemon is running
- Which interfaces are available
- Whether qmd and citation export are enabled
- Any obvious warnings

## Verbose Check

When the user asks for more detail, also run:

```bash
zhl doctor
zhl version
zhl raw core status
```

Additionally report:
- Installed version
- Config path
- Data and state directories
- Local Zotero detection
- API key status
- Per-library status and counts

## Presentation Rules

- Start with a one-paragraph summary.
- Call out issues explicitly: missing API key, daemon down, stale sync, qmd unavailable, unresolved conflicts.
- Keep the output readable; do not dump raw command output without summarizing it.
