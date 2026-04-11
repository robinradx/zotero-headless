from __future__ import annotations

import hashlib
import json
import uuid
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from .citations import CitationExportClient
from .config import Settings
from .core import CanonicalStore, ChangeType, EntityType
from .qmd import QmdAutoIndexer
from .utils import ensure_dir, now_iso, parse_library_id, read_json, sanitize_component, write_json


SNAPSHOT_MANIFEST = "manifest.json"


class RecoveryService:
    def __init__(
        self,
        settings: Settings,
        *,
        canonical: CanonicalStore | None = None,
        qmd_indexer: QmdAutoIndexer | None = None,
    ) -> None:
        self.settings = settings
        self.canonical = canonical or CanonicalStore(settings.resolved_canonical_db())
        self.qmd_indexer = qmd_indexer

    def snapshot_root(self) -> Path:
        return ensure_dir(self.settings.resolved_recovery_snapshot_dir())

    def temp_root(self) -> Path:
        return ensure_dir(self.settings.resolved_recovery_temp_dir())

    def audit_root(self) -> Path:
        return ensure_dir(self.settings.resolved_state_dir() / "recovery")

    def snapshot_path(self, snapshot_id: str) -> Path:
        return self.snapshot_root() / snapshot_id

    def restore_runs_path(self) -> Path:
        return self.audit_root() / "restore-runs.json"

    def recovery_events_path(self) -> Path:
        return self.audit_root() / "events.jsonl"

    def repositories(self) -> list[dict[str, Any]]:
        configured = [dict(entry) for entry in self.settings.backup_repositories]
        return [
            {
                "name": "local",
                "type": "local",
                "path": str(self.snapshot_root()),
            },
            *configured,
        ]

    def list_restore_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        runs = read_json(self.restore_runs_path(), [])
        if not isinstance(runs, list):
            return []
        runs = [dict(run) for run in runs]
        runs.sort(key=lambda run: str(run.get("updated_at") or run.get("created_at") or ""), reverse=True)
        return runs[:limit]

    def get_restore_run(self, run_id: str) -> dict[str, Any]:
        for run in self.list_restore_runs(limit=10000):
            if str(run.get("run_id")) == run_id:
                return run
        raise ValueError(f"Unknown restore run: {run_id}")

    def create_snapshot(self, *, reason: str = "manual") -> dict[str, Any]:
        snapshot_id = self._next_snapshot_id()
        temp_dir = self.temp_root() / f"{snapshot_id}.tmp"
        final_dir = self.snapshot_root() / snapshot_id
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        ensure_dir(temp_dir)

        components: dict[str, dict[str, Any]] = {}
        canonical_copy = temp_dir / "canonical.sqlite"
        self._backup_sqlite(self.settings.resolved_canonical_db(), canonical_copy)
        components["canonical_db"] = self._component_payload(canonical_copy, "file", source=str(self.settings.resolved_canonical_db()))

        mirror_source = self.settings.resolved_mirror_db()
        if mirror_source.exists():
            mirror_copy = temp_dir / "headless.sqlite"
            self._backup_sqlite(mirror_source, mirror_copy)
            components["mirror_db"] = self._component_payload(mirror_copy, "file", source=str(mirror_source))

        files_source = self.settings.resolved_file_cache_dir()
        if files_source.exists():
            files_archive = temp_dir / "files.tar.gz"
            self._archive_directory(files_source, files_archive)
            components["files_archive"] = self._component_payload(files_archive, "tar.gz", source=str(files_source))

        qmd_source = self.settings.resolved_export_dir()
        if qmd_source.exists():
            qmd_archive = temp_dir / "qmd-export.tar.gz"
            self._archive_directory(qmd_source, qmd_archive)
            components["qmd_export_archive"] = self._component_payload(qmd_archive, "tar.gz", source=str(qmd_source))

        citation_source = self.settings.resolved_citation_export_path()
        if citation_source.exists():
            citation_copy = temp_dir / sanitize_component(citation_source.name)
            shutil.copy2(citation_source, citation_copy)
            components["citation_export"] = self._component_payload(citation_copy, "file", source=str(citation_source))

        manifest = {
            "snapshot_id": snapshot_id,
            "created_at": now_iso(),
            "reason": reason,
            "paths": {
                "state_dir": str(self.settings.resolved_state_dir()),
                "canonical_db": str(self.settings.resolved_canonical_db()),
                "mirror_db": str(self.settings.resolved_mirror_db()),
                "files": str(self.settings.resolved_file_cache_dir()),
                "qmd_export": str(self.settings.resolved_export_dir()),
                "citation_export": str(self.settings.resolved_citation_export_path()),
            },
            "components": components,
            "canonical_status": self.canonical.status(),
            "libraries": self._library_inventory(canonical_copy),
        }
        write_json(temp_dir / SNAPSHOT_MANIFEST, manifest)
        temp_dir.replace(final_dir)
        self._append_event("snapshot_created", snapshot_id=snapshot_id, reason=reason, path=str(final_dir))
        return self.get_snapshot(snapshot_id)

    def list_snapshots(self, *, limit: int = 100) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for path in self.snapshot_root().iterdir():
            manifest_path = path / SNAPSHOT_MANIFEST
            if not path.is_dir() or not manifest_path.exists():
                continue
            manifest = read_json(manifest_path, {})
            manifest["path"] = str(path)
            entries.append(manifest)
        entries.sort(key=lambda entry: str(entry.get("created_at") or ""), reverse=True)
        return entries[:limit]

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        path = self.snapshot_path(snapshot_id)
        manifest_path = path / SNAPSHOT_MANIFEST
        if not manifest_path.exists():
            raise ValueError(f"Unknown snapshot: {snapshot_id}")
        manifest = read_json(manifest_path, {})
        manifest["path"] = str(path)
        return manifest

    def verify_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.get_snapshot(snapshot_id)
        errors: list[str] = []
        verified: dict[str, dict[str, Any]] = {}
        path = Path(snapshot["path"])
        for name, component in dict(snapshot.get("components") or {}).items():
            relative_path = component.get("path")
            if not relative_path:
                errors.append(f"{name}: missing path metadata")
                continue
            local_path = path / str(relative_path)
            if not local_path.exists():
                errors.append(f"{name}: missing file {local_path}")
                continue
            digest = self._sha256(local_path)
            size = local_path.stat().st_size
            if digest != component.get("sha256"):
                errors.append(f"{name}: sha256 mismatch")
            if int(component.get("size") or 0) != size:
                errors.append(f"{name}: size mismatch")
            verified[name] = {
                "path": str(local_path),
                "size": size,
                "sha256": digest,
            }
        result = {
            "snapshot_id": snapshot_id,
            "ok": not errors,
            "errors": errors,
            "verified_components": verified,
        }
        self._append_event(
            "snapshot_verified",
            snapshot_id=snapshot_id,
            ok=result["ok"],
            errors=errors,
        )
        return result

    def push_snapshot(self, snapshot_id: str, *, repository: str) -> dict[str, Any]:
        snapshot = self.get_snapshot(snapshot_id)
        repo = self._repository(repository)
        source_dir = Path(snapshot["path"])
        if repo["type"] == "local":
            return {
                "snapshot_id": snapshot_id,
                "repository": repository,
                "status": "already-local",
                "path": str(source_dir),
            }
        if repo["type"] == "filesystem":
            target_root = ensure_dir(Path(str(repo["path"])).expanduser())
            destination = target_root / snapshot_id
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source_dir, destination)
            result = {
                "snapshot_id": snapshot_id,
                "repository": repository,
                "status": "pushed",
                "destination": str(destination),
            }
            self._append_event("snapshot_pushed", **result)
            return result
        if repo["type"] == "rsync":
            target = f"{str(repo['target']).rstrip('/')}/{snapshot_id}/"
            command = ["rsync", "-a", f"{source_dir}/", target]
            result = self._run_external(command)
            result = {
                "snapshot_id": snapshot_id,
                "repository": repository,
                "status": "pushed",
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            self._append_event("snapshot_pushed", **result)
            return result
        if repo["type"] == "s3":
            target = f"{str(repo['uri']).rstrip('/')}/{snapshot_id}"
            command = ["aws", "s3", "sync", str(source_dir), target]
            result = self._run_external(command)
            payload = {
                "snapshot_id": snapshot_id,
                "repository": repository,
                "status": "pushed",
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            self._append_event("snapshot_pushed", **payload)
            return payload
        raise ValueError(f"Unsupported repository type: {repo['type']}")

    def pull_snapshot(self, snapshot_id: str, *, repository: str) -> dict[str, Any]:
        repo = self._repository(repository)
        if repo["type"] == "local":
            return self.get_snapshot(snapshot_id)
        destination = self.snapshot_root() / snapshot_id
        temp_destination = self.temp_root() / f"{snapshot_id}.pull"
        if temp_destination.exists():
            shutil.rmtree(temp_destination)
        ensure_dir(temp_destination)
        if destination.exists():
            shutil.rmtree(destination)
        if repo["type"] == "filesystem":
            source = Path(str(repo["path"])).expanduser() / snapshot_id
            if not source.exists():
                raise ValueError(f"Snapshot {snapshot_id} not found in repository {repository}")
            shutil.copytree(source, temp_destination, dirs_exist_ok=True)
        elif repo["type"] == "rsync":
            source = f"{str(repo['target']).rstrip('/')}/{snapshot_id}/"
            self._run_external(["rsync", "-a", source, str(temp_destination)])
        elif repo["type"] == "s3":
            source = f"{str(repo['uri']).rstrip('/')}/{snapshot_id}"
            self._run_external(["aws", "s3", "sync", source, str(temp_destination)])
        else:
            raise ValueError(f"Unsupported repository type: {repo['type']}")
        temp_destination.replace(destination)
        verification = self.verify_snapshot(snapshot_id)
        if not verification["ok"]:
            raise RuntimeError(f"Pulled snapshot verification failed: {verification['errors']}")
        self._append_event("snapshot_pulled", snapshot_id=snapshot_id, repository=repository, destination=str(destination))
        return self.get_snapshot(snapshot_id)

    def plan_restore(self, *, snapshot_id: str, library_id: str | None = None) -> dict[str, Any]:
        snapshot = self.get_snapshot(snapshot_id)
        verification = self.verify_snapshot(snapshot_id)
        if not verification["ok"]:
            raise RuntimeError(f"Snapshot verification failed: {verification['errors']}")
        if library_id is None:
            return {
                "snapshot_id": snapshot_id,
                "mode": "full-state",
                "current": {
                    "canonical_status": self.canonical.status(),
                    "state_dir": str(self.settings.resolved_state_dir()),
                },
                "snapshot": snapshot,
                "components": snapshot.get("components") or {},
            }

        snapshot_store = CanonicalStore(self._snapshot_canonical_db(snapshot_id))
        snapshot_library = snapshot_store.get_library(library_id)
        current_library = self.canonical.get_library(library_id)
        if not snapshot_library and not current_library:
            raise ValueError(f"Library {library_id} not found in current state or snapshot")

        actions = self._diff_library(snapshot_store, self.canonical, library_id)
        summary = {
            "total": len(actions),
            "create": sum(1 for action in actions if action["action"] == "create"),
            "update": sum(1 for action in actions if action["action"] == "update"),
            "delete": sum(1 for action in actions if action["action"] == "delete"),
            "restore": sum(1 for action in actions if action["action"] == "restore"),
        }
        return {
            "snapshot_id": snapshot_id,
            "mode": "library",
            "library_id": library_id,
            "snapshot_library": snapshot_library,
            "current_library": current_library,
            "summary": summary,
            "actions": actions,
        }

    def execute_restore(
        self,
        *,
        snapshot_id: str,
        library_id: str | None = None,
        confirm: bool = False,
        push_remote: bool = False,
        apply_local: bool = False,
    ) -> dict[str, Any]:
        if not confirm:
            raise ValueError("Restore execution requires confirm=True")
        run = self._create_restore_run(snapshot_id=snapshot_id, library_id=library_id, push_remote=push_remote, apply_local=apply_local)
        plan = self.plan_restore(snapshot_id=snapshot_id, library_id=library_id)
        safety_snapshot = self.create_snapshot(reason=f"pre-restore:{library_id or 'full-state'}")
        self._update_restore_run(
            run["run_id"],
            status="running",
            plan=plan,
            safety_snapshot_id=safety_snapshot["snapshot_id"],
        )
        try:
            if library_id is None:
                restored = self._restore_full_state(snapshot_id)
                result = {
                    "snapshot_id": snapshot_id,
                    "mode": "full-state",
                    "run_id": run["run_id"],
                    "safety_snapshot_id": safety_snapshot["snapshot_id"],
                    "restored": restored,
                }
                self._update_restore_run(run["run_id"], status="completed", result=result)
                self._append_event("restore_completed", run_id=run["run_id"], snapshot_id=snapshot_id, mode="full-state")
                return result

            snapshot_store = CanonicalStore(self._snapshot_canonical_db(snapshot_id))
            snapshot_library = snapshot_store.get_library(library_id)
            if snapshot_library:
                self.canonical.upsert_library(
                    library_id,
                    name=str(snapshot_library.get("name") or library_id),
                    source=str(snapshot_library.get("source") or "restored"),
                    editable=bool(snapshot_library.get("editable", True)),
                    metadata=dict(snapshot_library.get("metadata") or {}),
                )

            applied: list[dict[str, Any]] = []
            for action in plan["actions"]:
                entity_type = EntityType(str(action["entity_type"]))
                entity_key = str(action["entity_key"])
                current = self.canonical.get_entity(library_id, entity_type, entity_key)
                if action["action"] == "delete":
                    if current and not current.get("deleted"):
                        self.canonical.delete_entity(library_id, entity_type, entity_key)
                        applied.append(action)
                    continue
                snapshot_entity = snapshot_store.get_entity(library_id, entity_type, entity_key)
                if not snapshot_entity:
                    continue
                change_type = ChangeType.CREATE if not current or current.get("deleted") else ChangeType.UPDATE
                self.canonical.save_entity(
                    library_id,
                    entity_type,
                    dict(snapshot_entity["payload"]),
                    entity_key=entity_key,
                    synced=False,
                    deleted=False,
                    change_type=change_type,
                    base_version=int(current["version"]) if current else None,
                )
                applied.append(action)

            self._refresh_library_artifacts(library_id)
            sync_result = None
            library_type, _ = parse_library_id(library_id)
            if push_remote and library_type in {"user", "group"}:
                from .adapters.web_sync import CanonicalWebSyncAdapter
                from .web_api import ZoteroWebClient

                sync_result = CanonicalWebSyncAdapter(
                    self.canonical,
                    ZoteroWebClient(self.settings),
                    qmd_indexer=self.qmd_indexer,
                ).push_changes(library_id)
            elif apply_local and library_type == "local":
                from .adapters.local_desktop import LocalDesktopAdapter

                if not self.settings.data_dir:
                    raise ValueError("Local restore apply requested but no data_dir is configured")
                sync_result = LocalDesktopAdapter(
                    self.canonical,
                    qmd_indexer=self.qmd_indexer,
                    settings=self.settings,
                ).apply_pending_writes(self.settings.data_dir, library_id=library_id)
            result = {
                "snapshot_id": snapshot_id,
                "mode": "library",
                "run_id": run["run_id"],
                "library_id": library_id,
                "safety_snapshot_id": safety_snapshot["snapshot_id"],
                "summary": plan["summary"],
                "applied": len(applied),
                "applied_actions": applied,
                "follow_up_result": sync_result,
            }
            self._update_restore_run(run["run_id"], status="completed", result=result)
            self._append_event("restore_completed", run_id=run["run_id"], snapshot_id=snapshot_id, mode="library", library_id=library_id)
            return result
        except Exception as exc:
            self._update_restore_run(run["run_id"], status="failed", error=str(exc))
            self._append_event("restore_failed", run_id=run["run_id"], snapshot_id=snapshot_id, library_id=library_id, error=str(exc))
            raise

    def _restore_full_state(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.get_snapshot(snapshot_id)
        components = dict(snapshot.get("components") or {})
        snapshot_dir = Path(snapshot["path"])
        restored: dict[str, Any] = {}

        canonical_component = components.get("canonical_db")
        if canonical_component:
            self._restore_sqlite_file(snapshot_dir / canonical_component["path"], self.settings.resolved_canonical_db())
            restored["canonical_db"] = str(self.settings.resolved_canonical_db())

        mirror_component = components.get("mirror_db")
        if mirror_component:
            self._restore_sqlite_file(snapshot_dir / mirror_component["path"], self.settings.resolved_mirror_db())
            restored["mirror_db"] = str(self.settings.resolved_mirror_db())

        self._restore_archive_component(
            snapshot_dir,
            components.get("files_archive"),
            self.settings.resolved_file_cache_dir(),
        )
        restored["files"] = str(self.settings.resolved_file_cache_dir())
        self._restore_archive_component(
            snapshot_dir,
            components.get("qmd_export_archive"),
            self.settings.resolved_export_dir(),
        )
        restored["qmd_export"] = str(self.settings.resolved_export_dir())

        citation_target = self.settings.resolved_citation_export_path()
        citation_component = components.get("citation_export")
        if citation_component:
            shutil.copy2(snapshot_dir / citation_component["path"], citation_target)
        elif citation_target.exists():
            citation_target.unlink()
        restored["citation_export"] = str(citation_target)
        return restored

    def _restore_archive_component(
        self,
        snapshot_dir: Path,
        component: dict[str, Any] | None,
        target_dir: Path,
    ) -> None:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        ensure_dir(target_dir)
        if not component:
            return
        archive_path = snapshot_dir / str(component["path"])
        self._extract_archive(archive_path, target_dir)

    def _refresh_library_artifacts(self, library_id: str) -> None:
        if self.qmd_indexer is not None:
            try:
                self.qmd_indexer.refresh_canonical_library(self.canonical, library_id)
            except Exception:
                pass
        try:
            CitationExportClient(self.settings).export_from_canonical(self.canonical, library_id=library_id)
        except Exception:
            pass

    def _library_inventory(self, canonical_db_path: Path) -> list[dict[str, Any]]:
        if not canonical_db_path.exists():
            return []
        with closing(sqlite3.connect(canonical_db_path)) as conn:
            conn.row_factory = sqlite3.Row
            table_exists = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='libraries'"
            ).fetchone()[0]
            if not table_exists:
                return []
            libraries = conn.execute(
                """
                SELECT library_id, library_kind, library_key, name, source, editable, metadata_json
                FROM libraries
                ORDER BY library_id
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for library in libraries:
                counts = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS total_entities,
                        SUM(CASE WHEN deleted = 0 THEN 1 ELSE 0 END) AS active_entities,
                        SUM(CASE WHEN deleted = 1 THEN 1 ELSE 0 END) AS deleted_entities,
                        SUM(CASE WHEN synced = 0 THEN 1 ELSE 0 END) AS unsynced_entities,
                        SUM(CASE WHEN conflict_json IS NOT NULL THEN 1 ELSE 0 END) AS conflicts
                    FROM entities
                    WHERE library_id = ?
                    """,
                    (library["library_id"],),
                ).fetchone()
                result.append(
                    {
                        "library_id": library["library_id"],
                        "library_kind": library["library_kind"],
                        "library_key": library["library_key"],
                        "name": library["name"],
                        "source": library["source"],
                        "editable": bool(library["editable"]),
                        "metadata": json.loads(library["metadata_json"] or "{}"),
                        "counts": {
                            "total_entities": int(counts["total_entities"] or 0),
                            "active_entities": int(counts["active_entities"] or 0),
                            "deleted_entities": int(counts["deleted_entities"] or 0),
                            "unsynced_entities": int(counts["unsynced_entities"] or 0),
                            "conflicts": int(counts["conflicts"] or 0),
                        },
                    }
                )
        return result

    def _diff_library(
        self,
        snapshot_store: CanonicalStore,
        current_store: CanonicalStore,
        library_id: str,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for entity_type in EntityType:
            snapshot_entities = {
                entity["entity_key"]: entity
                for entity in snapshot_store.list_entities(
                    library_id,
                    entity_type,
                    limit=100000,
                    include_deleted=True,
                )
            }
            current_entities = {
                entity["entity_key"]: entity
                for entity in current_store.list_entities(
                    library_id,
                    entity_type,
                    limit=100000,
                    include_deleted=True,
                )
            }
            for entity_key in sorted(set(snapshot_entities) | set(current_entities)):
                snapshot_entity = snapshot_entities.get(entity_key)
                current_entity = current_entities.get(entity_key)
                if snapshot_entity and not current_entity:
                    if snapshot_entity.get("deleted"):
                        continue
                    actions.append(
                        self._diff_action(entity_type, entity_key, "create", snapshot_entity=snapshot_entity, current_entity=None)
                    )
                    continue
                if current_entity and not snapshot_entity:
                    if current_entity.get("deleted"):
                        continue
                    actions.append(
                        self._diff_action(entity_type, entity_key, "delete", snapshot_entity=None, current_entity=current_entity)
                    )
                    continue
                if not snapshot_entity or not current_entity:
                    continue
                if snapshot_entity.get("deleted") and current_entity.get("deleted"):
                    continue
                if snapshot_entity.get("deleted") and not current_entity.get("deleted"):
                    actions.append(
                        self._diff_action(entity_type, entity_key, "delete", snapshot_entity=snapshot_entity, current_entity=current_entity)
                    )
                    continue
                if not snapshot_entity.get("deleted") and current_entity.get("deleted"):
                    actions.append(
                        self._diff_action(entity_type, entity_key, "restore", snapshot_entity=snapshot_entity, current_entity=current_entity)
                    )
                    continue
                if snapshot_entity.get("payload") != current_entity.get("payload"):
                    actions.append(
                        self._diff_action(entity_type, entity_key, "update", snapshot_entity=snapshot_entity, current_entity=current_entity)
                    )
        return actions

    def _diff_action(
        self,
        entity_type: EntityType,
        entity_key: str,
        action: str,
        *,
        snapshot_entity: dict[str, Any] | None,
        current_entity: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "entity_type": entity_type.value,
            "entity_key": entity_key,
            "action": action,
            "snapshot_version": int(snapshot_entity["version"]) if snapshot_entity else None,
            "current_version": int(current_entity["version"]) if current_entity else None,
            "snapshot_deleted": bool(snapshot_entity.get("deleted")) if snapshot_entity else None,
            "current_deleted": bool(current_entity.get("deleted")) if current_entity else None,
            "snapshot_title": snapshot_entity.get("title") if snapshot_entity else None,
            "current_title": current_entity.get("title") if current_entity else None,
        }

    def _snapshot_canonical_db(self, snapshot_id: str) -> Path:
        snapshot = self.get_snapshot(snapshot_id)
        component = dict(snapshot.get("components") or {}).get("canonical_db")
        if not component:
            raise ValueError(f"Snapshot {snapshot_id} does not include a canonical database")
        return Path(snapshot["path"]) / str(component["path"])

    def _component_payload(self, path: Path, kind: str, *, source: str) -> dict[str, Any]:
        return {
            "path": path.name,
            "kind": kind,
            "source": source,
            "size": path.stat().st_size,
            "sha256": self._sha256(path),
        }

    def _backup_sqlite(self, source: Path, destination: Path) -> None:
        ensure_dir(destination.parent)
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)

    def _restore_sqlite_file(self, source: Path, destination: Path) -> None:
        temp_destination = destination.with_name(f".{destination.name}.restore")
        if temp_destination.exists():
            temp_destination.unlink()
        for suffix in ("-wal", "-shm"):
            sidecar = destination.with_name(destination.name + suffix)
            if sidecar.exists():
                sidecar.unlink()
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(temp_destination)) as dst:
            src.backup(dst)
        temp_destination.replace(destination)

    def _archive_directory(self, source: Path, destination: Path) -> None:
        ensure_dir(destination.parent)
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(source, arcname=".")

    def _extract_archive(self, archive_path: Path, destination: Path) -> None:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                member_path = destination / member.name
                if not member_path.resolve().is_relative_to(destination.resolve()):
                    raise ValueError(f"Unsafe archive member: {member.name}")
            archive.extractall(destination)

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _repository(self, name: str) -> dict[str, Any]:
        for repo in self.repositories():
            if str(repo.get("name")) == name:
                return repo
        raise ValueError(f"Unknown repository: {name}")

    def _run_external(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        executable = command[0]
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required external command not found: {executable}")
        return subprocess.run(command, check=True, capture_output=True, text=True)

    def _next_snapshot_id(self) -> str:
        prefix = now_iso().replace("-", "").replace(":", "").replace(".", "").replace("Z", "Z")
        with tempfile.NamedTemporaryFile(prefix="zhl-", suffix=".tmp", dir=self.temp_root(), delete=True) as handle:
            token = Path(handle.name).stem.split("-")[-1][:8]
        return f"{prefix}-{token}"

    def _create_restore_run(
        self,
        *,
        snapshot_id: str,
        library_id: str | None,
        push_remote: bool,
        apply_local: bool,
    ) -> dict[str, Any]:
        run = {
            "run_id": uuid.uuid4().hex,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "status": "planned",
            "snapshot_id": snapshot_id,
            "library_id": library_id,
            "push_remote": bool(push_remote),
            "apply_local": bool(apply_local),
            "plan": None,
            "result": None,
            "error": None,
            "safety_snapshot_id": None,
        }
        runs = read_json(self.restore_runs_path(), [])
        if not isinstance(runs, list):
            runs = []
        runs.append(run)
        write_json(self.restore_runs_path(), runs)
        self._append_event("restore_created", run_id=run["run_id"], snapshot_id=snapshot_id, library_id=library_id)
        return run

    def _update_restore_run(self, run_id: str, **updates: Any) -> dict[str, Any]:
        runs = read_json(self.restore_runs_path(), [])
        if not isinstance(runs, list):
            runs = []
        for index, run in enumerate(runs):
            if str(run.get("run_id")) != run_id:
                continue
            updated = dict(run)
            updated.update(updates)
            updated["updated_at"] = now_iso()
            runs[index] = updated
            write_json(self.restore_runs_path(), runs)
            return updated
        raise ValueError(f"Unknown restore run: {run_id}")

    def _append_event(self, event_type: str, **payload: Any) -> None:
        path = self.recovery_events_path()
        ensure_dir(path.parent)
        record = {"timestamp": now_iso(), "event": event_type, **payload}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
