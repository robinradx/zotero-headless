from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .adapters.local_desktop import LocalDesktopAdapter
from .adapters.web_sync import CanonicalWebSyncAdapter
from .capabilities import get_capabilities
from .config import Settings
from .core import CanonicalStore, EntityType
from .daemon import current_daemon_status
from .library_routing import merged_libraries, prefers_canonical_reads
from .local_db import LocalZoteroDB
from .qmd import QmdClient
from .service import HeadlessService, LocalWriteRequiresDaemonError
from .store import MirrorStore
from .sync import SyncService
from .web_api import ZoteroWebClient
from .config import load_settings


TOOLS = [
    {
        "name": "zotero_list_libraries",
        "description": "List all libraries across the mirror and headless store.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_core_status",
        "description": "Report status of the headless store.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_core_libraries",
        "description": "List libraries in the headless store.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_core_changes",
        "description": "List headless store change-log entries, optionally filtered by library.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "zotero_capabilities",
        "description": "Report currently available capabilities and configured paths.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_daemon_status",
        "description": "Report the current status of the planned Zotero-backed daemon runtime.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_list_items",
        "description": "List items in a library from the mirror or headless store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "query": {"type": "string"},
            },
            "required": ["library_id"],
        },
    },
    {
        "name": "zotero_list_collections",
        "description": "List collections in a library from the mirror or headless store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "query": {"type": "string"},
            },
            "required": ["library_id"],
        },
    },
    {
        "name": "zotero_get_item",
        "description": "Get a single item by key from the mirror or headless store.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}, "item_key": {"type": "string"}},
            "required": ["library_id", "item_key"],
        },
    },
    {
        "name": "zotero_get_collection",
        "description": "Get a single collection by key from the mirror or headless store.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}, "collection_key": {"type": "string"}},
            "required": ["library_id", "collection_key"],
        },
    },
    {
        "name": "zotero_local_sql",
        "description": "Run a guarded read-only SQL query against the local zotero.sqlite database.",
        "inputSchema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
    {
        "name": "zotero_local_import",
        "description": "Import the configured local Zotero desktop profile into headless local:* libraries.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_local_poll",
        "description": "Poll the configured local Zotero desktop profile for item and collection changes against headless local:* state.",
        "inputSchema": {
            "type": "object",
            "properties": {"since_version": {"type": "integer"}},
        },
    },
    {
        "name": "zotero_local_plan_apply",
        "description": "Plan pending headless local:* writeback operations against the current local Zotero desktop schema without executing them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 1000},
            },
        },
    },
    {
        "name": "zotero_local_apply",
        "description": "Apply the currently plannable pending headless local:* operations to the local Zotero desktop database. Experimental and intentionally narrow in scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 1000},
            },
        },
    },
    {
        "name": "zotero_sync_mirror_discover",
        "description": "Discover remote Zotero libraries and register them in the mirror via the Zotero Web API.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_sync_mirror_pull",
        "description": "Pull a remote Zotero library into the mirror via the Zotero Web API.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}},
            "required": ["library_id"],
        },
    },
    {
        "name": "zotero_sync_discover",
        "description": "Discover remote Zotero libraries and register them in the headless store.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "zotero_sync_pull",
        "description": "Pull a remote Zotero library into the headless store via the Zotero Web API.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}},
            "required": ["library_id"],
        },
    },
    {
        "name": "zotero_sync_push",
        "description": "Push pending headless store changes for a remote Zotero library to the Zotero Web API.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}},
            "required": ["library_id"],
        },
    },
    {
        "name": "zotero_sync_conflicts",
        "description": "List unresolved sync conflicts for a library.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "entity_type": {"type": "string", "enum": ["item", "collection"]},
            },
            "required": ["library_id"],
        },
    },
    {
        "name": "zotero_sync_conflict_rebase",
        "description": "Resolve a sync conflict by keeping the local payload but rebasing it onto the latest remote version.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "entity_type": {"type": "string", "enum": ["item", "collection"]},
                "entity_key": {"type": "string"},
            },
            "required": ["library_id", "entity_type", "entity_key"],
        },
    },
    {
        "name": "zotero_sync_conflict_accept_remote",
        "description": "Resolve a sync conflict by accepting the latest remote payload and discarding the local pending version.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "entity_type": {"type": "string", "enum": ["item", "collection"]},
                "entity_key": {"type": "string"},
            },
            "required": ["library_id", "entity_type", "entity_key"],
        },
    },
    {
        "name": "zotero_qmd_query",
        "description": "Run qmd hybrid semantic search over exported Zotero Markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "zotero_qmd_vsearch",
        "description": "Run qmd vector search over exported Zotero Markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "zotero_qmd_search",
        "description": "Run qmd keyword search over exported Zotero Markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "library_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "zotero_create_item",
        "description": "Create an item in a remote Zotero library. Local library writes require the future daemon backend.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}, "item": {"type": "object"}},
            "required": ["library_id", "item"],
        },
    },
    {
        "name": "zotero_update_item",
        "description": "Update an existing item in a remote Zotero library. Local library writes require the future daemon backend.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "item_key": {"type": "string"},
                "patch": {"type": "object"},
            },
            "required": ["library_id", "item_key", "patch"],
        },
    },
    {
        "name": "zotero_delete_item",
        "description": "Delete an item from a remote Zotero library. Local library writes require the future daemon backend.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}, "item_key": {"type": "string"}},
            "required": ["library_id", "item_key"],
        },
    },
    {
        "name": "zotero_create_collection",
        "description": "Create a collection in a remote or headless Zotero library.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}, "collection": {"type": "object"}},
            "required": ["library_id", "collection"],
        },
    },
    {
        "name": "zotero_update_collection",
        "description": "Update an existing collection in a remote or headless Zotero library.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {"type": "string"},
                "collection_key": {"type": "string"},
                "patch": {"type": "object"},
            },
            "required": ["library_id", "collection_key", "patch"],
        },
    },
    {
        "name": "zotero_delete_collection",
        "description": "Delete a collection from a remote or headless Zotero library.",
        "inputSchema": {
            "type": "object",
            "properties": {"library_id": {"type": "string"}, "collection_key": {"type": "string"}},
            "required": ["library_id", "collection_key"],
        },
    },
]


def _result(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, sort_keys=True),
            }
        ]
    }


def run_stdio_server(settings: Settings) -> None:
    canonical = CanonicalStore(settings.resolved_canonical_db())
    store = MirrorStore(settings.resolved_mirror_db())
    sync_service = SyncService(settings, store)
    service = HeadlessService(settings, store, canonical)
    qmd = QmdClient(settings)
    local_adapter = LocalDesktopAdapter(canonical)

    def canonical_sync() -> CanonicalWebSyncAdapter:
        return CanonicalWebSyncAdapter(canonical, ZoteroWebClient(settings))

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            method = message.get("method")
            msg_id = message.get("id")
            params = message.get("params") or {}

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "zotero-headless", "version": "0.1.0"},
                    },
                }
            elif method == "notifications/initialized":
                continue
            elif method == "ping":
                response = {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            elif method == "tools/list":
                response = {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
            elif method == "tools/call":
                name = params["name"]
                arguments = params.get("arguments") or {}
                if name == "zotero_capabilities":
                    payload = get_capabilities(settings)
                elif name == "zotero_daemon_status":
                    payload = current_daemon_status(settings).to_dict()
                elif name == "zotero_core_status":
                    payload = canonical.status()
                elif name == "zotero_core_libraries":
                    payload = canonical.list_libraries()
                elif name == "zotero_core_changes":
                    payload = canonical.list_changes(
                        library_id=arguments.get("library_id"),
                        limit=int(arguments.get("limit", 20)),
                    )
                elif name == "zotero_list_libraries":
                    payload = merged_libraries(store, canonical)
                elif name == "zotero_list_items":
                    if prefers_canonical_reads(canonical, arguments["library_id"]):
                        payload = canonical.list_entities(
                            arguments["library_id"],
                            "item",
                            limit=int(arguments.get("limit", 20)),
                            query=arguments.get("query"),
                        )
                    else:
                        payload = store.list_objects(
                            arguments["library_id"],
                            "item",
                            limit=int(arguments.get("limit", 20)),
                            query=arguments.get("query"),
                        )
                elif name == "zotero_list_collections":
                    if prefers_canonical_reads(canonical, arguments["library_id"]):
                        payload = canonical.list_entities(
                            arguments["library_id"],
                            "collection",
                            limit=int(arguments.get("limit", 20)),
                            query=arguments.get("query"),
                        )
                    else:
                        payload = store.list_objects(
                            arguments["library_id"],
                            "collection",
                            limit=int(arguments.get("limit", 20)),
                            query=arguments.get("query"),
                        )
                elif name == "zotero_get_item":
                    payload = (
                        canonical.get_entity(arguments["library_id"], "item", arguments["item_key"])
                        if prefers_canonical_reads(canonical, arguments["library_id"])
                        else store.get_object(arguments["library_id"], "item", arguments["item_key"])
                    )
                elif name == "zotero_get_collection":
                    payload = (
                        canonical.get_entity(arguments["library_id"], "collection", arguments["collection_key"])
                        if prefers_canonical_reads(canonical, arguments["library_id"])
                        else store.get_object(arguments["library_id"], "collection", arguments["collection_key"])
                    )
                elif name == "zotero_local_sql":
                    sqlite_path = settings.resolved_local_db()
                    if not sqlite_path:
                        raise ValueError("No local Zotero DB configured")
                    payload = LocalZoteroDB(sqlite_path).query(arguments["sql"])
                elif name == "zotero_local_import":
                    payload = local_adapter.import_snapshot(settings.data_dir or "")
                elif name == "zotero_local_poll":
                    payload = [
                        {
                            "library_id": change.library_id,
                            "entity_type": change.entity_type.value,
                            "entity_key": change.entity_key,
                            "change_type": change.change_type.value,
                            "payload": change.payload,
                            "base_version": change.base_version,
                            "created_at": change.created_at,
                        }
                        for change in local_adapter.poll_changes(
                            settings.data_dir or "",
                            since_version=arguments.get("since_version"),
                        )
                    ]
                elif name == "zotero_local_plan_apply":
                    payload = local_adapter.plan_pending_writes(
                        settings.data_dir or "",
                        library_id=arguments.get("library_id"),
                        limit=int(arguments.get("limit", 1000)),
                    )
                elif name == "zotero_local_apply":
                    payload = local_adapter.apply_pending_writes(
                        settings.data_dir or "",
                        library_id=arguments.get("library_id"),
                        limit=int(arguments.get("limit", 1000)),
                    )
                elif name == "zotero_sync_pull":
                    payload = sync_service.sync_remote_library(arguments["library_id"]).__dict__
                elif name == "zotero_sync_discover":
                    payload = canonical_sync().discover_libraries()
                elif name == "zotero_sync_pull":
                    payload = canonical_sync().pull_library(arguments["library_id"])
                elif name == "zotero_sync_push":
                    payload = canonical_sync().push_changes(arguments["library_id"])
                elif name == "zotero_sync_mirror_discover":
                    payload = sync_service.discover_remote_libraries()
                elif name == "zotero_sync_mirror_pull":
                    payload = sync_service.sync_remote_library(arguments["library_id"]).__dict__
                elif name == "zotero_sync_conflicts":
                    payload = canonical_sync().list_conflicts(
                        arguments["library_id"],
                        entity_type=EntityType(arguments["entity_type"]) if arguments.get("entity_type") else None,
                    )
                elif name == "zotero_sync_conflict_rebase":
                    payload = canonical_sync().rebase_conflict_keep_local(
                        arguments["library_id"],
                        EntityType(arguments["entity_type"]),
                        arguments["entity_key"],
                    )
                elif name == "zotero_sync_conflict_accept_remote":
                    payload = canonical_sync().accept_remote_conflict(
                        arguments["library_id"],
                        EntityType(arguments["entity_type"]),
                        arguments["entity_key"],
                    )
                elif name == "zotero_qmd_query":
                    payload = qmd.search(
                        "query",
                        arguments["query"],
                        limit=int(arguments.get("limit", 10)),
                        library_id=arguments.get("library_id"),
                    )
                elif name == "zotero_qmd_vsearch":
                    payload = qmd.search(
                        "vsearch",
                        arguments["query"],
                        limit=int(arguments.get("limit", 10)),
                        library_id=arguments.get("library_id"),
                    )
                elif name == "zotero_qmd_search":
                    payload = qmd.search(
                        "search",
                        arguments["query"],
                        limit=int(arguments.get("limit", 10)),
                        library_id=arguments.get("library_id"),
                    )
                elif name == "zotero_create_item":
                    payload = service.create_item(arguments["library_id"], arguments["item"])
                elif name == "zotero_update_item":
                    payload = service.update_item(arguments["library_id"], arguments["item_key"], arguments["patch"])
                elif name == "zotero_delete_item":
                    payload = service.delete_item(arguments["library_id"], arguments["item_key"])
                elif name == "zotero_create_collection":
                    payload = service.create_collection(arguments["library_id"], arguments["collection"])
                elif name == "zotero_update_collection":
                    payload = service.update_collection(
                        arguments["library_id"],
                        arguments["collection_key"],
                        arguments["patch"],
                    )
                elif name == "zotero_delete_collection":
                    payload = service.delete_collection(arguments["library_id"], arguments["collection_key"])
                else:
                    raise ValueError(f"Unknown tool: {name}")
                response = {"jsonrpc": "2.0", "id": msg_id, "result": _result(payload)}
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"},
                }
        except LocalWriteRequiresDaemonError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id") if isinstance(locals().get("message"), dict) else None,
                "error": {"code": -32001, "message": str(exc)},
            }
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id") if isinstance(locals().get("message"), dict) else None,
                "error": {"code": -32000, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="zotero-headless-mcp")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    run_stdio_server(load_settings())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
