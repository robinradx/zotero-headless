from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import Settings
from .core import CanonicalStore, EntityType
from .store import MirrorStore
from .utils import ensure_dir, sanitize_component


class QmdClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.export_dir = settings.resolved_export_dir()

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        cache_home = Path(env.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
        config_home = Path(env.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        ensure_dir(cache_home)
        ensure_dir(cache_home / "qmd")
        ensure_dir(config_home)
        ensure_dir(config_home / "qmd")
        env["XDG_CACHE_HOME"] = str(cache_home)
        env["XDG_CONFIG_HOME"] = str(config_home)
        return env

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["qmd", *args],
            text=True,
            capture_output=True,
            env=self._env(),
            check=False,
        )

    def ensure_collection(self) -> dict[str, Any]:
        ensure_dir(self.export_dir)
        existing = self._run(["collection", "list"])
        if existing.returncode != 0:
            add = self._run(["collection", "add", str(self.export_dir), "--name", self.settings.qmd_collection])
            if add.returncode != 0:
                raise RuntimeError(add.stderr.strip() or add.stdout.strip() or "qmd collection add failed")
            return {"created": True, "stdout": add.stdout}

        if self.settings.qmd_collection not in existing.stdout:
            add = self._run(["collection", "add", str(self.export_dir), "--name", self.settings.qmd_collection])
            if add.returncode != 0:
                raise RuntimeError(add.stderr.strip() or add.stdout.strip() or "qmd collection add failed")
            return {"created": True, "stdout": add.stdout}
        return {"created": False, "stdout": existing.stdout}

    def _write_markdown(
        self,
        lib_id: str,
        kind: str,
        object_key: str,
        title: str | None,
        version: int,
        payload: dict[str, Any],
    ) -> None:
        lib_dir = ensure_dir(self.export_dir / sanitize_component(lib_id))
        kind_dir = ensure_dir(lib_dir / f"{kind}s")
        filename = kind_dir / f"{sanitize_component(object_key)}.md"
        data = payload.get("data", payload)
        lines = [
            "---",
            f'title: "{(title or "").replace("\"", "\\\"")}"',
            f"library_id: {lib_id}",
            f"kind: {kind}",
            f"key: {object_key}",
            f"version: {version}",
            "---",
            "",
            f"# {title or object_key}",
            "",
        ]
        if kind == "item":
            if data.get("itemType"):
                lines.append(f"Item type: `{data['itemType']}`")
                lines.append("")
            if data.get("filename"):
                lines.append(f"Filename: `{data['filename']}`")
                lines.append("")
            if data.get("headlessFilePath"):
                lines.append(f"Cached file: `{data['headlessFilePath']}`")
                lines.append("")
            if data.get("citationKey"):
                lines.append(f"Citation key: `{data['citationKey']}`")
                lines.append("")
            aliases = data.get("citationAliases") or []
            if aliases:
                lines.append(f"Citation aliases: `{', '.join(str(alias) for alias in aliases)}`")
                lines.append("")
            if data.get("itemType") == "annotation":
                lines.append("## Annotation")
                if data.get("annotationType"):
                    lines.append(f"Type: `{data['annotationType']}`")
                if data.get("parentItemKey"):
                    lines.append(f"Parent item: `{data['parentItemKey']}`")
                if data.get("annotationPageLabel"):
                    lines.append(f"Page: `{data['annotationPageLabel']}`")
                if data.get("annotationColor"):
                    lines.append(f"Color: `{data['annotationColor']}`")
                if data.get("annotationAuthorName"):
                    lines.append(f"Author: {data['annotationAuthorName']}")
                lines.append("")
                if data.get("annotationText"):
                    lines.append("### Selected text")
                    lines.append(str(data["annotationText"]))
                    lines.append("")
                if data.get("annotationComment"):
                    lines.append("### Comment")
                    lines.append(str(data["annotationComment"]))
                    lines.append("")
            creators = data.get("creators") or []
            if creators:
                lines.append("## Creators")
                for creator in creators:
                    name = creator.get("name") or " ".join(
                        filter(None, [creator.get("firstName"), creator.get("lastName")])
                    )
                    lines.append(f"- {creator.get('creatorType', 'creator')}: {name}")
                lines.append("")
            for key in ("abstractNote", "note", "url", "date", "publicationTitle", "websiteTitle", "extra"):
                if data.get(key):
                    lines.append(f"## {key}")
                    lines.append(str(data[key]))
                    lines.append("")
            fields = data.get("fields") or {}
            if fields:
                lines.append("## Fields")
                for field_name in sorted(fields):
                    lines.append(f"- {field_name}: {fields[field_name]}")
                lines.append("")
            notes = data.get("notes") or []
            if notes:
                lines.append("## Notes")
                for note in notes:
                    note_text = note.get("note") or note.get("title") or ""
                    lines.append(note_text)
                    lines.append("")
            fulltext = data.get("fulltext") or {}
            if isinstance(fulltext, dict) and fulltext.get("content"):
                lines.append("## Fulltext")
                lines.append(str(fulltext["content"]))
                lines.append("")
        else:
            lines.append("## JSON")
            lines.append("```json")
            lines.append(json.dumps(payload, indent=2, sort_keys=True))
            lines.append("```")
            lines.append("")
        filename.write_text("\n".join(lines), encoding="utf-8")
        return filename

    def _prune_library_export(self, library_id: str, expected_files: set[Path]) -> int:
        library_dir = self.export_dir / sanitize_component(library_id)
        if not library_dir.exists():
            return 0
        pruned = 0
        for path in library_dir.rglob("*.md"):
            if path not in expected_files:
                path.unlink()
                pruned += 1
        for directory in sorted((path for path in library_dir.rglob("*") if path.is_dir()), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
        if library_dir.exists() and not any(library_dir.iterdir()):
            library_dir.rmdir()
        return pruned

    def _prune_export_root(self, active_library_ids: set[str]) -> int:
        if not self.export_dir.exists():
            return 0
        active_dirs = {self.export_dir / sanitize_component(library_id) for library_id in active_library_ids}
        pruned = 0
        for child in self.export_dir.iterdir():
            if child.is_dir() and child not in active_dirs:
                shutil.rmtree(child)
                pruned += 1
        return pruned

    def export_from_store(self, store: MirrorStore, library_id: str | None = None) -> dict[str, Any]:
        ensure_dir(self.export_dir)
        exported = 0
        pruned = 0
        libraries = [store.get_library(library_id)] if library_id else store.list_libraries()
        active_library_ids: set[str] = set()
        for library in libraries:
            if not library:
                continue
            lib_id = library["library_id"]
            active_library_ids.add(lib_id)
            expected_files: set[Path] = set()
            for kind in ("collection", "search", "item"):
                for obj in store.list_objects(lib_id, kind, limit=100000):
                    expected_files.add(
                        self._write_markdown(
                            lib_id,
                            kind,
                            obj["object_key"],
                            obj.get("title"),
                            obj["version"],
                            obj["payload"],
                        )
                    )
                    exported += 1
            pruned += self._prune_library_export(lib_id, expected_files)
        if library_id is None:
            pruned += self._prune_export_root(active_library_ids)
        self.ensure_collection()
        return {
            "exported": exported,
            "pruned": pruned,
            "export_dir": str(self.export_dir),
            "collection": self.settings.qmd_collection,
        }

    def export_from_canonical(self, canonical: CanonicalStore, library_id: str | None = None) -> dict[str, Any]:
        ensure_dir(self.export_dir)
        exported = 0
        pruned = 0
        libraries = [canonical.get_library(library_id)] if library_id else canonical.list_libraries()
        active_library_ids: set[str] = set()
        for library in libraries:
            if not library:
                continue
            lib_id = library["library_id"]
            active_library_ids.add(lib_id)
            expected_files: set[Path] = set()
            for entity_type in (EntityType.COLLECTION, EntityType.SEARCH, EntityType.ITEM):
                for obj in canonical.list_entities(lib_id, entity_type, limit=100000):
                    expected_files.add(
                        self._write_markdown(
                            lib_id,
                            entity_type.value,
                            obj["entity_key"],
                            obj.get("title"),
                            obj["version"],
                            obj["payload"],
                        )
                    )
                    exported += 1
            pruned += self._prune_library_export(lib_id, expected_files)
        if library_id is None:
            pruned += self._prune_export_root(active_library_ids)
        self.ensure_collection()
        return {
            "exported": exported,
            "pruned": pruned,
            "export_dir": str(self.export_dir),
            "collection": self.settings.qmd_collection,
        }

    def embed(self, force: bool = False) -> str:
        self.ensure_collection()
        args = ["embed"]
        if force:
            args.append("-f")
        result = self._run(args)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "qmd embed failed")
        return result.stdout

    def search(self, mode: str, query: str, *, limit: int = 10, library_id: str | None = None) -> Any:
        self.ensure_collection()
        args = [mode, query, "--json", "-n", str(limit), "-c", self.settings.qmd_collection]
        result = self._run(args)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"qmd {mode} failed")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {"raw": result.stdout}
        if library_id:
            filtered = []
            for row in payload if isinstance(payload, list) else payload.get("results", []):
                text = json.dumps(row, sort_keys=True)
                if sanitize_component(library_id) in text:
                    filtered.append(row)
            return filtered
        return payload


class QmdAutoIndexer:
    def __init__(self, settings: Settings):
        self.client = QmdClient(settings)

    def enabled(self) -> bool:
        return shutil.which("qmd") is not None

    def refresh_canonical_library(self, canonical: CanonicalStore, library_id: str) -> dict[str, Any]:
        if not self.enabled():
            return {"enabled": False, "reason": "qmd_missing", "library_id": library_id}
        result = self.client.export_from_canonical(canonical, library_id)
        self.client.embed(force=True)
        return {"enabled": True, "library_id": library_id, **result}

    def refresh_mirror_library(self, store: MirrorStore, library_id: str) -> dict[str, Any]:
        if not self.enabled():
            return {"enabled": False, "reason": "qmd_missing", "library_id": library_id}
        result = self.client.export_from_store(store, library_id)
        self.client.embed(force=True)
        return {"enabled": True, "library_id": library_id, **result}
