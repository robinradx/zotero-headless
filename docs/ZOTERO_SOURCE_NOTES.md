# Zotero Source Notes

The repo no longer vendors a Zotero source snapshot. These notes describe the upstream Zotero areas that matter for the optional desktop-helper path and for local desktop interoperability work.

Current tracked upstream release baseline: Zotero `9.0` from April 10, 2026.

Upstream changes in that release that matter most here:

- native citation-key support is now part of Zotero itself, so local desktop interoperability should prefer real `citationKey` fields when present and only fall back to `extra` when needed
- Zotero desktop now uses a browser-based account login flow, but `zotero-headless` still depends on Zotero Web API keys for remote sync

Use them together with:

- `desktop_helper/metadata.json` for the pinned upstream revision you are validating against
- `desktop_helper/patches/` for the explicit helper delta maintained by this repo

## Relevant Upstream Areas

- `chrome/content/zotero/xpcom/zotero.js`
  - `Zotero.init(options)` is the top-level startup entrypoint.
  - `_initFull()` initializes the database and then starts the major services.
  - the local API and sync services are both initialized from here.

- `app/assets/commandLineHandler.js`
  - exposes existing CLI flags such as `--datadir`
  - natural seam for a dedicated `ZoteroDaemon` bootstrap flag when maintaining the optional helper path

- `chrome/content/zotero/xpcom/data/item.js`
  - defines `Zotero.Item`
  - shows persistence through Zotero's own data layer

- `chrome/content/zotero/xpcom/data/items.js`
  - shows local mutation semantics such as sync bookkeeping and trash behavior

- `chrome/content/zotero/xpcom/db.js`
  - transaction layer used by Zotero internals

- `chrome/content/zotero/xpcom/schema.js`
  - schema details for versions, sync fields, and other local invariants

- `chrome/content/zotero/xpcom/sync/syncRunner.js`
  - orchestrates sync sessions and library-level coordination

- `chrome/content/zotero/xpcom/sync/syncEventListeners.js`
  - shows how local changes become queued sync work

- `chrome/content/zotero/xpcom/sync/syncLocal.js`
  - local sync bookkeeping and delete/sync queues

- `chrome/content/zotero/xpcom/server/server_localAPI.js`
  - exposes a local implementation of the Zotero Web API under `/api/`
  - read-only only, with writes explicitly unsupported

- `chrome/content/zotero/xpcom/server/server_connector.js`
  - tied to the normal Zotero runtime and active UI assumptions
  - not sufficient as a standalone headless API

## Working Conclusion

The clean-room runtime remains the main product path.

The optional desktop-helper path, if maintained, should stay narrow:

1. patch Zotero's bootstrap only where needed for a `ZoteroDaemon`-style startup path
2. reuse upstream initialization for read-only local API access
3. keep write behavior out of the helper unless there is a clearly bounded and validated need
4. keep `zotero-headless` itself as the external CLI, HTTP API, and MCP wrapper
