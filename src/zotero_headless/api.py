from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .adapters.local_desktop import LocalDesktopAdapter
from .adapters.web_sync import CanonicalWebSyncAdapter
from .capabilities import get_capabilities
from .config import Settings
from .core import CanonicalStore, EntityType
from .daemon import current_daemon_status
from .library_routing import merged_libraries, prefers_canonical_reads
from .local_db import LocalZoteroDB
from .observability import build_metrics_text, read_jobs_state, read_runtime_state, record_http_request
from .qmd import QmdClient
from .service import HeadlessService, LocalWriteRequiresDaemonError
from .store import MirrorStore
from .sync import SyncService
from .web_api import ZoteroWebClient


def make_handler(settings: Settings, store: MirrorStore):
    canonical = CanonicalStore(settings.resolved_canonical_db())
    sync_service = SyncService(settings, store)
    service = HeadlessService(settings, store, canonical)
    qmd = QmdClient(settings)
    local_adapter = LocalDesktopAdapter(canonical)

    def canonical_sync() -> CanonicalWebSyncAdapter:
        return CanonicalWebSyncAdapter(canonical, ZoteroWebClient(settings))

    class Handler(BaseHTTPRequestHandler):
        server_version = "zotero-headless/0.1"

        def log_message(self, format: str, *args) -> None:
            return

        def _record_request(self, status: int) -> None:
            started_at = getattr(self, "_request_started_at", None)
            if started_at is None:
                return
            self._request_started_at = None
            record_http_request(
                settings,
                method=self.command,
                path=self.path,
                status=status,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                remote_addr=self.client_address[0] if self.client_address else None,
            )

        def _json_response(self, status: int, payload):
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self._record_request(status)

        def _text_response(self, status: int, body: str, *, content_type: str = "text/plain; charset=utf-8"):
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            self._record_request(status)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self):
            self._request_started_at = time.perf_counter()
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            parts = [part for part in parsed.path.split("/") if part]

            if parsed.path == "/health":
                return self._json_response(200, {"ok": True})
            if parsed.path == "/capabilities":
                return self._json_response(200, get_capabilities(settings))
            if parsed.path == "/daemon/status":
                return self._json_response(200, current_daemon_status(settings).to_dict())
            if parsed.path == "/daemon/runtime":
                return self._json_response(200, read_runtime_state(settings) or {})
            if parsed.path == "/daemon/jobs":
                return self._json_response(200, read_jobs_state(settings))
            if parsed.path == "/metrics":
                return self._text_response(200, build_metrics_text(settings))
            if parsed.path == "/core/status":
                return self._json_response(200, canonical.status())
            if parsed.path == "/core/libraries":
                return self._json_response(200, {"libraries": canonical.list_libraries()})
            if parsed.path == "/core/changes":
                library_id = params.get("library_id", [None])[0]
                limit = int(params.get("limit", ["100"])[0])
                return self._json_response(200, {"changes": canonical.list_changes(library_id=library_id, limit=limit)})
            if parsed.path == "/sync/canonical/conflicts":
                library_id = params.get("library_id", [None])[0]
                if not library_id:
                    return self._json_response(400, {"error": "library_id is required"})
                entity_type_name = params.get("entity_type", [None])[0]
                entity_type = EntityType(entity_type_name) if entity_type_name else None
                return self._json_response(200, {"conflicts": canonical_sync().list_conflicts(library_id, entity_type=entity_type)})
            if parsed.path == "/libraries":
                return self._json_response(200, {"libraries": merged_libraries(store, canonical)})
            if parsed.path == "/search/query":
                query = params.get("q", [""])[0]
                library_id = params.get("library_id", [None])[0]
                return self._json_response(200, {"results": qmd.search("query", query, library_id=library_id)})
            if parsed.path == "/search/vsearch":
                query = params.get("q", [""])[0]
                library_id = params.get("library_id", [None])[0]
                return self._json_response(200, {"results": qmd.search("vsearch", query, library_id=library_id)})
            if parsed.path == "/search/search":
                query = params.get("q", [""])[0]
                library_id = params.get("library_id", [None])[0]
                return self._json_response(200, {"results": qmd.search("search", query, library_id=library_id)})

            if len(parts) >= 3 and parts[0] == "libraries":
                library_id = parts[1]
                if len(parts) == 3 and parts[2] in {"items", "collections", "searches"}:
                    kind = parts[2][:-1]
                    limit = int(params.get("limit", ["100"])[0])
                    query = params.get("q", [None])[0]
                    if prefers_canonical_reads(canonical, library_id):
                        entity_type = {"item": "item", "collection": "collection", "search": "search"}[kind]
                        return self._json_response(
                            200,
                            {"results": canonical.list_entities(library_id, entity_type, limit=limit, query=query)},
                        )
                    return self._json_response(
                        200,
                        {"results": store.list_objects(library_id, kind, limit=limit, query=query)},
                    )
                if len(parts) == 4 and parts[2] == "items":
                    item = (
                        canonical.get_entity(library_id, "item", parts[3])
                        if prefers_canonical_reads(canonical, library_id)
                        else store.get_object(library_id, "item", parts[3])
                    )
                    if not item:
                        return self._json_response(404, {"error": "Item not found"})
                    return self._json_response(200, item)
                if len(parts) == 4 and parts[2] == "collections":
                    collection = (
                        canonical.get_entity(library_id, "collection", parts[3])
                        if prefers_canonical_reads(canonical, library_id)
                        else store.get_object(library_id, "collection", parts[3])
                    )
                    if not collection:
                        return self._json_response(404, {"error": "Collection not found"})
                    return self._json_response(200, collection)
            return self._json_response(404, {"error": "Not found"})

        def do_POST(self):
            self._request_started_at = time.perf_counter()
            parsed = urlparse(self.path)
            body = self._read_json()
            if parsed.path == "/sync/discover":
                return self._json_response(200, {"libraries": sync_service.discover_remote_libraries()})
            if parsed.path == "/sync/pull":
                library_id = body.get("library_id")
                if library_id:
                    return self._json_response(200, {"result": sync_service.sync_remote_library(library_id).__dict__})
                results = [sync_service.sync_remote_library(lib["library_id"]).__dict__ for lib in store.list_libraries() if lib["source"] == "remote"]
                return self._json_response(200, {"results": results})
            if parsed.path == "/sync/canonical/discover":
                return self._json_response(200, {"libraries": canonical_sync().discover_libraries()})
            if parsed.path == "/sync/canonical/pull":
                return self._json_response(200, {"result": canonical_sync().pull_library(body["library_id"])})
            if parsed.path == "/sync/canonical/push":
                return self._json_response(200, {"result": canonical_sync().push_changes(body["library_id"])})
            if parsed.path == "/sync/canonical/conflicts/rebase":
                return self._json_response(
                    200,
                    {
                        "result": canonical_sync().rebase_conflict_keep_local(
                            body["library_id"],
                            EntityType(body["entity_type"]),
                            body["entity_key"],
                        )
                    },
                )
            if parsed.path == "/sync/canonical/conflicts/accept-remote":
                return self._json_response(
                    200,
                    {
                        "result": canonical_sync().accept_remote_conflict(
                            body["library_id"],
                            EntityType(body["entity_type"]),
                            body["entity_key"],
                        )
                    },
                )
            if parsed.path == "/local/import":
                return self._json_response(200, local_adapter.import_snapshot(settings.data_dir or ""))
            if parsed.path == "/local/poll":
                changes = local_adapter.poll_changes(
                    settings.data_dir or "",
                    since_version=body.get("since_version"),
                )
                return self._json_response(
                    200,
                    {
                        "changes": [
                            {
                                "library_id": change.library_id,
                                "entity_type": change.entity_type.value,
                                "entity_key": change.entity_key,
                                "change_type": change.change_type.value,
                                "payload": change.payload,
                                "base_version": change.base_version,
                                "created_at": change.created_at,
                            }
                            for change in changes
                        ]
                    },
                )
            if parsed.path == "/local/plan-apply":
                return self._json_response(
                    200,
                    local_adapter.plan_pending_writes(
                        settings.data_dir or "",
                        library_id=body.get("library_id"),
                        limit=int(body.get("limit", 1000)),
                    ),
                )
            if parsed.path == "/local/apply":
                return self._json_response(
                    200,
                    local_adapter.apply_pending_writes(
                        settings.data_dir or "",
                        library_id=body.get("library_id"),
                        limit=int(body.get("limit", 1000)),
                    ),
                )
            if parsed.path == "/search/export":
                library_id = body.get("library_id")
                if library_id:
                    if prefers_canonical_reads(canonical, library_id):
                        return self._json_response(200, qmd.export_from_canonical(canonical, library_id))
                    return self._json_response(200, qmd.export_from_store(store, library_id))
                exported = 0
                by_backend = {"mirror_exported": 0, "canonical_exported": 0}
                for library in merged_libraries(store, canonical):
                    library_id = library["library_id"]
                    if prefers_canonical_reads(canonical, library_id):
                        result = qmd.export_from_canonical(canonical, library_id)
                        by_backend["canonical_exported"] += int(result["exported"])
                    else:
                        result = qmd.export_from_store(store, library_id)
                        by_backend["mirror_exported"] += int(result["exported"])
                    exported += int(result["exported"])
                return self._json_response(
                    200,
                    {
                        "exported": exported,
                        "mirror_exported": by_backend["mirror_exported"],
                        "canonical_exported": by_backend["canonical_exported"],
                        "export_dir": str(settings.resolved_export_dir()),
                        "collection": settings.qmd_collection,
                    },
                )
            if parsed.path == "/core/libraries":
                library_id = body["library_id"]
                library = canonical.upsert_library(
                    library_id,
                    name=body["name"],
                    source=body.get("source", "headless"),
                    editable=bool(body.get("editable", True)),
                    metadata=body.get("metadata") or {},
                )
                return self._json_response(200, library)
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 3 and parts[0] == "libraries" and parts[2] == "items":
                library_id = parts[1]
                try:
                    created = service.create_item(library_id, body)
                except LocalWriteRequiresDaemonError as exc:
                    return self._json_response(501, {"error": str(exc)})
                return self._json_response(200, created)
            if len(parts) == 3 and parts[0] == "libraries" and parts[2] == "collections":
                library_id = parts[1]
                try:
                    created = service.create_collection(library_id, body)
                except LocalWriteRequiresDaemonError as exc:
                    return self._json_response(501, {"error": str(exc)})
                return self._json_response(200, created)
            return self._json_response(404, {"error": "Not found"})

        def do_PATCH(self):
            self._request_started_at = time.perf_counter()
            parsed = urlparse(self.path)
            body = self._read_json()
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 4 and parts[0] == "libraries" and parts[2] == "items":
                library_id, item_key = parts[1], parts[3]
                try:
                    updated = service.update_item(library_id, item_key, body, replace=False)
                except LocalWriteRequiresDaemonError as exc:
                    return self._json_response(501, {"error": str(exc)})
                except KeyError:
                    return self._json_response(404, {"error": "Item not found"})
                return self._json_response(200, updated)
            if len(parts) == 4 and parts[0] == "libraries" and parts[2] == "collections":
                library_id, collection_key = parts[1], parts[3]
                try:
                    updated = service.update_collection(library_id, collection_key, body, replace=False)
                except LocalWriteRequiresDaemonError as exc:
                    return self._json_response(501, {"error": str(exc)})
                except KeyError:
                    return self._json_response(404, {"error": "Collection not found"})
                return self._json_response(200, updated)
            return self._json_response(404, {"error": "Not found"})

        def do_DELETE(self):
            self._request_started_at = time.perf_counter()
            parsed = urlparse(self.path)
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 4 and parts[0] == "libraries" and parts[2] == "items":
                library_id, item_key = parts[1], parts[3]
                try:
                    deleted = service.delete_item(library_id, item_key)
                except LocalWriteRequiresDaemonError as exc:
                    return self._json_response(501, {"error": str(exc)})
                except KeyError:
                    return self._json_response(404, {"error": "Item not found"})
                return self._json_response(200, deleted)
            if len(parts) == 4 and parts[0] == "libraries" and parts[2] == "collections":
                library_id, collection_key = parts[1], parts[3]
                try:
                    deleted = service.delete_collection(library_id, collection_key)
                except LocalWriteRequiresDaemonError as exc:
                    return self._json_response(501, {"error": str(exc)})
                except KeyError:
                    return self._json_response(404, {"error": "Collection not found"})
                return self._json_response(200, deleted)
            return self._json_response(404, {"error": "Not found"})

    return Handler


def serve_api(settings: Settings, host: str, port: int) -> None:
    store = MirrorStore(settings.resolved_mirror_db())
    handler = make_handler(settings, store)
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
