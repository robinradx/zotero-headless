---
name: zotero-local
description: This skill should be used when the user asks about "local Zotero", "desktop Zotero", "import Zotero", "local library", "Zotero profile", "apply changes to Zotero", "writeback", "plan-apply", or wants to interact with a locally installed Zotero desktop application. Covers import, polling, and the narrow supported write scope.
---

# Zotero Local — Desktop Interoperability

Zotero-headless can import from and write back to a locally installed Zotero desktop profile. The local adapter operates on the Zotero SQLite database with a carefully scoped write path.

## Import Local Profile

Import all libraries, items, collections, notes, and annotations from the local Zotero installation:

```
MCP:  zotero_local_import
CLI:  zhl raw local import
```

Import reads the local Zotero database and populates the headless canonical store. It extracts:
- Libraries and their metadata
- Items with all fields
- Collections and hierarchy
- Notes and annotations
- Attachment metadata and file references
- Citation keys (Zotero 9 native + Better BibTeX fallback)

## Poll for Changes

Detect modifications to the local Zotero database since a given version:

```
MCP:  zotero_local_poll  (since_version: N)
CLI:  zhl raw local poll --since-version N
```

Use polling to keep the headless store in sync with desktop Zotero without full re-import.

## Write Back to Local Zotero

Writing back to the local Zotero database follows a **two-phase safety pattern**: plan first, then apply.

### Phase 1: Plan Apply

Preview what changes will be written:

```
MCP:  zotero_local_plan_apply  (library_id: "local:1", limit: 1000)
CLI:  zhl raw local plan-apply --library local:1
```

The plan shows every operation that will be performed. **Always review the plan before applying.**

### Phase 2: Apply

Execute the planned changes:

```
MCP:  zotero_local_apply  (library_id: "local:1")
CLI:  zhl raw local apply --library local:1
```

### Supported Write Scope

The local apply path supports a **narrow, intentionally limited** set of operations:

| Operation | Supported |
|-----------|-----------|
| Item create/update/trash | Yes (supported scalar fields) |
| Creator writeback | Yes |
| Tag writeback | Yes |
| Note item writeback | Yes |
| Annotation child-item writeback | Yes |
| Attachment metadata updates | Yes |
| Imported-file/URL attachment copying | Yes |
| Linked-file/URL attachment handling | Yes |
| Embedded-image attachment support | Yes |
| Collection create/update/trash | Yes |
| Item collection membership | Yes |
| Arbitrary schema modifications | **No** |
| Direct SQL writes | **No** |

## Local SQL Queries

Run read-only SQL queries against the local Zotero database:

```
MCP:  zotero_local_sql  (query: "SELECT ...")
CLI:  zhl raw local sql "SELECT key, typeName FROM items LIMIT 10"
```

**Read-only.** Never attempt to write via SQL — use the apply flow instead.

## Safety Rules

- **Never mutate the local Zotero database directly** — always use plan-apply.
- **Always review the plan** before applying changes.
- **Create a snapshot** before applying changes to local Zotero (`zotero_recovery_snapshot_create`).
- **Close Zotero desktop** or ensure it is not actively writing when running import or apply operations to avoid SQLite locking issues.
- **Use `local:1`** as the library ID for the default local profile.

## Workflow Example

1. Import local profile: `zotero_local_import`
2. Make changes via MCP mutation tools
3. Plan the writeback: `zotero_local_plan_apply` with `library_id: "local:1"`
4. Review the plan output
5. Create a snapshot: `zotero_recovery_snapshot_create` with reason "before local apply"
6. Apply: `zotero_local_apply` with `library_id: "local:1"`
7. Open Zotero desktop to verify changes
