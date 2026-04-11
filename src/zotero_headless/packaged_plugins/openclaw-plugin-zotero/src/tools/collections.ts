// src/tools/collections.ts
import { Type } from "../schema.js";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission } from "../permissions.js";

export function createCollectionsTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_collections",
    description:
      "List, get, create, rename, or delete Zotero collections. Actions: list/get (read), create (add), rename/delete (write).",
    parameters: Type.Object({
      action: Type.Union(
        [
          Type.Literal("list"),
          Type.Literal("get"),
          Type.Literal("create"),
          Type.Literal("rename"),
          Type.Literal("delete"),
        ],
        { description: "Action to perform" },
      ),
      library: Type.String({ description: "Library ID" }),
      collectionKey: Type.Optional(
        Type.String({ description: "Collection key (required for get/rename/delete)" }),
      ),
      name: Type.Optional(
        Type.String({ description: "Collection name (required for create/rename)" }),
      ),
      parentCollection: Type.Optional(
        Type.String({ description: "Parent collection key for create" }),
      ),
    }),
    async execute(params: {
      action: "list" | "get" | "create" | "rename" | "delete";
      library: string;
      collectionKey?: string;
      name?: string;
      parentCollection?: string;
    }) {
      const permMap = {
        list: "read", get: "read", create: "add", rename: "write", delete: "write",
      } as const;
      const denied = checkPermission(params.library, permMap[params.action], config);
      if (denied) return { content: [{ type: "text" as const, text: denied }] };

      switch (params.action) {
        case "list": {
          const collections = await client.listCollections(params.library);
          return {
            content: [{ type: "text" as const, text: JSON.stringify(collections, null, 2) }],
          };
        }

        case "get": {
          if (!params.collectionKey) {
            return { content: [{ type: "text" as const, text: "collectionKey is required for get" }] };
          }
          const coll = await client.getCollection(params.library, params.collectionKey);
          return {
            content: [{ type: "text" as const, text: JSON.stringify(coll, null, 2) }],
          };
        }

        case "create": {
          if (!params.name) {
            return { content: [{ type: "text" as const, text: "name is required for create" }] };
          }
          const data: Record<string, unknown> = { name: params.name };
          if (params.parentCollection) data.parentCollection = params.parentCollection;
          const created = await client.createCollection(params.library, data);
          return {
            content: [{ type: "text" as const, text: `Collection created: ${JSON.stringify(created, null, 2)}` }],
          };
        }

        case "rename": {
          if (!params.collectionKey || !params.name) {
            return { content: [{ type: "text" as const, text: "collectionKey and name required for rename" }] };
          }
          const updated = await client.updateCollection(
            params.library, params.collectionKey, { name: params.name },
          );
          return {
            content: [{ type: "text" as const, text: `Collection renamed: ${JSON.stringify(updated, null, 2)}` }],
          };
        }

        case "delete": {
          if (!params.collectionKey) {
            return { content: [{ type: "text" as const, text: "collectionKey is required for delete" }] };
          }
          await client.deleteCollection(params.library, params.collectionKey);
          return {
            content: [{ type: "text" as const, text: `Collection ${params.collectionKey} deleted` }],
          };
        }
      }
    },
  };
}
