# Remote Sync

This guide covers syncing against zotero.org through the Zotero Web API.

## What You Need

- a Zotero Web API key
- at least one configured remote library
- a local canonical store managed by `zotero-headless`

The Zotero 9 browser-based desktop login flow does not replace the API key used here.

## What It Supports

- personal libraries
- group libraries
- pull and push flows
- version-aware sync
- conflict reporting
- supported attachment upload and download paths
- supported fulltext refresh paths

## Typical Workflow

Run setup:

```text
zhl setup start
```

Discover libraries:

```text
zhl sync discover
```

Pull a library:

```text
zhl sync pull --library user:123456
```

Push staged changes:

```text
zhl sync push --library user:123456
```

Check conflicts:

```text
zhl sync conflicts --library user:123456
```

## How To Think About It

Remote sync is an adapter around the clean-room runtime.

That means:

- remote objects are pulled into canonical state
- local edits are staged there first
- pushes back to zotero.org use version-aware remote operations
- conflicts are part of the model, not an edge case to ignore

## Zotero 9 Note

Zotero 9 introduced native citation-key support in the desktop app. `zotero-headless` now:

- attempts native `citationKey` writes on remote item create/update
- falls back automatically when the remote API behavior does not accept that field

That keeps newer behavior available without breaking compatibility with older server-side expectations.
