// src/permissions.test.ts
import { describe, it, expect } from "vitest";
import {
  resolvePermissions,
  checkPermission,
  DEFAULT_PERMISSIONS,
} from "./permissions.js";

describe("resolvePermissions", () => {
  it("returns defaults when no overrides configured", () => {
    const perms = resolvePermissions("user:123", {});
    expect(perms).toEqual(DEFAULT_PERMISSIONS);
  });

  it("applies defaultPermissions overrides", () => {
    const perms = resolvePermissions("user:123", {
      defaultPermissions: { sync: true },
    });
    expect(perms.sync).toBe(true);
    expect(perms.read).toBe(true); // unchanged default
  });

  it("applies per-library overrides over defaults", () => {
    const perms = resolvePermissions("user:123", {
      defaultPermissions: { sync: true },
      libraries: { "user:123": { sync: false, write: true } },
    });
    expect(perms.sync).toBe(false); // per-library wins
    expect(perms.write).toBe(true);
    expect(perms.read).toBe(true); // from default
  });

  it("ignores per-library overrides for non-matching library", () => {
    const perms = resolvePermissions("group:999", {
      libraries: { "user:123": { write: true } },
    });
    expect(perms.write).toBe(false); // not user:123, gets default
  });
});

describe("checkPermission", () => {
  it("returns null when permission is granted", () => {
    const result = checkPermission("user:123", "read", {});
    expect(result).toBeNull();
  });

  it("returns error string when permission is denied", () => {
    const result = checkPermission("user:123", "write", {});
    expect(result).toContain("write");
    expect(result).toContain("user:123");
  });
});
