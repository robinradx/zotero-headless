#!/bin/bash
set -euo pipefail

# Quick zotero-headless availability check on session start.
# Outputs a brief status line; exits 0 regardless to avoid blocking.

if ! command -v zhl &>/dev/null; then
  echo "zotero-headless: zhl CLI not found. Run 'pip install zotero-headless' to install."
  exit 0
fi

# Capture daemon status (non-blocking, short timeout)
daemon_status=$(timeout 3 zhl daemon status 2>/dev/null || echo "daemon: not running")

# Capture version
version=$(zhl version 2>/dev/null | head -1 || echo "version: unknown")

echo "zotero-headless: ${version} | ${daemon_status}"
