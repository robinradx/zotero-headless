from __future__ import annotations

import getpass
from dataclasses import dataclass
from typing import Literal
from typing import Callable

from .autodiscover import autodiscover_settings
from .config import Settings
from .core import CanonicalStore
from .utils import format_library_id
from .web_api import ZoteroWebClient


PromptFn = Callable[[str], str]
SecretPromptFn = Callable[[str], str]
WizardMode = Literal["full", "account", "libraries", "local"]


@dataclass(slots=True)
class WizardLibrary:
    library_id: str
    name: str
    editable: bool = True
    kind: str = "user"


@dataclass(slots=True)
class WizardResult:
    settings: Settings
    discovered_libraries: list[dict[str, object]]
    selected_library_ids: list[str]
    config_path: str | None = None
    autodiscovered: dict[str, object] | None = None


def _default_data_dir(existing: Settings) -> str | None:
    discovered = autodiscover_settings(existing)
    return discovered.data_dir


def _prompt_value(
    label: str,
    *,
    default: str | None = None,
    input_fn: PromptFn = input,
) -> str | None:
    suffix = f" [{default}]" if default else ""
    value = input_fn(f"{label}{suffix}: ").strip()
    if value:
        return value
    return default


def _prompt_secret(
    label: str,
    *,
    default: str | None = None,
    secret_fn: SecretPromptFn = getpass.getpass,
) -> str | None:
    suffix = " [saved]" if default else ""
    value = secret_fn(f"{label}{suffix}: ").strip()
    if value:
        return value
    return default


def _parse_selection(raw: str, total: int, *, default_all: bool = True) -> list[int]:
    value = raw.strip().lower()
    if not value:
        return list(range(total)) if default_all else []
    if value in {"all", "*"}:
        return list(range(total))
    if value in {"none", "0"}:
        return []
    indices: list[int] = []
    for chunk in value.split(","):
        part = chunk.strip()
        if not part:
            continue
        index = int(part)
        if index < 1 or index > total:
            raise ValueError(f"Selection index out of range: {index}")
        zero_index = index - 1
        if zero_index not in indices:
            indices.append(zero_index)
    return indices


def _selection_prompt_suffix(default_indices: list[int], libraries: list[WizardLibrary]) -> str:
    if not default_indices:
        return "all" if libraries else "none"
    return ",".join(str(index + 1) for index in default_indices)


def _apply_base_settings(existing: Settings) -> Settings:
    return Settings(
        data_dir=existing.data_dir,
        api_key=existing.api_key,
        user_id=existing.user_id,
        remote_library_ids=list(existing.remote_library_ids),
        default_library_id=existing.default_library_id,
        api_base=existing.api_base,
        state_dir=str(existing.resolved_state_dir()),
        canonical_db=str(existing.resolved_canonical_db()),
        mirror_db=str(existing.resolved_mirror_db()),
        export_dir=str(existing.resolved_export_dir()),
        file_cache_dir=str(existing.resolved_file_cache_dir()),
        qmd_collection=existing.qmd_collection,
        zotero_bin=existing.zotero_bin,
        daemon_host=existing.daemon_host,
        daemon_port=existing.daemon_port,
    )


def _discover_remote_libraries(settings: Settings, client_factory: type[ZoteroWebClient] = ZoteroWebClient) -> tuple[int, list[WizardLibrary]]:
    client = client_factory(settings)
    key_info = client.get_current_key()
    user_id = int(key_info["userID"])
    libraries: list[WizardLibrary] = []
    user_access = (key_info.get("access") or {}).get("user") or {}
    if user_access.get("library"):
        libraries.append(
            WizardLibrary(
                library_id=format_library_id("user", user_id),
                name=key_info.get("username") or f"user:{user_id}",
                editable=bool(user_access.get("write")),
                kind="user",
            )
        )

    groups, _ = client.get_group_versions(user_id)
    group_access = ((key_info.get("access") or {}).get("groups") or {}).get("all") or {}
    for group_id in groups:
        payload, _ = client.get_group(group_id)
        libraries.append(
            WizardLibrary(
                library_id=format_library_id("group", group_id),
                name=payload.get("data", {}).get("name") or payload.get("name") or f"group:{group_id}",
                editable=bool(group_access.get("write")),
                kind="group",
            )
        )
    return user_id, libraries


def _seed_canonical_libraries(settings: Settings, libraries: list[WizardLibrary]) -> list[dict[str, object]]:
    store = CanonicalStore(settings.resolved_canonical_db())
    discovered: list[dict[str, object]] = []
    for library in libraries:
        existing = store.get_library(library.library_id) or {}
        discovered.append(
            store.upsert_library(
                library.library_id,
                name=library.name,
                source="remote-sync",
                editable=library.editable,
                metadata=(existing.get("metadata") or {"library_version": 0, "last_full_sync": None}),
            )
        )
    return discovered


def run_setup_wizard(
    existing: Settings,
    *,
    mode: WizardMode = "full",
    input_fn: PromptFn = input,
    secret_fn: SecretPromptFn = getpass.getpass,
    client_factory: type[ZoteroWebClient] = ZoteroWebClient,
) -> WizardResult:
    autodiscovered = autodiscover_settings(existing)
    updated = _apply_base_settings(existing)

    if mode in {"full", "local"}:
        updated.data_dir = _prompt_value("Zotero data directory", default=autodiscovered.data_dir, input_fn=input_fn)
        updated.zotero_bin = _prompt_value(
            "Zotero desktop binary (optional)",
            default=autodiscovered.zotero_bin,
            input_fn=input_fn,
        )

    if mode in {"full", "account", "libraries"}:
        updated.api_base = _prompt_value("Zotero API base", default=existing.api_base, input_fn=input_fn) or existing.api_base
        updated.api_key = _prompt_secret(
            "Zotero API key (leave blank for local-only setup)",
            default=existing.api_key,
            secret_fn=secret_fn,
        )

    discovered_payloads: list[dict[str, object]] = []
    selected_library_ids: list[str] = []

    if mode in {"full", "account", "libraries"} and updated.api_key:
        user_id, discovered = _discover_remote_libraries(updated, client_factory=client_factory)
        account_changed = existing.user_id not in {None, user_id}
        updated.user_id = user_id
        if discovered:
            print("\nDiscovered remote libraries:")
            existing_selection = set() if account_changed else set(existing.remote_library_ids)
            default_indices = [idx for idx, library in enumerate(discovered) if library.library_id in existing_selection]
            if not default_indices:
                default_indices = list(range(len(discovered)))
            for idx, library in enumerate(discovered, start=1):
                suffix = "personal" if library.kind == "user" else "group"
                writable = "writable" if library.editable else "read-only"
                selected = " selected" if (idx - 1) in default_indices else ""
                print(f"  {idx}. {library.name} ({library.library_id}, {suffix}, {writable}{selected})")
            raw = input_fn(
                f"\nRemote libraries to configure [all, none, or comma-separated numbers; default: {_selection_prompt_suffix(default_indices, discovered)}]: "
            )
            selected_indices = _parse_selection(raw, len(discovered), default_all=not bool(existing_selection))
            if not raw.strip():
                selected_indices = default_indices
            selected_library_ids = [discovered[index].library_id for index in selected_indices]
            updated.remote_library_ids = selected_library_ids
            default_library = None
            if selected_library_ids:
                previous_default = None if account_changed else existing.default_library_id
                fallback = previous_default if previous_default in selected_library_ids else next(
                    (library.library_id for library in discovered if library.kind == "user" and library.library_id in selected_library_ids),
                    selected_library_ids[0],
                )
                default_library = _prompt_value(
                    "Default remote library",
                    default=fallback,
                    input_fn=input_fn,
                )
            updated.default_library_id = default_library
            discovered_payloads = _seed_canonical_libraries(updated, discovered)
        else:
            updated.remote_library_ids = []
            updated.default_library_id = None
    elif mode in {"full", "account", "libraries"}:
        updated.user_id = None
        updated.remote_library_ids = []
        updated.default_library_id = None

    if mode == "full":
        host = _prompt_value("Daemon host", default=existing.daemon_host, input_fn=input_fn) or existing.daemon_host
        port_raw = _prompt_value("Daemon port", default=str(existing.daemon_port), input_fn=input_fn) or str(existing.daemon_port)
        qmd_collection = _prompt_value("qmd collection name", default=existing.qmd_collection, input_fn=input_fn) or existing.qmd_collection
        updated.daemon_host = host
        updated.daemon_port = int(port_raw)
        updated.qmd_collection = qmd_collection

    return WizardResult(
        settings=updated,
        discovered_libraries=discovered_payloads,
        selected_library_ids=selected_library_ids,
        autodiscovered=autodiscovered.to_dict(),
    )
