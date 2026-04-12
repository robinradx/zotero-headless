// src/index.ts
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { DaemonClient } from "./clients/daemon-client.js";
import { UnifiedClient } from "./client.js";
import { createStatusTool } from "./tools/status.js";
import { createSearchTool } from "./tools/search.js";
import { createItemTool } from "./tools/items.js";
import { createCollectionsTool } from "./tools/collections.js";
import { createSyncTool } from "./tools/sync.js";
import { createAttachmentsTool } from "./tools/attachments.js";
import { createExportTool } from "./tools/export.js";
import { createBackupTool } from "./tools/backup.js";
import { createZoteroCommand } from "./commands/zotero.js";
import { createGatewaySyncHook } from "./hooks/gateway-sync.js";
import type { ZoteroPluginConfig, DaemonConfig } from "./types.js";

export default definePluginEntry({
  id: "zotero",
  name: "Zotero",
  description:
    "Zotero library access via zotero-headless daemon — search, items, collections, sync, export",

  register(api) {
    const pluginCfg = (api.pluginConfig ?? {}) as ZoteroPluginConfig;

    // Resolve config with defaults
    const daemonCfg: DaemonConfig = {
      host: String(pluginCfg.daemon?.host ?? "127.0.0.1"),
      port: Number(pluginCfg.daemon?.port ?? 23119),
      syncOnStartup: pluginCfg.daemon?.syncOnStartup !== false,
    };

    // Create clients
    const daemon = new DaemonClient({
      host: daemonCfg.host,
      port: daemonCfg.port,
    });
    const client = new UnifiedClient(daemon);

    // Register tools
    api.registerTool(createStatusTool(client, pluginCfg));
    api.registerTool(createSearchTool(client, pluginCfg));
    api.registerTool(createItemTool(client, pluginCfg));
    api.registerTool(createCollectionsTool(client, pluginCfg));
    api.registerTool(createSyncTool(client, pluginCfg));
    api.registerTool(createAttachmentsTool(client, pluginCfg));
    api.registerTool(createExportTool(client, pluginCfg));
    api.registerTool(createBackupTool(client, pluginCfg));

    // Register chat command
    api.registerCommand(createZoteroCommand(client, pluginCfg));

    // Register gateway startup hook for auto-sync
    const syncHook = createGatewaySyncHook(client, pluginCfg, {
      info: (...args: unknown[]) => api.logger.info?.(args.map(String).join(" ")),
      warn: (...args: unknown[]) => api.logger.warn?.(args.map(String).join(" ")),
    });
    api.registerHook("gateway_startup", () => {
      syncHook().catch((err) => {
        api.logger.warn?.(`Zotero startup sync failed: ${err instanceof Error ? err.message : String(err)}`);
      });
    });

    client.getMode().then((mode) => {
      if (mode === "http") {
        api.logger.info?.("Zotero: connected to daemon (HTTP mode)");
      } else {
        api.logger.warn?.(
          "Zotero: daemon unavailable. Start zotero-headless and point the plugin at its HTTP endpoint.",
        );
      }
    }).catch((err) => {
      api.logger.warn?.(`Zotero daemon health check failed: ${err instanceof Error ? err.message : String(err)}`);
    });
  },
});
