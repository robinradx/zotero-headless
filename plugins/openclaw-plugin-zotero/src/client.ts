// src/client.ts
import { DaemonClient } from "./clients/daemon-client.js";
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
  private daemonHealthy: boolean | null = null;
  private lastHealthCheck = 0;
  private healthCacheTtl = 30_000;

  constructor(daemon: DaemonClient) {
    this.daemon = daemon;
  }

  private async isDaemonReachable(): Promise<boolean> {
    const now = Date.now();
    if (this.daemonHealthy !== null && now - this.lastHealthCheck < this.healthCacheTtl) {
      return this.daemonHealthy;
    }
    this.daemonHealthy = await this.daemon.health();
    this.lastHealthCheck = now;
    return this.daemonHealthy;
  }

  invalidateHealthCache(): void {
    this.daemonHealthy = null;
    this.lastHealthCheck = 0;
  }

  async getMode(): Promise<TransportMode> {
    return (await this.isDaemonReachable()) ? "http" : "unavailable";
  }

  private async run<T>(daemonFn: () => Promise<T>): Promise<T> {
    if (await this.isDaemonReachable()) {
      try {
        return await daemonFn();
      } catch (err) {
        if (isConnectionError(err)) {
          this.invalidateHealthCache();
        } else {
          throw err;
        }
      }
    }
    throw new Error(
      "zotero-headless daemon is unavailable. Start the daemon and point the OpenClaw plugin at its HTTP endpoint.",
    );
  }

  async getLibraries() {
    return this.run(() => this.daemon.getLibraries());
  }

  async searchItems(query: string, libraryId?: string, limit?: number) {
    return this.run(() => this.daemon.searchItems(query, libraryId, limit));
  }

  async getItem(libraryId: string, itemKey: string) {
    return this.run(() => this.daemon.getItem(libraryId, itemKey));
  }

  async listItems(libraryId: string, query?: string, limit?: number) {
    return this.run(() => this.daemon.listItems(libraryId, query, limit));
  }

  async createItem(libraryId: string, data: Record<string, unknown>) {
    return this.run(() => this.daemon.createItem(libraryId, data));
  }

  async updateItem(libraryId: string, itemKey: string, data: Record<string, unknown>) {
    return this.run(() => this.daemon.updateItem(libraryId, itemKey, data));
  }

  async deleteItem(libraryId: string, itemKey: string) {
    return this.run(() => this.daemon.deleteItem(libraryId, itemKey));
  }

  async listCollections(libraryId: string) {
    return this.run(() => this.daemon.listCollections(libraryId));
  }

  async getCollection(libraryId: string, collectionKey: string) {
    return this.run(() => this.daemon.getCollection(libraryId, collectionKey));
  }

  async createCollection(libraryId: string, data: Record<string, unknown>) {
    return this.run(() => this.daemon.createCollection(libraryId, data));
  }

  async updateCollection(libraryId: string, collectionKey: string, data: Record<string, unknown>) {
    return this.run(() => this.daemon.updateCollection(libraryId, collectionKey, data));
  }

  async deleteCollection(libraryId: string, collectionKey: string) {
    return this.run(() => this.daemon.deleteCollection(libraryId, collectionKey));
  }

  async syncPull(libraryId: string) {
    return this.run(() => this.daemon.syncPull(libraryId));
  }

  async syncPush(libraryId: string) {
    return this.run(() => this.daemon.syncPush(libraryId));
  }

  async syncConflicts(libraryId: string) {
    return this.run(() => this.daemon.syncConflicts(libraryId));
  }

  async searchExport(libraryId?: string) {
    return this.run(() => this.daemon.searchExport(libraryId));
  }

  async listSnapshots(limit?: number) {
    return this.run(() => this.daemon.listSnapshots(limit));
  }

  async getSnapshot(snapshotId: string) {
    return this.run(() => this.daemon.getSnapshot(snapshotId));
  }

  async createSnapshot(reason?: string) {
    return this.run(() => this.daemon.createSnapshot(reason));
  }

  async verifySnapshot(snapshotId: string) {
    return this.run(() => this.daemon.verifySnapshot(snapshotId));
  }

  async pushSnapshot(snapshotId: string, repository: string) {
    return this.run(() => this.daemon.pushSnapshot(snapshotId, repository));
  }

  async pullSnapshot(snapshotId: string, repository: string) {
    return this.run(() => this.daemon.pullSnapshot(snapshotId, repository));
  }

  async planRestore(snapshotId: string, libraryId?: string) {
    return this.run(() => this.daemon.planRestore(snapshotId, libraryId));
  }

  async executeRestore(params: {
    snapshotId: string;
    libraryId?: string;
    confirm: boolean;
    pushRemote?: boolean;
    applyLocal?: boolean;
  }) {
    return this.run(() => this.daemon.executeRestore(params));
  }

  async listRestoreRuns(limit?: number) {
    return this.run(() => this.daemon.listRestoreRuns(limit));
  }

  async listRepositories() {
    return this.run(() => this.daemon.listRepositories());
  }

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
