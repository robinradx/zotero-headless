// src/clients/cli-client.ts
import { execFile } from "node:child_process";

export interface CliClientConfig {
  binary: string;
}

export class CliClient {
  private binary: string;

  constructor(config: CliClientConfig) {
    this.binary = config.binary;
  }

  private exec(args: string[]): Promise<string> {
    return new Promise((resolve, reject) => {
      execFile(this.binary, args, { timeout: 30_000 }, (err, stdout, stderr) => {
        if (err) {
          reject(new Error(`CLI error: ${err.message}${stderr ? `\n${stderr}` : ""}`));
          return;
        }
        resolve(stdout.trim());
      });
    });
  }

  private validateLibraryId(id: string): void {
    if (!/^(user|group):\d+$/.test(id) && !/^local:\d+$/.test(id)) {
      throw new Error(`Invalid library ID format: ${id}`);
    }
  }

  private async execJson(args: string[]): Promise<unknown> {
    const output = await this.exec(args);
    return JSON.parse(output);
  }

  async health(): Promise<boolean> {
    try {
      await this.exec(["--version"]);
      return true;
    } catch {
      return false;
    }
  }

  async getLibraries(): Promise<
    Array<{ libraryId: string; name: string; [k: string]: unknown }>
  > {
    const res = (await this.execJson([
      "raw", "sync", "discover", "--json",
    ])) as { libraries: Array<{ libraryId: string; name: string }> };
    return res.libraries;
  }

  async searchItems(
    query: string,
    libraryId?: string,
    limit?: number,
  ): Promise<Array<Record<string, unknown>>> {
    const args = ["search", query, "--json", "-n", String(limit ?? 10)];
    if (libraryId) args.push("--library", libraryId);
    const res = (await this.execJson(args)) as {
      results: Array<Record<string, unknown>>;
    };
    return res.results;
  }

  async getItem(
    libraryId: string,
    itemKey: string,
  ): Promise<Record<string, unknown>> {
    this.validateLibraryId(libraryId);
    return (await this.execJson([
      "raw", "item", "get", libraryId, itemKey, "--json",
    ])) as Record<string, unknown>;
  }

  async createItem(
    libraryId: string,
    data: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    this.validateLibraryId(libraryId);
    return (await this.execJson([
      "raw", "item", "create", libraryId, JSON.stringify(data), "--json",
    ])) as Record<string, unknown>;
  }

  async updateItem(
    libraryId: string,
    itemKey: string,
    data: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    this.validateLibraryId(libraryId);
    return (await this.execJson([
      "raw", "item", "update", libraryId, itemKey, JSON.stringify(data), "--json",
    ])) as Record<string, unknown>;
  }

  async deleteItem(
    libraryId: string,
    itemKey: string,
  ): Promise<Record<string, unknown>> {
    this.validateLibraryId(libraryId);
    return (await this.execJson([
      "raw", "item", "delete", libraryId, itemKey, "--json",
    ])) as Record<string, unknown>;
  }

  async listCollections(
    libraryId: string,
  ): Promise<Array<Record<string, unknown>>> {
    this.validateLibraryId(libraryId);
    const res = (await this.execJson([
      "raw", "collections", "list", libraryId, "--json",
    ])) as { results: Array<Record<string, unknown>> };
    return res.results;
  }

  async createCollection(
    libraryId: string,
    data: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    this.validateLibraryId(libraryId);
    return (await this.execJson([
      "raw", "collections", "create", libraryId, JSON.stringify(data), "--json",
    ])) as Record<string, unknown>;
  }

  async syncPull(libraryId: string): Promise<Record<string, unknown>> {
    return (await this.execJson([
      "raw", "sync", "pull", "--library", libraryId, "--json",
    ])) as Record<string, unknown>;
  }

  async syncPush(libraryId: string): Promise<Record<string, unknown>> {
    return (await this.execJson([
      "raw", "sync", "push", "--library", libraryId, "--json",
    ])) as Record<string, unknown>;
  }

  async syncConflicts(
    libraryId: string,
  ): Promise<Array<Record<string, unknown>>> {
    const res = (await this.execJson([
      "raw", "sync", "conflicts", "--library", libraryId, "--json",
    ])) as { conflicts: Array<Record<string, unknown>> };
    return res.conflicts;
  }

  async searchExport(
    libraryId?: string,
  ): Promise<Record<string, unknown>> {
    const args = ["raw", "qmd", "export", "--json"];
    if (libraryId) args.push("--library", libraryId);
    return (await this.execJson(args)) as Record<string, unknown>;
  }

  // --- Recovery / Backup ---

  async listSnapshots(limit?: number): Promise<Array<Record<string, unknown>>> {
    const args = ["recovery", "snapshot-list", "--json"];
    if (limit) args.push("-n", String(limit));
    const res = (await this.execJson(args)) as
      | { snapshots: Array<Record<string, unknown>> }
      | Array<Record<string, unknown>>;
    return Array.isArray(res) ? res : res.snapshots;
  }

  async getSnapshot(snapshotId: string): Promise<Record<string, unknown>> {
    return (await this.execJson([
      "recovery", "snapshot-show", snapshotId, "--json",
    ])) as Record<string, unknown>;
  }

  async createSnapshot(reason?: string): Promise<Record<string, unknown>> {
    const args = ["recovery", "snapshot-create", "--json"];
    if (reason) args.push("--reason", reason);
    return (await this.execJson(args)) as Record<string, unknown>;
  }

  async verifySnapshot(snapshotId: string): Promise<Record<string, unknown>> {
    return (await this.execJson([
      "recovery", "snapshot-verify", snapshotId, "--json",
    ])) as Record<string, unknown>;
  }

  async pushSnapshot(
    snapshotId: string,
    repository: string,
  ): Promise<Record<string, unknown>> {
    return (await this.execJson([
      "recovery", "snapshot-push", snapshotId, "--repository", repository, "--json",
    ])) as Record<string, unknown>;
  }

  async pullSnapshot(
    snapshotId: string,
    repository: string,
  ): Promise<Record<string, unknown>> {
    return (await this.execJson([
      "recovery", "snapshot-pull", snapshotId, "--repository", repository, "--json",
    ])) as Record<string, unknown>;
  }

  async planRestore(
    snapshotId: string,
    libraryId?: string,
  ): Promise<Record<string, unknown>> {
    const args = ["recovery", "restore-plan", "--snapshot", snapshotId, "--json"];
    if (libraryId) args.push("--library", libraryId);
    return (await this.execJson(args)) as Record<string, unknown>;
  }

  async executeRestore(params: {
    snapshotId: string;
    libraryId?: string;
    confirm: boolean;
    pushRemote?: boolean;
    applyLocal?: boolean;
  }): Promise<Record<string, unknown>> {
    const args = ["recovery", "restore-execute", "--snapshot", params.snapshotId, "--json"];
    if (params.libraryId) args.push("--library", params.libraryId);
    if (params.confirm) args.push("--confirm");
    if (params.pushRemote) args.push("--push-remote");
    if (params.applyLocal) args.push("--apply-local");
    return (await this.execJson(args)) as Record<string, unknown>;
  }

  async listRestoreRuns(limit?: number): Promise<Array<Record<string, unknown>>> {
    const args = ["recovery", "restore-list", "--json"];
    if (limit) args.push("-n", String(limit));
    const res = (await this.execJson(args)) as
      | { restores: Array<Record<string, unknown>> }
      | Array<Record<string, unknown>>;
    return Array.isArray(res) ? res : res.restores;
  }

  async listRepositories(): Promise<Array<Record<string, unknown>>> {
    const res = (await this.execJson([
      "recovery", "repositories", "--json",
    ])) as
      | { repositories: Array<Record<string, unknown>> }
      | Array<Record<string, unknown>>;
    return Array.isArray(res) ? res : res.repositories;
  }
}
