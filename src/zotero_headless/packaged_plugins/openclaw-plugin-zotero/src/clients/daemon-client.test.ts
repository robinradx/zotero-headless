// src/clients/daemon-client.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DaemonClient } from "./daemon-client.js";

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("DaemonClient", () => {
  let client: DaemonClient;

  beforeEach(() => {
    client = new DaemonClient({ host: "localhost", port: 8787 });
    mockFetch.mockReset();
  });

  describe("health", () => {
    it("returns true when daemon responds with ok", async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true }),
      });
      expect(await client.health()).toBe(true);
    });

    it("returns false when daemon is unreachable", async () => {
      mockFetch.mockRejectedValue(new Error("ECONNREFUSED"));
      expect(await client.health()).toBe(false);
    });
  });

  describe("getLibraries", () => {
    it("returns library list", async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ libraries: [{ libraryId: "user:123", name: "My Library" }] }),
      });
      const result = await client.getLibraries();
      expect(result).toHaveLength(1);
      expect(result[0].libraryId).toBe("user:123");
    });
  });

  describe("searchItems", () => {
    it("calls search endpoint with query", async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ results: [{ itemKey: "ABC123", title: "Test" }] }),
      });
      const result = await client.searchItems("test query");
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/search/query?q=test+query"),
        expect.any(Object),
      );
      expect(result).toHaveLength(1);
    });
  });

  describe("getItem", () => {
    it("fetches single item by library and key", async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ itemKey: "ABC", data: { title: "Test" } }),
      });
      const result = await client.getItem("user:123", "ABC");
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/libraries/user:123/items/ABC"),
        expect.any(Object),
      );
      expect(result.itemKey).toBe("ABC");
    });
  });

  describe("createItem", () => {
    it("posts new item to library", async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ itemKey: "NEW123" }),
      });
      const result = await client.createItem("user:123", {
        itemType: "journalArticle",
        title: "New Paper",
      });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/libraries/user:123/items"),
        expect.objectContaining({ method: "POST" }),
      );
      expect(result.itemKey).toBe("NEW123");
    });
  });

  describe("error handling", () => {
    it("throws on non-ok response", async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: "Not found" }),
      });
      await expect(client.getItem("user:123", "NOPE")).rejects.toThrow("404");
    });
  });
});
