# Documentation

This folder is for people using or maintaining `zotero-headless`.

Start here if you want to understand which part of the tool you need, how to drive it from the terminal, or how to connect an agent client over MCP or HTTP.

## Guides

- [USE_CASES.md](./USE_CASES.md)
  - which workflow fits your setup: desktop with Zotero installed, headless server, remote-sync-first, or agent integration
- [CLI.md](./CLI.md)
  - human-oriented command guide for setup, local interoperability, sync, qmd, citations, daemon, and machine-oriented `raw` usage
- [API_AND_MCP.md](./API_AND_MCP.md)
  - when to use HTTP vs MCP, how to start each one, and how agent setup fits in
- [LOCAL_DESKTOP.md](./LOCAL_DESKTOP.md)
  - how local profile import, staged planning, and narrow apply/writeback work
- [REMOTE_SYNC.md](./REMOTE_SYNC.md)
  - how remote Zotero Web API sync works for personal and group libraries
- [DESKTOP_HELPER.md](./DESKTOP_HELPER.md)
  - optional contributor workflow for the externally patched Zotero helper path
- [ZOTERO_SOURCE_NOTES.md](./ZOTERO_SOURCE_NOTES.md)
  - upstream Zotero source areas that matter when validating local compatibility or helper behavior

## Quick Orientation

If you already have Zotero Desktop and want `zotero-headless` to work with it:

- read [USE_CASES.md](./USE_CASES.md)
- then read [LOCAL_DESKTOP.md](./LOCAL_DESKTOP.md)

If you want a server-style runtime with no Zotero GUI:

- read [USE_CASES.md](./USE_CASES.md)
- then read [REMOTE_SYNC.md](./REMOTE_SYNC.md)
- then read [API_AND_MCP.md](./API_AND_MCP.md)

If you mostly care about commands:

- read [CLI.md](./CLI.md)

If you are working on the optional Zotero-backed helper experiment:

- read [DESKTOP_HELPER.md](./DESKTOP_HELPER.md)
- then read [ZOTERO_SOURCE_NOTES.md](./ZOTERO_SOURCE_NOTES.md)

## Current Baseline

- tracked upstream Zotero release: `9.0`
- main product path: clean-room headless runtime plus adapters
- optional contributor path: externally patched desktop helper
