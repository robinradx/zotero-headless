from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .utils import default_config_path, default_state_dir, ensure_dir, read_json, write_json


@dataclass(slots=True)
class Settings:
    data_dir: str | None = None
    api_key: str | None = None
    user_id: int | None = None
    remote_library_ids: list[str] = field(default_factory=list)
    default_library_id: str | None = None
    api_base: str = "https://api.zotero.org"
    state_dir: str | None = None
    canonical_db: str | None = None
    mirror_db: str | None = None
    export_dir: str | None = None
    citation_export_enabled: bool = False
    citation_export_format: str = "biblatex"
    citation_export_path: str | None = None
    file_cache_dir: str | None = None
    qmd_collection: str = "zotero-headless"
    recovery_snapshot_dir: str | None = None
    recovery_temp_dir: str | None = None
    recovery_auto_snapshots: bool = True
    backup_repositories: list[dict[str, object]] = field(default_factory=list)
    zotero_bin: str | None = None
    daemon_host: str = "127.0.0.1"
    daemon_port: int = 23119

    def resolved_state_dir(self) -> Path:
        return Path(self.state_dir).expanduser() if self.state_dir else default_state_dir()

    def resolved_canonical_db(self) -> Path:
        return Path(self.canonical_db).expanduser() if self.canonical_db else self.resolved_state_dir() / "canonical.sqlite"

    def resolved_mirror_db(self) -> Path:
        return Path(self.mirror_db).expanduser() if self.mirror_db else self.resolved_state_dir() / "headless.sqlite"

    def resolved_export_dir(self) -> Path:
        return Path(self.export_dir).expanduser() if self.export_dir else self.resolved_state_dir() / "qmd-export"

    def resolved_citation_export_path(self) -> Path:
        if self.citation_export_path:
            return Path(self.citation_export_path).expanduser()
        suffix = ".json" if self.citation_export_format == "csl-json" else ".bib"
        return self.resolved_state_dir() / f"citations{suffix}"

    def resolved_file_cache_dir(self) -> Path:
        return Path(self.file_cache_dir).expanduser() if self.file_cache_dir else self.resolved_state_dir() / "files"

    def resolved_recovery_snapshot_dir(self) -> Path:
        if self.recovery_snapshot_dir:
            return Path(self.recovery_snapshot_dir).expanduser()
        return self.resolved_state_dir() / "snapshots"

    def resolved_recovery_temp_dir(self) -> Path:
        if self.recovery_temp_dir:
            return Path(self.recovery_temp_dir).expanduser()
        return self.resolved_state_dir() / "recovery-tmp"

    def resolved_local_db(self) -> Path | None:
        if not self.data_dir:
            return None
        return Path(self.data_dir).expanduser() / "zotero.sqlite"

    def ensure_runtime_dirs(self) -> None:
        ensure_dir(self.resolved_state_dir())
        ensure_dir(self.resolved_export_dir())
        ensure_dir(self.resolved_citation_export_path().parent)
        ensure_dir(self.resolved_file_cache_dir())
        ensure_dir(self.resolved_canonical_db().parent)
        ensure_dir(self.resolved_mirror_db().parent)
        ensure_dir(self.resolved_recovery_snapshot_dir())
        ensure_dir(self.resolved_recovery_temp_dir())

    def as_dict(self) -> dict:
        return asdict(self)


def load_settings(path: Path | None = None, *, ensure_dirs: bool = True) -> Settings:
    config_path = path or default_config_path()
    raw = read_json(config_path, {})
    settings = Settings(**raw)
    env_data_dir = os.environ.get("ZOTERO_HEADLESS_DATA_DIR")
    env_api_key = os.environ.get("ZOTERO_HEADLESS_API_KEY")
    env_user_id = os.environ.get("ZOTERO_HEADLESS_USER_ID")
    env_api_base = os.environ.get("ZOTERO_HEADLESS_API_BASE")
    env_zotero_bin = os.environ.get("ZOTERO_HEADLESS_ZOTERO_BIN")
    env_daemon_host = os.environ.get("ZOTERO_HEADLESS_DAEMON_HOST")
    env_daemon_port = os.environ.get("ZOTERO_HEADLESS_DAEMON_PORT")

    if env_data_dir:
        settings.data_dir = env_data_dir
    if env_api_key:
        settings.api_key = env_api_key
    if env_user_id:
        settings.user_id = int(env_user_id)
    if env_api_base:
        settings.api_base = env_api_base
    if env_zotero_bin:
        settings.zotero_bin = env_zotero_bin
    if env_daemon_host:
        settings.daemon_host = env_daemon_host
    if env_daemon_port:
        settings.daemon_port = int(env_daemon_port)

    if ensure_dirs:
        settings.ensure_runtime_dirs()
    return settings


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    ensure_dir(config_path.parent)
    write_json(config_path, settings.as_dict())
    return config_path
