// src/tools/search.ts
import { Type } from "../schema.js";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission } from "../permissions.js";

export function createSearchTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_search",
    description:
      "Search Zotero library using semantic search (qmd-backed). Returns rich item summaries: title, authors, year, citekey, abstract snippet, tags. Two-stage: semantic ranking then metadata enrichment.",
    parameters: Type.Object({
      query: Type.String({ description: "Search query (semantic, keywords, or title)" }),
      library: Type.Optional(Type.String({ description: "Library ID to search (e.g. user:123456). Omit for all libraries." })),
      limit: Type.Optional(Type.Number({ description: "Max results to return (default 10)", default: 10 })),
    }),
    async execute(params: { query: string; library?: string; limit?: number }) {
      if (params.library) {
        const denied = checkPermission(params.library, "read", config);
        if (denied) return { content: [{ type: "text" as const, text: denied }] };
      }

      const results = await client.searchItems(
        params.query,
        params.library,
        params.limit ?? 10,
      );

      if (results.length === 0) {
        return {
          content: [{ type: "text" as const, text: `No results for "${params.query}"` }],
        };
      }

      // Enrich results with full metadata where possible
      const enriched = await Promise.all(
        results.map(async (r) => {
          const key = String(r.itemKey ?? r.key ?? "");
          const libId = String(r.libraryId ?? r.library_id ?? params.library ?? "");
          if (key && libId) {
            try {
              const full = await client.getItem(libId, key);
              return { ...r, ...full };
            } catch {
              return r;
            }
          }
          return r;
        }),
      );

      const lines = enriched.map((item, i) => {
        const data = (item.data ?? item) as Record<string, unknown>;
        const title = String(data.title ?? "Untitled");
        const authors = formatAuthors(data.creators ?? data.authors);
        const year = String(data.date ?? data.year ?? "");
        const citekey = String(data.citationKey ?? data.citekey ?? "");
        const tags = Array.isArray(data.tags)
          ? data.tags.map((t: unknown) =>
              typeof t === "object" && t !== null && "tag" in t
                ? String((t as Record<string, unknown>).tag)
                : String(t),
            )
          : [];
        const abstract = truncate(String(data.abstractNote ?? ""), 150);
        const key = String(item.itemKey ?? item.key ?? "");

        const parts = [`${i + 1}. **${title}**`];
        if (authors) parts.push(`   Authors: ${authors}`);
        if (year) parts.push(`   Year: ${year}`);
        if (citekey) parts.push(`   Citekey: ${citekey}`);
        if (key) parts.push(`   Key: ${key}`);
        if (tags.length) parts.push(`   Tags: ${tags.join(", ")}`);
        if (abstract) parts.push(`   Abstract: ${abstract}`);
        return parts.join("\n");
      });

      return {
        content: [{ type: "text" as const, text: lines.join("\n\n") }],
      };
    },
  };
}

function formatAuthors(creators: unknown): string {
  if (!Array.isArray(creators)) return "";
  return creators
    .map((c: unknown) => {
      if (typeof c === "string") return c;
      if (typeof c === "object" && c !== null) {
        const cr = c as Record<string, unknown>;
        if (cr.name) return String(cr.name);
        const parts = [cr.lastName, cr.firstName].filter(Boolean);
        return parts.join(", ");
      }
      return "";
    })
    .filter(Boolean)
    .join("; ");
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max) + "…";
}
