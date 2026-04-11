// src/tools/backup.ts
import { Type } from "../schema.js";
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { checkPermission } from "../permissions.js";

export function createBackupTool(client: UnifiedClient, config: ZoteroPluginConfig) {
  return {
    name: "zotero_backup",
    description:
      "Manage Zotero library backups: create snapshots, list/verify/push/pull snapshots, plan and execute restores. Requires backup permission.",
    parameters: Type.Object({
      action: Type.Union(
        [
          Type.Literal("snapshot_create"),
          Type.Literal("snapshot_list"),
          Type.Literal("snapshot_show"),
          Type.Literal("snapshot_verify"),
          Type.Literal("snapshot_push"),
          Type.Literal("snapshot_pull"),
          Type.Literal("restore_plan"),
          Type.Literal("restore_execute"),
          Type.Literal("restore_list"),
          Type.Literal("repositories"),
        ],
        { description: "Backup/recovery action to perform" },
      ),
      snapshotId: Type.Optional(
        Type.String({ description: "Snapshot ID (required for show/verify/push/pull/restore actions)" }),
      ),
      reason: Type.Optional(
        Type.String({ description: "Reason for creating a snapshot (default: manual)" }),
      ),
      repository: Type.Optional(
        Type.String({ description: "Repository name for push/pull operations" }),
      ),
      library: Type.Optional(
        Type.String({ description: "Library ID for library-scoped restore" }),
      ),
      confirm: Type.Optional(
        Type.Boolean({ description: "Confirm restore execution (required for restore_execute, default false)" }),
      ),
      pushRemote: Type.Optional(
        Type.Boolean({ description: "Push restored changes to Zotero web after restore" }),
      ),
      applyLocal: Type.Optional(
        Type.Boolean({ description: "Apply restored changes to local desktop Zotero" }),
      ),
      limit: Type.Optional(
        Type.Number({ description: "Max results for list actions (default 20)" }),
      ),
    }),
    async execute(params: {
      action: string;
      snapshotId?: string;
      reason?: string;
      repository?: string;
      library?: string;
      confirm?: boolean;
      pushRemote?: boolean;
      applyLocal?: boolean;
      limit?: number;
    }) {
      // Check backup permission on target library if specified, otherwise check on first library
      const libraries = await client.getLibraries().catch(() => []);
      const checkLib = params.library ?? libraries[0]?.libraryId;
      if (checkLib) {
        const denied = checkPermission(checkLib, "backup", config);
        if (denied) return { content: [{ type: "text" as const, text: denied }] };
      }

      switch (params.action) {
        case "snapshot_create": {
          const result = await client.createSnapshot(params.reason);
          return {
            content: [{ type: "text" as const, text: `Snapshot created:\n${JSON.stringify(result, null, 2)}` }],
          };
        }

        case "snapshot_list": {
          const snapshots = await client.listSnapshots(params.limit ?? 20);
          if (snapshots.length === 0) {
            return { content: [{ type: "text" as const, text: "No snapshots found." }] };
          }
          const lines = snapshots.map((s) => {
            const id = String(s.snapshot_id ?? s.snapshotId ?? "?");
            const created = String(s.created_at ?? s.createdAt ?? "?");
            const reason = String(s.reason ?? "");
            return `${id} — ${created}${reason ? ` (${reason})` : ""}`;
          });
          return {
            content: [{ type: "text" as const, text: `Snapshots (${snapshots.length}):\n${lines.join("\n")}` }],
          };
        }

        case "snapshot_show": {
          if (!params.snapshotId) {
            return { content: [{ type: "text" as const, text: "snapshotId is required for snapshot_show" }] };
          }
          const snapshot = await client.getSnapshot(params.snapshotId);
          return {
            content: [{ type: "text" as const, text: JSON.stringify(snapshot, null, 2) }],
          };
        }

        case "snapshot_verify": {
          if (!params.snapshotId) {
            return { content: [{ type: "text" as const, text: "snapshotId is required for snapshot_verify" }] };
          }
          const result = await client.verifySnapshot(params.snapshotId);
          const ok = (result as Record<string, unknown>).ok;
          return {
            content: [{
              type: "text" as const,
              text: ok
                ? `Snapshot ${params.snapshotId} verified OK`
                : `Snapshot ${params.snapshotId} verification failed:\n${JSON.stringify(result, null, 2)}`,
            }],
          };
        }

        case "snapshot_push": {
          if (!params.snapshotId || !params.repository) {
            return { content: [{ type: "text" as const, text: "snapshotId and repository are required for snapshot_push" }] };
          }
          const result = await client.pushSnapshot(params.snapshotId, params.repository);
          return {
            content: [{ type: "text" as const, text: `Snapshot pushed:\n${JSON.stringify(result, null, 2)}` }],
          };
        }

        case "snapshot_pull": {
          if (!params.snapshotId || !params.repository) {
            return { content: [{ type: "text" as const, text: "snapshotId and repository are required for snapshot_pull" }] };
          }
          const result = await client.pullSnapshot(params.snapshotId, params.repository);
          return {
            content: [{ type: "text" as const, text: `Snapshot pulled:\n${JSON.stringify(result, null, 2)}` }],
          };
        }

        case "restore_plan": {
          if (!params.snapshotId) {
            return { content: [{ type: "text" as const, text: "snapshotId is required for restore_plan" }] };
          }
          const plan = await client.planRestore(params.snapshotId, params.library);
          return {
            content: [{ type: "text" as const, text: `Restore plan:\n${JSON.stringify(plan, null, 2)}` }],
          };
        }

        case "restore_execute": {
          if (!params.snapshotId) {
            return { content: [{ type: "text" as const, text: "snapshotId is required for restore_execute" }] };
          }
          if (!params.confirm) {
            return {
              content: [{
                type: "text" as const,
                text: "Restore requires confirm: true. Review the restore plan first with restore_plan, then set confirm to true.",
              }],
            };
          }
          const result = await client.executeRestore({
            snapshotId: params.snapshotId,
            libraryId: params.library,
            confirm: true,
            pushRemote: params.pushRemote,
            applyLocal: params.applyLocal,
          });
          return {
            content: [{ type: "text" as const, text: `Restore executed:\n${JSON.stringify(result, null, 2)}` }],
          };
        }

        case "restore_list": {
          const runs = await client.listRestoreRuns(params.limit ?? 20);
          if (runs.length === 0) {
            return { content: [{ type: "text" as const, text: "No restore runs found." }] };
          }
          return {
            content: [{ type: "text" as const, text: `Restore runs:\n${JSON.stringify(runs, null, 2)}` }],
          };
        }

        case "repositories": {
          const repos = await client.listRepositories();
          if (repos.length === 0) {
            return { content: [{ type: "text" as const, text: "No backup repositories configured." }] };
          }
          const lines = repos.map((r) => {
            const name = String(r.name ?? "?");
            const type = String(r.type ?? "?");
            return `${name} (${type})`;
          });
          return {
            content: [{ type: "text" as const, text: `Repositories:\n${lines.join("\n")}` }],
          };
        }

        default:
          return { content: [{ type: "text" as const, text: `Unknown action: ${params.action}` }] };
      }
    },
  };
}
