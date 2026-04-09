from __future__ import annotations

import getpass
from dataclasses import dataclass
from typing import Literal
from typing import Callable

from .autodiscover import autodiscover_settings
from .cli_ui import (
    ConfirmFn,
    SelectManyFn,
    SelectOneFn,
    prompt_yes_no,
    questionary_confirm,
    questionary_password,
    questionary_select_many,
    questionary_select_one,
    questionary_text,
)
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
    none_values: set[str] | None = None,
    input_fn: PromptFn = input,
) -> str | None:
    suffix = f" [{default}]" if default else ""
    value = input_fn(f"{label}{suffix}: ").strip()
    if none_values and value.lower() in none_values:
        return None
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


def _prompt_numbered_choice(
    label: str,
    options: list[str],
    *,
    default_index: int | None = None,
    input_fn: PromptFn = input,
) -> int:
    while True:
        suffix = f" [{default_index + 1}]" if default_index is not None else ""
        raw = input_fn(f"{label}{suffix}: ").strip()
        if not raw and default_index is not None:
            return default_index
        try:
            selected = int(raw)
        except ValueError:
            continue
        if 1 <= selected <= len(options):
            return selected - 1


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


def _prompt_library_selection(
    libraries: list[WizardLibrary],
    *,
    default_indices: list[int],
    has_existing_selection: bool,
    input_fn: PromptFn = input,
    confirm_fn: ConfirmFn | None = None,
    select_many_fn: SelectManyFn | None = None,
) -> list[int]:
    confirm_fn = confirm_fn or (lambda label, default=None: prompt_yes_no(label, default=default, input_fn=input_fn))
    if len(libraries) == 1:
        return [0]

    if has_existing_selection and default_indices:
        keep_default = confirm_fn("Use the currently selected remote libraries", True)
        if keep_default:
            return default_indices
    if not has_existing_selection:
        use_all = confirm_fn("Configure all discovered remote libraries", True)
        if use_all:
            return list(range(len(libraries)))
        if select_many_fn is not None:
            choices = [
                (
                    str(index),
                    f"{library.name} ({library.library_id}, {'personal' if library.kind == 'user' else 'group'}, {'writable' if library.editable else 'read-only'})",
                )
                for index, library in enumerate(libraries)
            ]
            selected = select_many_fn("Select remote libraries to configure", choices, [])
            return [int(value) for value in selected]

    while True:
        raw = input_fn(
            f"Remote libraries to configure [all, none, or comma-separated numbers; default: {_selection_prompt_suffix(default_indices, libraries)}]: "
        )
        try:
            selected = _parse_selection(raw, len(libraries), default_all=not bool(default_indices))
        except ValueError:
            continue
        if not raw.strip():
            return default_indices or list(range(len(libraries)))
        return selected


def _prompt_default_library(
    libraries: list[WizardLibrary],
    *,
    selected_indices: list[int],
    account_changed: bool,
    existing: Settings,
    input_fn: PromptFn = input,
    select_one_fn: SelectOneFn | None = None,
) -> str | None:
    if not selected_indices:
        return None
    selected_library_ids = [libraries[index].library_id for index in selected_indices]
    if len(selected_indices) == 1:
        selected = libraries[selected_indices[0]]
        print(f"Using {selected.name} ({selected.library_id}) as the default remote library.")
        return selected.library_id

    previous_default = None if account_changed else existing.default_library_id
    fallback = previous_default if previous_default in selected_library_ids else next(
        (libraries[index].library_id for index in selected_indices if libraries[index].kind == "user"),
        selected_library_ids[0],
    )

    if select_one_fn is not None:
        choices = [
            (libraries[index].library_id, f"{libraries[index].name} ({libraries[index].library_id})")
            for index in selected_indices
        ]
        return select_one_fn("Choose the default remote library", choices, fallback)

    print("\nDefault remote library:")
    default_index = 0
    for display_index, library_index in enumerate(selected_indices, start=1):
        library = libraries[library_index]
        marker = " default" if library.library_id == fallback else ""
        print(f"  {display_index}. {library.name} ({library.library_id}){marker}")
        if library.library_id == fallback:
            default_index = display_index - 1

    chosen_index = _prompt_numbered_choice(
        "Choose the default remote library",
        [libraries[index].library_id for index in selected_indices],
        default_index=default_index,
        input_fn=input_fn,
    )
    return libraries[selected_indices[chosen_index]].library_id


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
        citation_export_enabled=existing.citation_export_enabled,
        citation_export_format=existing.citation_export_format,
        citation_export_path=existing.citation_export_path,
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
    confirm_fn: ConfirmFn | None = None,
    select_one_fn: SelectOneFn | None = None,
    select_many_fn: SelectManyFn | None = None,
    client_factory: type[ZoteroWebClient] = ZoteroWebClient,
) -> WizardResult:
    using_default_input = input_fn is input
    using_default_secret = secret_fn is getpass.getpass
    if using_default_input:
        input_fn = lambda prompt: questionary_text(prompt.rstrip(": "), default=None)
    if using_default_secret:
        secret_fn = lambda prompt: questionary_password(prompt.rstrip(": "), default=None)
    if confirm_fn is None:
        if using_default_input:
            confirm_fn = questionary_confirm
        else:
            confirm_fn = lambda label, default=None: prompt_yes_no(label, default=default, input_fn=input_fn)
    if select_one_fn is None and using_default_input:
        select_one_fn = questionary_select_one
    if select_many_fn is None and using_default_input:
        select_many_fn = questionary_select_many
    autodiscovered = autodiscover_settings(existing)
    updated = _apply_base_settings(existing)
    print("Starting zotero-headless setup.")

    if mode in {"full", "local"}:
        if mode == "full" and autodiscovered.data_dir:
            updated.data_dir = autodiscovered.data_dir
            print(f"Using autodiscovered Zotero data directory: {autodiscovered.data_dir}")
        else:
            updated.data_dir = _prompt_value(
                "Zotero data directory for local desktop interoperability (optional; enter 'skip' to disable)",
                default=autodiscovered.data_dir,
                none_values={"skip", "none", "disable", "disabled"},
                input_fn=input_fn,
            )
        if mode == "full" and autodiscovered.zotero_bin:
            updated.zotero_bin = autodiscovered.zotero_bin
            print(f"Using autodiscovered Zotero desktop binary: {autodiscovered.zotero_bin}")
        else:
            updated.zotero_bin = _prompt_value(
                "Zotero desktop binary (optional)",
                default=autodiscovered.zotero_bin,
                input_fn=input_fn,
            )

    configure_remote = mode in {"account", "libraries"}
    if mode in {"full", "account", "libraries"}:
        if mode == "full":
            configure_remote = confirm_fn("Configure Zotero web sync now", bool(existing.api_key))
        if configure_remote:
            updated.api_base = _prompt_value("Zotero API base", default=existing.api_base, input_fn=input_fn) or existing.api_base
            updated.api_key = _prompt_secret(
                "Zotero API key",
                default=existing.api_key,
                secret_fn=secret_fn,
            )
        else:
            updated.api_key = None

    discovered_payloads: list[dict[str, object]] = []
    selected_library_ids: list[str] = []

    if mode in {"full", "account", "libraries"} and configure_remote and updated.api_key:
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
            selected_indices = _prompt_library_selection(
                discovered,
                default_indices=default_indices,
                has_existing_selection=bool(existing_selection),
                input_fn=input_fn,
                confirm_fn=confirm_fn,
                select_many_fn=select_many_fn,
            )
            selected_library_ids = [discovered[index].library_id for index in selected_indices]
            updated.remote_library_ids = selected_library_ids
            updated.default_library_id = _prompt_default_library(
                discovered,
                selected_indices=selected_indices,
                account_changed=account_changed,
                existing=existing,
                input_fn=input_fn,
                select_one_fn=select_one_fn,
            )
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
