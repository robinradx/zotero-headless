# Architecture

## Goal

Build a headless Zotero-compatible system that:

- supports local-only users
- supports synced users and group libraries
- exposes CLI, HTTP API, and MCP interfaces
- provides semantic search via qmd over derived Markdown/text

## Constraints

### 1. Direct SQLite writes are not acceptable

Zotero's official documentation explicitly warns that direct modification of `zotero.sqlite` bypasses validation and referential integrity checks and can corrupt the database or break sync behavior.

### 2. Zotero's local HTTP server is not sufficient as the main architecture

The connector HTTP server exists only when the Zotero desktop client is already open. It does not satisfy the headless requirement.

### 3. Zotero has no supported headless mode

The inherited Firefox `--headless` flag is not an intentional Zotero feature and is not sufficient on its own.

## Correct Target Architecture

### Canonical source of truth

- a clean-room headless core
- own canonical DB
- own operation log and sync bookkeeping
- own schemas for items, collections, attachments, tags, notes, annotations, and relations

### Core runtime

- our own process and APIs
- exposes:
  - local write operations
  - sync operations
  - attachment/file access
  - structured query endpoints

### Minimal daemon runtime

- `zotero-headlessd`
- hosts the clean-room core for service and headless deployments
- runs scheduled or triggered sync jobs
- exposes HTTP/RPC/MCP
- has no dependency on Zotero desktop for server mode

### Web sync adapter

- first-class component, not a later bridge
- implements Zotero web sync semantics against zotero.org
- required for synced users and group libraries

### Local desktop adapter

- thin Zotero-specific interoperability layer
- reads local Zotero desktop state
- eventually applies validated headless changes back to desktop-compatible local state
- writeback mechanism intentionally deferred until the clean-room core exists:
  - narrow extracted Zotero-compatible apply layer
  - or tiny Zotero-backed daemon

### Vendored Zotero bootstrap

- retained as a research and fallback path for the local desktop adapter
- not the system architecture for the whole product

### Derived layers

- search/export cache
  - can be rebuilt from the canonical store
- Markdown/text export
  - one file per item/note/annotation/chunked attachment text
- qmd index
  - lexical + vector + reranking search over exported text

### Interface layer

- CLI
- HTTP API
- MCP server

All of these should ultimately call the clean-room core for mutations.

## Operational Modes

### Local-only mode

- source of truth: clean-room core
- runtime: daemon in server deployments, direct local process on end-user machines
- local desktop interoperability: through the local desktop adapter
- search: qmd over exported Markdown/text
- no web dependency required

### Synced mode

- source of truth: clean-room core
- runtime: daemon for service deployments or local process on end-user machines
- sync: Zotero-compatible web sync adapter from day one
- local desktop interoperability: optional but supported through the local desktop adapter
- search: qmd over exported Markdown/text

### Server mode

- runtime: minimal daemon
- dependencies: clean-room core and web sync adapter
- Zotero desktop is optional and generally absent
- ideal for MCP/API/search automation on Linux servers

## Current Repository Status

Implemented today:

- first-pass domain boundaries for core and adapters
- initial runtime split between daemon host and optional desktop adapter
- read-only local DB inspection
- canonical local desktop snapshot import for `local:*` libraries
- canonical local desktop change polling for items and collections
- experimental narrow local desktop apply layer for a safe subset of item and collection writes
- remote Web API pull/write support
- first-pass canonical remote sync adapter
- cache/mirror for experimentation
- qmd export/search
- CLI/API/MCP scaffolding

Still required for the real solution:

- real daemon host for the clean-room core
- conflict-aware web sync completion
- local desktop write path completion beyond the current experimental subset
- file/attachment handling
- complete library sync ownership locally and remotely
