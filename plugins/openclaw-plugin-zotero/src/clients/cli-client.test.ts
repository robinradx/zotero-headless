// src/clients/cli-client.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CliClient } from "./cli-client.js";
import * as childProcess from "node:child_process";

vi.mock("node:child_process");

const mockExecFile = vi.mocked(childProcess.execFile);

describe("CliClient", () => {
  let client: CliClient;

  beforeEach(() => {
    client = new CliClient({ binary: "zhl" });
    vi.resetAllMocks();
  });

  describe("health", () => {
    it("returns true when binary is available", async () => {
      mockExecFile.mockImplementation((_cmd, _args, _opts, cb) => {
        (cb as Function)(null, '{"ok":true}', "");
        return {} as any;
      });
      expect(await client.health()).toBe(true);
    });

    it("returns false when binary not found", async () => {
      mockExecFile.mockImplementation((_cmd, _args, _opts, cb) => {
        (cb as Function)(new Error("ENOENT"), "", "");
        return {} as any;
      });
      expect(await client.health()).toBe(false);
    });
  });

  describe("searchItems", () => {
    it("runs zhl search with --json flag", async () => {
      mockExecFile.mockImplementation((_cmd, _args, _opts, cb) => {
        (cb as Function)(null, JSON.stringify({ results: [{ itemKey: "A1" }] }), "");
        return {} as any;
      });
      const results = await client.searchItems("test query");
      expect(mockExecFile).toHaveBeenCalledWith(
        "zhl",
        ["search", "test query", "--json", "-n", "10"],
        expect.any(Object),
        expect.any(Function),
      );
      expect(results).toHaveLength(1);
    });
  });

  describe("getLibraries", () => {
    it("parses library list from CLI", async () => {
      mockExecFile.mockImplementation((_cmd, _args, _opts, cb) => {
        (cb as Function)(null, JSON.stringify({ libraries: [{ libraryId: "user:1" }] }), "");
        return {} as any;
      });
      const libs = await client.getLibraries();
      expect(libs).toHaveLength(1);
    });
  });
});
