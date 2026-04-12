// src/client.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { UnifiedClient } from "./client.js";
import { DaemonClient } from "./clients/daemon-client.js";

vi.mock("./clients/daemon-client.js");

describe("UnifiedClient", () => {
  let client: UnifiedClient;
  let mockDaemon: DaemonClient;

  beforeEach(() => {
    mockDaemon = new DaemonClient({ host: "127.0.0.1", port: 23119 });
    client = new UnifiedClient(mockDaemon);
    vi.resetAllMocks();
  });

  describe("transport selection", () => {
    it("uses daemon when reachable", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(true);
      vi.mocked(mockDaemon.getLibraries).mockResolvedValue([
        { libraryId: "user:1", name: "My Library" },
      ]);
      const result = await client.getLibraries();
      expect(result).toHaveLength(1);
      expect(mockDaemon.getLibraries).toHaveBeenCalled();
    });

    it("throws when the daemon is down", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(false);
      await expect(client.getLibraries()).rejects.toThrow("daemon is unavailable");
    });
  });

  describe("mode reporting", () => {
    it("reports http mode when daemon is reachable", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(true);
      const mode = await client.getMode();
      expect(mode).toBe("http");
    });

    it("reports unavailable mode when the daemon is down", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(false);
      const mode = await client.getMode();
      expect(mode).toBe("unavailable");
    });
  });
});
