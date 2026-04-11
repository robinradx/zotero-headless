// src/types.ts

/** Per-library permission flags */
export interface LibraryPermissions {
  read: boolean;
  add: boolean;
  write: boolean;
  sync: boolean;
  attachments: boolean;
  export: boolean;
  backup: boolean;
}

/** Plugin configuration shape (matches openclaw.plugin.json configSchema) */
export interface ZoteroPluginConfig {
  daemon?: {
    host?: string;
    port?: number;
    autoStart?: boolean;
    syncOnStartup?: boolean;
  };
  cli?: {
    binary?: string;
  };
  libraries?: Record<string, Partial<LibraryPermissions>>;
  defaultPermissions?: Partial<LibraryPermissions>;
}

/** Resolved daemon config with defaults applied */
export interface DaemonConfig {
  host: string;
  port: number;
  autoStart: boolean;
  syncOnStartup: boolean;
}

/** Resolved CLI config with defaults applied */
export interface CliConfig {
  binary: string;
}

/** Zotero item summary returned by search */
export interface ZoteroItemSummary {
  itemKey: string;
  libraryId: string;
  itemType: string;
  title: string;
  authors: string[];
  year: string;
  citekey?: string;
  abstractSnippet?: string;
  tags: string[];
}

/** Full Zotero item metadata */
export interface ZoteroItem {
  itemKey: string;
  libraryId: string;
  itemType: string;
  data: Record<string, unknown>;
}

/** Collection metadata */
export interface ZoteroCollection {
  collectionKey: string;
  libraryId: string;
  name: string;
  parentCollection?: string;
}

/** Library info */
export interface ZoteroLibrary {
  libraryId: string;
  name: string;
  itemCount?: number;
  lastSync?: string;
}

/** Sync result */
export interface SyncResult {
  libraryId: string;
  status: "ok" | "error" | "skipped";
  message?: string;
  conflicts?: SyncConflict[];
}

/** Sync conflict */
export interface SyncConflict {
  entityType: string;
  entityKey: string;
  field: string;
  localValue: unknown;
  remoteValue: unknown;
}

/** Transport mode indicator */
export type TransportMode = "http" | "cli" | "unavailable";

/** Status response */
export interface ZoteroStatus {
  mode: TransportMode;
  daemonReachable: boolean;
  cliBinaryFound: boolean;
  libraries: ZoteroLibrary[];
  permissions: Record<string, LibraryPermissions>;
}
