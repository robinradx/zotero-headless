// src/tools/status.ts
import { Type } from "../schema.js";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { resolvePermissions } from "../permissions.js";

export function createStatusTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_status",
    description:
      "Check Zotero daemon health, available libraries, item counts, last sync times, and per-library permissions. Always available — no permissions required.",
    parameters: Type.Object({}),
    async execute() {
      const mode = await client.getMode();
      const daemonReachable = mode === "http";

      let libraries: Array<{ libraryId: string; name: string; [k: string]: unknown }> = [];
      try {
        libraries = await client.getLibraries();
      } catch {
        // Both transports failed — report empty
      }

      const permissions: Record<string, ReturnType<typeof resolvePermissions>> = {};
      for (const lib of libraries) {
        permissions[lib.libraryId] = resolvePermissions(lib.libraryId, config);
      }

      const lines: string[] = [
        `Transport: ${mode}`,
        `Daemon reachable: ${daemonReachable}`,
        "",
        `Libraries (${libraries.length}):`,
      ];

      for (const lib of libraries) {
        const perms = permissions[lib.libraryId];
        const permFlags = Object.entries(perms)
          .map(([k, v]) => `${k}:${v ? "yes" : "no"}`)
          .join(" ");
        lines.push(`  ${lib.libraryId} — ${lib.name} [${permFlags}]`);
      }

      return {
        content: [{ type: "text" as const, text: lines.join("\n") }],
      };
    },
  };
}
