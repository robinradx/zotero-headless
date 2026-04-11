# Desktop Helper

This guide is only for contributors working on the optional Zotero-backed helper path.

Most users do not need this.

## What It Is

The helper path is the narrow workflow for launching an externally patched Zotero binary with `-ZoteroDaemon`.

It is not the main architecture of `zotero-headless`.

## When It Matters

Use this path only when:

- you are validating a helper patch against upstream Zotero
- you are checking whether an upstream change affects the helper seam
- you need a Zotero-backed experiment for contributor work

## Files

- `desktop_helper/metadata.json`
  - the tracked upstream Zotero revision
- `desktop_helper/patches/`
  - the local patch series
- [ZOTERO_SOURCE_NOTES.md](./ZOTERO_SOURCE_NOTES.md)
  - upstream source areas worth checking

## Rules

- pin a real upstream tag or commit
- keep patches explicit and reviewable
- validate against an external Zotero checkout or built binary
- keep the helper narrow

The clean-room runtime remains the primary product path. The helper exists to support validation and narrowly scoped experiments, not to become a second runtime product.
