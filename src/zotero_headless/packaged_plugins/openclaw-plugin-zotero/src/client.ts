// src/client.ts
import { DaemonClient } from "./clients/daemon-client.js";
import { CliClient } from "./clients/cli-client.js";
import type { TransportMode } from "./types.js";

function isConnectionError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return (
    msg.includes("econnrefused") ||
    msg.includes("econnreset") ||
    msg.includes("fetch failed") ||
    msg.includes("network")
  );
}

export class UnifiedClient {
  private daemon: DaemonClient;
  private cli: CliClient;
  private daemonHealthy: boolean | null = null;
  private lastHealthCheck = 0;
  private healthCacheTtl = 30_000; // 30 seconds

  constructor(daemon: DaemonClient, cli: CliClient) {
    this.daemon = daemon;
    this.cli = cli;
  }

  private async isDaemonReachable(): Promise<boolean> {
    const now = Date.now();
    if (
      this.daemonHealthy !== null &&
      now - this.lastHealthCheck < this.healthCacheTtl
    ) {
      return this.daemonHealthy;
    }
    this.daemonHealthy = await this.daemon.health();
    this.lastHealthCheck = now;
    return this.daemonHealthy;
  }

  /** Invalidate daemon health cache (call when daemon goes down/comes up) */
  invalidateHealthCache(): void {
    this.daemonHealthy = null;
    this.lastHealthCheck = 0;
  }

  async getMode(): Promise<TransportMode> {
    if (await this.isDaemonReachable()) return "http";
    if (await this.cli.health()) return "cli";
    return "unavailable";
  }

  /**
   * Run an operation, trying daemon first, then CLI fallback.
   */
  private async run<T>(
    daemonFn: () => Promise<T>,
    cliFn: () => Promise<T>,
  ): Promise<T> {
    if (await this.isDaemonReachable()) {
      try {
        return await daemonFn();
      } catch (err) {
        // Daemon was reachable but call failed — only fallback on connection errors
        if (isConnectionError(err)) {
          this.invalidateHealthCache();
        } else {
          throw err;
        }
      }
    }
    try {
      return await cliFn();
    } catch (err) {
      throw new Error(
        `zotero-headless not available. Daemon not running, CLI failed: ${
          err instanceof Error ? err.message : String(err)
        }. Install with: uv tool install zotero-headless`,
      );
    }
  }

  // --- Library operations ---

  async getLibraries() {
    return this.run(
      () => this.daemon.getLibraries(),
      () => this.cli.getLibraries(),
    );
  }

  // --- Search ---

  async searchItems(query: string, libraryId?: string, limit?: number) {
    return this.run(
      () => this.daemon.searchItems(query, libraryId, limit),
      () => this.cli.searchItems(query, libraryId, limit),
    );
  }

  // --- Items ---

  async getItem(libraryId: string, itemKey: string) {
    return this.run(
      () => this.daemon.getItem(libraryId, itemKey),
      () => this.cli.getItem(libraryId, itemKey),
    );
  }

  async listItems(libraryId: string, query?: string, limit?: number) {
    return this.run(
      () => this.daemon.listItems(libraryId, query, limit),
      async () => {
        // CLI doesn't have a direct listItems — use search if query, otherwise error
        if (query) return this.cli.searchItems(query, libraryId, limit);
        throw new Error("listItems without query requires the daemon");
      },
    );
  }

  async createItem(libraryId: string, data: Record<string, unknown>) {
    return this.run(
      () => this.daemon.createItem(libraryId, data),
      () => this.cli.createItem(libraryId, data),
    );
  }

  async updateItem(
    libraryId: string,
    itemKey: string,
    data: Record<string, unknown>,
  ) {
    return this.run(
      () => this.daemon.updateItem(libraryId, itemKey, data),
      () => this.cli.updateItem(libraryId, itemKey, data),
    );
  }

  async deleteItem(libraryId: string, itemKey: string) {
    return this.run(
      () => this.daemon.deleteItem(libraryId, itemKey),
      () => this.cli.deleteItem(libraryId, itemKey),
    );
  }

  // --- Collections ---

  async listCollections(libraryId: string) {
    return this.run(
      () => this.daemon.listCollections(libraryId),
      () => this.cli.listCollections(libraryId),
    );
  }

  async getCollection(libraryId: string, collectionKey: string) {
    return this.run(
      () => this.daemon.getCollection(libraryId, collectionKey),
      async () => {
        throw new Error("getCollection by key requires the daemon");
      },
    );
  }

  async createCollection(libraryId: string, data: Record<string, unknown>) {
    return this.run(
      () => this.daemon.createCollection(libraryId, data),
      () => this.cli.createCollection(libraryId, data),
    );
  }

  async updateCollection(
    libraryId: string,
    collectionKey: string,
    data: Record<string, unknown>,
  ) {
    return this.run(
      () => this.daemon.updateCollection(libraryId, collectionKey, data),
      async () => {
        throw new Error("updateCollection requires the daemon");
      },
    );
  }

  async deleteCollection(libraryId: string, collectionKey: string) {
    return this.run(
      () => this.daemon.deleteCollection(libraryId, collectionKey),
      async () => {
        throw new Error("deleteCollection requires the daemon");
      },
    );
  }

  // --- Sync ---

  async syncPull(libraryId: string) {
    return this.run(
      () => this.daemon.syncPull(libraryId),
      () => this.cli.syncPull(libraryId),
    );
  }

  async syncPush(libraryId: string) {
    return this.run(
      () => this.daemon.syncPush(libraryId),
      () => this.cli.syncPush(libraryId),
    );
  }

  async syncConflicts(libraryId: string) {
    return this.run(
      () => this.daemon.syncConflicts(libraryId),
      () => this.cli.syncConflicts(libraryId),
    );
  }

  // --- Export ---

  async searchExport(libraryId?: string) {
    return this.run(
      () => this.daemon.searchExport(libraryId),
      () => this.cli.searchExport(libraryId),
    );
  }

  // --- Recovery / Backup ---

  async listSnapshots(limit?: number) {
    return this.run(
      () => this.daemon.listSnapshots(limit),
      () => this.cli.listSnapshots(limit),
    );
  }

  async getSnapshot(snapshotId: string) {
    return this.run(
      () => this.daemon.getSnapshot(snapshotId),
      () => this.cli.getSnapshot(snapshotId),
    );
  }

  async createSnapshot(reason?: string) {
    return this.run(
      () => this.daemon.createSnapshot(reason),
      () => this.cli.createSnapshot(reason),
    );
  }

  async verifySnapshot(snapshotId: string) {
    return this.run(
      () => this.daemon.verifySnapshot(snapshotId),
      () => this.cli.verifySnapshot(snapshotId),
    );
  }

  async pushSnapshot(snapshotId: string, repository: string) {
    return this.run(
      () => this.daemon.pushSnapshot(snapshotId, repository),
      () => this.cli.pushSnapshot(snapshotId, repository),
    );
  }

  async pullSnapshot(snapshotId: string, repository: string) {
    return this.run(
      () => this.daemon.pullSnapshot(snapshotId, repository),
      () => this.cli.pullSnapshot(snapshotId, repository),
    );
  }

  async planRestore(snapshotId: string, libraryId?: string) {
    return this.run(
      () => this.daemon.planRestore(snapshotId, libraryId),
      () => this.cli.planRestore(snapshotId, libraryId),
    );
  }

  async executeRestore(params: {
    snapshotId: string;
    libraryId?: string;
    confirm: boolean;
    pushRemote?: boolean;
    applyLocal?: boolean;
  }) {
    return this.run(
      () => this.daemon.executeRestore(params),
      () => this.cli.executeRestore(params),
    );
  }

  async listRestoreRuns(limit?: number) {
    return this.run(
      () => this.daemon.listRestoreRuns(limit),
      () => this.cli.listRestoreRuns(limit),
    );
  }

  async listRepositories() {
    return this.run(
      () => this.daemon.listRepositories(),
      () => this.cli.listRepositories(),
    );
  }

  // --- Status (daemon-only extras) ---

  async getDaemonStatus() {
    if (await this.isDaemonReachable()) {
      return this.daemon.getDaemonStatus();
    }
    return null;
  }

  async getCapabilities() {
    if (await this.isDaemonReachable()) {
      return this.daemon.getCapabilities();
    }
    return null;
  }
}
