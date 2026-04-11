// src/client.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { UnifiedClient } from "./client.js";
import { DaemonClient } from "./clients/daemon-client.js";
import { CliClient } from "./clients/cli-client.js";

vi.mock("./clients/daemon-client.js");
vi.mock("./clients/cli-client.js");

describe("UnifiedClient", () => {
  let client: UnifiedClient;
  let mockDaemon: DaemonClient;
  let mockCli: CliClient;

  beforeEach(() => {
    mockDaemon = new DaemonClient({ host: "localhost", port: 8787 });
    mockCli = new CliClient({ binary: "zhl" });
    client = new UnifiedClient(mockDaemon, mockCli);
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
      expect(mockCli.getLibraries).not.toHaveBeenCalled();
    });

    it("falls back to CLI when daemon is down", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(false);
      vi.mocked(mockCli.getLibraries).mockResolvedValue([
        { libraryId: "user:1", name: "My Library" },
      ]);
      const result = await client.getLibraries();
      expect(result).toHaveLength(1);
      expect(mockCli.getLibraries).toHaveBeenCalled();
    });

    it("throws when both daemon and CLI are unavailable", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(false);
      vi.mocked(mockCli.getLibraries).mockRejectedValue(new Error("ENOENT"));
      await expect(client.getLibraries()).rejects.toThrow("not available");
    });
  });

  describe("mode reporting", () => {
    it("reports http mode when daemon is reachable", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(true);
      const mode = await client.getMode();
      expect(mode).toBe("http");
    });

    it("reports cli mode when daemon is down but CLI works", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(false);
      vi.mocked(mockCli.health).mockResolvedValue(true);
      const mode = await client.getMode();
      expect(mode).toBe("cli");
    });

    it("reports unavailable mode when both are down", async () => {
      vi.mocked(mockDaemon.health).mockResolvedValue(false);
      vi.mocked(mockCli.health).mockResolvedValue(false);
      const mode = await client.getMode();
      expect(mode).toBe("unavailable");
    });
  });
});
