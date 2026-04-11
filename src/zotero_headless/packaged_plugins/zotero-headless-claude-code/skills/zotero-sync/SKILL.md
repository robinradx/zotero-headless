---
name: zotero-sync
description: This skill should be used when the user asks to "sync Zotero", "pull library", "push changes", "resolve conflicts", "sync conflicts", "discover libraries", "remote sync", or when sync operations fail or conflicts are detected. Covers the full remote sync lifecycle including conflict resolution.
---

# Zotero Sync — Remote Library Synchronization

Zotero-headless provides version-aware bidirectional sync with the Zotero Web API for personal (`user:*`) and group (`group:*`) libraries.

## Sync Lifecycle

### 1. Discover Remote Libraries

Before syncing, discover available libraries:

```
MCP:  zotero_sync_discover
CLI:  zhl raw sync discover
```

Returns all libraries the configured API key can access, with IDs and permissions.

### 2. Pull Remote State

Fetch the latest state from zotero.org:

```
MCP:  zotero_sync_pull  (library_id: "user:123456")
CLI:  zhl raw sync pull --library user:123456
```

Pull is incremental — only fetches changes since last sync version. First pull downloads the full library.

**Always pull before:**
- Reading items from a remote library
- Pushing local changes (to detect conflicts early)

### 3. Mutate Locally

Create, update, or delete items using MCP tools:

```
MCP:  zotero_create_item, zotero_update_item, zotero_delete_item
      zotero_create_collection, zotero_update_collection, zotero_delete_collection
```

All mutations go to the canonical headless store and are tracked in the changelog.

### 4. Push Changes

Send local changes to zotero.org:

```
MCP:  zotero_sync_push  (library_id: "user:123456")
CLI:  zhl raw sync push --library user:123456
```

Push is version-aware — it sends only items changed since last sync.

### 5. Handle Conflicts

If push fails due to version conflicts, inspect before retrying:

```
MCP:  zotero_sync_conflicts  (library_id: "user:123456")
CLI:  zhl raw sync conflicts --library user:123456
```

## Conflict Resolution

Two resolution strategies:

### Rebase (Keep Local Changes)

Apply local edits on top of the latest remote state:

```
MCP:  zotero_sync_conflict_rebase  (library_id, item_key)
```

Use when: local changes are intentional and should take precedence.

### Accept Remote

Discard local edits and adopt the remote version:

```
MCP:  zotero_sync_conflict_accept_remote  (library_id, item_key)
```

Use when: remote changes are authoritative or local edits were accidental.

### Resolution Workflow

1. Pull to get latest remote state.
2. List conflicts to see what diverged.
3. For each conflict, decide: rebase or accept-remote.
4. Resolve all conflicts.
5. Push again.

## Mirror Store

The mirror store holds read-only copies of remote state for fast lookups without affecting the canonical store:

```
MCP:  zotero_sync_mirror_discover, zotero_sync_mirror_pull
```

Use mirror operations when only read access is needed and canonical store should remain unchanged.

## Best Practices

- **Pull before push** — always fetch latest remote state to minimize conflicts.
- **Inspect conflicts before retrying** — never retry a failed push blindly.
- **Use incremental sync** — avoid full re-pulls unless diagnosing issues.
- **Check library permissions** — group libraries may have restricted write access.
- **Snapshot before bulk operations** — create a recovery snapshot before mass edits or syncs.
