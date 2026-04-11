from __future__ import annotations

import argparse
import os
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .config import Settings, load_settings
from .core import CanonicalStore, EntityType
from .observability import (
    clear_runtime_state,
    events_log_path,
    finish_background_sync_run,
    initialize_runtime_state,
    jobs_state_path,
    read_runtime_state,
    runtime_state_path,
    start_background_sync_run,
    write_runtime_state,
)
from .qmd import QmdAutoIndexer
from .store import MirrorStore
from .utils import ensure_dir


@dataclass(slots=True)
class DaemonStatus:
    available: bool
    mode: str
    message: str
    runtime_available: bool = False
    runtime_mode: str = "pending"
    runtime_message: str = ""
    runtime_running: bool = False
    runtime_read_api_ready: bool = False
    runtime_write_api_ready: bool = False
    runtime_launch_command: list[str] | None = None
    desktop_helper_command_available: bool = False
    read_api_ready: bool = False
    write_api_ready: bool = False
    desktop_helper_workflow_dir: str | None = None
    executable: str | None = None
    launch_command: list[str] | None = None
    local_api_url: str | None = None
    runtime_state_path: str | None = None
    jobs_state_path: str | None = None
    events_log_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def desktop_helper_workflow_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "desktop_helper"


def build_daemon_command(settings: Settings) -> list[str] | None:
    if not settings.zotero_bin:
        return None
    command = [settings.zotero_bin, "-ZoteroDaemon"]
    if settings.data_dir:
        command.extend(["-datadir", settings.data_dir])
    return command


def build_runtime_command(settings: Settings, *, sync_interval_seconds: int = 0) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "zotero_headless.daemon",
        "serve",
        "--host",
        settings.daemon_host,
        "--port",
        str(settings.daemon_port),
    ]
    if sync_interval_seconds > 0:
        command.extend(["--sync-interval", str(sync_interval_seconds)])
    return command


def _runtime_dir(settings: Settings) -> Path:
    return ensure_dir(settings.resolved_state_dir() / "daemon")


def _runtime_state_path(settings: Settings) -> Path:
    return runtime_state_path(settings)


def _read_runtime_state(settings: Settings) -> dict | None:
    return read_runtime_state(settings)


def _write_runtime_state(settings: Settings, payload: dict) -> None:
    write_runtime_state(settings, payload)


def _clear_runtime_state(settings: Settings) -> None:
    clear_runtime_state(settings)


def _probe_runtime_health(settings: Settings) -> bool:
    url = f"http://{settings.daemon_host}:{settings.daemon_port}/health"
    try:
        with urlopen(url, timeout=1.0) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


class BackgroundSyncWorker:
    def __init__(self, settings: Settings, canonical: CanonicalStore):
        self.settings = settings
        self.canonical = canonical
        self.qmd_indexer = QmdAutoIndexer(settings)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self, interval_seconds: int) -> None:
        if interval_seconds <= 0:
            return
        self.thread = threading.Thread(
            target=self._run,
            args=(interval_seconds,),
            name="zotero-headless-sync",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def _run(self, interval_seconds: int) -> None:
        while not self.stop_event.wait(interval_seconds):
            try:
                self.run_once(interval_seconds=interval_seconds)
            except Exception:
                continue

    def run_once(self, *, interval_seconds: int = 0) -> dict[str, object]:
        if not self.settings.api_key:
            return {"skipped": True, "reason": "api_key_missing"}
        from .adapters.web_sync import CanonicalWebSyncAdapter
        from .web_api import ZoteroWebClient

        adapter = CanonicalWebSyncAdapter(
            self.canonical,
            ZoteroWebClient(self.settings),
            qmd_indexer=self.qmd_indexer,
        )
        discovered = adapter.discover_libraries()
        summary: dict[str, object] = {
            "libraries_discovered": len(discovered),
            "libraries_pushed": 0,
            "libraries_pulled": 0,
            "entities_pushed": 0,
            "entities_deleted": 0,
            "conflicts": 0,
            "failures": 0,
            "updated": 0,
            "files_downloaded": 0,
            "files_pruned": 0,
            "fulltext_updated": 0,
        }
        start_background_sync_run(self.settings, interval_seconds=interval_seconds)
        try:
            for library in self.canonical.list_libraries():
                library_id = library["library_id"]
                if library["source"] != "remote-sync":
                    continue
                has_pending = bool(
                    self.canonical.list_unsynced_entities(library_id, EntityType.COLLECTION, limit=1, include_conflicts=False)
                    or self.canonical.list_unsynced_entities(library_id, EntityType.ITEM, limit=1, include_conflicts=False)
                )
                if has_pending:
                    push_result = adapter.push_changes(library_id)
                    summary["libraries_pushed"] = int(summary["libraries_pushed"]) + 1
                    summary["entities_pushed"] = int(summary["entities_pushed"]) + int(push_result.get("pushed") or 0)
                    summary["entities_deleted"] = int(summary["entities_deleted"]) + int(push_result.get("deleted") or 0)
                    summary["conflicts"] = int(summary["conflicts"]) + len(push_result.get("conflicts") or [])
                    summary["failures"] = int(summary["failures"]) + len(push_result.get("failures") or [])
                pull_result = adapter.pull_library(library_id)
                summary["libraries_pulled"] = int(summary["libraries_pulled"]) + 1
                summary["updated"] = int(summary["updated"]) + int(pull_result.get("updated") or 0)
                summary["files_downloaded"] = int(summary["files_downloaded"]) + int(pull_result.get("files_downloaded") or 0)
                summary["files_pruned"] = int(summary["files_pruned"]) + int(pull_result.get("files_pruned") or 0)
                summary["fulltext_updated"] = int(summary["fulltext_updated"]) + int(pull_result.get("fulltext_updated") or 0)
            finish_background_sync_run(
                self.settings,
                interval_seconds=interval_seconds,
                success=True,
                result=summary,
            )
            return summary
        except Exception as exc:
            finish_background_sync_run(
                self.settings,
                interval_seconds=interval_seconds,
                success=False,
                result=summary,
                error=str(exc),
            )
            raise


def serve_daemon_runtime(
    settings: Settings,
    *,
    host: str | None = None,
    port: int | None = None,
    sync_interval_seconds: int = 0,
) -> None:
    from .api import make_handler
    from http.server import ThreadingHTTPServer

    host = host or settings.daemon_host
    port = port or settings.daemon_port
    settings.daemon_host = host
    settings.daemon_port = port
    canonical = CanonicalStore(settings.resolved_canonical_db())
    store = MirrorStore(settings.resolved_mirror_db())
    worker = BackgroundSyncWorker(settings, canonical)
    handler = make_handler(settings, store)
    server = ThreadingHTTPServer((host, port), handler)
    initialize_runtime_state(
        settings,
        pid=os.getpid(),
        host=host,
        port=port,
        sync_interval_seconds=sync_interval_seconds,
    )
    worker.start(sync_interval_seconds)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        worker.stop()
        server.server_close()
        _clear_runtime_state(settings)


def current_daemon_status(settings: Settings | None = None) -> DaemonStatus:
    settings = settings or Settings()
    workflow_dir = desktop_helper_workflow_dir()
    launch_command = build_daemon_command(settings)
    runtime_command = build_runtime_command(settings)
    executable = settings.zotero_bin
    local_api_url = f"http://{settings.daemon_host}:{settings.daemon_port}/api/"
    runtime_state = _read_runtime_state(settings)
    runtime_running = bool(runtime_state) and _probe_runtime_health(settings)
    runtime_message = (
        "The clean-room zotero-headless-daemon runtime is implemented and can host the HTTP API/core services directly."
    )
    if runtime_running:
        runtime_message = (
            f"zotero-headless-daemon is running at http://{settings.daemon_host}:{settings.daemon_port} "
            "and serving the clean-room core API."
        )
    runtime_mode = "running" if runtime_running else "implemented"
    message = (
        "The clean-room daemon runtime is available."
        if not runtime_running
        else "The clean-room daemon runtime is running."
    )
    if executable:
        message += (
            " A desktop helper command is available for an externally patched Zotero binary, "
            "but this repo does not infer helper patch state from an in-repo source snapshot."
        )
    return DaemonStatus(
        available=runtime_running,
        mode="clean-room-runtime-ready",
        message=message,
        runtime_available=True,
        runtime_mode=runtime_mode,
        runtime_message=runtime_message,
        runtime_running=runtime_running,
        runtime_read_api_ready=runtime_running,
        runtime_write_api_ready=runtime_running,
        runtime_launch_command=runtime_command,
        desktop_helper_command_available=bool(launch_command),
        read_api_ready=False,
        write_api_ready=False,
        desktop_helper_workflow_dir=str(workflow_dir) if workflow_dir.exists() else None,
        executable=executable,
        launch_command=launch_command,
        local_api_url=local_api_url,
        runtime_state_path=str(runtime_state_path(settings)),
        jobs_state_path=str(jobs_state_path(settings)),
        events_log_path=str(events_log_path(settings)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zotero-headless-daemon")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--sync-interval", type=int, default=0)
    sub.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if args.command == "status":
        print(current_daemon_status(settings).to_dict())
        return 0
    if args.command == "serve":
        serve_daemon_runtime(
            settings,
            host=args.host,
            port=args.port,
            sync_interval_seconds=int(args.sync_interval),
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
