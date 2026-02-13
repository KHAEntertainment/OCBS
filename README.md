# OCBS — OpenClaw Backup System

An incremental, file-level backup system for OpenClaw that integrates with skills, crons, and heartbeats while remaining update-agnostic.

## Quick Start

```bash
# Install
cd /home/openclaw/.openclaw/workspace-coder/OCBS
uv venv && source .venv/bin/activate
uv pip install -e .

# Create a backup
ocbs backup --scope config

# Restore from latest backup
ocbs restore --latest
```

## What It Backs Up

| Scope | Contents |
|-------|----------|
| `config` | OpenClaw config, credentials |
| `config+session` | Config + agent sessions |
| `config+session+workspace` | Everything |

## Chat Commands (via OpenClaw Skill)

Once installed as a skill:

```
/ocbs backup                    # Quick backup (config scope)
/ocbs backup --scope full       # Full workspace backup
/ocbs restore --latest          # Restore from latest
/ocbs list                      # Show available backups
/ocbs status                    # Show storage status
/ocbs checkpoint "before update" # Create restore point
/ocbs checkpoint --serve        # Create checkpoint + serve restore page
/ocbs setup                     # Interactive wizard for schedules & heartbeat
/ocbs schedule                  # Manage automated backup schedules
/ocbs heartbeat                 # Configure health checks and alerts
/ocbs health                    # Quick backup health check
```

## Features

- **Incremental backups** — Only changed files are stored
- **Content-addressable** — SHA-256 deduplication prevents duplicates
- **Auto-cleanup** — Retains 7 daily, 4 weekly, 12 monthly backups
- **Checkpoint system** — Manual restore points for risky changes
- **Human-in-the-loop restore** — Web-based restore page for safe emergency recovery
- **Automated schedules** — Cron-based backup scheduling with configurable retention
- **Heartbeat health checks** — Alerts when backups are stale, optional auto-backup
- **Dual interface** — CLI commands + chat-based skill
- **Wizard mode** — Interactive setup for schedules and heartbeat configuration

## Installation

```bash
# Install package
uv pip install -e .

# Install OpenClaw skill
python install_skill.py

# Restart OpenClaw to load the skill
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `ocbs backup --scope <scope>` | Create backup |
| `ocbs restore --latest` | Restore latest backup |
| `ocbs restore --checkpoint <id>` | Restore checkpoint |
| `ocbs list` | List all backups |
| `ocbs status` | Show storage statistics |
| `ocbs clean` | Remove old backups |
| `ocbs checkpoint "reason"` | Create checkpoint |
| `ocbs checkpoint --serve --expires 4h` | Create checkpoint + serve restore page |
| `ocbs wizard` | Interactive setup wizard |
| `ocbs schedule wizard` | Schedule configuration wizard |
| `ocbs heartbeat wizard` | Heartbeat configuration wizard |
| `ocbs schedule list` | List scheduled backups |
| `ocbs heartbeat status` | Show heartbeat health status |
| `ocbs health` | Quick backup health check |

See [docs/setup.md](docs/setup.md) for detailed configuration.

## State Location

- Default: `~/.config/ocbs/`
- Pack files: `~/.config/ocbs/packs/`
- SQLite index: `~/.config/ocbs/index.db`

## License

MIT