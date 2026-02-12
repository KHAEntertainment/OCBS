# OCBS Setup & Configuration

## State Directory

OCBS stores all data in `~/.config/ocbs/` by default:

```
~/.config/ocbs/
├── index.db         # SQLite index (backups, chunks, checkpoints)
├── packs/           # Content-addressable chunk storage
├── config.json      # Integration settings
└── backup.log       # Cron job output
```

Override with: `ocbs --state-dir /path/to/state backup`

## Backup Scopes

### `config`
- `~/.openclaw/config/`
- `~/.openclaw/credentials/`

### `config+session`
- Everything above, plus:
- `~/.openclaw/sessions/`

### `config+session+workspace`
- Everything above, plus:
- `~/.openclaw/workspace/`

## Retention Policy

Auto-cleanup runs with each backup:

| Level | Keep | Criteria |
|-------|------|----------|
| Daily | 7 | All backups ≤ 7 days old |
| Weekly | 4 | 1 backup per week (8-30 days) |
| Monthly | 12 | 1 backup per month (31-365 days) |

Manual cleanup: `ocbs clean`

## Automated Backups (Cron)

```python
from ocbs.integration import OCBSIntegration

integration = OCBSIntegration()
integration.setup_cron(schedule='daily', scope='config')
```

Cron expressions:
- `daily` → 2 AM every day
- `weekly` → 2 AM every Sunday
- Custom → Any cron expression

Remove: `integration.remove_cron()`

## Heartbeat Auto-Restore

Configure health checks that trigger auto-restore if the gateway goes down:

```python
integration = OCBSIntegration()
integration.setup_heartbeat_check(enabled=True, timeout_minutes=30)
```

Auto-restore triggers when:
1. Gateway doesn't restart after a change
2. Gateway is unresponsive for >30 minutes

## Checkpoints

Create manual restore points before risky operations:

```bash
ocbs checkpoint "before system update"
ocbs restore --checkpoint 20260211_120000_cp
```

## Skill Installation

The skill provides chat-based backup control:

```bash
python install_skill.py
```

Then restart OpenClaw. Commands become available via chat:

```
/ocbs backup --scope config+session
/ocbs restore --latest
/ocbs checkpoint "reason text"
```

## Troubleshooting

### Backup finds no files
Ensure OpenClaw state exists at `~/.openclaw/`. OCBS reads from the actual OpenClaw directory, not its own state.

### Restore fails
Check file permissions and available disk space. Restore overwrites existing files.

### Cron not running
Ensure cron is installed: `which cron`. On systems without cron, use a systemd timer instead.

## Architecture

- **Incremental**: Only changed files are stored
- **Deduplication**: SHA-256 content addressing prevents duplicates
- **Isolation**: No modifications to OpenClaw core files
- **Update-agnostic**: Works across OpenClaw version upgrades