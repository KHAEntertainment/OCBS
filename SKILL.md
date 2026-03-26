# OCBS Skill

OpenClaw Backup System skill for chat-based backup and restore operations.

## Installation

```bash
cd /home/openclaw/.openclaw/workspace-coder/OCBS
python install_skill.py
```

## Commands

### backup
Create a backup of OpenClaw configuration.

```bash
/ocbs backup --scope config --reason "Before update"
/ocbs backup --scope config --source native --reason "Before upgrade"
```

**Parameters:**
- `--scope <scope>` - Backup scope: `config`, `config+session`, `config+session+workspace`, `minimal`
- `--source <source>` - Backup source: `direct` or `native`
- `--reason <reason>` - Optional reason for the backup

**Scope behavior:**

| Scope | Description |
|-------|-------------|
| `config` | Configuration only (openclaw.json, credentials) |
| `config+session` | Configuration + sessions directory |
| `config+session+workspace` | Full backup including workspace |
| `minimal` | Metadata-only checkpoint (stores backup ID, timestamp, scope, reason in SQLite; no file contents) — intended as a lightweight marker for tracking operations rather than a restorable backup |

**Source behavior:**
- `direct` reads OpenClaw files directly into OCBS chunk storage
- `native` runs `openclaw backup create`, extracts the archive, then imports it into OCBS chunk storage
- If the native CLI is unavailable, OCBS falls back to the direct source

### restore
Restore from a backup or checkpoint.

```bash
/ocbs restore --latest
/ocbs restore --checkpoint <checkpoint_id>
```

**Parameters:**
- `--latest` - Restore from the latest backup (default)
- `--checkpoint <id>` - Restore from a specific checkpoint
- `--target <dir>` - Target directory for restore (default: `~/.openclaw`)

### list
List available backups.

```bash
/ocbs list
/ocbs list --scope config
```

**Parameters:**
- `--scope <scope>` - Filter by scope

### status
Show backup status and statistics.

```bash
/ocbs status
```

### clean
Clean up old backups.

```bash
/ocbs clean
/ocbs clean --scope config
```

**Parameters:**
- `--scope <scope>` - Filter by scope

### checkpoint
Create a checkpoint for auto-restore with optional web server.

```bash
/ocbs checkpoint "Before major change" --serve
/ocbs checkpoint "Before major change" --serve --expiry 60 --host 100.90.22.52
```

**Parameters:**
- `--reason <reason>` - Reason for the checkpoint
- `--serve` - Start a restore web server and return a restore URL
- `--expiry <minutes>` - Set how long the restore link remains valid
- `--host <host>` - Override the host or IP used in the restore URL

**Serve behavior:**
- `--serve` starts the OCBS restore server so the checkpoint can be restored from a browser.
- `--expiry` controls the restore-link lifetime shown to the operator.
- `--host` overrides auto-detection when you need a specific Tailscale IP, localhost name, or custom domain.

**Restore Workflow with Serve:**

When `--serve` is used, a web server starts and a restore URL is returned:

1. Copy the restore URL
2. Visit it in a browser
3. Review backup details
4. Click "Restore" to proceed
5. OpenClaw gateway restarts automatically

The restore page shows:
- Checkpoint ID
- Reason for checkpoint
- Files included in backup
- Restore and Cancel buttons
- Expiration timer based on `--expiry`

### native-backup
Run OpenClaw native backup (tar.gz archive with manifest) via OCBS skill.

```bash
/ocbs native-backup --scope config --verify
/ocbs native-backup --scope config+session --output ~/Backups
```

**Parameters:**
- `--scope <scope>` - Backup scope: `config`, `config+session`, `config+session+workspace`
- `--verify` - Verify archive after creation
- `--output <dir>` - Custom output directory (default: current directory)

**Notes:**
- Wraps `openclaw backup create` command
- Creates full tar.gz archives (not incremental like OCBS backups)
- Useful for pre-upgrade snapshots or archive exports
- Requires OpenClaw CLI to be installed and in PATH

### native-verify
Verify a native backup archive.

```bash
/ocbs native-verify ./2026-03-09T00-00-00.000Z-openclaw-backup.tar.gz
```

**Parameters:**
- `--archive <path>` - Path to the native backup archive

**Notes:**
- Wraps `openclaw backup verify` command
- Validates archive structure and embedded manifest
- Quick way to check if archive is intact before restore

## CLI Commands (outside of skill)

These commands can be run directly from terminal:

```bash
# Create OCBS backup (incremental)
ocbs backup --scope config --reason "Quick safety snapshot"
ocbs backup --scope config --reason "Manual backup"
ocbs backup --scope config --source native --reason "Pre-upgrade snapshot"

# Restore from latest OCBS backup
ocbs restore --latest

# Restore specific OCBS checkpoint
ocbs restore --checkpoint <id>

# Create checkpoint with web server
ocbs checkpoint "Pre-update snapshot" --serve --expiry 60 --host 100.90.22.52

# List backups
ocbs list

# Show status
ocbs status

# Clean old backups
ocbs clean --scope config+session

# Native backup (tar.gz archive via OpenClaw)
ocbs native-backup --scope config --verify

# Verify native archive
ocbs native-verify ./2026-03-09-openclaw-backup.tar.gz
```

## Storage

OCBS stores all data in `~/.config/ocbs/` by default:

```text
~/.config/ocbs/
├── index.db           # SQLite index (backups, chunks, checkpoints, serve_records)
├── packs/             # Content-addressable chunk storage
├── config.json        # Integration settings
└── backup.log         # Cron job output
```

## Connection Detection

The `--host` parameter and web server auto-detect the best connection type:

1. **Custom domain** - If configured in OpenClaw gateway config
2. **Tailscale** - If Tailscale IP (`100.x.x.x`) is available
3. **Localhost** - Fallback for local access

## Integration

### Cron
Automatic backups can be configured via cron:

```bash
ocbs integration setup-cron --schedule daily --scope config
```

### Heartbeat
Health check for auto-restore can be configured:

```bash
ocbs integration setup-heartbeat --enabled --timeout 30
```

## Troubleshooting

### "Too many open files" error
This was fixed in v0.1.0 with batch processing. Restore now handles large backups (13,000+ files) without hitting file descriptor limits.

### Schema mismatch
The `serve_records` table uses `checkpoint_id` (not `backup_id`) to match checkpoint table schema.