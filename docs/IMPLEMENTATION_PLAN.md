# Implementation Plan

## Phase 1: Research and scaffolding

Status: completed

Completed:

- verified Zotero local DB is read-only for external consumers
- verified normal Zotero sync is local-first with object `version` and `synced` state
- verified local connector API requires the Zotero app to be open
- verified qmd is best used as a derived Markdown/text index
- built a first-pass CLI/API/MCP scaffold

## Phase 2: Make the current scaffold honest

Status: completed

Tasks completed:

- keep local DB access read-only
- keep remote Web API support
- keep qmd export/search
- reject local writes unless a Zotero-backed daemon exists
- document the architecture clearly

## Phase 3: Reframe around clean-room core

Status: started

Objective:

Move the implementation target away from "headless Zotero as the whole system" and toward:

- clean-room core
- minimal daemon runtime
- first-class web sync adapter
- thin local desktop adapter

Required capabilities:

- define the core item/library/change-log model
- define the daemon/runtime boundary
- isolate Zotero-specific concerns behind adapters
- keep local desktop write strategy explicitly undecided for now

Likely output:

- core domain modules
- daemon/runtime interfaces
- adapter interfaces
- updated docs and boundaries

## Phase 4: Canonical headless store

Status: completed

Tasks:

- implement canonical DB schema
- implement operation log
- define daemon ownership of the canonical store
- move API/CLI/MCP mutation semantics onto the canonical model
- treat the mirror strictly as temporary cache/export state

## Phase 5: Minimal daemon runtime

Status: not started

Tasks:

- implement `zotero-headlessd`
- host the canonical store and service APIs there
- run sync jobs and background indexing/export work
- support server deployments with no Zotero desktop dependency

## Phase 6: Web sync adapter

Status: started

Tasks:

- implement Zotero web sync semantics from the official protocol
- support user and group libraries from day one
- track remote library versions and per-object sync state
- handle conflict detection and sync retries explicitly

## Phase 7: Local desktop adapter

Status: started

Tasks:

- import from local Zotero data directories
- detect local desktop changes
- define attachment/storage mapping
- expand the current experimental narrow apply layer
- defer the final full local write mechanism decision until the core and web sync layers are mature

Decision point:

- extracted Zotero-compatible apply layer
- or tiny Zotero-backed daemon

## Phase 8: Search layer

Status: partially started

Tasks:

- define canonical Markdown export format
- include items, notes, annotations, and extracted attachment text
- add incremental export/update tracking
- optionally compare qmd with `zotero-rag`-style chunking/extraction ideas

## Phase 9: API and MCP stabilization

Status: partially started

Tasks:

- define stable schemas for items, collections, libraries, and sync jobs
- add explicit capability reporting:
  - local read-only
  - remote write available
  - daemon runtime available
  - web sync adapter available
  - local desktop adapter read available
  - local desktop adapter write available
- surface graceful errors for unsupported operations
