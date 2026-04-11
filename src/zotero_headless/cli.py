from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click
import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

from .agent_setup import (
    SUPPORTED_PLUGIN_TARGETS,
    SUPPORTED_SETUP_TARGETS,
    SUPPORTED_SKILL_TARGETS,
    SUPPORTED_SKILL_VARIANTS,
    doctor_report,
    export_skill,
    install_plugin_set,
    inspect_setup_target,
    install_mcp_setup,
    install_skill_set,
    normalize_target_name,
    refresh_installed_integrations,
    remove_mcp_setup,
    setup_list,
)
from .api import serve_api
from .adapters.local_desktop import LocalDesktopAdapter
from .adapters.web_sync import CanonicalWebSyncAdapter
from .capabilities import get_capabilities
from .citations import CitationExportClient
from .cli_ui import (
    render_config_payload,
    render_daemon_command,
    render_daemon_status,
    render_doctor_report,
    render_doctor_report_rich,
    render_install_result,
    render_install_result_rich,
    render_text_list,
    render_setup_result,
    render_setup_result_rich,
    render_setup_target,
    render_setup_target_rich,
    render_update_plan,
    render_update_plan_rich,
    render_update_result,
    render_update_result_rich,
    render_version_payload,
    render_version_payload_rich,
)
from .config import Settings, load_settings, save_settings
from .core import CanonicalStore, EntityType
from .daemon import build_daemon_command, build_runtime_command, current_daemon_status, serve_daemon_runtime
from .installer_update import build_update_plan, run_update, version_payload
from .installer_update import current_version
from .local_db import LocalZoteroDB
from .mcp import run_stdio_server
from .qmd import QmdAutoIndexer, QmdClient
from .recovery import RecoveryService
from .raw_cli import build_parser as build_parser
from .raw_cli import main as raw_main
from .service import HeadlessService
from .setup_wizard import run_setup_wizard
from .store import MirrorStore
from .sync import SyncService
from .web_api import ZoteroWebClient


app = typer.Typer(
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="Human-friendly zotero-headless CLI. Use [bold]zhl raw ...[/bold] for strict machine-oriented commands.",
)
setup_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Interactive setup and MCP client installation.")
skill_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Install or export agent skills.")
plugin_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Install local plugin bundles.")
daemon_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Inspect or run the daemon runtime.")
sync_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Human-friendly remote sync commands.")
local_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Human-friendly local desktop interoperability commands.")
citations_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Manage the auto-generated citations database export.")
recovery_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich", help="Snapshot, verify, restore, and replicate full headless recovery state.")
app.add_typer(setup_app, name="setup")
app.add_typer(skill_app, name="skill")
app.add_typer(plugin_app, name="plugin")
app.add_typer(daemon_app, name="daemon")
app.add_typer(sync_app, name="sync")
app.add_typer(local_app, name="local")
app.add_typer(citations_app, name="citations")
app.add_typer(recovery_app, name="recovery")

console = Console()


class CliState:
    def __init__(self) -> None:
        self.json_output = False


def _state(ctx: typer.Context) -> CliState:
    if ctx.obj is None:
        ctx.obj = CliState()
    return ctx.obj


def _emit(ctx: typer.Context, payload, *, renderer=None, title: str | None = None) -> None:
    if _state(ctx).json_output:
        # Bypass Rich for JSON output so consumers get clean, parseable output
        # regardless of terminal width, styling, or redirected stdout.
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        sys.stdout.flush()
        return
    if renderer is None:
        console.print(Pretty(payload))
        return
    content = renderer(payload)
    if title:
        if isinstance(content, str):
            console.print(Panel.fit(content, title=title))
        else:
            console.print(Panel(content, title=title))
    else:
        console.print(content)


def _render_install_results(entries: list[dict[str, object]], *, heading: str) -> str:
    renderables = [render_install_result_rich(entry, heading=heading) for entry in entries]
    return Group(*renderables)


def _human_settings(*, ensure_dirs: bool = True) -> Settings:
    return load_settings(ensure_dirs=ensure_dirs)


def _setup_payload(config_path: Path, settings: Settings, *, autodiscovered=None, discovered_libraries=None, selected_remote_libraries=None) -> dict[str, object]:
    warnings: list[str] = []
    if shutil.which("qmd") is None:
        warnings.append("qmd is not installed. qmd-backed search and indexing stay unavailable until you install `qmd`.")
    return {
        "config": str(config_path),
        "autodiscovered": autodiscovered or {},
        "settings": settings.as_dict(),
        "citation_export_path": str(settings.resolved_citation_export_path()),
        "discovered_libraries": discovered_libraries or [],
        "selected_remote_libraries": selected_remote_libraries or [],
        "warnings": warnings,
    }


def _runtime_services(settings: Settings):
    canonical = CanonicalStore(settings.resolved_canonical_db())
    store = MirrorStore(settings.resolved_mirror_db())
    qmd_indexer = QmdAutoIndexer(settings)
    sync_service = SyncService(settings, store, qmd_indexer=qmd_indexer)
    service = HeadlessService(settings, store, canonical, qmd_indexer=qmd_indexer)
    local_adapter = LocalDesktopAdapter(canonical, qmd_indexer=qmd_indexer, settings=settings)
    return canonical, store, qmd_indexer, sync_service, service, local_adapter


def _recovery_service(settings: Settings) -> RecoveryService:
    canonical, _, qmd_indexer, _, _, _ = _runtime_services(settings)
    return RecoveryService(settings, canonical=canonical, qmd_indexer=qmd_indexer)


def _library_table(entries: list[dict[str, object]]) -> Table:
    table = Table(title="MCP client setup targets")
    table.add_column("Target")
    table.add_column("Scope")
    table.add_column("Installed")
    table.add_column("Path")
    for entry in entries:
        table.add_row(
            str(entry.get("target")),
            str(entry.get("scope")),
            "yes" if entry.get("installed") else "no",
            str(entry.get("path") or "(generated only)"),
        )
    return table


def _sync_summary(title: str, payload: dict[str, object]) -> Panel:
    rows = []
    for key, value in payload.items():
        rows.append(f"{key}: {value}")
    return Panel.fit("\n".join(rows), title=title)


@app.callback()
def main_callback(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output instead of human-friendly formatting."),
) -> None:
    _state(ctx).json_output = json_output


@app.command("version")
def version_command(ctx: typer.Context) -> None:
    _emit(ctx, version_payload(), renderer=render_version_payload_rich, title="Version")


@app.command("update")
def update_command(
    ctx: typer.Context,
    check: bool = typer.Option(False, "--check", help="Only show the detected update plan."),
) -> None:
    plan = build_update_plan()
    if check:
        _emit(ctx, {"plan": plan.to_dict(), "current_version": current_version()}, renderer=render_update_plan_rich, title="Update")
        return
    if _state(ctx).json_output:
        payload = run_update(plan)
        if payload.get("updated"):
            payload["post_update"] = refresh_installed_integrations(_human_settings(ensure_dirs=False), cwd=Path.cwd())
        _emit(ctx, payload, renderer=render_update_result, title="Update")
        return

    before_version = current_version()
    console.print(f"Current version: [bold]{before_version}[/bold]")
    if not plan.auto_supported or not plan.command:
        _emit(ctx, {"plan": plan.to_dict(), "current_version": before_version}, renderer=render_update_plan, title="Update")
        return

    with console.status(f"Updating zotero-headless via {plan.method}...", spinner="dots"):
        payload = run_update(plan)
    if payload.get("updated"):
        with console.status("Refreshing installed integrations...", spinner="dots"):
            payload["post_update"] = refresh_installed_integrations(_human_settings(ensure_dirs=False), cwd=Path.cwd())
    _emit(ctx, payload, renderer=render_update_result_rich, title="Update")


@app.command("doctor")
def doctor_command(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    _emit(ctx, doctor_report(settings, cwd=Path.cwd()), renderer=render_doctor_report_rich, title="Doctor")


@app.command("capabilities")
def capabilities_command(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    payload = get_capabilities(settings)
    if _state(ctx).json_output:
        _emit(ctx, payload)
        return
    console.print(Panel.fit(render_config_payload(payload), title="Capabilities"))


@app.command("search")
def search_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Exploratory natural-language query for qmd semantic search."),
    library: str | None = typer.Option(None, "--library", help="Limit the search to one library."),
    limit: int = typer.Option(10, "-n", "--limit", help="Maximum number of results."),
) -> None:
    settings = _human_settings()
    client = QmdClient(settings)
    payload = client.search("query", query, limit=limit, library_id=library)
    _emit(ctx, payload, title="Search results")


@setup_app.command("start")
def setup_start(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    result = run_setup_wizard(settings, mode="full")
    path = save_settings(result.settings)
    _emit(
        ctx,
        _setup_payload(
            path,
            result.settings,
            autodiscovered=result.autodiscovered,
            discovered_libraries=result.discovered_libraries,
            selected_remote_libraries=result.selected_library_ids,
        ),
        renderer=render_setup_result_rich,
        title="Setup",
    )


@setup_app.command("account")
def setup_account(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    result = run_setup_wizard(settings, mode="account")
    path = save_settings(result.settings)
    _emit(
        ctx,
        _setup_payload(
            path,
            result.settings,
            autodiscovered=result.autodiscovered,
            discovered_libraries=result.discovered_libraries,
            selected_remote_libraries=result.selected_library_ids,
        ),
        renderer=render_setup_result_rich,
        title="Setup account",
    )


@setup_app.command("libraries")
def setup_libraries(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    result = run_setup_wizard(settings, mode="libraries")
    path = save_settings(result.settings)
    _emit(
        ctx,
        _setup_payload(
            path,
            result.settings,
            autodiscovered=result.autodiscovered,
            discovered_libraries=result.discovered_libraries,
            selected_remote_libraries=result.selected_library_ids,
        ),
        renderer=render_setup_result_rich,
        title="Setup libraries",
    )


@setup_app.command("local")
def setup_local(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    result = run_setup_wizard(settings, mode="local")
    path = save_settings(result.settings)
    _emit(
        ctx,
        _setup_payload(
            path,
            result.settings,
            autodiscovered=result.autodiscovered,
            discovered_libraries=result.discovered_libraries,
            selected_remote_libraries=result.selected_library_ids,
        ),
        renderer=render_setup_result_rich,
        title="Setup local",
    )


@setup_app.command("list")
def setup_list_command(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    entries = setup_list(settings, cwd=Path.cwd())
    if _state(ctx).json_output:
        _emit(ctx, {"targets": entries})
        return
    console.print(_library_table(entries))


@setup_app.command("show")
def setup_show_command(
    ctx: typer.Context,
    tool: str = typer.Argument(..., help="Target client to inspect."),
    scope: str = typer.Option("project", "--scope", help="Setup scope."),
) -> None:
    payload = inspect_setup_target(tool, _human_settings(ensure_dirs=False), cwd=Path.cwd(), scope=scope)
    _emit(ctx, payload, renderer=render_setup_target_rich, title="Setup target")


@setup_app.command("add")
def setup_add_command(
    ctx: typer.Context,
    tool: str = typer.Argument(..., help="Target client to configure."),
    scope: str = typer.Option("project", "--scope", help="Setup scope."),
) -> None:
    payload = install_mcp_setup(tool, _human_settings(ensure_dirs=False), cwd=Path.cwd(), scope=scope)
    _emit(ctx, payload, renderer=lambda entry: render_install_result_rich(entry, heading="Setup applied"), title="Setup")


@setup_app.command("remove")
def setup_remove_command(
    ctx: typer.Context,
    tool: str = typer.Argument(..., help="Target client to remove."),
    scope: str = typer.Option("project", "--scope", help="Setup scope."),
) -> None:
    payload = remove_mcp_setup(tool, cwd=Path.cwd(), scope=scope)
    _emit(ctx, payload, renderer=lambda entry: render_install_result_rich(entry, heading="Setup removed"), title="Setup")


@skill_app.command("install")
@skill_app.command("add")
@skill_app.command("update")
def skill_install_command(
    ctx: typer.Context,
    tool: str = typer.Argument(..., help="Skill target client."),
    variant: str = typer.Option("general", "--variant", help="Skill variant."),
) -> None:
    tool = normalize_target_name(tool)
    if tool != "all" and tool not in SUPPORTED_SKILL_TARGETS:
        raise typer.BadParameter(f"Unsupported skill target: {tool}")
    payload = install_skill_set(tool, variant=variant)
    if tool == "all":
        _emit(ctx, payload, renderer=lambda entries: _render_install_results(entries, heading="Skill installed"), title="Skill")
        return
    _emit(ctx, payload[0], renderer=lambda entry: render_install_result_rich(entry, heading="Skill installed"), title="Skill")


@skill_app.command("export")
def skill_export_command(
    ctx: typer.Context,
    tool: str = typer.Argument(..., help="Skill target client."),
    variant: str = typer.Option("general", "--variant", help="Skill variant."),
) -> None:
    tool = normalize_target_name(tool)
    payload = export_skill(tool, variant=variant)
    _emit(ctx, payload, title="Skill export")


def _run_plugin_command(ctx: typer.Context, tool: str, *, heading: str) -> None:
    tool = normalize_target_name(tool)
    if tool != "all" and tool not in SUPPORTED_PLUGIN_TARGETS:
        raise typer.BadParameter(f"Unsupported plugin target: {tool}")
    payload = install_plugin_set(tool, _human_settings(ensure_dirs=False), cwd=Path.cwd())
    if tool == "all":
        _emit(ctx, payload, renderer=lambda entries: _render_install_results(entries, heading=heading), title="Plugin")
        return
    _emit(ctx, payload[0], renderer=lambda entry: render_install_result_rich(entry, heading=heading), title="Plugin")


@plugin_app.command("install")
def plugin_install_command(
    ctx: typer.Context,
    tool: str = typer.Argument(..., help="Plugin target client."),
) -> None:
    _run_plugin_command(ctx, tool, heading="Plugin installed")


@plugin_app.command("update")
def plugin_update_command(
    ctx: typer.Context,
    tool: str = typer.Argument(..., help="Plugin target client."),
) -> None:
    _run_plugin_command(ctx, tool, heading="Plugin updated")


@daemon_app.command("status")
def daemon_status_command(ctx: typer.Context) -> None:
    payload = current_daemon_status(_human_settings(ensure_dirs=False)).to_dict()
    _emit(ctx, payload, renderer=render_daemon_status, title="Daemon status")


@daemon_app.command("command")
def daemon_command_command(ctx: typer.Context) -> None:
    settings = _human_settings(ensure_dirs=False)
    payload = {
        "runtime_argv": build_runtime_command(settings),
        "desktop_helper_argv": build_daemon_command(settings),
        "local_api_url": f"http://{settings.daemon_host}:{settings.daemon_port}/api/",
    }
    _emit(ctx, payload, renderer=render_daemon_command, title="Daemon command")


@daemon_app.command("serve")
def daemon_serve_command(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
    sync_interval: int = typer.Option(0, "--sync-interval"),
) -> None:
    settings = _human_settings()
    serve_daemon_runtime(settings, host=host, port=port, sync_interval_seconds=sync_interval)


@sync_app.command("discover")
def sync_discover_command(ctx: typer.Context) -> None:
    settings = _human_settings()
    canonical, _, qmd_indexer, _, _, _ = _runtime_services(settings)
    payload = CanonicalWebSyncAdapter(canonical, ZoteroWebClient(settings), qmd_indexer=qmd_indexer).discover_libraries()
    _emit(ctx, payload, title="Sync discover")


@sync_app.command("pull")
def sync_pull_command(
    ctx: typer.Context,
    library: str = typer.Option(..., "--library", help="Remote library ID."),
) -> None:
    settings = _human_settings()
    canonical, _, qmd_indexer, _, _, _ = _runtime_services(settings)
    payload = CanonicalWebSyncAdapter(canonical, ZoteroWebClient(settings), qmd_indexer=qmd_indexer).pull_library(library)
    _emit(ctx, payload, title="Sync pull")


@sync_app.command("push")
def sync_push_command(
    ctx: typer.Context,
    library: str = typer.Option(..., "--library", help="Remote library ID."),
) -> None:
    settings = _human_settings()
    canonical, _, qmd_indexer, _, _, _ = _runtime_services(settings)
    payload = CanonicalWebSyncAdapter(canonical, ZoteroWebClient(settings), qmd_indexer=qmd_indexer).push_changes(library)
    _emit(ctx, payload, title="Sync push")


@sync_app.command("conflicts")
def sync_conflicts_command(
    ctx: typer.Context,
    library: str = typer.Option(..., "--library", help="Remote library ID."),
    entity_type: str | None = typer.Option(None, "--entity-type", help="Optional entity type filter."),
) -> None:
    settings = _human_settings()
    canonical, _, qmd_indexer, _, _, _ = _runtime_services(settings)
    payload = CanonicalWebSyncAdapter(canonical, ZoteroWebClient(settings), qmd_indexer=qmd_indexer).list_conflicts(
        library,
        entity_type=EntityType(entity_type) if entity_type else None,
    )
    _emit(ctx, payload, title="Sync conflicts")


@local_app.command("import")
def local_import_command(ctx: typer.Context) -> None:
    settings = _human_settings()
    if not settings.data_dir:
        raise typer.BadParameter("Local Zotero data directory is not configured. Run `zhl setup local` first.")
    _, _, _, _, _, local_adapter = _runtime_services(settings)
    payload = local_adapter.import_snapshot(settings.data_dir)
    _emit(ctx, payload, title="Local import")


@local_app.command("plan-apply")
def local_plan_apply_command(
    ctx: typer.Context,
    library: str | None = typer.Option(None, "--library"),
    limit: int = typer.Option(1000, "--limit"),
) -> None:
    settings = _human_settings()
    if not settings.data_dir:
        raise typer.BadParameter("Local Zotero data directory is not configured. Run `zhl setup local` first.")
    _, _, _, _, _, local_adapter = _runtime_services(settings)
    payload = local_adapter.plan_pending_writes(settings.data_dir, library_id=library, limit=limit)
    _emit(ctx, payload, title="Local plan apply")


@local_app.command("apply")
def local_apply_command(
    ctx: typer.Context,
    library: str | None = typer.Option(None, "--library"),
    limit: int = typer.Option(1000, "--limit"),
) -> None:
    settings = _human_settings()
    if not settings.data_dir:
        raise typer.BadParameter("Local Zotero data directory is not configured. Run `zhl setup local` first.")
    _, _, _, _, _, local_adapter = _runtime_services(settings)
    payload = local_adapter.apply_pending_writes(settings.data_dir, library_id=library, limit=limit)
    _emit(ctx, payload, title="Local apply")


@citations_app.command("status")
def citations_status_command(ctx: typer.Context) -> None:
    payload = CitationExportClient(_human_settings()).status()
    _emit(ctx, payload, renderer=render_config_payload, title="Citations")


@citations_app.command("showpath")
def citations_showpath_command(ctx: typer.Context) -> None:
    settings = _human_settings()
    payload = {
        "path": str(settings.resolved_citation_export_path()),
        "format": settings.citation_export_format,
        "enabled": bool(settings.citation_export_enabled),
    }
    _emit(ctx, payload, renderer=render_config_payload, title="Citations path")


@citations_app.command("enable")
def citations_enable_command(
    ctx: typer.Context,
    format: str | None = typer.Option(None, "--format", help="Citation database format."),
    path: str | None = typer.Option(None, "--path", help="Output path for the citations database."),
) -> None:
    settings = _human_settings()
    settings.citation_export_enabled = True
    if format:
        settings.citation_export_format = format
    if path is not None:
        settings.citation_export_path = path
    save_settings(settings)
    canonical, _, _, _, _, _ = _runtime_services(settings)
    client = CitationExportClient(settings)
    payload = {
        "settings": settings.as_dict(),
        "status": client.status(),
        "export": client.export_from_canonical(canonical),
    }
    _emit(ctx, payload, renderer=render_config_payload, title="Citations")


@citations_app.command("disable")
def citations_disable_command(ctx: typer.Context) -> None:
    settings = _human_settings()
    settings.citation_export_enabled = False
    save_settings(settings)
    payload = {
        "settings": settings.as_dict(),
        "status": CitationExportClient(settings).status(),
    }
    _emit(ctx, payload, renderer=render_config_payload, title="Citations")


@citations_app.command("export")
def citations_export_command(
    ctx: typer.Context,
    library: str | None = typer.Option(None, "--library", help="Optional library scope."),
    format: str | None = typer.Option(None, "--format", help="Override citation database format."),
    path: str | None = typer.Option(None, "--path", help="Override output path."),
) -> None:
    settings = _human_settings()
    canonical, _, _, _, _, _ = _runtime_services(settings)
    payload = CitationExportClient(settings).export_from_canonical(
        canonical,
        library,
        format_name=format,
        output_path=path,
    )
    _emit(ctx, payload, renderer=render_config_payload, title="Citations")


@recovery_app.command("repositories")
def recovery_repositories_command(ctx: typer.Context) -> None:
    _emit(ctx, _recovery_service(_human_settings()).repositories(), title="Recovery repositories")


@recovery_app.command("snapshot-create")
def recovery_snapshot_create_command(
    ctx: typer.Context,
    reason: str = typer.Option("manual", "--reason"),
) -> None:
    _emit(ctx, _recovery_service(_human_settings()).create_snapshot(reason=reason), title="Recovery snapshot")


@recovery_app.command("snapshot-list")
def recovery_snapshot_list_command(
    ctx: typer.Context,
    limit: int = typer.Option(20, "-n", "--limit"),
) -> None:
    _emit(ctx, _recovery_service(_human_settings()).list_snapshots(limit=limit), title="Recovery snapshots")


@recovery_app.command("snapshot-show")
def recovery_snapshot_show_command(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(...),
) -> None:
    _emit(ctx, _recovery_service(_human_settings()).get_snapshot(snapshot_id), title="Recovery snapshot")


@recovery_app.command("snapshot-verify")
def recovery_snapshot_verify_command(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(...),
) -> None:
    _emit(ctx, _recovery_service(_human_settings()).verify_snapshot(snapshot_id), title="Recovery verify")


@recovery_app.command("snapshot-push")
def recovery_snapshot_push_command(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(...),
    repository: str = typer.Option(..., "--repository"),
) -> None:
    _emit(
        ctx,
        _recovery_service(_human_settings()).push_snapshot(snapshot_id, repository=repository),
        title="Recovery push",
    )


@recovery_app.command("snapshot-pull")
def recovery_snapshot_pull_command(
    ctx: typer.Context,
    snapshot_id: str = typer.Argument(...),
    repository: str = typer.Option(..., "--repository"),
) -> None:
    _emit(
        ctx,
        _recovery_service(_human_settings()).pull_snapshot(snapshot_id, repository=repository),
        title="Recovery pull",
    )


@recovery_app.command("restore-plan")
def recovery_restore_plan_command(
    ctx: typer.Context,
    snapshot_id: str = typer.Option(..., "--snapshot"),
    library: str | None = typer.Option(None, "--library"),
) -> None:
    _emit(
        ctx,
        _recovery_service(_human_settings()).plan_restore(snapshot_id=snapshot_id, library_id=library),
        title="Recovery restore plan",
    )


@recovery_app.command("restore-list")
def recovery_restore_list_command(
    ctx: typer.Context,
    limit: int = typer.Option(20, "-n", "--limit"),
) -> None:
    _emit(ctx, _recovery_service(_human_settings()).list_restore_runs(limit=limit), title="Recovery restores")


@recovery_app.command("restore-show")
def recovery_restore_show_command(
    ctx: typer.Context,
    run_id: str = typer.Argument(...),
) -> None:
    _emit(ctx, _recovery_service(_human_settings()).get_restore_run(run_id), title="Recovery restore")


@recovery_app.command("restore-execute")
def recovery_restore_execute_command(
    ctx: typer.Context,
    snapshot_id: str = typer.Option(..., "--snapshot"),
    library: str | None = typer.Option(None, "--library"),
    push_remote: bool = typer.Option(False, "--push-remote"),
    apply_local: bool = typer.Option(False, "--apply-local"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    _emit(
        ctx,
        _recovery_service(_human_settings()).execute_restore(
            snapshot_id=snapshot_id,
            library_id=library,
            push_remote=push_remote,
            apply_local=apply_local,
            confirm=confirm,
        ),
        title="Recovery restore",
    )


@app.command(
    "raw",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=False,
    help="Pass through to the strict machine-oriented CLI.",
)
def raw_command(ctx: typer.Context) -> None:
    raise typer.Exit(raw_main(ctx.args))


@app.command("api")
def api_command(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
) -> None:
    if ctx.args and ctx.args[0] != "serve":
        raise typer.BadParameter("The human API command only supports `zhl api --host ... --port ...`. Use `zhl raw api ...` for strict subcommands.")
    serve_api(_human_settings(), host, port)


@app.command("mcp")
def mcp_command() -> None:
    run_stdio_server(_human_settings())


def main(argv: list[str] | None = None) -> int:
    prog_name = Path(sys.argv[0]).name if not argv else "zotero-headless"
    try:
        app(standalone_mode=False, prog_name=prog_name, args=argv)
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except click.Abort:
        console.print("[red]Aborted.[/red]")
        return 1
    except SystemExit as exc:  # pragma: no cover - defensive path around click/typer exits
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
