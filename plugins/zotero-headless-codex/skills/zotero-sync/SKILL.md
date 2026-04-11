---
name: zotero-sync
description: Use this skill when the user wants to sync Zotero libraries, discover remote libraries, pull changes, push local edits, inspect conflicts, or recover from sync failures.
---

# Zotero Sync — Remote Library Synchronization

Zotero-headless supports version-aware bidirectional sync for personal and group Zotero libraries.

## Sync Lifecycle

### 1. Discover Remote Libraries

Discover what the configured API key can access:

- MCP: `zotero_sync_discover`
- CLI: `zhl raw sync discover`

### 2. Pull Remote State

Fetch the latest state before exact reads or writes:

- MCP: `zotero_sync_pull`
- CLI: `zhl raw sync pull --library <library_id>`

Pulls are incremental after the first full sync.

### 3. Mutate Locally

Use MCP mutation tools against the canonical store:

- `zotero_create_item`
- `zotero_update_item`
- `zotero_delete_item`
- collection mutation tools

### 4. Push Changes

Send local changes back to zotero.org:

- MCP: `zotero_sync_push`
- CLI: `zhl raw sync push --library <library_id>`

### 5. Handle Conflicts

If push fails, inspect conflicts before retrying:

- MCP: `zotero_sync_conflicts`
- CLI: `zhl raw sync conflicts --library <library_id>`

## Conflict Resolution

Two main strategies:

### Rebase / Keep Local

Use when the local edit is intentional and should survive:

- MCP: `zotero_sync_conflict_rebase`

### Accept Remote

Use when remote state is authoritative or local edits were accidental:

- MCP: `zotero_sync_conflict_accept_remote`

## Safe Resolution Workflow

1. Pull the library.
2. Inspect conflicts.
3. Decide item by item whether to keep local or accept remote.
4. Resolve conflicts.
5. Push again.

## Mirror Store

Use mirror sync when you need a read-only remote copy without touching canonical local state:

- `zotero_sync_mirror_discover`
- `zotero_sync_mirror_pull`

## Best Practices

- Pull before push.
- Snapshot before bulk edits or bulk resolutions.
- Check permissions for group libraries before assuming writes will succeed.
- Treat repeated push failures as a conflict diagnosis problem, not as a retry problem.
