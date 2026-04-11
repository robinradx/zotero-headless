---
name: zotero-search
description: Use this skill when the user wants to search Zotero, find papers, look up references, search their library, explore related work, or choose between semantic, vector, keyword, and exact metadata retrieval.
---

# Zotero Search — Choosing the Right Retrieval Method

Zotero-headless offers four retrieval paths. Choosing correctly improves recall and avoids wasting tokens on the wrong search mode.

## Decision Matrix

| Goal | Method | Tool / Command |
|------|--------|----------------|
| Explore a topic broadly | Hybrid semantic search | `zotero_qmd_query` |
| Find conceptually similar items | Vector search | `zotero_qmd_vsearch` |
| Match exact terms in metadata | Keyword search | `zotero_qmd_search` |
| Retrieve a known item by key | Direct MCP read | `zotero_get_item` |
| Filter or list current items | Direct MCP list | `zotero_list_items` |
| Run a custom metadata query | Local SQL | `zhl raw local sql "SELECT ..."` |

## Hybrid Semantic Search

The default choice for exploratory retrieval. It combines vector similarity with keyword matching.

Use it for:
- Topic exploration
- Literature review scaffolding
- Related-work discovery
- Queries where the user does not know exact titles or authors

Check `zhl capabilities` if qmd-backed search returns unexpectedly empty results.

## Vector Search

Pure embedding similarity. Use it when conceptual closeness matters more than exact wording.

Good fit for:
- Cross-disciplinary ideas
- Synonym-heavy topics
- Queries phrased in everyday language instead of paper terminology

## Keyword Search

Use exact-term search when the target string is known.

Good fit for:
- Author names
- Title fragments
- DOI lookups
- Citation keys

## Direct Reads

Use direct MCP reads for authoritative metadata:
- `zotero_get_item` for a known item
- `zotero_list_items` for current state with filters
- `zotero_list_collections` for organization context

If the library is remote, pull first.

## Local SQL

Useful for read-only bulk analysis or custom reporting not covered by the higher-level tools.

Never write via SQL.

## Search Strategy

1. Start broad with semantic search.
2. Follow promising hits with direct item reads.
3. Use keyword search to tighten precision.
4. Confirm exact metadata before citing or exporting.

## Anti-Patterns

- Do not use semantic search for a known item key.
- Do not assume qmd is available without checking capabilities when results look suspicious.
- Do not cite directly from exploratory results without confirming with an exact read.
