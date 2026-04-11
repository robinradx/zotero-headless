from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from .config import Settings
from .daemon import current_daemon_status
from .utils import ensure_dir


SERVER_NAME = "zotero-headless"
OPENCLAW_PLUGIN_ID = "zotero"
OPENCLAW_PLUGIN_DIRNAME = "openclaw-plugin-zotero"
CODEX_PLUGIN_NAME = "zotero-headless-codex"
CLAUDE_CODE_PLUGIN_NAME = "zotero-headless-claude-code"
SUPPORTED_SETUP_TARGETS = (
    "codex",
    "claude-code",
    "claude-desktop",
    "cursor",
    "gemini",
    "cline",
    "antigravity",
    "openclaw",
    "windsurf",
    "json",
)
SUPPORTED_PLUGIN_TARGETS = ("codex", "claude-code", "openclaw")
SUPPORTED_SKILL_TARGETS = (
    "cline",
    "antigravity",
    "openclaw",
    "codex",
    "opencode",
    "claude-code",
    "claude-desktop",
    "gemini-cli",
)
BULK_PLUGIN_TARGETS = SUPPORTED_PLUGIN_TARGETS
BULK_SKILL_TARGETS = tuple(target for target in SUPPORTED_SKILL_TARGETS if target != "claude-desktop")
SUPPORTED_SKILL_VARIANTS = ("general", "daemon")
USER_SCOPE_ONLY_TARGETS = {"codex", "claude-desktop", "gemini", "cline", "antigravity", "openclaw", "windsurf"}
PROJECT_OR_USER_TARGETS = {"cursor"}
PROJECT_ONLY_TARGETS = {"claude-code"}
TARGET_ALIASES = {
    "open-claw": "openclaw",
}


def normalize_target_name(target: str) -> str:
    return TARGET_ALIASES.get(target, target)


def _packaged_plugin_root() -> Path:
    return Path(__file__).resolve().parent / "packaged_plugins"


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


def _openclaw_binary() -> str | None:
    return shutil.which("openclaw")


def _openclaw_plugin_candidates(*, cwd: Path | None = None) -> list[Path]:
    base = (cwd or Path.cwd()).resolve()
    candidates = [
        base / "plugins" / OPENCLAW_PLUGIN_DIRNAME,
        base / "openclaw-plugin-zotero",
        base / OPENCLAW_PLUGIN_DIRNAME,
        _packaged_plugin_root() / OPENCLAW_PLUGIN_DIRNAME,
    ]
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _openclaw_plugin_path(*, cwd: Path | None = None) -> Path:
    for candidate in _openclaw_plugin_candidates(cwd=cwd):
        if candidate.exists():
            return candidate
    return _openclaw_plugin_candidates(cwd=cwd)[0]


def _openclaw_setup_instructions(*, cwd: Path | None = None) -> list[str]:
    plugin_path = _openclaw_plugin_path(cwd=cwd)
    return [
        f"Run `openclaw plugins install -l {plugin_path}` to link the local Zotero plugin into OpenClaw.",
        f"Run `openclaw plugins enable {OPENCLAW_PLUGIN_ID}` to enable it.",
        "Edit `~/.openclaw/openclaw.json` if you need to adjust daemon host, port, or per-library permissions.",
    ]


def _install_openclaw_plugin(
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    scope: str = "user",
) -> dict[str, Any]:
    plugin_path = _openclaw_plugin_path(cwd=cwd)
    config_path = setup_target_path("openclaw", cwd=cwd, home=home, scope=scope)
    assert config_path is not None
    binary = _openclaw_binary()
    if not plugin_path.exists():
        return {
            "target": "openclaw",
            "written": False,
            "installed": False,
            "path": str(config_path),
            "scope": scope,
            "reason": "plugin_not_found",
            "instructions": _openclaw_setup_instructions(cwd=cwd),
        }
    if not binary:
        return {
            "target": "openclaw",
            "written": False,
            "installed": False,
            "path": str(config_path),
            "scope": scope,
            "reason": "openclaw_not_found",
            "instructions": _openclaw_setup_instructions(cwd=cwd),
        }
    install = subprocess.run(
        [binary, "plugins", "install", "-l", str(plugin_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        return {
            "target": "openclaw",
            "written": False,
            "installed": False,
            "path": str(config_path),
            "scope": scope,
            "reason": "openclaw_install_failed",
            "stdout": install.stdout,
            "stderr": install.stderr,
            "instructions": _openclaw_setup_instructions(cwd=cwd),
        }
    enable = subprocess.run(
        [binary, "plugins", "enable", OPENCLAW_PLUGIN_ID],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "target": "openclaw",
        "written": enable.returncode == 0,
        "installed": enable.returncode == 0,
        "path": str(config_path),
        "scope": scope,
        "config": {
            "plugin_id": OPENCLAW_PLUGIN_ID,
            "plugin_path": str(plugin_path),
        },
        "stdout": "\n".join(part for part in (install.stdout.strip(), enable.stdout.strip()) if part),
        "stderr": "\n".join(part for part in (install.stderr.strip(), enable.stderr.strip()) if part),
        "notes": [
            f"Already ran `openclaw plugins install -l {plugin_path}`.",
            f"Already ran `openclaw plugins enable {OPENCLAW_PLUGIN_ID}`.",
            f"Inspect the plugin with `openclaw plugins inspect {OPENCLAW_PLUGIN_ID}` if you want to verify the active config.",
            "Install the matching skill with `zhl skill install openclaw` for better agent routing.",
        ],
    }


def _codex_plugin_source_path(*, cwd: Path | None = None) -> Path:
    base = (cwd or Path.cwd()).resolve()
    repo_path = (base / "plugins" / CODEX_PLUGIN_NAME).resolve()
    if repo_path.exists():
        return repo_path
    return (_packaged_plugin_root() / CODEX_PLUGIN_NAME).resolve()


def _codex_plugin_install_path(*, home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    return root / "plugins" / CODEX_PLUGIN_NAME


def _claude_code_plugin_source_path(*, cwd: Path | None = None) -> Path:
    base = (cwd or Path.cwd()).resolve()
    repo_path = (base / "plugins" / CLAUDE_CODE_PLUGIN_NAME).resolve()
    if repo_path.exists():
        return repo_path
    return (_packaged_plugin_root() / CLAUDE_CODE_PLUGIN_NAME).resolve()


def _claude_code_plugin_install_path(*, home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    return root / ".claude" / "plugins" / CLAUDE_CODE_PLUGIN_NAME


def _codex_plugin_marketplace_path(*, home: Path | None = None) -> Path:
    root = (home or Path.home()).expanduser()
    return root / ".agents" / "plugins" / "marketplace.json"


def _codex_marketplace_entry() -> dict[str, Any]:
    return {
        "name": CODEX_PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": f"./plugins/{CODEX_PLUGIN_NAME}",
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Research",
    }


def _update_codex_marketplace(*, home: Path | None = None) -> Path:
    path = _codex_plugin_marketplace_path(home=home)
    payload = _read_json_file(path) if path.exists() else {}
    if not payload:
        payload = {
            "name": "local-plugins",
            "interface": {
                "displayName": "Local Plugins",
            },
            "plugins": [],
        }
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        plugins = []
    entry = _codex_marketplace_entry()
    replaced = False
    for index, existing in enumerate(plugins):
        if isinstance(existing, dict) and existing.get("name") == CODEX_PLUGIN_NAME:
            plugins[index] = entry
            replaced = True
            break
    if not replaced:
        plugins.append(entry)
    payload["plugins"] = plugins
    interface = payload.get("interface")
    if not isinstance(interface, dict):
        payload["interface"] = {"displayName": "Local Plugins"}
    elif not interface.get("displayName"):
        interface["displayName"] = "Local Plugins"
    if not payload.get("name"):
        payload["name"] = "local-plugins"
    _write_json_file(path, payload)
    return path


def _install_claude_code_plugin(
    *,
    settings: Settings,
    cwd: Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    source = _claude_code_plugin_source_path(cwd=cwd)
    destination = _claude_code_plugin_install_path(home=home)
    if not source.exists():
        return {
            "target": "claude-code",
            "installed": False,
            "path": str(destination),
            "reason": "plugin_source_not_found",
            "instructions": [
                f"Expected the source plugin at `{source}`.",
            ],
        }
    ensure_dir(destination.parent)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    _write_json_file(destination / ".mcp.json", mcp_json_document(settings))
    return {
        "target": "claude-code",
        "installed": True,
        "path": str(destination),
        "source_path": str(source),
        "instructions": [
            "Restart Claude Code for the plugin to take effect.",
            f"Plugin installed at `{destination}`.",
        ],
    }


def setup_target_path(
    target: str,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    scope: str = "project",
) -> Path | None:
    target = normalize_target_name(target)
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
    if target == "openclaw":
        return home / ".openclaw" / "openclaw.json"
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
    target = normalize_target_name(target)
    if target not in SUPPORTED_SETUP_TARGETS:
        raise ValueError(f"Unsupported setup target: {target}")
    if target == "openclaw":
        return _install_openclaw_plugin(cwd=cwd, home=home, scope=scope)
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
    target = normalize_target_name(target)
    if target not in SUPPORTED_SETUP_TARGETS or target == "json":
        raise ValueError(f"Unsupported removable setup target: {target}")
    if target == "openclaw":
        path = setup_target_path(target, cwd=cwd, home=home, scope=scope)
        assert path is not None
        binary = _openclaw_binary()
        if not binary:
            return {"target": target, "removed": False, "path": str(path), "scope": scope, "reason": "openclaw_not_found"}
        result = subprocess.run(
            [binary, "plugins", "uninstall", OPENCLAW_PLUGIN_ID],
            check=False,
            capture_output=True,
            text=True,
        )
        return {
            "target": target,
            "removed": result.returncode == 0,
            "path": str(path),
            "scope": scope,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "reason": None if result.returncode == 0 else "openclaw_uninstall_failed",
        }
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
    target = normalize_target_name(target)
    path = setup_target_path(target, cwd=cwd, home=home, scope=scope)
    if target == "openclaw":
        binary = _openclaw_binary()
        if binary:
            inspected = subprocess.run(
                [binary, "plugins", "inspect", OPENCLAW_PLUGIN_ID, "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
            installed = inspected.returncode == 0
        else:
            installed = False
        return {
            "target": target,
            "path": str(path) if path else None,
            "installed": installed,
            "scope": scope,
            "config": {
                "plugin_id": OPENCLAW_PLUGIN_ID,
                "plugin_path": str(_openclaw_plugin_path(cwd=cwd)),
            },
        }
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
        inspect_setup_target("openclaw", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("windsurf", settings, cwd=cwd, home=home, scope="user"),
        inspect_setup_target("json", settings, cwd=cwd, home=home, scope="project"),
    ]
    return entries


def install_plugin(
    target: str,
    settings: Settings,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    target = normalize_target_name(target)
    if target not in SUPPORTED_PLUGIN_TARGETS:
        raise ValueError(f"Unsupported plugin target: {target}")
    if target == "openclaw":
        return _install_openclaw_plugin(cwd=cwd, home=home, scope="user")
    if target == "claude-code":
        return _install_claude_code_plugin(settings=settings, cwd=cwd, home=home)
    if target != "codex":
        raise ValueError(f"Unsupported plugin target: {target}")
    source = _codex_plugin_source_path(cwd=cwd)
    if not source.exists():
        return {
            "target": target,
            "installed": False,
            "path": str(_codex_plugin_install_path(home=home)),
            "reason": "plugin_source_not_found",
            "instructions": [
                f"Expected the source plugin at `{source}`.",
            ],
        }
    destination = _codex_plugin_install_path(home=home)
    ensure_dir(destination.parent)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    _write_json_file(destination / ".mcp.json", mcp_json_document(settings))
    marketplace = _update_codex_marketplace(home=home)
    return {
        "target": target,
        "installed": True,
        "path": str(destination),
        "source_path": str(source),
        "marketplace_path": str(marketplace),
        "instructions": [
            "Restart Codex or refresh plugins if the new local plugin does not appear immediately.",
            f"The installed marketplace entry points at `./plugins/{CODEX_PLUGIN_NAME}` under your home directory.",
        ],
    }


def install_plugin_set(
    target: str,
    settings: Settings,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> list[dict[str, Any]]:
    target = normalize_target_name(target)
    if target == "all":
        targets = BULK_PLUGIN_TARGETS
    elif target in SUPPORTED_PLUGIN_TARGETS:
        targets = (target,)
    else:
        raise ValueError(f"Unsupported plugin target: {target}")
    return [install_plugin(name, settings, cwd=cwd, home=home) for name in targets]


def _plugin_source_exists(target: str, *, cwd: Path | None = None) -> bool:
    target = normalize_target_name(target)
    if target == "codex":
        return _codex_plugin_source_path(cwd=cwd).exists()
    if target == "claude-code":
        return _claude_code_plugin_source_path(cwd=cwd).exists()
    if target == "openclaw":
        return _openclaw_plugin_path(cwd=cwd).exists()
    return False


def installed_plugin_targets(
    settings: Settings,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> list[str]:
    targets: list[str] = []
    if _codex_plugin_install_path(home=home).exists():
        targets.append("codex")
    if _claude_code_plugin_install_path(home=home).exists():
        targets.append("claude-code")
    openclaw_status = inspect_setup_target("openclaw", settings, cwd=cwd, home=home, scope="user")
    if openclaw_status.get("installed"):
        targets.append("openclaw")
    return targets


def _target_label(target: str) -> str:
    labels = {
        "codex": "Codex",
        "claude-code": "Claude Code",
        "claude-desktop": "Claude Desktop",
        "gemini-cli": "Gemini CLI",
        "cline": "Cline",
        "antigravity": "Antigravity",
        "openclaw": "OpenClaw",
        "opencode": "OpenCode",
    }
    return labels.get(target, target)


def _variant_label(variant: str) -> str:
    labels = {
        "general": "general runtime",
        "daemon": "daemon runtime",
    }
    return labels.get(variant, variant)


def _target_specific_notes(target: str) -> list[str]:
    if target == "claude-desktop":
        return [
            "- This skill is uploaded manually into Claude Desktop or claude.ai; it does not configure MCP by itself.",
            "- Prefer the HTTP API when you can reach a running `zotero-headless` daemon directly.",
            "- Use MCP only after the separate Claude Desktop MCP config has been installed.",
        ]
    if target in {"codex", "claude-code", "cline", "antigravity", "opencode"}:
        return [
            "- This client is comfortable with MCP tool use. Prefer MCP for exact reads and mutations when the server is installed.",
            "- If the client can also call HTTP directly, prefer the API for stable structured integrations or remote daemon access.",
        ]
    if target == "openclaw":
        return [
            "- Install or refresh the OpenClaw plugin with `zhl setup add openclaw --scope user` when working from this repository.",
            "- Prefer the native OpenClaw Zotero plugin when it is installed and enabled; it exposes tools directly without a separate MCP bridge.",
            "- Configure the plugin against a reachable `zotero-headless` daemon and drop to the HTTP API when you need lower-level inspection or remote debugging.",
        ]
    if target == "gemini-cli":
        return [
            "- Prefer the HTTP API for direct structured integrations when available.",
            "- Use MCP when the Gemini environment is already configured for MCP tool calls and that is the easiest path.",
        ]
    return []


def _variant_specific_notes(variant: str) -> list[str]:
    if variant == "daemon":
        return [
            "- Assume a true headless deployment: no Zotero Desktop GUI, no local desktop assumptions, and API-first operations.",
            "- Prefer the daemon HTTP API as the primary integration surface and use MCP as a client convenience layer.",
            "- Treat remote sync, runtime observability, and background jobs as normal operational concerns, not exceptional ones.",
            "- Only mention local desktop interoperability when the task explicitly involves a machine that also has Zotero Desktop installed.",
        ]
    return [
        "- Use the headless store as the primary working state even when a local Zotero installation exists.",
        "- Treat the local desktop adapter as an interoperability layer, not the default source of truth.",
        "- Reach for local desktop import/apply only when local-only state or explicit desktop interoperability is actually needed.",
    ]


def skill_text(target: str, *, variant: str = "general") -> str:
    target = normalize_target_name(target)
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    if variant not in SUPPORTED_SKILL_VARIANTS:
        raise ValueError(f"Unsupported skill variant: {variant}")
    target_label = _target_label(target)
    variant_label = _variant_label(variant)
    target_notes = "\n".join(_target_specific_notes(target))
    if target_notes:
        target_notes = f"\nTarget-specific notes:\n{target_notes}\n"
    variant_notes = "\n".join(_variant_specific_notes(variant))
    if variant_notes:
        variant_notes = f"\nVariant-specific notes:\n{variant_notes}\n"
    return f"""# Zotero Headless

Use this when working with a `zotero-headless` CLI, API, or MCP runtime from {target_label}.
Active skill variant: `{variant}` ({variant_label}).

Core priorities:
- Prefer the headless store and daemon runtime over direct filesystem or database assumptions.
- Treat qmd semantic search as automatically maintained from dataset changes.
- Use direct sync and conflict flows instead of retrying remote mutations blindly.
- For local desktop workflows, distinguish headless state from the Zotero desktop database and use the local adapter/import/apply flow.

Decision table:
- Exploratory retrieval, topic discovery, related-work lookup, RAG context building:
  - Use qmd semantic search.
- Exact metadata lookup with a known library ID, item key, or collection key:
  - Use direct API, CLI, or MCP reads.
- Create, update, delete, sync, conflict resolution, or local apply work:
  - Use direct mutation and sync commands, never qmd.
- Stable structured integration with a reachable daemon:
  - Prefer the HTTP API.
- MCP-native tool calling environment:
  - Prefer MCP when the client already handles tool use well.

Routing policy:
- Use qmd semantic search for:
  - finding relevant papers on a topic
  - retrieving related sources from natural-language prompts
  - summarizing themes across a library
  - building retrieval context before writing
- Use direct reads through API, CLI, or MCP for:
  - exact metadata inspection
  - exact list/get operations
  - authoritative current state
  - keyed parent/child traversal
- Use direct mutation and sync commands for:
  - item and collection create/update/delete
  - sync discover, pull, push
  - conflict resolution
  - local desktop import, plan-apply, and apply
- If you must use the CLI from an agent or script, prefer the strict `zhl raw ...` namespace over the human-oriented top-level commands.
- Prefer the HTTP API over MCP when the agent can call HTTP directly and wants stable structured integration.
- Prefer MCP when the client is already MCP-native and tool-use ergonomics are better there.
- Do not use qmd semantic search when the task already names exact objects or requires authoritative current metadata.
{variant_notes}
{target_notes}
Recommended workflow:
1. Start with `zhl capabilities` or `zhl daemon status` when runtime shape is unclear.
2. If remote libraries are involved, run `zhl raw sync discover` and `zhl raw sync pull --library <library_id>` before deeper work when you are driving the CLI programmatically.
3. Choose retrieval mode:
   - qmd for exploratory retrieval
   - API/MCP/CLI for exact reads
4. For writes, use direct mutation commands and then `zhl raw sync push --library <library_id>` when remote sync is required.
5. If a write fails, inspect `zhl raw sync conflicts --library <library_id>` before retrying.

Common recipes:
- Find papers about a topic:
  - `zhl qmd query "papers about retrieval augmented generation"`
- Fetch an exact item:
  - use API or MCP item-get tools with the known `library_id` and `item_key`
- Sync a remote library before exact reads:
  - `zhl raw sync discover`
  - `zhl raw sync pull --library user:123456`
- Resolve remote write issues:
  - `zhl raw sync conflicts --library user:123456`
- Desktop Zotero interoperability:
  - `zhl raw local import`
  - `zhl raw local plan-apply --library local:1`
  - `zhl raw local apply --library local:1`
- Headless daemon workflow:
  - `zhl-daemon serve --host 127.0.0.1 --port 8787 --sync-interval 300`
- Daemon observability:
  - `curl -s http://127.0.0.1:8787/daemon/runtime`
  - `curl -s http://127.0.0.1:8787/daemon/jobs`
  - `curl -s http://127.0.0.1:8787/metrics`

Anti-patterns:
- Do not scan exported markdown directly when qmd can answer the retrieval question.
- Do not use qmd for exact authoritative metadata lookups.
- Do not mutate the Zotero desktop database directly outside the supported local apply flow.
- Do not use mirror sync paths unless the task explicitly requires mirror-backed compatibility behavior.
- Do not retry failed remote writes blindly; inspect conflicts first.

High-value commands:
- `zhl capabilities`
- `zhl daemon status`
- `zhl raw sync discover`
- `zhl raw sync pull --library <library_id>`
- `zhl raw sync push --library <library_id>`
- `zhl raw sync conflicts --library <library_id>`
- `zhl qmd query "<topic>"`

Useful daemon endpoints:
- `/health`
- `/capabilities`
- `/daemon/status`
- `/daemon/runtime`
- `/daemon/jobs`
- `/metrics`
"""


def skill_target_path(target: str, *, home: Path | None = None, variant: str = "general") -> Path:
    target = normalize_target_name(target)
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    if variant not in SUPPORTED_SKILL_VARIANTS:
        raise ValueError(f"Unsupported skill variant: {variant}")
    home = (home or Path.home()).expanduser()
    if target == "codex":
        return home / ".codex" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "claude-code":
        return home / ".claude" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "claude-desktop":
        suffix = "" if variant == "general" else f"-{variant}"
        return home / "Desktop" / f"{SERVER_NAME}-claude-desktop{suffix}-skill.zip"
    if target == "gemini-cli":
        return home / ".gemini" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "cline":
        return home / ".cline" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "antigravity":
        return home / ".gemini" / "antigravity" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "openclaw":
        return home / ".openclaw" / "skills" / SERVER_NAME / "SKILL.md"
    if target == "opencode":
        return home / ".config" / "opencode" / "skill" / SERVER_NAME / "SKILL.md"
    raise ValueError(f"Unsupported skill target: {target}")


def _claude_desktop_skill_archive_payload() -> dict[str, str]:
    return {
        "name": "Zotero Headless",
        "slug": SERVER_NAME,
        "entrypoint": "SKILL.md",
        "description": "Claude Desktop/manual-upload skill archive for zotero-headless.",
    }


def _claude_desktop_upload_instructions(path: Path) -> list[str]:
    return [
        f"Find the generated skill archive at: {path}",
        "In Claude Desktop, open the Skills section and upload the archive.",
        "You can also upload the same archive in the Claude web app on claude.ai.",
    ]


def _write_claude_desktop_skill_archive(path: Path, *, variant: str) -> None:
    ensure_dir(path.parent)
    skill_body = skill_text("claude-desktop", variant=variant)
    metadata = json.dumps(_claude_desktop_skill_archive_payload(), indent=2, sort_keys=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_body)
        zf.writestr("metadata.json", metadata)


def install_skill(
    target: str,
    *,
    home: Path | None = None,
    variant: str = "general",
) -> dict[str, Any]:
    target = normalize_target_name(target)
    if target not in SUPPORTED_SKILL_TARGETS:
        raise ValueError(f"Unsupported skill target: {target}")
    if variant not in SUPPORTED_SKILL_VARIANTS:
        raise ValueError(f"Unsupported skill variant: {variant}")
    path = skill_target_path(target, home=home, variant=variant)
    if target == "claude-desktop":
        _write_claude_desktop_skill_archive(path, variant=variant)
        return {
            "target": target,
            "variant": variant,
            "installed": True,
            "path": str(path),
            "format": "zip",
            "instructions": _claude_desktop_upload_instructions(path),
        }
    _write_text(path, skill_text(target, variant=variant))
    return {"target": target, "variant": variant, "installed": True, "path": str(path)}


def install_skill_set(
    target: str,
    *,
    home: Path | None = None,
    variant: str = "general",
) -> list[dict[str, Any]]:
    target = normalize_target_name(target)
    if target == "all":
        targets = BULK_SKILL_TARGETS
    elif target in SUPPORTED_SKILL_TARGETS:
        targets = (target,)
    else:
        raise ValueError(f"Unsupported skill target: {target}")
    return [install_skill(name, home=home, variant=variant) for name in targets]


def installed_skill_targets(*, home: Path | None = None, variant: str = "general") -> list[str]:
    return [
        target
        for target in BULK_SKILL_TARGETS
        if skill_target_path(target, home=home, variant=variant).exists()
    ]


def refresh_installed_integrations(
    settings: Settings,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    variant: str = "general",
) -> dict[str, Any]:
    refreshed_skills: list[dict[str, Any]] = []
    refreshed_plugins: list[dict[str, Any]] = []
    skipped_plugins: list[dict[str, Any]] = []

    for target in installed_skill_targets(home=home, variant=variant):
        refreshed_skills.append(install_skill(target, home=home, variant=variant))

    for target in installed_plugin_targets(settings, cwd=cwd, home=home):
        if not _plugin_source_exists(target, cwd=cwd):
            skipped_plugins.append(
                {
                    "target": target,
                    "reason": "plugin_source_not_found",
                }
            )
            continue
        refreshed_plugins.append(install_plugin(target, settings, cwd=cwd, home=home))

    return {
        "skills": refreshed_skills,
        "plugins": refreshed_plugins,
        "skipped_plugins": skipped_plugins,
    }


def export_skill(target: str, *, variant: str = "general") -> dict[str, Any]:
    target = normalize_target_name(target)
    if variant not in SUPPORTED_SKILL_VARIANTS:
        raise ValueError(f"Unsupported skill variant: {variant}")
    if target == "claude-desktop":
        return {
            "target": target,
            "variant": variant,
            "content": skill_text(target, variant=variant),
            "format": "zip",
            "archive_contents": ["SKILL.md", "metadata.json"],
        }
    return {"target": target, "variant": variant, "content": skill_text(target, variant=variant)}


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
            "zotero_headless_daemon": shutil.which("zotero-headless-daemon"),
            "qmd": shutil.which("qmd"),
        },
        "settings": {
            "state_dir": str(settings.resolved_state_dir()),
            "headless_db": str(settings.resolved_canonical_db()),
            "mirror_db": str(settings.resolved_mirror_db()),
            "file_cache_dir": str(settings.resolved_file_cache_dir()),
            "export_dir": str(settings.resolved_export_dir()),
            "recovery_snapshot_dir": str(settings.resolved_recovery_snapshot_dir()),
            "recovery_temp_dir": str(settings.resolved_recovery_temp_dir()),
            "recovery_auto_snapshots": bool(settings.recovery_auto_snapshots),
            "data_dir": settings.data_dir,
            "local_db": str(settings.resolved_local_db()) if settings.resolved_local_db() else None,
            "api_key_configured": bool(settings.api_key),
        },
        "daemon": daemon.to_dict(),
        "setup_targets": setup_list(settings, cwd=cwd, home=home),
        "skill_targets": [
            {"target": target, "install_supported": True, "variants": list(SUPPORTED_SKILL_VARIANTS)}
            for target in SUPPORTED_SKILL_TARGETS
        ],
    }
