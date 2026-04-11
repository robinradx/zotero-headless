from __future__ import annotations

from typing import Any, Callable, Iterable

try:
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - optional at import time for test environments
    Group = None
    Panel = None
    Table = None
    Text = None

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


def _install_heading(entry: dict[str, Any], heading: str) -> str:
    if entry.get("removed") is not None:
        return heading
    installed = entry.get("installed")
    written = entry.get("written")
    succeeded = True
    if installed is False or written is False:
        succeeded = False
    if succeeded:
        return heading
    if heading.startswith("Plugin"):
        return "Plugin not installed"
    if heading.startswith("Setup"):
        return "Setup not applied"
    if heading.startswith("Skill"):
        return "Skill not installed"
    return heading


def _reason_text(reason: Any) -> str | None:
    mapping = {
        "plugin_not_found": "The local plugin bundle could not be found.",
        "openclaw_not_found": "The `openclaw` CLI is not available on PATH.",
        "openclaw_install_failed": "OpenClaw rejected the plugin install command.",
        "plugin_source_not_found": "The source plugin directory could not be found.",
        "config_not_found": "The target config file does not exist yet.",
        "openclaw_uninstall_failed": "OpenClaw rejected the plugin uninstall command.",
    }
    if not reason:
        return None
    return mapping.get(str(reason), str(reason))


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
    lines = [
        "Update check",
        f"Current version: {payload.get('current_version', 'unknown')}",
        f"Install method: {plan.get('method', 'unknown')}",
        f"Automatic update: {_bool_text(plan.get('auto_supported'))}",
        f"Suggested command: {command}",
        f"Reason: {plan.get('reason', '')}",
    ]
    return "\n".join(lines)


def render_update_result(payload: dict[str, Any]) -> str:
    plan = payload.get("plan") or {}
    command = " ".join(plan.get("command") or []) or "(no automatic command available)"
    command_succeeded = payload.get("command_succeeded")
    before_version = payload.get("before_version", "unknown")
    after_version = payload.get("after_version", "unknown")
    status = "failed"
    if payload.get("updated"):
        status = "updated"
    elif payload.get("already_current"):
        status = "already current"
    elif command_succeeded:
        status = "completed"
    lines = [
        "Update result",
        f"Status: {status}",
        f"Command succeeded: {_bool_text(command_succeeded)}",
        f"Version: {before_version} -> {after_version}",
        f"Updated: {_bool_text(payload.get('updated'))}",
        f"Install method: {plan.get('method', 'unknown')}",
        f"Command: {command}",
    ]
    duration_seconds = payload.get("duration_seconds")
    if isinstance(duration_seconds, (int, float)):
        lines.append(f"Duration: {duration_seconds:.1f}s")
    message = payload.get("message")
    if message:
        lines.append(f"Message: {message}")
    elif payload.get("already_current"):
        lines.append("Message: zotero-headless is already at the installed target version.")
    stdout = (payload.get("stdout") or "").strip()
    stderr = (payload.get("stderr") or "").strip()
    if stdout:
        lines.append("Stdout:")
        lines.extend(f"  {line}" for line in stdout.splitlines())
    if stderr:
        lines.append("Stderr:")
        lines.extend(f"  {line}" for line in stderr.splitlines())
    post_update = payload.get("post_update") or {}
    if post_update:
        skills = post_update.get("skills") or []
        plugins = post_update.get("plugins") or []
        skipped = post_update.get("skipped_plugins") or []
        lines.append("Post-update refresh:")
        lines.append(f"  Skills refreshed: {len(skills)}")
        lines.append(f"  Plugins refreshed: {len(plugins)}")
        if skipped:
            lines.append(f"  Plugins skipped: {len(skipped)}")
            for entry in skipped:
                lines.append(f"    - {entry.get('target')}: {entry.get('reason')}")
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
    heading = _install_heading(entry, heading)
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
    reason = _reason_text(entry.get("reason"))
    if reason:
        lines.append(f"Reason: {reason}")
    stdout = (entry.get("stdout") or "").strip()
    stderr = (entry.get("stderr") or "").strip()
    if stdout:
        lines.append("Stdout:")
        lines.extend(f"  {line}" for line in stdout.splitlines())
    if stderr:
        lines.append("Stderr:")
        lines.extend(f"  {line}" for line in stderr.splitlines())
    instructions = entry.get("instructions") or []
    if instructions:
        lines.append("Next steps:")
        lines.extend(f"- {line}" for line in instructions)
    notes = entry.get("notes") or []
    if notes:
        lines.append("Notes:")
        lines.extend(f"- {line}" for line in notes)
    return "\n".join(lines)


def render_setup_result(payload: dict[str, Any]) -> str:
    settings = payload.get("settings") or {}
    autodiscovered = payload.get("autodiscovered") or {}
    selected = payload.get("selected_remote_libraries") or []
    warnings = payload.get("warnings") or []
    citation_export_path = payload.get("citation_export_path") or settings.get("citation_export_path") or "not configured"
    lines = [
        "Setup complete",
        f"Config saved to: {payload.get('config')}",
        f"Local desktop interoperability: {_bool_text(bool(settings.get('data_dir')))}",
        f"Remote sync configured: {_bool_text(bool(settings.get('api_key')))}",
        f"Default remote library: {settings.get('default_library_id') or 'none'}",
        f"Daemon address: {settings.get('daemon_host')}:{settings.get('daemon_port')}",
        f"qmd collection: {settings.get('qmd_collection')}",
        f"Citations export: {_bool_text(bool(settings.get('citation_export_enabled')))} ({settings.get('citation_export_format')})",
        f"Citations path: {citation_export_path}",
        f"Recovery snapshots: {_bool_text(settings.get('recovery_auto_snapshots', True))}",
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
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
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
    for key in ("state_dir", "headless_db", "mirror_db", "export_dir", "file_cache_dir", "recovery_snapshot_dir", "recovery_temp_dir", "data_dir", "local_db"):
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


def _summary_table(title: str | None = None) -> Table:
    if Table is None:  # pragma: no cover - rich-only helper
        raise RuntimeError("rich is not installed")
    table = Table(title=title, box=None, show_header=False, pad_edge=False, expand=False)
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()
    return table


def _bullet_lines(items: list[str]) -> Text:
    if Text is None:  # pragma: no cover - rich-only helper
        raise RuntimeError("rich is not installed")
    text = Text()
    for index, item in enumerate(items):
        if index:
            text.append("\n")
        text.append("• ", style="cyan")
        text.append(item)
    return text


def render_version_payload_rich(payload: dict[str, Any]):
    if Table is None:
        return render_version_payload(payload)
    aliases = ", ".join(payload.get("aliases_found") or []) or "none"
    table = _summary_table()
    table.add_row("Package", f"[bold]{payload.get('package', 'zotero-headless')}[/bold]")
    table.add_row("Version", f"[bold]{payload.get('version', 'unknown')}[/bold]")
    table.add_row("Install method", str(payload.get("install_method", "unknown")))
    table.add_row("Executable", str(payload.get("executable", "unknown")))
    table.add_row("Python", str(payload.get("python", "unknown")))
    table.add_row("Aliases", aliases)
    return table


def render_update_plan_rich(payload: dict[str, Any]):
    if Table is None or Panel is None or Group is None:
        return render_update_plan(payload)
    plan = payload.get("plan") or {}
    command = " ".join(plan.get("command") or []) or "(no automatic command available)"
    table = _summary_table()
    table.add_row("Current version", str(payload.get("current_version", "unknown")))
    table.add_row("Install method", str(plan.get("method", "unknown")))
    table.add_row("Automatic update", _bool_text(plan.get("auto_supported")))
    table.add_row("Reason", str(plan.get("reason", "")))
    command_panel = Panel(command, title="Suggested command", border_style="cyan")
    return Group(table, command_panel)


def render_update_result_rich(payload: dict[str, Any]):
    if Table is None or Panel is None or Group is None or Text is None:
        return render_update_result(payload)
    plan = payload.get("plan") or {}
    command = " ".join(plan.get("command") or []) or "(no automatic command available)"
    command_succeeded = payload.get("command_succeeded")
    before_version = payload.get("before_version", "unknown")
    after_version = payload.get("after_version", "unknown")
    status = "failed"
    status_style = "red"
    if payload.get("updated"):
        status = "updated"
        status_style = "green"
    elif payload.get("already_current"):
        status = "already current"
        status_style = "yellow"
    elif command_succeeded:
        status = "completed"
        status_style = "cyan"
    table = _summary_table()
    table.add_row("Status", f"[bold {status_style}]{status}[/bold {status_style}]")
    table.add_row("Version", f"{before_version} -> {after_version}")
    table.add_row("Command succeeded", _bool_text(command_succeeded))
    table.add_row("Updated", _bool_text(payload.get("updated")))
    table.add_row("Install method", str(plan.get("method", "unknown")))
    duration_seconds = payload.get("duration_seconds")
    if isinstance(duration_seconds, (int, float)):
        table.add_row("Duration", f"{duration_seconds:.1f}s")

    renderables: list[Any] = [table, Panel(command, title="Command", border_style="cyan")]
    message = payload.get("message")
    if message:
        renderables.append(Panel(str(message), title="Message", border_style="yellow"))
    elif payload.get("already_current"):
        renderables.append(
            Panel(
                "zotero-headless is already at the installed target version.",
                title="Message",
                border_style="yellow",
            )
        )
    stdout = (payload.get("stdout") or "").strip()
    stderr = (payload.get("stderr") or "").strip()
    if stdout:
        renderables.append(Panel(stdout, title="Stdout", border_style="green"))
    if stderr:
        renderables.append(Panel(stderr, title="Stderr", border_style="yellow"))
    post_update = payload.get("post_update") or {}
    if post_update:
        skills = post_update.get("skills") or []
        plugins = post_update.get("plugins") or []
        skipped = post_update.get("skipped_plugins") or []
        refresh = _summary_table("Post-update refresh")
        refresh.add_row("Skills refreshed", str(len(skills)))
        refresh.add_row("Plugins refreshed", str(len(plugins)))
        refresh.add_row("Plugins skipped", str(len(skipped)))
        renderables.append(refresh)
        if skipped:
            skipped_lines = [f"{entry.get('target')}: {entry.get('reason')}" for entry in skipped]
            renderables.append(Panel(_bullet_lines(skipped_lines), title="Skipped plugins", border_style="yellow"))
    return Group(*renderables)


def render_setup_target_rich(entry: dict[str, Any]):
    if Table is None:
        return render_setup_target(entry)
    table = _summary_table()
    table.add_row("Target", str(entry.get("target")))
    table.add_row("Installed", _bool_text(entry.get("installed")))
    table.add_row("Scope", str(entry.get("scope")))
    table.add_row("Path", str(entry.get("path") or "(generated only)"))
    return table


def render_install_result_rich(entry: dict[str, Any], *, heading: str):
    if Table is None or Panel is None or Group is None or Text is None:
        return render_install_result(entry, heading=heading)
    heading = _install_heading(entry, heading)
    table = _summary_table()
    table.add_row("Action", heading)
    table.add_row("Target", str(entry.get("target")))
    if entry.get("variant"):
        table.add_row("Variant", str(entry.get("variant")))
    if "scope" in entry:
        table.add_row("Scope", str(entry.get("scope")))
    if entry.get("path"):
        table.add_row("Path", str(entry.get("path")))
    if entry.get("installed") is not None:
        table.add_row("Installed", _bool_text(entry.get("installed")))
    if entry.get("removed") is not None:
        table.add_row("Removed", _bool_text(entry.get("removed")))
    renderables: list[Any] = [table]
    reason = _reason_text(entry.get("reason"))
    if reason:
        renderables.append(Panel(reason, title="Reason", border_style="yellow"))
    stdout = (entry.get("stdout") or "").strip()
    stderr = (entry.get("stderr") or "").strip()
    if stdout:
        renderables.append(Panel(stdout, title="Stdout", border_style="green"))
    if stderr:
        renderables.append(Panel(stderr, title="Stderr", border_style="yellow"))
    instructions = entry.get("instructions") or []
    if instructions:
        renderables.append(Panel(_bullet_lines(list(instructions)), title="Next steps", border_style="cyan"))
    notes = entry.get("notes") or []
    if notes:
        renderables.append(Panel(_bullet_lines(list(notes)), title="Notes", border_style="blue"))
    return Group(*renderables)


def render_setup_result_rich(payload: dict[str, Any]):
    if Table is None or Panel is None or Group is None or Text is None:
        return render_setup_result(payload)
    settings = payload.get("settings") or {}
    autodiscovered = payload.get("autodiscovered") or {}
    selected = payload.get("selected_remote_libraries") or []
    warnings = payload.get("warnings") or []
    citation_export_path = payload.get("citation_export_path") or settings.get("citation_export_path") or "not configured"
    summary = _summary_table()
    summary.add_row("Config saved", str(payload.get("config")))
    summary.add_row("Local desktop", _bool_text(bool(settings.get("data_dir"))))
    summary.add_row("Remote sync", _bool_text(bool(settings.get("api_key"))))
    summary.add_row("Default remote library", str(settings.get("default_library_id") or "none"))
    summary.add_row("Daemon address", f"{settings.get('daemon_host')}:{settings.get('daemon_port')}")
    summary.add_row("qmd collection", str(settings.get("qmd_collection")))
    summary.add_row(
        "Citations export",
        f"{_bool_text(bool(settings.get('citation_export_enabled')))} ({settings.get('citation_export_format')})",
    )
    summary.add_row("Citations path", citation_export_path)
    summary.add_row("Recovery snapshots", _bool_text(settings.get("recovery_auto_snapshots", True)))
    renderables: list[Any] = [summary]
    if autodiscovered:
        auto = _summary_table("Autodiscovered")
        for key in ("data_dir", "zotero_bin"):
            value = autodiscovered.get(key)
            if value:
                auto.add_row(_label(key), str(value))
        renderables.append(auto)
    if selected:
        renderables.append(Panel(_bullet_lines([str(library_id) for library_id in selected]), title="Configured remote libraries", border_style="cyan"))
    if warnings:
        renderables.append(Panel(_bullet_lines([str(warning) for warning in warnings]), title="Warnings", border_style="yellow"))
    return Group(*renderables)


def render_doctor_report_rich(report: dict[str, Any]):
    if Table is None or Group is None:
        return render_doctor_report(report)
    cli = report.get("cli") or {}
    settings = report.get("settings") or {}
    daemon = report.get("daemon") or {}
    setup_targets = report.get("setup_targets") or []
    skill_targets = report.get("skill_targets") or []

    cli_table = _summary_table("CLI tools")
    for key, value in cli.items():
        cli_table.add_row(_label(key), str(value or "not found"))

    settings_table = _summary_table("Settings")
    for key in ("state_dir", "headless_db", "mirror_db", "export_dir", "file_cache_dir", "recovery_snapshot_dir", "recovery_temp_dir", "data_dir", "local_db"):
        settings_table.add_row(_label(key), str(settings.get(key) or "not configured"))
    settings_table.add_row("API key configured", _bool_text(settings.get("api_key_configured")))

    daemon_table = _summary_table("Daemon")
    for key in ("available", "mode", "message", "runtime_running", "read_api_ready", "write_api_ready", "local_api_url"):
        if key in daemon:
            value = daemon.get(key)
            if isinstance(value, bool):
                value = _bool_text(value)
            daemon_table.add_row(_label(key), str(value))

    setup_table = Table(title="MCP client setup", expand=False)
    setup_table.add_column("Target", style="bold cyan")
    setup_table.add_column("Scope")
    setup_table.add_column("Installed")
    for entry in setup_targets:
        setup_table.add_row(str(entry.get("target")), str(entry.get("scope")), _bool_text(entry.get("installed")))

    skills_table = Table(title="Skill targets", expand=False)
    skills_table.add_column("Target", style="bold cyan")
    skills_table.add_column("Variants")
    for entry in skill_targets:
        skills_table.add_row(str(entry.get("target")), ", ".join(entry.get("variants") or []))

    return Group(cli_table, settings_table, daemon_table, setup_table, skills_table)
