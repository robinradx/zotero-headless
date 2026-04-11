# Recovery And Backup

This guide covers the built-in recovery subsystem in `zotero-headless`.

It is designed as an operational safety layer for all library types:

- `headless:*`
- `local:*`
- `user:*`
- `group:*`

The goal is not just “show history”. The goal is:

- create immutable safety snapshots before risky operations
- restore full daemon state when local state is corrupted
- stage logical rollback plans for a single library
- replicate snapshots off-machine to backup storage

## What A Snapshot Contains

A recovery snapshot includes the full headless state boundary managed by `zotero-headless`:

- `canonical.sqlite`
- `headless.sqlite` when present
- cached files under `files/`
- qmd export output under `qmd-export/`
- citation export artifact
- a manifest with hashes, source paths, and library inventory

Snapshots are stored under:

```text
<state_dir>/snapshots/
```

Recovery runtime metadata is stored under:

```text
<state_dir>/recovery/
```

That directory records restore runs and append-only recovery events.

## Automatic Snapshot Hooks

When `recovery_auto_snapshots` is enabled, the runtime automatically creates snapshots around important boundaries:

- after remote pull
- before remote push
- after successful remote push
- after local import
- before local apply
- after local apply
- before every restore execution

## Repository Backends

The recovery subsystem always has one built-in repository:

- `local`

Additional repositories are configured through `backup_repositories` in the main config.

Supported repository types:

- `filesystem`
- `rsync`
- `s3`

Example:

```json
{
  "state_dir": "/srv/zotero-headless/state",
  "backup_repositories": [
    {
      "name": "archive-disk",
      "type": "filesystem",
      "path": "/mnt/zhl-backups"
    },
    {
      "name": "lab-rsync",
      "type": "rsync",
      "target": "backup@example.org:/srv/zhl-snapshots"
    },
    {
      "name": "s3-primary",
      "type": "s3",
      "uri": "s3://my-zhl-backups/prod"
    }
  ]
}
```

Notes:

- `filesystem` copies the immutable snapshot directory to another local or mounted path.
- `rsync` shells out to `rsync -a`.
- `s3` shells out to `aws s3 sync`, so AWS credentials and the AWS CLI must already be available in the environment.

## CLI

Human-friendly commands:

```text
zhl recovery repositories
zhl recovery snapshot-create --reason manual
zhl recovery snapshot-list
zhl recovery snapshot-show <snapshot_id>
zhl recovery snapshot-verify <snapshot_id>
zhl recovery snapshot-push <snapshot_id> --repository archive-disk
zhl recovery snapshot-pull <snapshot_id> --repository s3-primary
zhl recovery restore-plan --snapshot <snapshot_id> --library group:123
zhl recovery restore-list
zhl recovery restore-show <run_id>
zhl recovery restore-execute --snapshot <snapshot_id> --library group:123 --confirm
```

Machine-oriented raw commands:

```text
zhl raw recovery repositories
zhl raw recovery snapshot create --reason manual
zhl raw recovery snapshot list
zhl raw recovery snapshot show <snapshot_id>
zhl raw recovery snapshot verify <snapshot_id>
zhl raw recovery snapshot push <snapshot_id> --repository archive-disk
zhl raw recovery snapshot pull <snapshot_id> --repository s3-primary
zhl raw recovery restore plan --snapshot <snapshot_id> --library group:123
zhl raw recovery restore list
zhl raw recovery restore show <run_id>
zhl raw recovery restore execute --snapshot <snapshot_id> --library group:123 --confirm
```

## HTTP API

Read endpoints:

- `GET /recovery/repositories`
- `GET /recovery/snapshots?limit=20`
- `GET /recovery/snapshots/<snapshot_id>`
- `GET /recovery/restores?limit=20`
- `GET /recovery/restores/<run_id>`

Mutation endpoints:

- `POST /recovery/snapshots`
- `POST /recovery/snapshots/<snapshot_id>/verify`
- `POST /recovery/snapshots/<snapshot_id>/push`
- `POST /recovery/snapshots/<snapshot_id>/pull`
- `POST /recovery/restore/plan`
- `POST /recovery/restore/execute`

## Restore Modes

There are two restore modes.

### Full-State Restore

Use this when the local headless runtime itself is damaged.

This restores:

- canonical DB
- mirror DB when present
- files
- qmd export
- citation export

Command shape:

```text
zhl recovery restore-execute --snapshot <snapshot_id> --confirm
```

### Library-Scoped Restore

Use this when one logical library needs to be rolled back.

This mode:

1. loads the snapshot canonical DB
2. computes a diff for the target library
3. stages rollback changes into the current canonical store
4. optionally pushes those changes to remote Zotero or applies them to the local Zotero DB

Remote follow-up:

```text
zhl recovery restore-execute --snapshot <snapshot_id> --library group:123 --push-remote --confirm
```

Local follow-up:

```text
zhl recovery restore-execute --snapshot <snapshot_id> --library local:1 --apply-local --confirm
```

## Audit Trail

Every restore execution now creates a persisted restore run record with:

- `run_id`
- `snapshot_id`
- optional `library_id`
- status
- timestamps
- stored plan
- stored result
- stored error text on failure
- pre-restore safety snapshot id

Recovery events are also appended to:

```text
<state_dir>/recovery/events.jsonl
```

## Limits Of The Current Implementation

Current behavior is intentionally conservative:

- remote rollback still goes through normal sync semantics
- local rollback still goes through staged local apply semantics
- `rsync` and `s3` depend on external commands already being installed
- there is no background replication scheduler yet
- there is no retention pruning policy yet
- there is no write-freeze lock manager yet

The important part is that snapshot format, replication, verification, restore planning, and restore execution are already integrated through the same recovery model.
