// src/tools/export.ts
import { Type } from "../schema.js";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission } from "../permissions.js";

export function createExportTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_export",
    description:
      "Export Zotero items as BibTeX, qmd markdown, or formatted citations. Can export specific items by key or search results by query.",
    parameters: Type.Object({
      format: Type.Union(
        [Type.Literal("bibtex"), Type.Literal("qmd"), Type.Literal("citation")],
        { description: "Output format" },
      ),
      library: Type.Optional(Type.String({ description: "Library ID" })),
      itemKeys: Type.Optional(
        Type.Array(Type.String(), { description: "Specific item keys to export" }),
      ),
      query: Type.Optional(
        Type.String({ description: "Search query to find items to export (alternative to itemKeys)" }),
      ),
      citationStyle: Type.Optional(
        Type.String({ description: 'Citation style (default: "apa")', default: "apa" }),
      ),
    }),
    async execute(params: {
      format: "bibtex" | "qmd" | "citation";
      library?: string;
      itemKeys?: string[];
      query?: string;
      citationStyle?: string;
    }) {
      if (params.library) {
        const denied = checkPermission(params.library, "export", config);
        if (denied) return { content: [{ type: "text" as const, text: denied }] };
      }

      // Resolve items to export
      let items: Array<Record<string, unknown>> = [];

      if (params.itemKeys && params.library) {
        items = await Promise.all(
          params.itemKeys.map((key) => client.getItem(params.library!, key)),
        );
      } else if (params.query) {
        items = await client.searchItems(params.query, params.library, 20);
      } else {
        return {
          content: [{
            type: "text" as const,
            text: "Provide either itemKeys (with library) or query to select items for export.",
          }],
        };
      }

      if (items.length === 0) {
        return { content: [{ type: "text" as const, text: "No items found to export." }] };
      }

      switch (params.format) {
        case "bibtex": {
          const entries = items.map((item) => formatBibtex(item));
          return {
            content: [{ type: "text" as const, text: entries.join("\n\n") }],
          };
        }

        case "qmd": {
          // qmd export always exports the full library — itemKeys/query are not applied
          const result = await client.searchExport(params.library);
          return {
            content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
          };
        }

        case "citation": {
          const style = params.citationStyle ?? "apa";
          const citations = items.map((item) => formatCitation(item, style));
          return {
            content: [{ type: "text" as const, text: citations.join("\n\n") }],
          };
        }
      }
    },
  };
}

function formatBibtex(item: Record<string, unknown>): string {
  const data = (item.data ?? item) as Record<string, unknown>;
  const key = String(data.citationKey ?? data.citekey ?? data.itemKey ?? item.itemKey ?? "item");
  const type = mapItemTypeToBibtex(String(data.itemType ?? "misc"));
  const fields: string[] = [];

  if (data.title) fields.push(`  title = {${data.title}}`);
  if (data.date) fields.push(`  year = {${String(data.date).slice(0, 4)}}`);
  if (Array.isArray(data.creators)) {
    const authors = (data.creators as Array<Record<string, unknown>>)
      .filter((c) => c.creatorType === "author" || !c.creatorType)
      .map((c) => String(c.name ?? `${c.lastName ?? ""}, ${c.firstName ?? ""}`))
      .join(" and ");
    if (authors) fields.push(`  author = {${authors}}`);
  }
  if (data.DOI) fields.push(`  doi = {${data.DOI}}`);
  if (data.url) fields.push(`  url = {${data.url}}`);
  if (data.publicationTitle) fields.push(`  journal = {${data.publicationTitle}}`);
  if (data.volume) fields.push(`  volume = {${data.volume}}`);
  if (data.pages) fields.push(`  pages = {${data.pages}}`);

  return `@${type}{${key},\n${fields.join(",\n")}\n}`;
}

function mapItemTypeToBibtex(itemType: string): string {
  const map: Record<string, string> = {
    journalArticle: "article",
    book: "book",
    bookSection: "incollection",
    conferencePaper: "inproceedings",
    thesis: "phdthesis",
    report: "techreport",
    webpage: "misc",
    note: "misc",
  };
  return map[itemType] ?? "misc";
}

function formatCitation(item: Record<string, unknown>, _style: string): string {
  // Simple APA-ish format; full style support would require a citation engine
  const data = (item.data ?? item) as Record<string, unknown>;
  const authors = Array.isArray(data.creators)
    ? (data.creators as Array<Record<string, unknown>>)
        .filter((c) => c.creatorType === "author" || !c.creatorType)
        .map((c) => String(c.lastName ?? c.name ?? "Unknown"))
        .join(", ")
    : "Unknown";
  const year = data.date ? String(data.date).slice(0, 4) : "n.d.";
  const title = String(data.title ?? "Untitled");
  const source = String(data.publicationTitle ?? data.publisher ?? "");

  let citation = `${authors} (${year}). ${title}.`;
  if (source) citation += ` ${source}.`;
  if (data.DOI) citation += ` https://doi.org/${data.DOI}`;
  return citation;
}
