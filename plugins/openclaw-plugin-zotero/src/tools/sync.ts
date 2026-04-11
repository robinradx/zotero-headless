// src/tools/sync.ts
import { Type } from "@sinclair/typebox";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission, resolvePermissions } from "../permissions.js";

export function createSyncTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_sync",
    description:
      "Trigger sync operations with Zotero cloud. Actions: pull (download changes), push (upload changes), conflicts (check for conflicts). Requires sync permission.",
    parameters: Type.Object({
      action: Type.Union(
        [Type.Literal("pull"), Type.Literal("push"), Type.Literal("conflicts")],
        { description: "Sync action" },
      ),
      library: Type.Optional(
        Type.String({
          description: "Library ID. Omit to sync all libraries with sync permission enabled.",
        }),
      ),
    }),
    async execute(params: { action: "pull" | "push" | "conflicts"; library?: string }) {
      // If specific library, check permission
      if (params.library) {
        const denied = checkPermission(params.library, "sync", config);
        if (denied) return { content: [{ type: "text" as const, text: denied }] };
      }

      // If no library specified, find all sync-enabled libraries
      const libraries: string[] = [];
      if (params.library) {
        libraries.push(params.library);
      } else {
        const allLibs = await client.getLibraries();
        for (const lib of allLibs) {
          const perms = resolvePermissions(lib.libraryId, config);
          if (perms.sync) libraries.push(lib.libraryId);
        }
        if (libraries.length === 0) {
          return {
            content: [{
              type: "text" as const,
              text: "No libraries have sync permission enabled. Enable sync in openclaw.json under plugins.zotero.libraries.",
            }],
          };
        }
      }

      const results: string[] = [];
      for (const libId of libraries) {
        try {
          switch (params.action) {
            case "pull": {
              const r = await client.syncPull(libId);
              results.push(`${libId}: pull OK — ${JSON.stringify(r)}`);
              break;
            }
            case "push": {
              const r = await client.syncPush(libId);
              results.push(`${libId}: push OK — ${JSON.stringify(r)}`);
              break;
            }
            case "conflicts": {
              const conflicts = await client.syncConflicts(libId);
              if (conflicts.length === 0) {
                results.push(`${libId}: no conflicts`);
              } else {
                results.push(
                  `${libId}: ${conflicts.length} conflict(s)\n${JSON.stringify(conflicts, null, 2)}`,
                );
              }
              break;
            }
          }
        } catch (err) {
          results.push(
            `${libId}: ${params.action} FAILED — ${err instanceof Error ? err.message : String(err)}`,
          );
        }
      }

      return {
        content: [{ type: "text" as const, text: results.join("\n\n") }],
      };
    },
  };
}
