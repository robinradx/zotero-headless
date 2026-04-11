// src/commands/zotero.ts
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission, resolvePermissions } from "../permissions.js";

export function createZoteroCommand(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero",
    description: "Zotero library: search, cite, add, recent, sync, backup, status",
    acceptsArgs: true,
    handler: async (ctx: { args?: string }) => {
      const parts = (ctx.args?.trim() ?? "").split(/\s+/);
      const subcommand = parts[0]?.toLowerCase() ?? "";
      const subArgs = parts.slice(1).join(" ");

      try {
        switch (subcommand) {
          case "search": {
            if (!subArgs) return { text: "Usage: /zotero search <query>" };
            const searchLibs = await client.getLibraries();
            if (searchLibs.length > 0) {
              const denied = checkPermission(searchLibs[0].libraryId, "read", config);
              if (denied) return { text: denied };
            }
            const results = await client.searchItems(subArgs, undefined, 5);
            if (results.length === 0) return { text: `No results for "${subArgs}"` };
            const lines = results.map((r, i) => {
              const d = (r.data ?? r) as Record<string, unknown>;
              const title = String(d.title ?? "Untitled");
              const year = d.date ? String(d.date).slice(0, 4) : "";
              const authors = formatChatAuthors(d.creators ?? d.authors);
              return `${i + 1}. ${title}${authors ? ` — ${authors}` : ""}${year ? ` (${year})` : ""}`;
            });
            return { text: `Search results for "${subArgs}":\n${lines.join("\n")}` };
          }

          case "cite": {
            if (!subArgs) return { text: "Usage: /zotero cite <citekey or query>" };
            const citeLibs = await client.getLibraries();
            if (citeLibs.length > 0) {
              const denied = checkPermission(citeLibs[0].libraryId, "export", config);
              if (denied) return { text: denied };
            }
            const results = await client.searchItems(subArgs, undefined, 1);
            if (results.length === 0) return { text: `No item found for "${subArgs}"` };
            const item = results[0];
            const d = (item.data ?? item) as Record<string, unknown>;
            const authors = formatChatAuthors(d.creators ?? d.authors);
            const year = d.date ? String(d.date).slice(0, 4) : "n.d.";
            const title = String(d.title ?? "Untitled");
            const source = String(d.publicationTitle ?? "");
            let citation = `${authors || "Unknown"} (${year}). ${title}.`;
            if (source) citation += ` ${source}.`;
            if (d.DOI) citation += ` https://doi.org/${d.DOI}`;
            return { text: citation };
          }

          case "add": {
            if (!subArgs) return { text: "Usage: /zotero add <URL or DOI>" };
            // Determine default library
            const libs = await client.getLibraries();
            if (libs.length === 0) return { text: "No libraries available." };
            const libId = libs[0].libraryId;
            const denied = checkPermission(libId, "add", config);
            if (denied) return { text: denied };

            const isDoi = subArgs.match(/^10\.\d{4,}/);
            const data: Record<string, unknown> = isDoi
              ? { itemType: "journalArticle", DOI: subArgs }
              : { itemType: "webpage", url: subArgs, title: subArgs };

            const created = await client.createItem(libId, data);
            const title = String((created as Record<string, unknown>).title ?? subArgs);
            return { text: `Added to ${libId}: ${title}` };
          }

          case "recent": {
            const limit = parseInt(subArgs, 10) || 5;
            const libs = await client.getLibraries();
            if (libs.length === 0) return { text: "No libraries available." };
            const recentDenied = checkPermission(libs[0].libraryId, "read", config);
            if (recentDenied) return { text: recentDenied };
            const items = await client.listItems(libs[0].libraryId, undefined, limit);
            if (items.length === 0) return { text: "No recent items." };
            const lines = items.map((r, i) => {
              const d = (r.data ?? r) as Record<string, unknown>;
              return `${i + 1}. ${d.title ?? "Untitled"}`;
            });
            return { text: `Recent items:\n${lines.join("\n")}` };
          }

          case "sync": {
            const libId = subArgs || undefined;
            if (libId) {
              const denied = checkPermission(libId, "sync", config);
              if (denied) return { text: denied };
              const result = await client.syncPull(libId);
              return { text: `Sync pull for ${libId}: ${JSON.stringify(result)}` };
            }
            // Sync all sync-enabled libraries
            const libs = await client.getLibraries();
            const results: string[] = [];
            for (const lib of libs) {
              const perms = resolvePermissions(lib.libraryId, config);
              if (!perms.sync) continue;
              try {
                await client.syncPull(lib.libraryId);
                results.push(`${lib.libraryId}: OK`);
              } catch (err) {
                results.push(`${lib.libraryId}: FAILED — ${err instanceof Error ? err.message : String(err)}`);
              }
            }
            if (results.length === 0) return { text: "No libraries have sync permission enabled." };
            return { text: `Sync results:\n${results.join("\n")}` };
          }

          case "backup": {
            const backupAction = parts[1]?.toLowerCase() ?? "";
            if (backupAction === "create" || backupAction === "snapshot") {
              const reason = parts.slice(2).join(" ") || "manual";
              const result = await client.createSnapshot(reason);
              const id = String((result as Record<string, unknown>).snapshot_id ?? (result as Record<string, unknown>).snapshotId ?? "?");
              return { text: `Snapshot created: ${id}` };
            }
            if (backupAction === "list") {
              const snapshots = await client.listSnapshots(10);
              if (snapshots.length === 0) return { text: "No snapshots found." };
              const lines = snapshots.map((s) => {
                const id = String(s.snapshot_id ?? s.snapshotId ?? "?");
                const created = String(s.created_at ?? s.createdAt ?? "?");
                return `${id} — ${created}`;
              });
              return { text: `Snapshots:\n${lines.join("\n")}` };
            }
            if (backupAction === "verify" && parts[2]) {
              const result = await client.verifySnapshot(parts[2]);
              const ok = (result as Record<string, unknown>).ok;
              return { text: ok ? `Snapshot ${parts[2]} OK` : `Snapshot ${parts[2]} FAILED` };
            }
            return {
              text: [
                "/zotero backup commands:",
                "  create [reason] — Create a snapshot",
                "  list            — List snapshots",
                "  verify <id>     — Verify snapshot integrity",
              ].join("\n"),
            };
          }

          case "status": {
            const mode = await client.getMode();
            const libs = await client.getLibraries().catch(() => []);
            const lines = [`Mode: ${mode}`, `Libraries: ${libs.length}`];
            for (const lib of libs) {
              lines.push(`  ${lib.libraryId} — ${lib.name}`);
            }
            return { text: lines.join("\n") };
          }

          default: {
            return {
              text: [
                "/zotero commands:",
                "  search <query>   — Search library",
                "  cite <query>     — Get formatted citation",
                "  add <URL|DOI>    — Add item to library",
                "  recent [N]       — Show recent items",
                "  sync [library]   — Trigger sync",
                "  backup [create|list|verify] — Manage snapshots",
                "  status           — Daemon & library status",
              ].join("\n"),
            };
          }
        }
      } catch (err) {
        return { text: `Error: ${err instanceof Error ? err.message : String(err)}` };
      }
    },
  };
}

function formatChatAuthors(creators: unknown): string {
  if (!Array.isArray(creators)) return "";
  const names = creators
    .slice(0, 3)
    .map((c: unknown) => {
      if (typeof c === "object" && c !== null) {
        const cr = c as Record<string, unknown>;
        return String(cr.lastName ?? cr.name ?? "");
      }
      return String(c ?? "");
    })
    .filter(Boolean);
  const suffix = creators.length > 3 ? " et al." : "";
  return names.join(", ") + suffix;
}
