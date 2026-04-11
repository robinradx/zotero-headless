// src/tools/attachments.ts
import { Type } from "@sinclair/typebox";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission } from "../permissions.js";

export function createAttachmentsTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_attachments",
    description:
      "List attachments for a Zotero item. Requires attachments permission. Download/upload operations require the daemon to be running.",
    parameters: Type.Object({
      action: Type.Union(
        [Type.Literal("list")],
        { description: "Attachment action. Currently supports: list." },
      ),
      library: Type.String({ description: "Library ID" }),
      itemKey: Type.String({ description: "Parent item key" }),
    }),
    async execute(params: { action: "list"; library: string; itemKey: string }) {
      const denied = checkPermission(params.library, "attachments", config);
      if (denied) return { content: [{ type: "text" as const, text: denied }] };

      // Get item to validate it exists
      await client.getItem(params.library, params.itemKey);

      // Attachments are typically child items; list them via the items endpoint.
      // TODO: a getChildItems(libraryId, parentKey) API would be better than fetching all items.
      const allItems = await client.listItems(params.library, undefined, 500);
      const attachments = allItems.filter((i) => {
        const d = (i.data ?? i) as Record<string, unknown>;
        return d.parentItem === params.itemKey && d.itemType === "attachment";
      });

      if (attachments.length === 0) {
        return {
          content: [{ type: "text" as const, text: `No attachments found for item ${params.itemKey}` }],
        };
      }

      const lines = attachments.map((a) => {
        const d = (a.data ?? a) as Record<string, unknown>;
        return `- ${d.title ?? d.filename ?? "Untitled"} (${d.contentType ?? "unknown"}) [key: ${d.itemKey ?? a.itemKey}]`;
      });

      return {
        content: [{ type: "text" as const, text: `Attachments for ${params.itemKey}:\n${lines.join("\n")}` }],
      };
    },
  };
}
