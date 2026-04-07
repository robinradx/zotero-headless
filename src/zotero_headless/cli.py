from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_setup import (
    SUPPORTED_SETUP_TARGETS,
    SUPPORTED_SKILL_TARGETS,
    SUPPORTED_SKILL_VARIANTS,
    export_skill,
    doctor_report,
    install_mcp_setup,
    install_skill,
    inspect_setup_target,
    remove_mcp_setup,
    setup_list,
)
from .api import serve_api
from .adapters.local_desktop import LocalDesktopAdapter
from .adapters.web_sync import CanonicalWebSyncAdapter
from .capabilities import get_capabilities
from .cli_ui import (
    render_config_payload,
    render_daemon_command,
    render_daemon_status,
    render_doctor_report,
    render_install_result,
    render_setup_list,
    render_setup_result,
    render_setup_target,
    render_update_plan,
    render_update_result,
    render_version_payload,
)
from .config import Settings, load_settings, save_settings
from .core import CanonicalStore, ChangeType, EntityType
from .daemon import build_daemon_command, build_runtime_command, current_daemon_status, serve_daemon_runtime
from .library_routing import merged_libraries, prefers_canonical_reads
from .installer_update import build_update_plan, run_update, version_payload
from .local_db import LocalZoteroDB
from .mcp import run_stdio_server
from .qmd import QmdAutoIndexer, QmdClient
from .setup_wizard import run_setup_wizard
from .service import HeadlessService, LocalWriteRequiresDaemonError
from .store import MirrorStore
from .sync import SyncService
from .web_api import ZoteroWebClient


def _print(payload) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _emit(payload, *, as_json: bool = False, renderer=None) -> None:
    if not as_json and renderer is not None:
        print(renderer(payload))
        return
    _print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zotero-headless",
        description="Headless Zotero-compatible runtime with CLI, API, MCP, local desktop interoperability, and web sync.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output for human-facing commands.")
    sub = parser.add_subparsers(dest="command", required=True)

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_init = config_sub.add_parser("init")
    config_init.add_argument("--data-dir")
    config_init.add_argument("--api-key")
    config_init.add_argument("--user-id", type=int)
    config_init.add_argument("--remote-library-id", action="append", dest="remote_library_ids")
    config_init.add_argument("--default-library-id")
    config_init.add_argument("--api-base")
    config_init.add_argument("--zotero-bin")
    config_sub.add_parser("autodiscover")
    config_sub.add_parser("wizard")
    config_sub.add_parser("show")

    sub.add_parser("capabilities")
    sub.add_parser("version")
    update = sub.add_parser("update")
    update.add_argument("--check", action="store_true")

    setup = sub.add_parser("setup")
    setup_sub = setup.add_subparsers(dest="setup_command", required=True)
    setup_sub.add_parser("start")
    setup_sub.add_parser("account")
    setup_sub.add_parser("libraries")
    setup_sub.add_parser("local")
    setup_sub.add_parser("wizard")
    setup_sub.add_parser("list")
    setup_show = setup_sub.add_parser("show")
    setup_show.add_argument("tool", choices=list(SUPPORTED_SETUP_TARGETS))
    setup_show.add_argument("--scope", choices=["project", "user"], default="project")
    setup_add = setup_sub.add_parser("add")
    setup_add.add_argument("tool", choices=list(SUPPORTED_SETUP_TARGETS))
    setup_add.add_argument("--scope", choices=["project", "user"], default="project")
    setup_remove = setup_sub.add_parser("remove")
    setup_remove.add_argument("tool", choices=[tool for tool in SUPPORTED_SETUP_TARGETS if tool != "json"])
    setup_remove.add_argument("--scope", choices=["project", "user"], default="project")

    skill = sub.add_parser("skill")
    skill_sub = skill.add_subparsers(dest="skill_command", required=True)
    skill_add = skill_sub.add_parser("add")
    skill_add.add_argument("tool", choices=list(SUPPORTED_SKILL_TARGETS))
    skill_add.add_argument("--variant", choices=list(SUPPORTED_SKILL_VARIANTS), default="general")
    skill_install = skill_sub.add_parser("install")
    skill_install.add_argument("tool", choices=list(SUPPORTED_SKILL_TARGETS))
    skill_install.add_argument("--variant", choices=list(SUPPORTED_SKILL_VARIANTS), default="general")
    skill_update = skill_sub.add_parser("update")
    skill_update.add_argument("tool", choices=list(SUPPORTED_SKILL_TARGETS))
    skill_update.add_argument("--variant", choices=list(SUPPORTED_SKILL_VARIANTS), default="general")
    skill_export = skill_sub.add_parser("export")
    skill_export.add_argument("tool", choices=list(SUPPORTED_SKILL_TARGETS))
    skill_export.add_argument("--variant", choices=list(SUPPORTED_SKILL_VARIANTS), default="general")

    sub.add_parser("doctor")

    daemon = sub.add_parser("daemon")
    daemon_sub = daemon.add_subparsers(dest="daemon_command", required=True)
    daemon_sub.add_parser("status")
    daemon_sub.add_parser("command")
    daemon_serve = daemon_sub.add_parser("serve")
    daemon_serve.add_argument("--host")
    daemon_serve.add_argument("--port", type=int)
    daemon_serve.add_argument("--sync-interval", type=int, default=0)

    core = sub.add_parser("core")
    core_sub = core.add_subparsers(dest="core_command", required=True)
    core_sub.add_parser("status")
    core_sub.add_parser("libraries")
    core_create_library = core_sub.add_parser("create-library")
    core_create_library.add_argument("library_id")
    core_create_library.add_argument("name")
    core_create_library.add_argument("--source", default="headless")
    core_changes = core_sub.add_parser("changes")
    core_changes.add_argument("--library")
    core_changes.add_argument("-n", "--limit", type=int, default=20)
    core_put_item = core_sub.add_parser("put-item")
    core_put_item.add_argument("library_id")
    core_put_item.add_argument("json_payload")
    core_put_item.add_argument("--key")

    local = sub.add_parser("local")
    local_sub = local.add_subparsers(dest="local_command", required=True)
    local_sub.add_parser("libraries")
    local_sql = local_sub.add_parser("sql")
    local_sql.add_argument("sql")
    local_item = local_sub.add_parser("item")
    local_item.add_argument("item_key")
    local_sub.add_parser("import")
    local_poll = local_sub.add_parser("poll")
    local_poll.add_argument("--since-version", type=int)
    local_plan_apply = local_sub.add_parser("plan-apply")
    local_plan_apply.add_argument("--library")
    local_plan_apply.add_argument("--limit", type=int, default=1000)
    local_apply = local_sub.add_parser("apply")
    local_apply.add_argument("--library")
    local_apply.add_argument("--limit", type=int, default=1000)

    sync = sub.add_parser("sync")
    sync_sub = sync.add_subparsers(dest="sync_command", required=True)
    sync_sub.add_parser("discover")
    sync_pull = sync_sub.add_parser("pull")
    sync_pull.add_argument("--library", required=True)
    sync_push = sync_sub.add_parser("push")
    sync_push.add_argument("--library", required=True)
    sync_sub.add_parser("mirror-discover")
    sync_mirror_pull = sync_sub.add_parser("mirror-pull")
    sync_mirror_pull.add_argument("--library")
    sync_conflicts = sync_sub.add_parser("conflicts")
    sync_conflicts.add_argument("--library", required=True)
    sync_conflicts.add_argument("--entity-type", choices=["item", "collection"])
    sync_conflict_rebase = sync_sub.add_parser("conflict-rebase")
    sync_conflict_rebase.add_argument("--library", required=True)
    sync_conflict_rebase.add_argument("--entity-type", choices=["item", "collection"], required=True)
    sync_conflict_rebase.add_argument("--key", required=True)
    sync_conflict_accept = sync_sub.add_parser("conflict-accept-remote")
    sync_conflict_accept.add_argument("--library", required=True)
    sync_conflict_accept.add_argument("--entity-type", choices=["item", "collection"], required=True)
    sync_conflict_accept.add_argument("--key", required=True)

    qmd = sub.add_parser("qmd")
    qmd_sub = qmd.add_subparsers(dest="qmd_command", required=True)
    qmd_export = qmd_sub.add_parser("export")
    qmd_export.add_argument("--library")
    qmd_sub.add_parser("embed")
    for command in ("query", "search", "vsearch"):
        qmd_cmd = qmd_sub.add_parser(command)
        qmd_cmd.add_argument("query")
        qmd_cmd.add_argument("--library")
        qmd_cmd.add_argument("-n", "--limit", type=int, default=10)

    api = sub.add_parser("api")
    api_sub = api.add_subparsers(dest="api_command", required=True)
    api_serve = api_sub.add_parser("serve")
    api_serve.add_argument("--host", default="127.0.0.1")
    api_serve.add_argument("--port", type=int, default=8787)

    mcp = sub.add_parser("mcp")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_sub.add_parser("serve")

    mirror = sub.add_parser("mirror")
    mirror_sub = mirror.add_subparsers(dest="mirror_command", required=True)
    mirror_sub.add_parser("libraries")
    mirror_collections = mirror_sub.add_parser("collections")
    mirror_collections.add_argument("library_id")
    mirror_collections.add_argument("-n", "--limit", type=int, default=20)
    mirror_collections.add_argument("-q", "--query")
    mirror_collection = mirror_sub.add_parser("collection")
    mirror_collection.add_argument("library_id")
    mirror_collection.add_argument("collection_key")
    mirror_items = mirror_sub.add_parser("items")
    mirror_items.add_argument("library_id")
    mirror_items.add_argument("-n", "--limit", type=int, default=20)
    mirror_items.add_argument("-q", "--query")
    mirror_item = mirror_sub.add_parser("item")
    mirror_item.add_argument("library_id")
    mirror_item.add_argument("item_key")

    item = sub.add_parser("item")
    item_sub = item.add_subparsers(dest="item_command", required=True)
    item_create = item_sub.add_parser("create")
    item_create.add_argument("library_id")
    item_create.add_argument("json_payload")
    item_update = item_sub.add_parser("update")
    item_update.add_argument("library_id")
    item_update.add_argument("item_key")
    item_update.add_argument("json_payload")
    item_delete = item_sub.add_parser("delete")
    item_delete.add_argument("library_id")
    item_delete.add_argument("item_key")

    collection = sub.add_parser("collection")
    collection_sub = collection.add_subparsers(dest="collection_command", required=True)
    collection_create = collection_sub.add_parser("create")
    collection_create.add_argument("library_id")
    collection_create.add_argument("json_payload")
    collection_update = collection_sub.add_parser("update")
    collection_update.add_argument("library_id")
    collection_update.add_argument("collection_key")
    collection_update.add_argument("json_payload")
    collection_delete = collection_sub.add_parser("delete")
    collection_delete.add_argument("library_id")
    collection_delete.add_argument("collection_key")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        settings = load_settings()
        if args.config_command == "autodiscover":
            from .autodiscover import autodiscover_settings

            _emit(
                {"autodiscovered": autodiscover_settings(settings).to_dict(), "settings": settings.as_dict()},
                as_json=args.json,
                renderer=render_config_payload,
            )
            return 0
        if args.config_command == "init":
            updated = Settings(
                data_dir=args.data_dir or settings.data_dir,
                api_key=args.api_key or settings.api_key,
                user_id=args.user_id if args.user_id is not None else settings.user_id,
                remote_library_ids=args.remote_library_ids if args.remote_library_ids is not None else list(settings.remote_library_ids),
                default_library_id=args.default_library_id or settings.default_library_id,
                api_base=args.api_base or settings.api_base,
                state_dir=str(settings.resolved_state_dir()),
                canonical_db=str(settings.resolved_canonical_db()),
                mirror_db=str(settings.resolved_mirror_db()),
                export_dir=str(settings.resolved_export_dir()),
                file_cache_dir=str(settings.resolved_file_cache_dir()),
                qmd_collection=settings.qmd_collection,
                zotero_bin=args.zotero_bin or settings.zotero_bin,
                daemon_host=settings.daemon_host,
                daemon_port=settings.daemon_port,
            )
            path = save_settings(updated)
            _emit(
                {"config": str(path), "settings": updated.as_dict()},
                as_json=args.json,
                renderer=render_setup_result,
            )
            return 0
        if args.config_command == "wizard":
            result = run_setup_wizard(settings)
            path = save_settings(result.settings)
            _emit(
                {
                    "config": str(path),
                    "settings": result.settings.as_dict(),
                    "discovered_libraries": result.discovered_libraries,
                    "selected_remote_libraries": result.selected_library_ids,
                },
                as_json=args.json,
                renderer=render_setup_result,
            )
            return 0
        if args.config_command == "show":
            _emit(settings.as_dict(), as_json=args.json, renderer=render_config_payload)
            return 0

    if args.command == "capabilities":
        settings = load_settings(ensure_dirs=False)
        _print(get_capabilities(settings))
        return 0

    if args.command == "version":
        _emit(version_payload(), as_json=args.json, renderer=render_version_payload)
        return 0

    if args.command == "update":
        plan = build_update_plan()
        if args.check:
            _emit({"plan": plan.to_dict()}, as_json=args.json, renderer=render_update_plan)
            return 0
        _emit(run_update(plan), as_json=args.json, renderer=render_update_result)
        return 0

    if args.command == "setup":
        settings = load_settings(ensure_dirs=False)
        cwd = Path.cwd()
        if args.setup_command in {"start", "wizard", "account", "libraries", "local"}:
            mode = {
                "start": "full",
                "wizard": "full",
                "account": "account",
                "libraries": "libraries",
                "local": "local",
            }[args.setup_command]
            result = run_setup_wizard(settings, mode=mode)
            path = save_settings(result.settings)
            _emit(
                {
                    "config": str(path),
                    "autodiscovered": result.autodiscovered,
                    "settings": result.settings.as_dict(),
                    "discovered_libraries": result.discovered_libraries,
                    "selected_remote_libraries": result.selected_library_ids,
                },
                as_json=args.json,
                renderer=render_setup_result,
            )
            return 0
        if args.setup_command == "list":
            _emit({"targets": setup_list(settings, cwd=cwd)}, as_json=args.json, renderer=lambda payload: render_setup_list(payload["targets"]))
            return 0
        if args.setup_command == "show":
            _emit(
                inspect_setup_target(args.tool, settings, cwd=cwd, scope=args.scope),
                as_json=args.json,
                renderer=render_setup_target,
            )
            return 0
        if args.setup_command == "add":
            _emit(
                install_mcp_setup(args.tool, settings, cwd=cwd, scope=args.scope),
                as_json=args.json,
                renderer=lambda payload: render_install_result(payload, heading="MCP setup written"),
            )
            return 0
        if args.setup_command == "remove":
            _emit(
                remove_mcp_setup(args.tool, cwd=cwd, scope=args.scope),
                as_json=args.json,
                renderer=lambda payload: render_install_result(payload, heading="MCP setup removed"),
            )
            return 0

    if args.command == "skill":
        if args.skill_command in {"add", "install", "update"}:
            _emit(
                install_skill(args.tool, variant=args.variant),
                as_json=args.json,
                renderer=lambda payload: render_install_result(payload, heading="Skill installed"),
            )
            return 0
        if args.skill_command == "export":
            _print(export_skill(args.tool, variant=args.variant))
            return 0

    if args.command == "doctor":
        settings = load_settings(ensure_dirs=False)
        _emit(doctor_report(settings, cwd=Path.cwd()), as_json=args.json, renderer=render_doctor_report)
        return 0

    if args.command == "daemon":
        settings = load_settings(ensure_dirs=False)
        if args.daemon_command == "status":
            _emit(current_daemon_status(settings).to_dict(), as_json=args.json, renderer=render_daemon_status)
            return 0
        if args.daemon_command == "command":
            _emit(
                {
                    "runtime_argv": build_runtime_command(settings),
                    "desktop_helper_argv": build_daemon_command(settings),
                    "local_api_url": f"http://{settings.daemon_host}:{settings.daemon_port}/api/",
                },
                as_json=args.json,
                renderer=render_daemon_command,
            )
            return 0
        if args.daemon_command == "serve":
            runtime_settings = load_settings()
            serve_daemon_runtime(
                runtime_settings,
                host=args.host,
                port=args.port,
                sync_interval_seconds=args.sync_interval,
            )
            return 0

    settings = load_settings()
    canonical = CanonicalStore(settings.resolved_canonical_db())
    store = MirrorStore(settings.resolved_mirror_db())
    qmd_indexer = QmdAutoIndexer(settings)
    sync_service = SyncService(settings, store, qmd_indexer=qmd_indexer)
    service = HeadlessService(settings, store, canonical, qmd_indexer=qmd_indexer)
    local_adapter = LocalDesktopAdapter(canonical, qmd_indexer=qmd_indexer)

    if args.command == "core":
        if args.core_command == "status":
            _print(canonical.status())
            return 0
        if args.core_command == "libraries":
            _print(canonical.list_libraries())
            return 0
        if args.core_command == "create-library":
            _print(
                canonical.upsert_library(
                    args.library_id,
                    name=args.name,
                    source=args.source,
                )
            )
            return 0
        if args.core_command == "changes":
            _print(canonical.list_changes(library_id=args.library, limit=args.limit))
            return 0
        if args.core_command == "put-item":
            payload = json.loads(args.json_payload)
            existing = canonical.get_entity(args.library_id, EntityType.ITEM, args.key or payload.get("key", ""))
            change_type = ChangeType.UPDATE if existing else ChangeType.CREATE
            result = canonical.save_entity(
                args.library_id,
                EntityType.ITEM,
                payload,
                entity_key=args.key,
                synced=False,
                change_type=change_type,
            )
            try:
                qmd_indexer.refresh_canonical_library(canonical, args.library_id)
            except Exception:
                pass
            _print(result)
            return 0

    if args.command == "local":
        sqlite_path = settings.resolved_local_db()
        if not sqlite_path:
            parser.error("Local Zotero data_dir is not configured")
        db = LocalZoteroDB(sqlite_path)
        if args.local_command == "libraries":
            _print(db.list_libraries())
            return 0
        if args.local_command == "sql":
            _print(db.query(args.sql))
            return 0
        if args.local_command == "item":
            _print(db.get_item_detail(args.item_key))
            return 0
        if args.local_command == "import":
            _print(local_adapter.import_snapshot(settings.data_dir or ""))
            return 0
        if args.local_command == "poll":
            _print(
                [
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
                        since_version=args.since_version,
                    )
                ]
            )
            return 0
        if args.local_command == "plan-apply":
            _print(
                local_adapter.plan_pending_writes(
                    settings.data_dir or "",
                    library_id=args.library,
                    limit=args.limit,
                )
            )
            return 0
        if args.local_command == "apply":
            _print(
                local_adapter.apply_pending_writes(
                    settings.data_dir or "",
                    library_id=args.library,
                    limit=args.limit,
                )
            )
            return 0

    if args.command == "sync":
        if args.sync_command == "discover":
            client = ZoteroWebClient(settings)
            adapter = CanonicalWebSyncAdapter(canonical, client, qmd_indexer=qmd_indexer)
            _print(adapter.discover_libraries())
            return 0
        if args.sync_command == "pull":
            client = ZoteroWebClient(settings)
            adapter = CanonicalWebSyncAdapter(canonical, client, qmd_indexer=qmd_indexer)
            _print(adapter.pull_library(args.library))
            return 0
        if args.sync_command == "push":
            client = ZoteroWebClient(settings)
            adapter = CanonicalWebSyncAdapter(canonical, client, qmd_indexer=qmd_indexer)
            _print(adapter.push_changes(args.library))
            return 0
        if args.sync_command == "mirror-discover":
            _print(sync_service.discover_remote_libraries())
            return 0
        if args.sync_command == "conflicts":
            client = ZoteroWebClient(settings)
            adapter = CanonicalWebSyncAdapter(canonical, client, qmd_indexer=qmd_indexer)
            entity_type = EntityType(args.entity_type) if args.entity_type else None
            _print(adapter.list_conflicts(args.library, entity_type=entity_type))
            return 0
        if args.sync_command == "conflict-rebase":
            client = ZoteroWebClient(settings)
            adapter = CanonicalWebSyncAdapter(canonical, client, qmd_indexer=qmd_indexer)
            _print(
                adapter.rebase_conflict_keep_local(
                    args.library,
                    EntityType(args.entity_type),
                    args.key,
                )
            )
            return 0
        if args.sync_command == "conflict-accept-remote":
            client = ZoteroWebClient(settings)
            adapter = CanonicalWebSyncAdapter(canonical, client, qmd_indexer=qmd_indexer)
            _print(
                adapter.accept_remote_conflict(
                    args.library,
                    EntityType(args.entity_type),
                    args.key,
                )
            )
            return 0
        if args.sync_command == "mirror-pull":
            if args.library:
                _print(sync_service.sync_remote_library(args.library).__dict__)
            else:
                results = [
                    sync_service.sync_remote_library(library["library_id"]).__dict__
                    for library in store.list_libraries()
                    if library["source"] == "remote"
                ]
                _print(results)
            return 0

    if args.command == "qmd":
        client = QmdClient(settings)
        if args.qmd_command == "export":
            if args.library:
                if prefers_canonical_reads(canonical, args.library):
                    _print(client.export_from_canonical(canonical, args.library))
                else:
                    _print(client.export_from_store(store, args.library))
            else:
                exported = 0
                by_backend = {"mirror_exported": 0, "canonical_exported": 0}
                for library in merged_libraries(store, canonical):
                    library_id = library["library_id"]
                    if prefers_canonical_reads(canonical, library_id):
                        result = client.export_from_canonical(canonical, library_id)
                        by_backend["canonical_exported"] += int(result["exported"])
                    else:
                        result = client.export_from_store(store, library_id)
                        by_backend["mirror_exported"] += int(result["exported"])
                    exported += int(result["exported"])
                _print(
                    {
                        "exported": exported,
                        "mirror_exported": by_backend["mirror_exported"],
                        "canonical_exported": by_backend["canonical_exported"],
                        "export_dir": str(settings.resolved_export_dir()),
                        "collection": settings.qmd_collection,
                    }
                )
            return 0
        if args.qmd_command == "embed":
            print(client.embed())
            return 0
        if args.qmd_command in {"query", "search", "vsearch"}:
            _print(client.search(args.qmd_command, args.query, limit=args.limit, library_id=args.library))
            return 0

    if args.command == "mirror":
        if args.mirror_command == "libraries":
            _print(merged_libraries(store, canonical))
            return 0
        if args.mirror_command == "collections":
            if prefers_canonical_reads(canonical, args.library_id):
                _print(canonical.list_entities(args.library_id, EntityType.COLLECTION, limit=args.limit, query=args.query))
            else:
                _print(store.list_objects(args.library_id, "collection", limit=args.limit, query=args.query))
            return 0
        if args.mirror_command == "collection":
            if prefers_canonical_reads(canonical, args.library_id):
                _print(canonical.get_entity(args.library_id, EntityType.COLLECTION, args.collection_key))
            else:
                _print(store.get_object(args.library_id, "collection", args.collection_key))
            return 0
        if args.mirror_command == "items":
            if prefers_canonical_reads(canonical, args.library_id):
                _print(canonical.list_entities(args.library_id, EntityType.ITEM, limit=args.limit, query=args.query))
            else:
                _print(store.list_objects(args.library_id, "item", limit=args.limit, query=args.query))
            return 0
        if args.mirror_command == "item":
            if prefers_canonical_reads(canonical, args.library_id):
                _print(canonical.get_entity(args.library_id, EntityType.ITEM, args.item_key))
            else:
                _print(store.get_object(args.library_id, "item", args.item_key))
            return 0

    if args.command == "item":
        try:
            if args.item_command == "create":
                _print(service.create_item(args.library_id, json.loads(args.json_payload)))
                return 0
            if args.item_command == "update":
                _print(service.update_item(args.library_id, args.item_key, json.loads(args.json_payload)))
                return 0
            if args.item_command == "delete":
                _print(service.delete_item(args.library_id, args.item_key))
                return 0
        except LocalWriteRequiresDaemonError as exc:
            _print({"error": str(exc), "library_id": args.library_id})
            return 1

    if args.command == "collection":
        try:
            if args.collection_command == "create":
                _print(service.create_collection(args.library_id, json.loads(args.json_payload)))
                return 0
            if args.collection_command == "update":
                _print(service.update_collection(args.library_id, args.collection_key, json.loads(args.json_payload)))
                return 0
            if args.collection_command == "delete":
                _print(service.delete_collection(args.library_id, args.collection_key))
                return 0
        except LocalWriteRequiresDaemonError as exc:
            _print({"error": str(exc), "library_id": args.library_id})
            return 1

    if args.command == "api" and args.api_command == "serve":
        serve_api(settings, args.host, args.port)
        return 0

    if args.command == "mcp" and args.mcp_command == "serve":
        run_stdio_server(settings)
        return 0

    parser.error("Unhandled command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
