// src/clients/daemon-client.ts

export interface DaemonClientConfig {
  host: string;
  port: number;
}

export class DaemonClient {
  private baseUrl: string;

  constructor(config: DaemonClientConfig) {
    this.baseUrl = `http://${config.host}:${config.port}`;
  }

  private async request(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<unknown> {
    const url = `${this.baseUrl}${path}`;
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const json = await res.json();
    if (!res.ok) {
      const msg =
        typeof json === "object" && json !== null && "error" in json
          ? (json as Record<string, unknown>).error
          : res.status;
      throw new Error(`Daemon API error ${res.status}: ${msg}`);
    }
    return json;
  }

  async health(): Promise<boolean> {
    try {
      await this.request("GET", "/health");
      return true;
    } catch {
      return false;
    }
  }

  async getCapabilities(): Promise<Record<string, unknown>> {
    return (await this.request("GET", "/capabilities")) as Record<
      string,
      unknown
    >;
  }

  async getLibraries(): Promise<
    Array<{ libraryId: string; name: string; [k: string]: unknown }>
  > {
    const res = (await this.request("GET", "/libraries")) as {
      libraries: Array<{ libraryId: string; name: string }>;
    };
    return res.libraries;
  }

  async searchItems(
    query: string,
    libraryId?: string,
    limit?: number,
  ): Promise<Array<Record<string, unknown>>> {
    const params = new URLSearchParams({ q: query });
    if (libraryId) params.set("library_id", libraryId);
    if (limit) params.set("limit", String(limit));
    const res = (await this.request(
      "GET",
      `/search/query?${params}`,
    )) as { results: Array<Record<string, unknown>> };
    return res.results;
  }

  async listItems(
    libraryId: string,
    query?: string,
    limit?: number,
  ): Promise<Array<Record<string, unknown>>> {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    const path = `/libraries/${libraryId}/items${qs ? `?${qs}` : ""}`;
    const res = (await this.request("GET", path)) as {
      results: Array<Record<string, unknown>>;
    };
    return res.results;
  }

  async getItem(
    libraryId: string,
    itemKey: string,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "GET",
      `/libraries/${libraryId}/items/${itemKey}`,
    )) as Record<string, unknown>;
  }

  async createItem(
    libraryId: string,
    data: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "POST",
      `/libraries/${libraryId}/items`,
      data,
    )) as Record<string, unknown>;
  }

  async updateItem(
    libraryId: string,
    itemKey: string,
    data: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "PATCH",
      `/libraries/${libraryId}/items/${itemKey}`,
      data,
    )) as Record<string, unknown>;
  }

  async deleteItem(
    libraryId: string,
    itemKey: string,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "DELETE",
      `/libraries/${libraryId}/items/${itemKey}`,
    )) as Record<string, unknown>;
  }

  async listCollections(
    libraryId: string,
  ): Promise<Array<Record<string, unknown>>> {
    const res = (await this.request(
      "GET",
      `/libraries/${libraryId}/collections`,
    )) as { results: Array<Record<string, unknown>> };
    return res.results;
  }

  async getCollection(
    libraryId: string,
    collectionKey: string,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "GET",
      `/libraries/${libraryId}/collections/${collectionKey}`,
    )) as Record<string, unknown>;
  }

  async createCollection(
    libraryId: string,
    data: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "POST",
      `/libraries/${libraryId}/collections`,
      data,
    )) as Record<string, unknown>;
  }

  async updateCollection(
    libraryId: string,
    collectionKey: string,
    data: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "PATCH",
      `/libraries/${libraryId}/collections/${collectionKey}`,
      data,
    )) as Record<string, unknown>;
  }

  async deleteCollection(
    libraryId: string,
    collectionKey: string,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "DELETE",
      `/libraries/${libraryId}/collections/${collectionKey}`,
    )) as Record<string, unknown>;
  }

  async syncPull(libraryId: string): Promise<Record<string, unknown>> {
    return (await this.request("POST", "/sync/pull", {
      library_id: libraryId,
    })) as Record<string, unknown>;
  }

  async syncPush(libraryId: string): Promise<Record<string, unknown>> {
    return (await this.request("POST", "/sync/push", {
      library_id: libraryId,
    })) as Record<string, unknown>;
  }

  async syncConflicts(
    libraryId: string,
  ): Promise<Array<Record<string, unknown>>> {
    const res = (await this.request(
      "GET",
      `/sync/conflicts?library_id=${libraryId}`,
    )) as { conflicts: Array<Record<string, unknown>> };
    return res.conflicts;
  }

  async searchExport(libraryId?: string): Promise<Record<string, unknown>> {
    return (await this.request("POST", "/search/export", {
      library_id: libraryId,
    })) as Record<string, unknown>;
  }

  async getDaemonStatus(): Promise<Record<string, unknown>> {
    return (await this.request(
      "GET",
      "/daemon/status",
    )) as Record<string, unknown>;
  }

  // --- Recovery / Backup ---

  async listSnapshots(limit?: number): Promise<Array<Record<string, unknown>>> {
    const params = limit ? `?limit=${limit}` : "";
    const res = (await this.request(
      "GET",
      `/recovery/snapshots${params}`,
    )) as { snapshots: Array<Record<string, unknown>> };
    return res.snapshots;
  }

  async getSnapshot(snapshotId: string): Promise<Record<string, unknown>> {
    return (await this.request(
      "GET",
      `/recovery/snapshots/${snapshotId}`,
    )) as Record<string, unknown>;
  }

  async createSnapshot(reason?: string): Promise<Record<string, unknown>> {
    return (await this.request("POST", "/recovery/snapshots", {
      reason: reason ?? "manual",
    })) as Record<string, unknown>;
  }

  async verifySnapshot(snapshotId: string): Promise<Record<string, unknown>> {
    return (await this.request(
      "POST",
      `/recovery/snapshots/${snapshotId}/verify`,
    )) as Record<string, unknown>;
  }

  async pushSnapshot(
    snapshotId: string,
    repository: string,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "POST",
      `/recovery/snapshots/${snapshotId}/push`,
      { repository },
    )) as Record<string, unknown>;
  }

  async pullSnapshot(
    snapshotId: string,
    repository: string,
  ): Promise<Record<string, unknown>> {
    return (await this.request(
      "POST",
      `/recovery/snapshots/${snapshotId}/pull`,
      { repository },
    )) as Record<string, unknown>;
  }

  async planRestore(
    snapshotId: string,
    libraryId?: string,
  ): Promise<Record<string, unknown>> {
    return (await this.request("POST", "/recovery/restore/plan", {
      snapshot_id: snapshotId,
      library_id: libraryId,
    })) as Record<string, unknown>;
  }

  async executeRestore(params: {
    snapshotId: string;
    libraryId?: string;
    confirm: boolean;
    pushRemote?: boolean;
    applyLocal?: boolean;
  }): Promise<Record<string, unknown>> {
    return (await this.request("POST", "/recovery/restore/execute", {
      snapshot_id: params.snapshotId,
      library_id: params.libraryId,
      confirm: params.confirm,
      push_remote: params.pushRemote ?? false,
      apply_local: params.applyLocal ?? false,
    })) as Record<string, unknown>;
  }

  async listRestoreRuns(limit?: number): Promise<Array<Record<string, unknown>>> {
    const params = limit ? `?limit=${limit}` : "";
    const res = (await this.request(
      "GET",
      `/recovery/restores${params}`,
    )) as { restores: Array<Record<string, unknown>> };
    return res.restores;
  }

  async getRestoreRun(runId: string): Promise<Record<string, unknown>> {
    return (await this.request(
      "GET",
      `/recovery/restores/${runId}`,
    )) as Record<string, unknown>;
  }

  async listRepositories(): Promise<Array<Record<string, unknown>>> {
    const res = (await this.request(
      "GET",
      "/recovery/repositories",
    )) as { repositories: Array<Record<string, unknown>> };
    return res.repositories;
  }
}
