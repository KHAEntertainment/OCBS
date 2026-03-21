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
ocbs backup --scope config --source native

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
/ocbs backup --scope config+session+workspace
/ocbs backup --scope config --source native
/ocbs restore --latest          # Restore from latest
/ocbs list                      # Show available backups
/ocbs status                    # Show storage status
/ocbs checkpoint "before update" # Create restore point
```

## Features

- **Incremental backups** — Only changed files are stored
- **Content-addressable** — SHA-256 deduplication prevents duplicates
- **Native backend option** — Can wrap `openclaw backup create` as a source
- **Auto-cleanup** — Retains 7 daily, 4 weekly, 12 monthly backups
- **Checkpoint system** — Manual restore points for risky changes
- **Dual interface** — CLI commands + chat-based skill
- **Cron/heartbeat ready** — Automated backups and health checks

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
| `ocbs backup --scope <scope> --source <source>` | Create backup |
| `ocbs restore --latest` | Restore latest backup |
| `ocbs restore --checkpoint <id>` | Restore checkpoint |
| `ocbs list` | List all backups |
| `ocbs status` | Show storage statistics |
| `ocbs clean` | Remove old backups |
| `ocbs checkpoint "reason"` | Create checkpoint |

See [docs/setup.md](docs/setup.md) for detailed configuration.

## Backup Sources

- `direct` reads `~/.openclaw` files directly and stores changed content in OCBS packs.
- `native` runs `openclaw backup create`, extracts the tar.gz, and stores the extracted files in the same OCBS chunk store.

You can choose per backup:

```bash
ocbs backup --scope config --source direct
ocbs backup --scope config+session --source native
```

Or set a default in `~/.config/ocbs/config.json`:

```json
{
  "defaultSource": "native",
  "nativeBackupDir": "/tmp/ocbs-native-cache"
}
```

## State Location

- Default: `~/.config/ocbs/`
- Pack files: `~/.config/ocbs/packs/`
- SQLite index: `~/.config/ocbs/index.db`

## License

MIT
