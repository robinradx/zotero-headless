# API And MCP

`zotero-headless` exposes the same underlying runtime through two integration styles:

- HTTP API
- MCP

Use the one that matches your client.

## When To Use HTTP

Use the HTTP API when:

- you are integrating from another app or service
- you want long-running server deployments
- you want direct requests from scripts, automation, or custom tooling

Start it directly:

```text
zhl api --host 127.0.0.1 --port 8787
```

Or run it through the daemon:

```text
zhl-daemon serve --host 127.0.0.1 --port 8787 --sync-interval 300
```

Quick check:

```text
curl -s http://127.0.0.1:8787/capabilities
```

## When To Use MCP

Use MCP when:

- your agent client already speaks MCP
- you want native tool use inside Codex, Claude Code, Cursor, Gemini, Cline, Windsurf, or similar tools

Start the stdio server:

```text
zhl-mcp
```

## Client Setup

To install MCP config for a client:

```text
zhl setup add codex --scope user
zhl setup add cursor --scope project
zhl setup add claude-code --scope project
```

To inspect what was written:

```text
zhl setup show codex --scope user
```

## Skill Installation

Some clients benefit from a matching skill pack:

```text
zhl skill install codex
zhl skill install claude-code
zhl skill install gemini-cli
```

This is separate from the MCP server itself. MCP gives the client tool access; the skill gives the agent a better prompt/workflow layer.

## Choosing Between Them

Choose HTTP when:

- the integration is service-to-service
- you want a stable host and port
- you want `curl`, scripts, or custom clients

Choose MCP when:

- the integration is an MCP-capable agent tool
- you want native tool discovery and invocation inside the client

Use both when:

- you want agents through MCP
- and you also want direct HTTP access for other automation
