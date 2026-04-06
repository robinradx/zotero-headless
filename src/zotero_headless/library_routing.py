from __future__ import annotations

from .core import CanonicalStore
from .store import MirrorStore
from .utils import parse_library_id


def prefers_canonical_reads(canonical: CanonicalStore, library_id: str) -> bool:
    library_type, _ = parse_library_id(library_id)
    if library_type == "headless":
        return True
    return canonical.get_library(library_id) is not None


def prefers_canonical_writes(canonical: CanonicalStore, library_id: str) -> bool:
    library_type, _ = parse_library_id(library_id)
    if library_type == "headless":
        return True
    if library_type == "local":
        return False
    return canonical.get_library(library_id) is not None


def merged_libraries(store: MirrorStore, canonical: CanonicalStore) -> list[dict]:
    merged: dict[str, dict] = {library["library_id"]: library for library in store.list_libraries()}
    for library in canonical.list_libraries():
        merged[library["library_id"]] = library
    return sorted(merged.values(), key=lambda library: library["library_id"])
