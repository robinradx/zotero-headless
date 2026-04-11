# Contributing

This project is open source, pre-release, and intentionally transparent about its architecture and tradeoffs.

## Principles

- keep the repo debuggable
- prefer reproducible behavior over hiding complexity
- keep Zotero-specific behavior isolated to adapters where possible
- treat the canonical headless store as the system of record
- use qmd as a derived index, not primary storage

## Local Development

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Compile-check:

```bash
python3 -m compileall src/zotero_headless tests
```

Useful runtime commands:

```bash
zotero-headless capabilities
zotero-headless daemon status
zotero-headless doctor
zotero-headless setup list
```

## Workspace Hygiene

Keep personal or tool-local material in ignored directories such as:

- `.codex/`
- `.agents/`
- `.notes/`
- `.tmp/`

Those are intentionally excluded from version control.

## Desktop Helper Workflow

The repo does not vendor Zotero source anymore. If you work on the optional desktop-helper path:

- update `desktop_helper/metadata.json` with the upstream Zotero commit or tag you validated against
- keep the helper delta as explicit patch files under `desktop_helper/patches/`
- document any behavior assumptions that depend on those patches in the relevant code and docs

## Tests And Scope

When changing behavior:

- add or update regression tests
- keep public behavior explicit in CLI, API, and MCP surfaces
- do not silently expand support claims beyond what is actually verified
