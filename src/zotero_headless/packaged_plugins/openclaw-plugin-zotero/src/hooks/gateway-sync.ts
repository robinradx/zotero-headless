// src/hooks/gateway-sync.ts
import type { UnifiedClient } from "../client.js";
import type { ZoteroPluginConfig } from "../types.js";
import { resolvePermissions } from "../permissions.js";

export function createGatewaySyncHook(
  client: UnifiedClient,
  config: ZoteroPluginConfig,
  logger: { info?: (...args: unknown[]) => void; warn?: (...args: unknown[]) => void },
) {
  return async () => {
    const daemonCfg = config.daemon ?? {};
    if (daemonCfg.syncOnStartup === false) {
      logger.info?.("Zotero sync on startup disabled");
      return;
    }

    logger.info?.("Zotero: running startup sync...");

    let libraries: Array<{ libraryId: string; name: string }>;
    try {
      libraries = await client.getLibraries();
    } catch (err) {
      logger.warn?.(
        `Zotero startup sync: could not list libraries — ${err instanceof Error ? err.message : String(err)}`,
      );
      return;
    }

    for (const lib of libraries) {
      const perms = resolvePermissions(lib.libraryId, config);
      if (!perms.sync) {
        logger.info?.(`Zotero startup sync: skipping ${lib.libraryId} (sync disabled)`);
        continue;
      }

      try {
        await client.syncPull(lib.libraryId);
        logger.info?.(`Zotero startup sync: ${lib.libraryId} OK`);
      } catch (err) {
        logger.warn?.(
          `Zotero startup sync: ${lib.libraryId} FAILED — ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
  };
}
