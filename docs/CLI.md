# CLI Guide

`zotero-headless` exposes two command styles:

- human-oriented commands on `zhl ...`
- strict machine-oriented commands on `zhl raw ...`

## Basic Pattern

Human-facing commands:

```text
zhl version
zhl doctor
zhl capabilities
```

Machine-oriented commands:

```text
zhl raw sync discover
zhl raw item create user:123456 '{"itemType":"note","note":"Hello"}'
```

## Setup

Run the guided setup:

```text
zhl setup start
```

Reconfigure only one part:

```text
zhl setup account
zhl setup libraries
zhl setup local
```

Inspect or install MCP client setup:

```text
zhl setup list
zhl setup show codex --scope user
zhl setup add codex --scope user
zhl setup remove codex --scope user
```

Install or export skill material:

```text
zhl skill install codex
zhl skill install openclaw
zhl skill export claude-desktop
```

Install the repo-local Codex plugin bundle:

```text
zhl plugin install codex
zhl plugin install openclaw
```

The Codex bundle includes the MCP config, a focused Zotero skill pack, research and sync agents, and a startup status hook.

For OpenClaw's native integration, run `zhl plugin install openclaw`. That shells out to `openclaw plugins install -l ./plugins/openclaw-plugin-zotero` and then enables `zotero`.

## Local Desktop Commands

Import a local profile:

```text
zhl local import
```

Plan staged writeback:

```text
zhl local plan-apply --library local:1
```

Apply supported staged changes:

```text
zhl local apply --library local:1
```

Read more:

- [LOCAL_DESKTOP.md](./LOCAL_DESKTOP.md)

## Remote Sync Commands

Discover configured remote libraries:

```text
zhl sync discover
```

Pull a remote library:

```text
zhl sync pull --library user:123456
```

Push staged changes:

```text
zhl sync push --library user:123456
```

Inspect conflicts:

```text
zhl sync conflicts --library user:123456
```

Read more:

- [REMOTE_SYNC.md](./REMOTE_SYNC.md)

## Search And Citations

Natural-language qmd search:

```text
zhl search "transformer interpretability"
zhl qmd query "transformer interpretability"
```

Citations export management:

```text
zhl citations status
zhl citations enable
zhl citations export --library user:123456
```

## Daemon, API, And MCP

Inspect daemon state:

```text
zhl daemon status
zhl daemon command
```

Run the daemon:

```text
zhl-daemon serve --host 127.0.0.1 --port 8787 --sync-interval 300
```

Run the HTTP API directly:

```text
zhl api --host 127.0.0.1 --port 8787
```

Run the MCP server:

```text
zhl-mcp
```

Read more:

- [API_AND_MCP.md](./API_AND_MCP.md)

## JSON Output

Many human commands support `--json`:

```text
zhl --json doctor
zhl --json version
zhl --json daemon status
```

Use this when another tool needs clean parseable output.
