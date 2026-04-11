// src/index.ts
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import type { OpenClawPluginApi, AnyAgentTool } from "openclaw/plugin-sdk";
import { DaemonClient } from "./clients/daemon-client.js";
import { CliClient } from "./clients/cli-client.js";
import { UnifiedClient } from "./client.js";
import { DaemonService } from "./service/daemon.js";
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
import type { ZoteroPluginConfig, DaemonConfig, CliConfig } from "./types.js";

export default definePluginEntry({
  id: "zotero",
  name: "Zotero",
  description:
    "Zotero library access via zotero-headless daemon — search, items, collections, sync, export",

  register(api: OpenClawPluginApi) {
    const pluginCfg = (api.pluginConfig ?? {}) as ZoteroPluginConfig;

    // Resolve config with defaults
    const daemonCfg: DaemonConfig = {
      host: String(pluginCfg.daemon?.host ?? "localhost"),
      port: Number(pluginCfg.daemon?.port ?? 8787),
      autoStart: pluginCfg.daemon?.autoStart !== false,
      syncOnStartup: pluginCfg.daemon?.syncOnStartup !== false,
    };

    const cliCfg: CliConfig = {
      binary: String(pluginCfg.cli?.binary ?? "zhl"),
    };

    // Create clients
    const daemon = new DaemonClient({
      host: daemonCfg.host,
      port: daemonCfg.port,
    });
    const cli = new CliClient({ binary: cliCfg.binary });
    const client = new UnifiedClient(daemon, cli);

    // Daemon service (lifecycle management)
    const daemonService = new DaemonService(daemonCfg, cliCfg, {
      info: (...args: unknown[]) => api.logger.info?.(args.map(String).join(" ")),
      warn: (...args: unknown[]) => api.logger.warn?.(args.map(String).join(" ")),
    });

    // Register tools
    api.registerTool(createStatusTool(client, pluginCfg) as unknown as AnyAgentTool);
    api.registerTool(createSearchTool(client, pluginCfg) as unknown as AnyAgentTool);
    api.registerTool(createItemTool(client, pluginCfg) as unknown as AnyAgentTool);
    api.registerTool(createCollectionsTool(client, pluginCfg) as unknown as AnyAgentTool);
    api.registerTool(createSyncTool(client, pluginCfg) as unknown as AnyAgentTool);
    api.registerTool(createAttachmentsTool(client, pluginCfg) as unknown as AnyAgentTool);
    api.registerTool(createExportTool(client, pluginCfg) as unknown as AnyAgentTool);
    api.registerTool(createBackupTool(client, pluginCfg) as unknown as AnyAgentTool);

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

    // Start daemon service (async, non-blocking)
    daemonService.start().then(() => {
      // Health check on load
      return client.getMode().then((mode) => {
        if (mode === "http") {
          api.logger.info?.("Zotero: connected to daemon (HTTP mode)");
        } else if (mode === "cli") {
          api.logger.info?.("Zotero: using CLI fallback mode");
        } else {
          api.logger.warn?.(
            "Zotero: neither daemon nor CLI available. Install zotero-headless: uv tool install zotero-headless",
          );
        }
      });
    }).catch((err) => {
      api.logger.warn?.(`Zotero daemon startup error: ${err instanceof Error ? err.message : String(err)}`);
    });
  },
});
