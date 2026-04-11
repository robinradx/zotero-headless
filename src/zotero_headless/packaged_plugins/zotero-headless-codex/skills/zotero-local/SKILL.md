---
name: zotero-local
description: Use this skill when the user wants to import from desktop Zotero, poll for local changes, plan a local apply, or write supported changes back to a local Zotero installation.
---

# Zotero Local — Desktop Interoperability

Zotero-headless can import from and carefully write back to a local Zotero desktop profile.

## Import Local Profile

Import local libraries, items, collections, notes, annotations, and attachment metadata:

- MCP: `zotero_local_import`
- CLI: `zhl raw local import`

## Poll for Local Changes

Use polling to detect incremental changes since a known version:

- MCP: `zotero_local_poll`
- CLI: `zhl raw local poll --since-version <n>`

## Write Back to Local Zotero

Local writeback is intentionally narrow and always follows a two-phase flow.

### Phase 1: Plan Apply

Preview all operations:

- MCP: `zotero_local_plan_apply`
- CLI: `zhl raw local plan-apply --library local:1`

### Phase 2: Apply

Execute the reviewed plan:

- MCP: `zotero_local_apply`
- CLI: `zhl raw local apply --library local:1`

## Supported Write Scope

Supported:
- Item create, update, and trash for supported fields
- Creators
- Tags
- Notes
- Annotation child items
- Attachment metadata updates
- Imported and linked attachment handling
- Collection create, update, trash, and membership

Not supported:
- Arbitrary schema modifications
- Direct SQL writes

## Local SQL

For read-only custom queries:

- MCP: `zotero_local_sql`
- CLI: `zhl raw local sql "SELECT ..."`

## Safety Rules

- Never mutate the local Zotero DB directly.
- Always review the plan before apply.
- Snapshot before local apply.
- Avoid running import/apply while Zotero desktop is actively writing to the database.
