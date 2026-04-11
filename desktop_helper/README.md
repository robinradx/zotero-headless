# Desktop Helper Workflow

This directory tracks the optional Zotero desktop-helper workflow without vendoring the upstream Zotero source tree.

## Purpose

Use this only when you need to maintain or validate the narrow helper path that launches an externally patched Zotero binary with `-ZoteroDaemon`.

The clean-room daemon remains the primary runtime.

## Layout

- `metadata.json`
  - upstream provenance for the helper work
- `patches/`
  - explicit patch series against the pinned upstream revision

## Maintenance Rules

1. Pin an exact upstream Zotero commit or tag in `metadata.json`.
2. Keep local helper changes as reviewable patch files under `patches/`.
3. Do not treat the helper as ready just because patches exist; validate against a real upstream checkout or built binary.
4. Keep the helper narrow. Avoid expanding it into a second product runtime.
