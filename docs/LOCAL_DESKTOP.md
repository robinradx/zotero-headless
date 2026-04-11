# Local Desktop Interoperability

This guide covers the path where `zotero-headless` works with an existing Zotero Desktop profile.

## What This Path Is For

Use it when:

- Zotero Desktop is already part of your workflow
- you want to import local libraries into the headless runtime
- you want staged planning and narrow apply support back to that local profile

## What It Touches

- `zotero.sqlite`
- the Zotero `storage/` directory

The important safety model is:

1. import local desktop state into the canonical store
2. make or queue changes there
3. inspect the planned apply step
4. apply only the supported subset back to the local profile

## Typical Workflow

Configure local access:

```text
zhl setup local
```

Import the local profile:

```text
zhl local import
```

Inspect planned local writes:

```text
zhl local plan-apply --library local:1
```

Apply supported staged writes:

```text
zhl local apply --library local:1
```

## What Is Currently Supported

The local interoperability layer focuses on:

- collection import and staged apply
- item import and supported scalar fields
- notes
- annotations
- supported attachment metadata and file mapping
- citation-key compatibility

Zotero 9 note:

- native `citationKey` fields are preserved when present locally
- fallback through `extra` remains in place for compatibility

## What This Path Is Not

It is not:

- unrestricted direct SQLite editing
- a claim of full Zotero Desktop feature parity
- a replacement for Zotero Desktop itself

Unsupported or risky local writes should stay explicit, blocked, or staged until supported properly.
