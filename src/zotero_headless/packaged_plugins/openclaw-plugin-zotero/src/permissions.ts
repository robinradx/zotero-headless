// src/permissions.ts
import type { LibraryPermissions, ZoteroPluginConfig } from "./types.js";

export const DEFAULT_PERMISSIONS: LibraryPermissions = {
  read: true,
  add: true,
  write: false,
  sync: false,
  attachments: false,
  export: true,
  backup: false,
};

/**
 * Resolve effective permissions for a library.
 * Priority: per-library overrides > defaultPermissions > DEFAULT_PERMISSIONS
 */
export function resolvePermissions(
  libraryId: string,
  config: Pick<ZoteroPluginConfig, "libraries" | "defaultPermissions">,
): LibraryPermissions {
  const base = { ...DEFAULT_PERMISSIONS, ...config.defaultPermissions };
  const override = config.libraries?.[libraryId];
  if (override) {
    return { ...base, ...override };
  }
  return base;
}

/**
 * Check if a permission is granted for a library.
 * Returns null if granted, or an error message string if denied.
 */
export function checkPermission(
  libraryId: string,
  permission: keyof LibraryPermissions,
  config: Pick<ZoteroPluginConfig, "libraries" | "defaultPermissions">,
): string | null {
  const perms = resolvePermissions(libraryId, config);
  if (perms[permission]) return null;
  return `Permission '${permission}' denied for library ${libraryId}. Enable in openclaw.json under plugins.zotero.libraries.`;
}
