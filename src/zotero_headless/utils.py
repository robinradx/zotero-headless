from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ANNOTATION_TYPE_IDS: dict[str, int] = {
    "highlight": 1,
    "note": 2,
    "image": 3,
    "ink": 4,
    "underline": 5,
    "text": 6,
}
ANNOTATION_TYPE_NAMES: dict[int, str] = {value: key for key, value in ANNOTATION_TYPE_IDS.items()}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def sanitize_component(value: str) -> str:
    value = value.strip()
    if not value:
        return "untitled"
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    return value.strip("-") or "untitled"


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def format_library_id(library_type: str, remote_id: int | str) -> str:
    return f"{library_type}:{remote_id}"


def parse_library_id(library_id: str) -> tuple[str, str]:
    if ":" not in library_id:
        raise ValueError(f"Invalid library id: {library_id!r}")
    library_type, remote_id = library_id.split(":", 1)
    if library_type not in {"user", "group", "local", "headless"}:
        raise ValueError(f"Unsupported library type: {library_type!r}")
    return library_type, remote_id


def parse_extra_kv(extra: str | None) -> dict[str, str]:
    if not extra:
        return {}
    kv: dict[str, str] = {}
    for line in str(extra).splitlines():
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        normalized = re.sub(r"\s+", " ", label.strip().lower())
        if not normalized:
            continue
        kv[normalized] = value.strip()
    return kv


def detect_citation_key(payload: dict[str, Any] | None = None, fields: dict[str, Any] | None = None) -> str | None:
    payload = payload or {}
    fields = fields or {}
    direct = payload.get("citationKey")
    if direct:
        return str(direct)
    field_value = fields.get("citationKey")
    if field_value:
        return str(field_value)
    extra = payload.get("extra")
    if extra is None:
        extra = fields.get("extra")
    if extra:
        extra_kv = parse_extra_kv(str(extra))
        if extra_kv.get("citation key"):
            return extra_kv["citation key"]
        if extra_kv.get("citation-key"):
            return extra_kv["citation-key"]
    return None


def detect_citation_aliases(payload: dict[str, Any] | None = None, fields: dict[str, Any] | None = None) -> list[str]:
    payload = payload or {}
    fields = fields or {}
    direct = payload.get("citationAliases")
    if isinstance(direct, list):
        aliases = [str(value).strip() for value in direct if str(value).strip()]
        if aliases:
            return aliases
    extra = payload.get("extra")
    if extra is None:
        extra = fields.get("extra")
    if extra:
        extra_kv = parse_extra_kv(str(extra))
        raw = extra_kv.get("tex.ids") or extra_kv.get("tex ids")
        if raw:
            aliases = [part.strip() for part in str(raw).split(",") if part.strip()]
            if aliases:
                return aliases
    return []


def set_pinned_citation_key_in_extra(extra: str | None, citation_key: str) -> str:
    lines = [] if not extra else str(extra).splitlines()
    replaced = False
    result: list[str] = []
    for line in lines:
        if ":" in line:
            label, _ = line.split(":", 1)
            normalized = re.sub(r"\s+", " ", label.strip().lower())
            if normalized in {"citation key", "citation-key"}:
                if not replaced:
                    result.append(f"Citation Key: {citation_key}")
                    replaced = True
                continue
        result.append(line)
    if not replaced:
        if result and result[-1].strip():
            result.append("")
        result.append(f"Citation Key: {citation_key}")
    return "\n".join(result).strip()


def set_pinned_citation_aliases_in_extra(extra: str | None, aliases: list[str]) -> str:
    normalized_aliases = [str(alias).strip() for alias in aliases if str(alias).strip()]
    lines = [] if not extra else str(extra).splitlines()
    replaced = False
    result: list[str] = []
    for line in lines:
        if ":" in line:
            label, _ = line.split(":", 1)
            normalized = re.sub(r"\s+", " ", label.strip().lower())
            if normalized in {"tex.ids", "tex ids"}:
                if normalized_aliases and not replaced:
                    result.append(f"tex.ids: {', '.join(normalized_aliases)}")
                    replaced = True
                continue
        result.append(line)
    if normalized_aliases and not replaced:
        if result and result[-1].strip():
            result.append("")
        result.append(f"tex.ids: {', '.join(normalized_aliases)}")
    return "\n".join(result).strip()


def normalize_annotation_type(value: object) -> tuple[str, int] | None:
    if value is None:
        return None
    if isinstance(value, int):
        name = ANNOTATION_TYPE_NAMES.get(value)
        if name:
            return name, value
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        if text.isdigit():
            annotation_id = int(text)
            name = ANNOTATION_TYPE_NAMES.get(annotation_id)
            if name:
                return name, annotation_id
            return None
        annotation_id = ANNOTATION_TYPE_IDS.get(text)
        if annotation_id is not None:
            return text, annotation_id
    return None


def annotation_display_title(payload: dict[str, Any] | None = None) -> str | None:
    payload = payload or {}
    text = str(payload.get("annotationText") or "").strip()
    comment = str(payload.get("annotationComment") or "").strip()
    page_label = str(payload.get("annotationPageLabel") or "").strip()
    annotation_type = str(payload.get("annotationType") or "annotation").strip()
    lead = text or comment
    if not lead:
        return None
    compact = " ".join(lead.split())
    if len(compact) > 80:
        compact = compact[:77].rstrip() + "..."
    if page_label:
        return f"{annotation_type}@{page_label}: {compact}"
    return f"{annotation_type}: {compact}"


def default_config_path() -> Path:
    override = os.environ.get("ZOTERO_HEADLESS_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "zotero-headless" / "config.json"


def default_state_dir(profile: str | None = None) -> Path:
    override = os.environ.get("ZOTERO_HEADLESS_STATE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    root = base / "zotero-headless"
    if not profile:
        return root
    return root / "profiles" / sanitize_component(profile)
