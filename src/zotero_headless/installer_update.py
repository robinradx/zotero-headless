from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__

PACKAGE_NAME = "zotero-headless"
FALLBACK_VERSION = __version__


@dataclass(slots=True)
class UpdatePlan:
    method: str
    command: list[str]
    auto_supported: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "command": self.command,
            "auto_supported": self.auto_supported,
            "reason": self.reason,
        }


def current_version() -> str:
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return FALLBACK_VERSION


def _path_text(*values: str | None) -> str:
    return " ".join(value or "" for value in values).lower()


def detect_install_method(
    *,
    prefix: str | None = None,
    executable: str | None = None,
    argv0: str | None = None,
    base_prefix: str | None = None,
    virtual_env: str | None = None,
) -> str:
    prefix = prefix or sys.prefix
    executable = executable or sys.executable
    argv0 = argv0 or sys.argv[0]
    base_prefix = base_prefix if base_prefix is not None else getattr(sys, "base_prefix", prefix)
    virtual_env = virtual_env if virtual_env is not None else os.environ.get("VIRTUAL_ENV")
    haystack = _path_text(prefix, executable, argv0)
    if "pipx/venvs" in haystack or "pipx\\venvs" in haystack:
        return "pipx"
    if "/uv/tools/" in haystack or "\\uv\\tools\\" in haystack or ".local/share/uv/tools" in haystack:
        return "uv-tool"
    if prefix != base_prefix or virtual_env:
        return "venv-pip"
    return "unknown"


def build_update_plan(
    *,
    prefix: str | None = None,
    executable: str | None = None,
    argv0: str | None = None,
    base_prefix: str | None = None,
    virtual_env: str | None = None,
    uv_path: str | None = None,
    pipx_path: str | None = None,
) -> UpdatePlan:
    method = detect_install_method(
        prefix=prefix,
        executable=executable,
        argv0=argv0,
        base_prefix=base_prefix,
        virtual_env=virtual_env,
    )
    uv_path = uv_path if uv_path is not None else shutil.which("uv")
    pipx_path = pipx_path if pipx_path is not None else shutil.which("pipx")
    executable = executable or sys.executable

    if method == "uv-tool":
        if uv_path:
            return UpdatePlan(
                method=method,
                command=[uv_path, "tool", "upgrade", PACKAGE_NAME],
                auto_supported=True,
                reason="Detected uv tool installation.",
            )
        return UpdatePlan(
            method=method,
            command=["uv", "tool", "upgrade", PACKAGE_NAME],
            auto_supported=False,
            reason="Detected uv tool installation, but `uv` is not on PATH.",
        )

    if method == "pipx":
        if pipx_path:
            return UpdatePlan(
                method=method,
                command=[pipx_path, "upgrade", PACKAGE_NAME],
                auto_supported=True,
                reason="Detected pipx installation.",
            )
        return UpdatePlan(
            method=method,
            command=["pipx", "upgrade", PACKAGE_NAME],
            auto_supported=False,
            reason="Detected pipx installation, but `pipx` is not on PATH.",
        )

    if method == "venv-pip":
        return UpdatePlan(
            method=method,
            command=[executable, "-m", "pip", "install", "--upgrade", PACKAGE_NAME],
            auto_supported=True,
            reason="Detected virtualenv-based installation.",
        )

    return UpdatePlan(
        method="unknown",
        command=[],
        auto_supported=False,
        reason="Could not detect a managed install method. Use uv tool or pipx explicitly.",
    )


def run_update(plan: UpdatePlan) -> dict[str, object]:
    if not plan.auto_supported or not plan.command:
        return {
            "updated": False,
            "plan": plan.to_dict(),
            "message": "Automatic update is not supported for this install method.",
        }
    completed = subprocess.run(plan.command, check=False, capture_output=True, text=True)
    return {
        "updated": completed.returncode == 0,
        "returncode": completed.returncode,
        "plan": plan.to_dict(),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def executable_aliases() -> list[str]:
    aliases = []
    for name in ("zhl", "zhl-daemon", "zhl-mcp", "zotero-headless", "zotero-headless-daemon", "zotero-headless-mcp"):
        if shutil.which(name):
            aliases.append(name)
    return aliases


def version_payload() -> dict[str, object]:
    return {
        "package": PACKAGE_NAME,
        "version": current_version(),
        "install_method": detect_install_method(),
        "executable": str(Path(sys.argv[0]).name),
        "python": sys.executable,
        "aliases_found": executable_aliases(),
    }
