from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ..utils import now_iso


class EntityType(StrEnum):
    ITEM = "item"
    COLLECTION = "collection"
    SEARCH = "search"
    ATTACHMENT = "attachment"
    TAG = "tag"


class ChangeType(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(slots=True)
class ChangeRecord:
    library_id: str
    entity_type: EntityType
    entity_key: str
    change_type: ChangeType
    payload: dict[str, object] = field(default_factory=dict)
    base_version: int | None = None
    created_at: str = field(default_factory=now_iso)
