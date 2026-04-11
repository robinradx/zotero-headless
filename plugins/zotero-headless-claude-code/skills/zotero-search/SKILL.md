---
name: zotero-search
description: This skill should be used when the user asks to "search Zotero", "find papers", "look up references", "search my library", "find articles about", "semantic search", "keyword search", or wants to explore or retrieve items from their Zotero library. Guides selection between qmd semantic search, vector search, keyword search, and direct MCP reads.
---

# Zotero Search — Choosing the Right Retrieval Method

Zotero-headless offers four retrieval methods. Selecting the right one avoids wasted tokens and returns the most useful results.

## Decision Matrix

| Goal | Method | Tool / Command |
|------|--------|----------------|
| Explore a topic broadly | Hybrid semantic search | `zotero_qmd_query` |
| Find conceptually similar items | Vector search | `zotero_qmd_vsearch` |
| Match exact terms in metadata | Keyword search | `zotero_qmd_search` |
| Get a known item by key | Direct MCP read | `zotero_get_item` |
| List items with filters | Direct MCP list | `zotero_list_items` with `?q=` |
| Run arbitrary metadata queries | Local SQL | `zhl raw local sql "SELECT ..."` |

## Hybrid Semantic Search (`zotero_qmd_query`)

The default choice for exploratory retrieval. Combines vector similarity with keyword matching for best recall.

**When to use:** Topic exploration, finding related work, literature review, discovering relevant papers the user may not know about.

**Parameters:**
- `query` — natural language description of the topic
- `library_id` — optional, scope to a specific library

**Example:** "Find papers about transformer architectures in NLP" → `zotero_qmd_query` with query "transformer architectures natural language processing"

**Requires:** qmd CLI tool installed and library exported. If search returns empty, check `zhl capabilities` to verify qmd availability.

## Vector Search (`zotero_qmd_vsearch`)

Pure embedding-based similarity. Best when the query is conceptual and exact terms may not appear in metadata.

**Parameters:**
- `query` — natural language description of the concept
- `library_id` — optional, scope to a specific library

**When to use:** Finding conceptually related items where terminology varies, cross-disciplinary connections.

## Keyword Search (`zotero_qmd_search`)

Exact term matching. Fast and precise when the target terms are known.

**When to use:** Looking for a specific author, title fragment, DOI, or citation key.

## Direct MCP Reads

Authoritative current state from the canonical store. No qmd dependency.

**When to use:**
- Retrieving a specific item by key: `zotero_get_item`
- Listing items with simple filters: `zotero_list_items` with `?q=` parameter
- Listing collections: `zotero_list_collections`
- Getting exact metadata for citation or export

**Important:** Direct reads return the canonical store state. If remote data is needed, pull the library first with `zotero_sync_pull`.

## Local SQL Queries

Direct read-only SQL access to the local Zotero desktop database.

**When to use:** Complex metadata queries not supported by other methods, bulk analysis, custom reporting.

**Command:** `zhl raw local sql "SELECT itemID, key FROM items WHERE itemTypeID = 2 LIMIT 10"`

**Constraints:** Read-only. Never write to the local database directly.

## Search Strategy

1. **Start broad** — use `zotero_qmd_query` for topic exploration.
2. **Narrow down** — once relevant items are identified, use `zotero_get_item` for full metadata.
3. **Cross-reference** — use `zotero_list_collections` to find organizational context.
4. **Verify freshness** — if results seem stale, pull the library and re-search.

## Anti-Patterns

- **Do not** use semantic search to look up a known item key — use `zotero_get_item` directly.
- **Do not** assume qmd is available — check `zhl capabilities` first if search returns unexpected results.
- **Do not** rely on search results for authoritative metadata — always confirm with direct MCP reads before citing or exporting.
