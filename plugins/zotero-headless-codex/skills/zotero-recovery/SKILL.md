---
name: zotero-recovery
description: Use this skill when the user wants snapshots, backups, restore planning, rollback guidance, or any recovery workflow around risky Zotero operations.
---

# Zotero Recovery — Snapshots, Restore, and Backup

Zotero-headless provides immutable snapshots, planned restores, and optional off-machine backup replication.

## When to Snapshot

Create snapshots before:
- Bulk edits or deletes
- Large sync pushes
- Local apply operations
- Restore operations
- Any risky experimental migration

## Create Snapshots

- MCP: `zotero_recovery_snapshot_create`
- CLI: `zhl recovery snapshot-create --reason "before bulk edits"`

A snapshot captures canonical state, mirror state, cache state, qmd export state, and citation export data.

## List and Verify Snapshots

- `zotero_recovery_snapshot_list`
- `zotero_recovery_snapshot_verify`

Verification checks file hashes against the snapshot manifest.

## Restore Workflow

Always restore in two phases.

### 1. Plan

- MCP: `zotero_recovery_restore_plan`
- CLI: `zhl recovery restore-plan --snapshot <id> --library <library_id>`

### 2. Execute

- MCP: `zotero_recovery_restore_execute`
- CLI: `zhl recovery restore-execute --snapshot <id> --library <library_id> --confirm`

Restore requires explicit confirmation.

## Backup Repositories

Available repository types include:
- `local`
- `filesystem`
- `rsync`
- `s3`

Use repository listing and snapshot push/pull operations when snapshots need to live off-machine.

## Best Practices

- Snapshot before the risky step, not after it.
- Review restore plans before executing them.
- Verify critical snapshots.
- Use descriptive snapshot reasons so recovery history is legible later.
