from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .config import Settings
from .daemon import current_daemon_status
from .utils import ensure_dir


SERVER_NAME = "zotero-headless"
SUPPORTED_SETUP_TARGETS = (
    "codex",
    "claude-code",
    "claude-desktop",
    "cursor",
    "gemini",
    "cline",
    "antigravity",
    "windsurf",
    "json",
)
SUPPORTED_SKILL_TARGETS = (
    "cline",
    "antigravity",
    "openclaw",
    "codex",
    "opencode",
    "claude-code",
    "gemini-cli",
)
USER_SCOPE_ONLY_TARGETS = {"codex", "claude-desktop", "gemini", "cline", "antigravity", "windsurf"}
PROJECT_OR_USER_TARGETS = {"cursor"}
PROJECT_ONLY_TARGETS = {"claude-code"}


def _env_map(settings: Settings) -> dict[str, str]:
    env: dict[str, str] = {}
    if settings.api_key:
        env["ZOTERO_HEADLESS_API_KEY"] = settings.api_key
    if settings.data_dir:
        env["ZOTERO_HEADLESS_DATA_DIR"] = settings.data_dir
    if settings.state_dir:
        env["ZOTERO_HEADLESS_STATE_DIR"] = str(settings.resolved_state_dir())
    return env


def mcp_stdio_spec(settings: Settings) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "command": "zotero-headless-mcp",
        "args": [],
    }
    env = _env_map(settings)
    if env:
        spec["env"] = env
    return spec


def mcp_json_document(settings: Settings) -> dict[str, Any]:
    return {"mcpServers": {SERVER_NAME: mcp_stdio_spec(settings)}}


def _quote_toml(value: str) -> str:
    return json.dumps(value)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_quote_toml(value) for value in values) + "]"


def _codex_block(settings: Settings) -> str:
    spec = mcp_stdio_spec(settings)
    lines = [
        f"[mcp_servers.{SERVER_NAME}]",
        f'command = {_quote_toml(str(spec["command"]))}',
        f'args = {_toml_array([str(arg) for arg in spec.get("args") or []])}',
    ]
    env = spec.get("env") or {}
    if env:
        lines.append("")
        lines.append(f"[mcp_servers.{SERVER_NAME}.env]")
        for key in sorted(env):
            lines.append(f"{key} = {_quote_toml(str(env[key]))}")
    return "\n".join(lines) + "\n"


def _remove_codex_server_block(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    prefix = f"[mcp_servers.{SERVER_NAME}"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped.startswith(prefix):
                skipping = True
                continue
            if skipping:
                skipping = False
        if not skipping:
            kept.append(line)
    result = "\n".join(kept).strip()
    return result + ("\n" if result else "")


def _write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _merge_mcp_server(payload: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload)
    servers = dict(merged.get("mcpServers") or {})
    servers[SERVER_NAME] = spec
    merged["mcpServers"] = servers
    return merged


def _remove_mcp_server(payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload)
    servers = dict(merged.get("mcpServers") or {})
    servers.pop(SERVER_NAME, None)
    if servers:
        merged["mcpServers"] = servers
    else:
        merged.pop("mcpServers", None)
    return merged


def setup_target_path(
    target: str,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    scope: str = "project",
) -> Path | None:
    cwd = (cwd or Path.cwd()).resolve()
    home = (home or Path.home()).expanduser()
    if target in USER_SCOPE_ONLY_TARGETS and scope != "user":
        raise ValueError(f"{target} only supports --scope user")
    if target in PROJECT_ONLY_TARGETS and scope != "project":
        raise ValueError(f"{target} only supports --scope project")
    if target == "codex":
        return home / ".codex" / "config.toml"
    if target == "claude-code":
        return cwd / ".mcp.json"
    if target == "claude-desktop":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if target == "cursor":
        if scope == "user":
            return home / ".cursor" / "mcp.json"
        return cwd / ".cursor" / "mcp.json"
    if target == "gemini":
        return home / ".gemini" / "settings.json"
    if target == "cline":
        return home / ".cline" / "data" / "settings" / "cline_mcp_settings.json"
    if target == "antigravity":
        return home / ".gemini" / "antigravity" / "mcp_config.json"
    if target == "windsurf":
        return home / ".codeium" / "windsurf" / "mcp_config.json"
    if target == "json":
        return None
    raise ValueError(f"Unsupported setup target: {target}")


def install_mcp_setup(
    target: str,
    settings: Settings,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    scope: str = "project",
) -> dict[str, Any]:
    if target not in SUPPORTED_SETUP_TARGETS:
        raise ValueError(f"Unsupported setup target: {target}")
    spec = mcp_stdio_spec(settings)
    if target == "json":
        return {
            "target": target,
            "written": False,
            "path": None,
            "config": mcp_json_document(settings),
        }
    path = setup_target_path(target, cwd=cwd, home=home, scope=scope)
    assert path is not None
    if target == "codex":
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        cleaned = _remove_codex_server_block(existing).rstrip()
        block = _codex_block(settings).strip()
        content = (cleaned + "\n\n" + block).strip() + "\n"
        _write_text(path, content)
    elif target in {"claude-code", "claude-desktop", "cursor", "gemini", "cline", "antigravity", "windsurf"}:
        payload = _read_json_file(path)
        payload = _merge_mcp_server(payload, spec)
        _write_json_file(path, payload)
    return {
        "target": target,
        "written": True,
        "path": str(path),
        "config": spec if target != "codex" else {"toml_server": SERVER_NAME},
        "scope": scope,
    }


def remove_mcp_setup(
    target: str,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    scope: str = "project",
) -> dict[str, Any]:
    if target not in SUPPORTED_SETUP_TARGETS or target == "json":
        raise ValueError(f"Unsupported removable setup target: {target}")
    path = setup_target_path(target, cwd=cwd, home=home, scope=scope)
    assert path is not None
    if not path.exists():
        return {"target": target, "removed": False, "path": str(path), "reason": "config_not_found"}
    if target == "codex":
        cleaned = _remove_codex_server_block(path.read_text(encoding="utf-8"))
        _write_text(path, cleaned)
    else:
        payload = _remove_mcp_server(_read_json_file(path))
        _write_json_file(path, payload)
    return {"target": target, "removed": True, "path": str(path), "scope": scope}


def inspect_setup_target(
    target: str,
    settings: Settings,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    scope: str = "project",
) -> dict[str, Any]:
    path = setup_target_path(target, cwd=cwd, home=home, scope=scope)
    installed = False
    if path and path.exists():
        if target == "codex":
            installed = f"[mcp_servers.{SERVER_NAME}]" in path.read_text(encoding="utf-8")
        else:
            payload = _read_json_file(path)
            installed = SERVER_NAME in (payload.get("mcpServers") or {})
    return {
        "target": target,
        "path": str(path) if path else None,
        "installed": installed,
        "scope": scope,
        "config": mcp_json_document(settings) if target == "json" else mcp_stdio_spec(settings),
    }


def setup_list(settings: Settings, *, cwd: Path | None = None, home: Path | None = None) -> list[dict[str, Any]]:
    entries = [
        inspect_setup_target("codex", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("claude-code", settings, cwd=cwd, home=home, scope="project"),
        inspect_setup_target("claude-desktop", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("cursor", settings, cwd=cwd, home=home, scope="project"),
        inspect_setup_target("cursor", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("gemini", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("cline", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("antigravity", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("windsurf", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("json", settings, cwd=cwd, home=home, scope="project"),
    ]
    return entries


def skill_text(target: str) -> str:
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    return """# Zotero Headless

Use this when working with a `zotero-headless` CLI, API, or MCP runtime.

Priorities:
- Prefer the canonical headless store and daemon runtime over direct file/database assumptions.
- Use sync conflict tools before retrying remote mutations blindly.
- For local desktop workflows, distinguish canonical state from the Zotero desktop database and use the local adapter/apply flow.
- For search/RAG tasks, prefer qmd export/query flows over ad hoc filesystem scans.

High-value commands:
- `zotero-headless capabilities`
- `zotero-headless daemon status`
- `zotero-headless sync canonical-discover`
- `zotero-headless sync canonical-pull --library <library_id>`
- `zotero-headless sync canonical-push --library <library_id>`
- `zotero-headless sync conflicts --library <library_id>`

When the daemon is running, useful runtime endpoints are:
- `/daemon/status`
- `/daemon/runtime`
- `/daemon/jobs`
- `/metrics`
"""


def skill_target_path(target: str, *, home: Path | None = None) -> Path:
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    home = (home or Path.home()).expanduser()
    if target == "codex":
        return home / ".codex" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "claude-code":
        return home / ".claude" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "gemini-cli":
        return home / ".gemini" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "cline":
        return home / ".cline" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "antigravity":
        return home / ".gemini" / "antigravity" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "openclaw":
        return home / ".moltbot" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "opencode":
        return home / ".config" / "opencode" / "skill" / SERVER_NAME / "SKILL.md"
    raise ValueError(f"Unsupported skill target: {target}")


def install_skill(
    target: str,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    path = skill_target_path(target, home=home)
    _write_text(path, skill_text(target))
    return {"target": target, "installed": True, "path": str(path)}


def export_skill(target: str) -> dict[str, Any]:
    return {"target": target, "content": skill_text(target)}


def doctor_report(
    settings: Settings,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    daemon = current_daemon_status(settings)
    return {
        "cli": {
            "zotero_headless": shutil.which("zotero-headless"),
            "zotero_headless_mcp": shutil.which("zotero-headless-mcp"),
            "zotero_headlessd": shutil.which("zotero-headlessd"),
            "qmd": shutil.which("qmd"),
        },
        "settings": {
            "state_dir": str(settings.resolved_state_dir()),
            "canonical_db": str(settings.resolved_canonical_db()),
            "mirror_db": str(settings.resolved_mirror_db()),
            "file_cache_dir": str(settings.resolved_file_cache_dir()),
            "export_dir": str(settings.resolved_export_dir()),
            "data_dir": settings.data_dir,
            "local_db": str(settings.resolved_local_db()) if settings.resolved_local_db() else None,
            "api_key_configured": bool(settings.api_key),
        },
        "daemon": daemon.to_dict(),
        "setup_targets": setup_list(settings, cwd=cwd, home=home),
        "skill_targets": [{"target": target, "install_supported": True} for target in SUPPORTED_SKILL_TARGETS],
    }
