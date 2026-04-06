#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    (ROOT / "pyproject.toml", r'(^version = ")[^"]+(")', r"\g<1>{version}\g<2>"),
    (ROOT / "src" / "zotero_headless" / "__init__.py", r'(^__version__ = ")[^"]+(")', r"\g<1>{version}\g<2>"),
]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def replace_version(path: Path, pattern: str, replacement: str, version: str) -> bool:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement.format(version=version), text, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected exactly one version match in {path}")
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def bump_version(version: str) -> list[str]:
    if not VERSION_RE.match(version):
        raise ValueError("Version must use semantic format MAJOR.MINOR.PATCH")
    changed: list[str] = []
    for path, pattern, replacement in TARGETS:
        if replace_version(path, pattern, replacement, version):
            changed.append(str(path.relative_to(ROOT)))
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bump zotero-headless version references")
    parser.add_argument("version", help="New semantic version, e.g. 0.3.1")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        changed = bump_version(args.version)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if changed:
        print(f"Updated version to {args.version}:")
        for path in changed:
            print(f"- {path}")
    else:
        print(f"Version already at {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
