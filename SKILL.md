# OCBS Backup Skill

Incremental backup system for OpenClaw with restore capability.

## Commands

### `/ocbs backup [--scope <scope>] [--reason <text>]`
Create an incremental backup.

| Parameter | Description |
|-----------|-------------|
| `--scope` | Backup scope: `minimal`, `config`, `config+session`, `config+session+workspace` |
| `--reason` | Optional reason for the backup |

**Examples:**
```bash
/ocbs backup
/ocbs backup --scope config+session
/ocbs backup --scope config --reason "before system update"
```

### `/ocbs restore --latest [--target <path>]`
Restore from the most recent backup.

| Parameter | Description |
|-----------|-------------|
| `--latest` | Restore from latest backup (required) |
| `--target` | Optional target directory |

**Examples:**
```bash
/ocbs restore --latest
/ocbs restore --latest --target /tmp/restore
```

### `/ocbs restore --checkpoint <id>`
Restore from a specific checkpoint.

| Parameter | Description |
|-----------|-------------|
| `--checkpoint` | Checkpoint ID (e.g., `20260211_120000_cp`) |

**Examples:**
```bash
/ocbs restore --checkpoint 20260211_120000_cp
```

### `/ocbs status`
Show current backup status and storage statistics.

**Output includes:**
- Total backups per scope
- Total chunks stored
- Pack file size
- Latest backup timestamp

### `/ocbs list [--scope <scope>]`
List available backups.

| Parameter | Description |
|-----------|-------------|
| `--scope` | Optional scope filter |

**Example:**
```bash
/ocbs list
/ocbs list --scope config
```

### `/ocbs clean [--scope <scope>]`
Clean up old backups based on retention policy.

Retention: 7 daily, 4 weekly, 12 monthly backups.

| Parameter | Description |
|-----------|-------------|
| `--scope` | Optional scope filter |

### `/ocbs checkpoint "<reason>" [--serve] [--expires <duration>] [--host <name>]`
Create a checkpoint for potential auto-restore, with optional restore page serving.

| Parameter | Description |
|-----------|-------------|
| `"<reason>"` | Reason for creating the checkpoint |
| `--serve` | Generate a restore page URL for the checkpoint |
| `--expires` | Link expiry duration (e.g., `4h`, `1d`); default `4h` |
| `--host` | Host/IP for the restore URL (e.g., Tailscale IP); default `localhost` |

**Examples:**
```bash
/ocbs checkpoint "before system update"
/ocbs checkpoint "migrating configuration"
/ocbs checkpoint "before update" --serve
/ocbs checkpoint "before update" --serve --expires 24h --host 100.x.x.x
```

## Auto-Restore Checkpoints

The checkpoint system allows creating manual restore points before risky operations:

1. Create checkpoint: `/ocbs checkpoint "reason"`
2. Make your changes
3. If something breaks: `/ocbs restore --checkpoint <id>`
4. If changes succeed: continue (checkpoint remains but inactive)

Optionally generate a shareable restore page:

```bash
/ocbs checkpoint "reason" --serve --expires 4h --host 100.x.x.x
```

## Backup Scopes

| Scope | Contents | Storage Impact |
|-------|----------|----------------|
| `minimal` | Essential config only (openclaw.json, auth-profiles.json, credentials) | Minimal (~10-20 files) |
| `config` | Config, credentials | Minimal |
| `config+session` | Config + sessions | Moderate |
| `config+session+workspace` | Everything | High |

For Raspberry Pi and storage-limited devices, use `config` or `config+session` scopes.

## State Location

- **Directory:** `~/.config/ocbs/`
- **Index:** SQLite database
- **Packs:** Content-addressable chunk storage

## Integration

The skill integrates with OpenClaw's:
- **Cron:** Automated scheduled backups
- **Heartbeat:** Health checks for auto-restore
- **Messaging:** Status notifications

## See Also

- **CLI:** Run `ocbs --help` for CLI reference
- **Docs:** [docs/setup.md](../docs/setup.md) for detailed configuration
- **Repo:** https://github.com/KHAEntertainment/OCBS