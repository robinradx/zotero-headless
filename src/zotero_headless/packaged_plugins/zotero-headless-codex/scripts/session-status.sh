#!/bin/bash
set -euo pipefail

# Lightweight availability check for new Codex sessions.
# Never fail the session if zotero-headless is not installed yet.

if ! command -v zhl >/dev/null 2>&1; then
  echo "zotero-headless: zhl CLI not found. Run 'pip install zotero-headless' and 'zhl plugin install codex'."
  exit 0
fi

version="$(zhl version 2>/dev/null | head -1 || true)"
daemon_status="$(zhl daemon status 2>/dev/null | head -1 || true)"

if [ -z "$version" ]; then
  version="version: unknown"
fi

if [ -z "$daemon_status" ]; then
  daemon_status="daemon: unavailable"
fi

echo "zotero-headless: ${version} | ${daemon_status}"
