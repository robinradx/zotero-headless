# Zotero Source Notes

These notes are based on the local Zotero source snapshot in:

- [vendor/zotero 2](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202)

## Relevant Bootstrap Files

- [zotero.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/zotero.js)
  - `Zotero.init(options)` is the top-level startup entrypoint.
  - `_initFull()` initializes the database and then starts the major services.
  - Around line 698, `Zotero.Server.init()` is started when `httpServer.enabled` is true.
  - Around line 714, `Zotero.Sync.Runner = new Zotero.Sync.Runner_Module;` is created.
  - daemon mode can force-enable the local API before those services come up.

- [commandLineHandler.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/app/assets/commandLineHandler.js)
  - exposes existing CLI flags such as `--datadir`
  - now the seam for a dedicated `ZoteroDaemon` bootstrap flag

## Relevant Data-Layer Files

- [item.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/data/item.js)
  - defines `Zotero.Item`
  - exposes properties like `libraryID`, `key`, `version`, and `synced`
  - uses `saveTx()` for persistence through Zotero's own data layer

- [items.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/data/items.js)
  - shows local mutation semantics
  - for example, trashing items marks `item.synced = false` and updates `clientDateModified`

- [db.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/db.js)
  - transaction layer used by Zotero internals

- [schema.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/schema.js)
  - confirms schema details such as `items.version` and `items.synced`

## Relevant Sync Files

- [syncRunner.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/sync/syncRunner.js)
  - orchestrates sync sessions
  - checks API key access
  - coordinates library sync and conflict handling

- [syncEventListeners.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/sync/syncEventListeners.js)
  - shows how local object changes are translated into queued sync work

- [syncLocal.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/sync/syncLocal.js)
  - local sync bookkeeping and delete/sync queues

## Relevant Server Files

- [server_localAPI.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/server/server_localAPI.js)
  - exposes a fairly complete local implementation of the Zotero Web API under `/api/`
  - read-only only, with writes explicitly unsupported
  - appears to be data-layer based rather than pane-based
  - disabled by default via `extensions.zotero.httpServer.localAPI.enabled`

- [server_connector.js](/Users/robinradx/Documents/GitHub/zotero-headless/vendor/zotero%202/chrome/content/zotero/xpcom/server/server_connector.js)
  - confirms the app-local connector API depends on the normal Zotero runtime
  - tied to active pane/selection behavior and therefore not sufficient as a standalone headless API

## Working Conclusion

The most plausible implementation path is:

1. Add a dedicated `ZoteroDaemon` startup path to Zotero's own application bootstrap.
2. Reuse Zotero initialization and sync services, but skip the normal pane/window UI.
3. Auto-enable the built-in read-only local API for daemon mode as the first headless surface.
4. Add daemon-specific write endpoints later, because the built-in local API does not support writes.
5. Keep `zotero-headless` as the external CLI/API/MCP wrapper around that daemon.
