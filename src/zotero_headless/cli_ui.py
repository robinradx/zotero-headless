from __future__ import annotations

from typing import Any, Callable, Iterable

try:
    import questionary
except ImportError:  # pragma: no cover - optional at import time for test environments
    questionary = None


PromptFn = Callable[[str], str]
SecretPromptFn = Callable[[str], str]
ConfirmFn = Callable[[str, bool | None], bool]
SelectOneFn = Callable[[str, list[tuple[str, str]], str | None], str]
SelectManyFn = Callable[[str, list[tuple[str, str]], list[str]], list[str]]


def prompt_yes_no(
    label: str,
    *,
    default: bool | None = None,
    input_fn: PromptFn = input,
) -> bool:
    if default is True:
        suffix = " [Y/n]"
    elif default is False:
        suffix = " [y/N]"
    else:
        suffix = " [y/n]"

    while True:
        raw = input_fn(f"{label}{suffix}: ").strip().lower()
        if not raw:
            if default is not None:
                return default
        elif raw in {"y", "yes"}:
            return True
        elif raw in {"n", "no"}:
            return False


def questionary_text(label: str, *, default: str | None = None) -> str:
    if questionary is None:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{label}{suffix}: ").strip()
        return raw or (default or "")
    result = questionary.text(label, default=default or "").ask()
    return (result or default or "").strip()


def questionary_password(label: str, *, default: str | None = None) -> str:
    if questionary is None:
        suffix = " [saved]" if default else ""
        raw = input(f"{label}{suffix}: ").strip()
        return raw or (default or "")
    result = questionary.password(label).ask()
    return (result or default or "").strip()


def questionary_confirm(label: str, default: bool | None = None) -> bool:
    if questionary is None:
        return prompt_yes_no(label, default=default)
    return bool(questionary.confirm(label, default=default if default is not None else True).ask())


def questionary_select_one(label: str, choices: list[tuple[str, str]], default: str | None = None) -> str:
    if questionary is None:
        for index, (value, title) in enumerate(choices, start=1):
            marker = " (default)" if value == default else ""
            print(f"  {index}. {title}{marker}")
        while True:
            raw = input(f"{label}: ").strip()
            if not raw and default is not None:
                return default
            try:
                selected = int(raw)
            except ValueError:
                continue
            if 1 <= selected <= len(choices):
                return choices[selected - 1][0]
    q_choices = [questionary.Choice(title=title, value=value) for value, title in choices]
    return questionary.select(label, choices=q_choices, default=default).ask()


def questionary_select_many(label: str, choices: list[tuple[str, str]], defaults: list[str] | None = None) -> list[str]:
    defaults = defaults or []
    if questionary is None:
        print(label)
        for index, (_, title) in enumerate(choices, start=1):
            marker = " [selected]" if choices[index - 1][0] in defaults else ""
            print(f"  {index}. {title}{marker}")
        raw = input("Selection (all, none, or comma-separated numbers): ").strip().lower()
        if not raw:
            return defaults
        if raw in {"all", "*"}:
            return [value for value, _ in choices]
        if raw in {"none", "0"}:
            return []
        selected: list[str] = []
        for part in raw.split(","):
            index = int(part.strip())
            if 1 <= index <= len(choices):
                selected.append(choices[index - 1][0])
        return selected

    q_choices = [
        questionary.Choice(title=title, value=value, checked=value in defaults)
        for value, title in choices
    ]
    result = questionary.checkbox(label, choices=q_choices).ask()
    return list(result or [])


def _label(text: str) -> str:
    return text.replace("_", " ").strip().capitalize()


def _bool_text(value: Any) -> str:
    return "yes" if value else "no"


def _lines_for_mapping(mapping: dict[str, Any], *, indent: str = "") -> list[str]:
    lines: list[str] = []
    for key, value in mapping.items():
        label = _label(str(key))
        if isinstance(value, dict):
            lines.append(f"{indent}{label}:")
            lines.extend(_lines_for_mapping(value, indent=indent + "  "))
        elif isinstance(value, list):
            lines.append(f"{indent}{label}:")
            if not value:
                lines.append(f"{indent}  - none")
            else:
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{indent}  -")
                        lines.extend(_lines_for_mapping(item, indent=indent + "    "))
                    else:
                        lines.append(f"{indent}  - {item}")
        else:
            if isinstance(value, bool):
                value = _bool_text(value)
            lines.append(f"{indent}{label}: {value}")
    return lines


def render_version_payload(payload: dict[str, Any]) -> str:
    aliases = ", ".join(payload.get("aliases_found") or []) or "none"
    return "\n".join(
        [
            f"{payload.get('package', 'zotero-headless')} {payload.get('version', 'unknown')}",
            f"Install method: {payload.get('install_method', 'unknown')}",
            f"Current executable: {payload.get('executable', 'unknown')}",
            f"Python: {payload.get('python', 'unknown')}",
            f"Available aliases: {aliases}",
        ]
    )


def render_update_plan(payload: dict[str, Any]) -> str:
    plan = payload.get("plan") or {}
    command = " ".join(plan.get("command") or []) or "(no automatic command available)"
    return "\n".join(
        [
            "Update check",
            f"Install method: {plan.get('method', 'unknown')}",
            f"Automatic update: {_bool_text(plan.get('auto_supported'))}",
            f"Suggested command: {command}",
            f"Reason: {plan.get('reason', '')}",
        ]
    )


def render_update_result(payload: dict[str, Any]) -> str:
    plan = payload.get("plan") or {}
    command = " ".join(plan.get("command") or []) or "(no automatic command available)"
    lines = [
        "Update result",
        f"Updated: {_bool_text(payload.get('updated'))}",
        f"Install method: {plan.get('method', 'unknown')}",
        f"Command: {command}",
    ]
    message = payload.get("message")
    if message:
        lines.append(f"Message: {message}")
    stdout = (payload.get("stdout") or "").strip()
    stderr = (payload.get("stderr") or "").strip()
    if stdout:
        lines.append("Stdout:")
        lines.extend(f"  {line}" for line in stdout.splitlines())
    if stderr:
        lines.append("Stderr:")
        lines.extend(f"  {line}" for line in stderr.splitlines())
    return "\n".join(lines)


def render_setup_list(entries: list[dict[str, Any]]) -> str:
    lines = ["MCP client setup targets"]
    for entry in entries:
        path = entry.get("path") or "(generated only)"
        status = "installed" if entry.get("installed") else "not installed"
        scope = entry.get("scope")
        label = entry.get("target")
        if scope:
            lines.append(f"- {label} [{scope}]: {status}")
        else:
            lines.append(f"- {label}: {status}")
        lines.append(f"  path: {path}")
    return "\n".join(lines)


def render_setup_target(entry: dict[str, Any]) -> str:
    lines = [
        f"Setup target: {entry.get('target')}",
        f"Installed: {_bool_text(entry.get('installed'))}",
        f"Scope: {entry.get('scope')}",
        f"Path: {entry.get('path') or '(generated only)'}",
    ]
    return "\n".join(lines)


def render_install_result(entry: dict[str, Any], *, heading: str) -> str:
    lines = [
        heading,
        f"Target: {entry.get('target')}",
    ]
    if entry.get("variant"):
        lines.append(f"Variant: {entry.get('variant')}")
    if "scope" in entry:
        lines.append(f"Scope: {entry.get('scope')}")
    if entry.get("path"):
        lines.append(f"Path: {entry.get('path')}")
    if entry.get("installed") is not None:
        lines.append(f"Installed: {_bool_text(entry.get('installed'))}")
    if entry.get("removed") is not None:
        lines.append(f"Removed: {_bool_text(entry.get('removed'))}")
    instructions = entry.get("instructions") or []
    if instructions:
        lines.append("Next steps:")
        lines.extend(f"- {line}" for line in instructions)
    return "\n".join(lines)


def render_setup_result(payload: dict[str, Any]) -> str:
    settings = payload.get("settings") or {}
    autodiscovered = payload.get("autodiscovered") or {}
    selected = payload.get("selected_remote_libraries") or []
    lines = [
        "Setup complete",
        f"Config saved to: {payload.get('config')}",
        f"Local desktop interoperability: {_bool_text(bool(settings.get('data_dir')))}",
        f"Remote sync configured: {_bool_text(bool(settings.get('api_key')))}",
        f"Default remote library: {settings.get('default_library_id') or 'none'}",
        f"Daemon address: {settings.get('daemon_host')}:{settings.get('daemon_port')}",
        f"qmd collection: {settings.get('qmd_collection')}",
    ]
    if autodiscovered:
        lines.append("Autodiscovered:")
        for key in ("data_dir", "zotero_bin"):
            value = autodiscovered.get(key)
            if value:
                lines.append(f"- {_label(key)}: {value}")
    if selected:
        lines.append("Configured remote libraries:")
        lines.extend(f"- {library_id}" for library_id in selected)
    return "\n".join(lines)


def render_doctor_report(report: dict[str, Any]) -> str:
    cli = report.get("cli") or {}
    settings = report.get("settings") or {}
    daemon = report.get("daemon") or {}
    setup_targets = report.get("setup_targets") or []
    skill_targets = report.get("skill_targets") or []

    lines = ["Doctor report", "", "CLI tools:"]
    for key, value in cli.items():
        lines.append(f"- {_label(key)}: {value or 'not found'}")

    lines.extend(["", "Settings:"])
    for key in ("state_dir", "headless_db", "mirror_db", "export_dir", "file_cache_dir", "data_dir", "local_db"):
        lines.append(f"- {_label(key)}: {settings.get(key) or 'not configured'}")
    lines.append(f"- API key configured: {_bool_text(settings.get('api_key_configured'))}")

    lines.extend(["", "Daemon:"])
    daemon_summary_keys = (
        "available",
        "mode",
        "message",
        "runtime_running",
        "read_api_ready",
        "write_api_ready",
        "local_api_url",
    )
    for key in daemon_summary_keys:
        if key in daemon:
            value = daemon.get(key)
            if isinstance(value, bool):
                value = _bool_text(value)
            lines.append(f"- {_label(key)}: {value}")

    lines.extend(["", "MCP client setup:"])
    for entry in setup_targets:
        status = "installed" if entry.get("installed") else "not installed"
        lines.append(f"- {entry.get('target')} [{entry.get('scope')}]: {status}")

    lines.extend(["", "Skill targets:"])
    for entry in skill_targets:
        variants = ", ".join(entry.get("variants") or [])
        lines.append(f"- {entry.get('target')}: variants {variants}")

    return "\n".join(lines)


def render_daemon_status(payload: dict[str, Any]) -> str:
    return "\n".join(_lines_for_mapping(payload))


def render_daemon_command(payload: dict[str, Any]) -> str:
    return "\n".join(_lines_for_mapping(payload))


def render_config_payload(payload: dict[str, Any]) -> str:
    return "\n".join(_lines_for_mapping(payload))


def render_text_list(lines: Iterable[str]) -> str:
    return "\n".join(lines)
