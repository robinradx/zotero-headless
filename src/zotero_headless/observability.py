from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .utils import ensure_dir, now_iso, read_json, write_json


_STATE_LOCK = threading.Lock()


def daemon_dir(settings: Settings, *, create: bool = False) -> Path:
    path = settings.resolved_state_dir() / "daemon"
    return ensure_dir(path) if create else path


def runtime_state_path(settings: Settings) -> Path:
    return daemon_dir(settings) / "runtime.json"


def jobs_state_path(settings: Settings) -> Path:
    return daemon_dir(settings) / "jobs.json"


def events_log_path(settings: Settings) -> Path:
    return daemon_dir(settings) / "events.jsonl"


def read_runtime_state(settings: Settings) -> dict[str, Any] | None:
    path = runtime_state_path(settings)
    if not path.exists():
        return None
    return read_json(path, None)


def write_runtime_state(settings: Settings, payload: dict[str, Any]) -> None:
    ensure_dir(runtime_state_path(settings).parent)
    write_json(runtime_state_path(settings), payload)


def clear_runtime_state(settings: Settings) -> None:
    path = runtime_state_path(settings)
    if path.exists():
        path.unlink()


def default_jobs_state(sync_interval_seconds: int = 0) -> dict[str, Any]:
    return {
        "background_sync": {
            "enabled": sync_interval_seconds > 0,
            "interval_seconds": sync_interval_seconds,
            "running": False,
            "runs_total": 0,
            "successes_total": 0,
            "failures_total": 0,
            "last_started_at": None,
            "last_finished_at": None,
            "last_success_at": None,
            "last_error": None,
            "last_result": None,
        }
    }


def read_jobs_state(settings: Settings) -> dict[str, Any]:
    path = jobs_state_path(settings)
    if not path.exists():
        return default_jobs_state()
    return read_json(path, default_jobs_state())


def write_jobs_state(settings: Settings, payload: dict[str, Any]) -> None:
    ensure_dir(jobs_state_path(settings).parent)
    write_json(jobs_state_path(settings), payload)


def append_daemon_event(settings: Settings, event_type: str, **payload: Any) -> None:
    record = {"timestamp": now_iso(), "event": event_type, **payload}
    path = events_log_path(settings)
    ensure_dir(path.parent)
    with _STATE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")


def initialize_runtime_state(
    settings: Settings,
    *,
    pid: int,
    host: str,
    port: int,
    sync_interval_seconds: int,
) -> dict[str, Any]:
    runtime = {
        "pid": pid,
        "host": host,
        "port": port,
        "started_at": now_iso(),
        "sync_interval_seconds": sync_interval_seconds,
        "api_url": f"http://{host}:{port}",
        "request_count": 0,
        "last_request_at": None,
        "last_request": None,
        "jobs_state_path": str(jobs_state_path(settings)),
        "events_log_path": str(events_log_path(settings)),
    }
    with _STATE_LOCK:
        write_runtime_state(settings, runtime)
        write_jobs_state(settings, default_jobs_state(sync_interval_seconds))
    append_daemon_event(
        settings,
        "daemon_started",
        pid=pid,
        host=host,
        port=port,
        sync_interval_seconds=sync_interval_seconds,
    )
    return runtime


def record_http_request(
    settings: Settings,
    *,
    method: str,
    path: str,
    status: int,
    duration_ms: int,
    remote_addr: str | None = None,
) -> None:
    timestamp = now_iso()
    with _STATE_LOCK:
        runtime = read_runtime_state(settings)
        if runtime:
            runtime["request_count"] = int(runtime.get("request_count") or 0) + 1
            runtime["last_request_at"] = timestamp
            runtime["last_request"] = {
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": duration_ms,
                "remote_addr": remote_addr,
                "timestamp": timestamp,
            }
            write_runtime_state(settings, runtime)
    append_daemon_event(
        settings,
        "http_request",
        method=method,
        path=path,
        status=status,
        duration_ms=duration_ms,
        remote_addr=remote_addr,
    )


def start_background_sync_run(settings: Settings, *, interval_seconds: int) -> dict[str, Any]:
    timestamp = now_iso()
    with _STATE_LOCK:
        jobs = read_jobs_state(settings)
        job = dict(jobs.get("background_sync") or {})
        job["enabled"] = interval_seconds > 0
        job["interval_seconds"] = interval_seconds
        job["running"] = True
        job["last_started_at"] = timestamp
        job["last_error"] = None
        jobs["background_sync"] = job
        write_jobs_state(settings, jobs)
    append_daemon_event(settings, "background_sync_started", interval_seconds=interval_seconds)
    return jobs


def finish_background_sync_run(
    settings: Settings,
    *,
    interval_seconds: int,
    success: bool,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    with _STATE_LOCK:
        jobs = read_jobs_state(settings)
        job = dict(jobs.get("background_sync") or {})
        job["enabled"] = interval_seconds > 0
        job["interval_seconds"] = interval_seconds
        job["running"] = False
        job["runs_total"] = int(job.get("runs_total") or 0) + 1
        job["last_finished_at"] = timestamp
        job["last_result"] = result
        if success:
            job["successes_total"] = int(job.get("successes_total") or 0) + 1
            job["last_success_at"] = timestamp
            job["last_error"] = None
        else:
            job["failures_total"] = int(job.get("failures_total") or 0) + 1
            job["last_error"] = error
        jobs["background_sync"] = job
        write_jobs_state(settings, jobs)
    append_daemon_event(
        settings,
        "background_sync_finished" if success else "background_sync_failed",
        interval_seconds=interval_seconds,
        result=result,
        error=error,
    )
    return jobs


def _iso_to_unix(value: str | None) -> int:
    if not value:
        return 0
    normalized = value.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return 0


def build_metrics_text(settings: Settings) -> str:
    runtime = read_runtime_state(settings) or {}
    jobs = read_jobs_state(settings)
    background = jobs.get("background_sync") or {}
    lines = [
        "# HELP zotero_headless_runtime_running Whether the clean-room daemon runtime is running.",
        "# TYPE zotero_headless_runtime_running gauge",
        f"zotero_headless_runtime_running {1 if runtime else 0}",
        "# HELP zotero_headless_http_requests_total Total HTTP requests served by the daemon runtime.",
        "# TYPE zotero_headless_http_requests_total counter",
        f"zotero_headless_http_requests_total {int(runtime.get('request_count') or 0)}",
        "# HELP zotero_headless_background_sync_enabled Whether periodic background sync is enabled.",
        "# TYPE zotero_headless_background_sync_enabled gauge",
        f"zotero_headless_background_sync_enabled {1 if background.get('enabled') else 0}",
        "# HELP zotero_headless_background_sync_running Whether a background sync job is currently running.",
        "# TYPE zotero_headless_background_sync_running gauge",
        f"zotero_headless_background_sync_running {1 if background.get('running') else 0}",
        "# HELP zotero_headless_background_sync_runs_total Total completed background sync runs.",
        "# TYPE zotero_headless_background_sync_runs_total counter",
        f"zotero_headless_background_sync_runs_total {int(background.get('runs_total') or 0)}",
        "# HELP zotero_headless_background_sync_successes_total Total successful background sync runs.",
        "# TYPE zotero_headless_background_sync_successes_total counter",
        f"zotero_headless_background_sync_successes_total {int(background.get('successes_total') or 0)}",
        "# HELP zotero_headless_background_sync_failures_total Total failed background sync runs.",
        "# TYPE zotero_headless_background_sync_failures_total counter",
        f"zotero_headless_background_sync_failures_total {int(background.get('failures_total') or 0)}",
        "# HELP zotero_headless_background_sync_last_success_unixtime Unix timestamp of the last successful background sync.",
        "# TYPE zotero_headless_background_sync_last_success_unixtime gauge",
        f"zotero_headless_background_sync_last_success_unixtime {_iso_to_unix(background.get('last_success_at'))}",
    ]
    return "\n".join(lines) + "\n"
