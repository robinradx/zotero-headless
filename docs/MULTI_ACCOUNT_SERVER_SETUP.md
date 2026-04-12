# Multi-Account Server Setup

This guide explains how to run `zotero-headless` for two or more separate Zotero accounts on one machine.

The current model is:

- one `zotero-headless` profile = one Zotero API key
- one profile can sync one personal library plus any group libraries visible to that account
- multiple separate personal accounts require multiple separate profiles

The recommended approach is:

- one shared installation of `zotero-headless`
- one named profile per person
- one daemon instance per person
- optional wrapper command per person

This is simpler and safer than separate Python environments.

## Recommended Shape

Example for two users, `alice` and `bob`:

Suggested daemon ports:

- `alice`: `8787`
- `bob`: `8788`

## Why This Works

`zotero-headless` supports named profiles through:

- `--profile <name>`
- `ZOTERO_HEADLESS_PROFILE=<name>`

Each profile gets its own saved settings, and if a profile does not set `state_dir` explicitly, it gets an isolated default state directory automatically.

That means one machine can host multiple independent runtime profiles as long as each daemon uses a different port.

## Preconditions

Before starting:

- `zotero-headless` is installed and available as `zhl`
- each person has their own Zotero API key
- each person knows which personal and group libraries they want enabled
- the machine has a directory where persistent runtime state can be stored

## Step 1: Configure The First User

Run:

```bash
zhl --profile alice setup start
```

During setup:

- enter Alice's Zotero API key
- select Alice's personal library and any desired group libraries
- keep the daemon host as `127.0.0.1`
- keep the daemon port as `8787`

After setup, verify:

```bash
zhl --profile alice --json capabilities
zhl --profile alice sync discover
```

## Step 2: Configure The Second User

Run:

```bash
zhl --profile bob setup start
```

During setup:

- enter Bob's Zotero API key
- select Bob's personal library and any desired group libraries
- keep the daemon host as `127.0.0.1`
- keep the daemon port as `8788`

After setup, verify:

```bash
zhl --profile bob --json capabilities
zhl --profile bob sync discover
```

## Step 3: Start Separate Daemons

Start Alice:

```bash
zhl --profile alice daemon serve --host 127.0.0.1 --port 8787 --sync-interval 300
```

Start Bob:

```bash
zhl --profile bob daemon serve --host 127.0.0.1 --port 8788 --sync-interval 300
```

These can run under:

- `systemd`
- `launchd`
- `supervisord`
- `tmux`
- any other process manager

## Step 4: Optional Wrapper Commands

Create `/srv/zotero-headless/bin/zhl-alice`:

```sh
#!/bin/sh
exec zhl --profile alice "$@"
```

Create `/srv/zotero-headless/bin/zhl-bob`:

```sh
#!/bin/sh
exec zhl --profile bob "$@"
```

Make them executable:

```bash
chmod +x /srv/zotero-headless/bin/zhl-alice
chmod +x /srv/zotero-headless/bin/zhl-bob
```

Optional:

- add `/srv/zotero-headless/bin` to `PATH`
- create matching wrapper commands for `zhl-daemon` and `zhl-mcp` if needed

## Step 5: Verify Isolation

Run:

```bash
zhl --profile alice daemon status
zhl --profile bob daemon status
```

Then verify each profile reports its own default library and state path:

```bash
zhl --profile alice --json capabilities
zhl --profile bob --json capabilities
```

Check each daemon health endpoint:

```bash
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8788/health
```

Check each daemon library list:

```bash
curl -s http://127.0.0.1:8787/core/libraries
curl -s http://127.0.0.1:8788/core/libraries
```

Alice's endpoint should not expose Bob's personal library and vice versa.

## Operational Rules

Follow these rules:

- never bind two daemons to the same port
- always use the correct profile or user-specific wrapper command when running manual CLI actions
- if automations or agents call the CLI, make them call the correct wrapper command

## Recommended Commands For Daily Use

Examples:

```bash
zhl --profile alice sync pull --library user:ALICE_USER_ID
zhl --profile alice sync conflicts --library user:ALICE_USER_ID
zhl --profile bob sync pull --library user:BOB_USER_ID
zhl --profile bob sync conflicts --library user:BOB_USER_ID
```

If the exact personal library IDs are not known ahead of time, discover them with:

```bash
zhl --profile alice sync discover
zhl --profile bob sync discover
```

## Optional: Separate OS Users

If the machine supports separate Unix users, that is even cleaner.

In that model:

- install `zotero-headless` once globally or once per user
- let each Unix user keep their own default config path
- let each Unix user keep their own default state path
- run each daemon under that Unix account

This reduces the risk of someone accidentally running the wrong profile.

## Optional: systemd Template

Example unit for Alice:

```ini
[Unit]
Description=zotero-headless daemon for Alice
After=network.target

[Service]
ExecStart=/usr/local/bin/zhl --profile alice daemon serve --host 127.0.0.1 --port 8787 --sync-interval 300
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Create a second unit for Bob with:

- Bob's config path
- Bob's state path
- port `8788`

## What Not To Do

Avoid these approaches:

- separate Python environments just for account isolation
- one shared config file with manual API key swapping
- one shared daemon process serving multiple personal accounts
- shared state directories between users

Separate Python environments are not necessary unless the machine already requires them for unrelated reasons.

## If You Want To Automate This Further

Possible future improvements in code:

- first-class named profiles
- a `zhl --profile <name>` flag
- generated per-profile wrapper scripts
- templated service installation
- a true multi-tenant daemon model with per-request account selection

For the current use case, none of that is required. Separate profile directories plus separate daemon instances are enough.
