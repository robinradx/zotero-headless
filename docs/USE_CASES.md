# Common Use Cases

This guide is the fastest way to decide how to use `zotero-headless`.

## 1. I have Zotero Desktop and want better automation

Use this path when:

- Zotero is already installed on your machine
- you want to import your local profile into `zotero-headless`
- you want MCP, API, qmd search, or staged local writeback on top of that profile

Typical flow:

```text
uv tool install zotero-headless
zhl setup start
zhl local import
zhl qmd query "papers about retrieval augmented generation"
zhl-mcp
```

Read next:

- [LOCAL_DESKTOP.md](./LOCAL_DESKTOP.md)
- [API_AND_MCP.md](./API_AND_MCP.md)

## 2. I want a headless server without Zotero Desktop

Use this path when:

- the machine does not run the Zotero GUI
- you want the daemon, API, background sync, and MCP
- your libraries should come from zotero.org

Typical flow:

```text
uv tool install zotero-headless
zhl setup start
zhl-daemon serve --host 0.0.0.0 --port 23119 --sync-interval 300
```

Then connect through:

- HTTP API
- MCP
- qmd-backed search

Read next:

- [REMOTE_SYNC.md](./REMOTE_SYNC.md)
- [API_AND_MCP.md](./API_AND_MCP.md)

## 3. I mainly want shell commands

Use this path when:

- you want terminal administration
- you want setup, sync, search, and local interoperability from the shell
- you want human-oriented output by default

Read:

- [CLI.md](./CLI.md)

## 4. I want agent integration

Use this path when:

- you want Codex, Claude Code, Cursor, Gemini, Cline, Windsurf, or a similar client to access your libraries

You usually have two choices:

- MCP for native tool use in agent clients
- HTTP API when the client or integration prefers direct requests

Typical flow:

```text
zhl setup add codex --scope user
zhl skill install codex
zhl-mcp
```

Read:

- [API_AND_MCP.md](./API_AND_MCP.md)
- [CLI.md](./CLI.md)

## 5. I need to work on the optional Zotero-backed helper

Use this path only when:

- you are maintaining or validating the `-ZoteroDaemon` experiment
- you are comparing clean-room behavior against an externally patched Zotero build

Read:

- [DESKTOP_HELPER.md](./DESKTOP_HELPER.md)
- [ZOTERO_SOURCE_NOTES.md](./ZOTERO_SOURCE_NOTES.md)
