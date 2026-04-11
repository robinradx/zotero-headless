// src/tools/items.ts
import { Type } from "@sinclair/typebox";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission } from "../permissions.js";

export function createItemTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_item",
    description:
      "Get, create, update, or delete Zotero items. Supports all item types (journalArticle, book, note, etc.). Actions: get (read), create (add), update/delete (write).",
    parameters: Type.Object({
      action: Type.Union(
        [
          Type.Literal("get"),
          Type.Literal("create"),
          Type.Literal("update"),
          Type.Literal("delete"),
        ],
        { description: "Action to perform" },
      ),
      library: Type.String({
        description: "Library ID (e.g. user:123456)",
      }),
      itemKey: Type.Optional(
        Type.String({
          description: "Item key (required for get/update/delete)",
        }),
      ),
      data: Type.Optional(
        Type.Record(Type.String(), Type.Unknown(), {
          description:
            'Item data for create/update. Must include "itemType" for create.',
        }),
      ),
    }),
    async execute(params: {
      action: "get" | "create" | "update" | "delete";
      library: string;
      itemKey?: string;
      data?: Record<string, unknown>;
    }) {
      // Permission check
      const permMap = { get: "read", create: "add", update: "write", delete: "write" } as const;
      const denied = checkPermission(params.library, permMap[params.action], config);
      if (denied) return { content: [{ type: "text" as const, text: denied }] };

      switch (params.action) {
        case "get": {
          if (!params.itemKey) {
            return { content: [{ type: "text" as const, text: "itemKey is required for get" }] };
          }
          const item = await client.getItem(params.library, params.itemKey);
          return {
            content: [{ type: "text" as const, text: JSON.stringify(item, null, 2) }],
          };
        }

        case "create": {
          if (!params.data) {
            return { content: [{ type: "text" as const, text: "data is required for create" }] };
          }
          const created = await client.createItem(params.library, params.data);
          return {
            content: [
              {
                type: "text" as const,
                text: `Item created: ${JSON.stringify(created, null, 2)}`,
              },
            ],
          };
        }

        case "update": {
          if (!params.itemKey || !params.data) {
            return {
              content: [
                { type: "text" as const, text: "itemKey and data are required for update" },
              ],
            };
          }
          const updated = await client.updateItem(
            params.library,
            params.itemKey,
            params.data,
          );
          return {
            content: [
              {
                type: "text" as const,
                text: `Item updated: ${JSON.stringify(updated, null, 2)}`,
              },
            ],
          };
        }

        case "delete": {
          if (!params.itemKey) {
            return {
              content: [{ type: "text" as const, text: "itemKey is required for delete" }],
            };
          }
          await client.deleteItem(params.library, params.itemKey);
          return {
            content: [
              { type: "text" as const, text: `Item ${params.itemKey} deleted` },
            ],
          };
        }
      }
    },
  };
}
