---
name: zotero-recovery
description: This skill should be used when the user asks to "backup Zotero", "create snapshot", "restore library", "rollback changes", "recovery", "backup repository", "undo sync", or when operations may risk data loss. Covers snapshot creation, restore planning, and backup replication.
---

# Zotero Recovery — Snapshots, Restore, and Backup

Zotero-headless provides immutable full-state snapshots with restore capabilities and off-machine backup replication.

## When to Snapshot

Create snapshots before any risky operation:
- Before bulk item edits or deletions
- Before pushing large changesets to remote
- Before local apply operations
- Before restore operations (automatic)
- Before any experimental workflow

Automatic snapshot hooks fire after remote pull, before/after remote push, after local import, before/after local apply, and before every restore.

## Creating Snapshots

```
MCP:  zotero_recovery_snapshot_create  (reason: "before bulk edits")
CLI:  zhl recovery snapshot-create --reason "before bulk edits"
```

A snapshot captures: canonical DB, mirror DB, cached files, qmd export state, and citation export data. Each snapshot includes a manifest with SHA-256 hashes and library inventory.

## Listing and Verifying Snapshots

```
MCP:  zotero_recovery_snapshot_list
CLI:  zhl recovery snapshot-list

MCP:  zotero_recovery_snapshot_verify  (snapshot_id: "...")
```

Verification checks all file hashes against the manifest to ensure integrity.

## Restore Workflow

Restore is a two-phase process: plan, then execute.

### 1. Plan the Restore

```
MCP:  zotero_recovery_restore_plan  (snapshot_id: "...", library_id: "user:123456")
CLI:  zhl recovery restore-plan --snapshot <id> --library group:123
```

The plan shows what will change — review it before executing.

### 2. Execute the Restore

```
MCP:  zotero_recovery_restore_execute  (snapshot_id: "...", library_id: "...", confirm: true)
CLI:  zhl recovery restore-execute --snapshot <id> --library group:123 --confirm
```

The `confirm` flag is required — restore will not execute without it.

### 3. Review Restore History

```
MCP:  zotero_recovery_restore_list
MCP:  zotero_recovery_restore_show  (run_id: "...")
```

## Backup Repositories

Snapshots can be replicated to off-machine backup repositories:

```
MCP:  zotero_recovery_repositories
CLI:  zhl recovery repositories
```

### Supported Repository Types

| Type | Description |
|------|-------------|
| `local` | Built-in, always available |
| `filesystem` | Any mounted filesystem path |
| `rsync` | Remote via rsync over SSH |
| `s3` | AWS S3 bucket (via AWS CLI) |

### Push/Pull Snapshots

```
Push to backup:  zotero_recovery_snapshot_push  (snapshot_id, repo)
Pull from backup: zotero_recovery_snapshot_pull  (snapshot_id, repo)
```

## Best Practices

- **Snapshot proactively** — create snapshots before risky operations, not after problems occur.
- **Always plan before restoring** — review the restore plan to understand what will change.
- **Verify snapshot integrity** — run verification after creating snapshots, especially before critical restores.
- **Use off-machine backups** — replicate important snapshots to S3 or rsync repositories.
- **Name snapshots descriptively** — use the reason field to document why the snapshot was created.
