from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings


@dataclass(slots=True)
class AutodiscoveryResult:
    data_dir: str | None = None
    zotero_bin: str | None = None
    api_key_found: bool = False
    selected_remote_library_ids: list[str] | None = None
    default_library_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "data_dir": self.data_dir,
            "zotero_bin": self.zotero_bin,
            "api_key_found": self.api_key_found,
            "selected_remote_library_ids": list(self.selected_remote_library_ids or []),
            "default_library_id": self.default_library_id,
        }


def _candidate_data_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / "Zotero",
        home / ".zotero" / "zotero",
        home / ".var" / "app" / "org.zotero.Zotero" / "data" / "Zotero",
        Path("/var/lib/zotero"),
        Path("/srv/zotero"),
    ]


def _candidate_binaries() -> list[Path]:
    return [
        Path("/Applications/Zotero.app/Contents/MacOS/zotero"),
        Path("/usr/bin/zotero"),
        Path("/usr/local/bin/zotero"),
        Path("/snap/bin/zotero"),
        Path.home() / ".local" / "bin" / "zotero",
    ]


def autodiscover_settings(existing: Settings) -> AutodiscoveryResult:
    data_dir = existing.data_dir
    if not data_dir:
        for candidate in _candidate_data_dirs():
            if (candidate / "zotero.sqlite").exists():
                data_dir = str(candidate)
                break

    zotero_bin = existing.zotero_bin
    if not zotero_bin:
        for candidate in _candidate_binaries():
            if candidate.exists():
                zotero_bin = str(candidate)
                break

    selected_remote_library_ids = list(existing.remote_library_ids) if existing.remote_library_ids else []
    return AutodiscoveryResult(
        data_dir=data_dir,
        zotero_bin=zotero_bin,
        api_key_found=bool(existing.api_key),
        selected_remote_library_ids=selected_remote_library_ids,
        default_library_id=existing.default_library_id,
    )
