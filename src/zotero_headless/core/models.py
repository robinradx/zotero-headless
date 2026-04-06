from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LibraryRef:
    kind: str
    key: str

    @property
    def library_id(self) -> str:
        return f"{self.kind}:{self.key}"


@dataclass(slots=True)
class SyncState:
    version: int = 0
    synced: bool = False
    remote_version: int | None = None
    deleted: bool = False


@dataclass(slots=True)
class AttachmentRecord:
    key: str
    parent_key: str | None = None
    title: str | None = None
    content_type: str | None = None
    path: str | None = None
    storage_hash: str | None = None
    sync: SyncState = field(default_factory=SyncState)


@dataclass(slots=True)
class HeadlessItem:
    key: str
    library: LibraryRef
    item_type: str
    fields: dict[str, object] = field(default_factory=dict)
    creators: list[dict[str, object]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    collections: list[str] = field(default_factory=list)
    relations: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    attachments: list[AttachmentRecord] = field(default_factory=list)
    sync: SyncState = field(default_factory=SyncState)


@dataclass(slots=True)
class HeadlessLibrary:
    ref: LibraryRef
    name: str
    editable: bool = True
    source: str = "headless"
    metadata: dict[str, object] = field(default_factory=dict)
