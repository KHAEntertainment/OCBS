# OCBS Skill

OpenClaw Backup System skill for chat-based backup and restore operations.

## Installation

\`\`\`bash
cd /home/openclaw/.openclaw/workspace-coder/OCBS
python install_skill.py
\`\`\`

## Commands

### backup
Create a backup of OpenClaw configuration.

\`\`\`bash
/ocbs backup --scope config --reason "Before update"
\`\`\`

**Parameters:**
- \`--scope <scope>\` - Backup scope: \`config\`, \`config+session\`, \`config+session+workspace\`
- \`--reason <reason>\` - Optional reason for the backup

### restore
Restore from a backup or checkpoint.

\`\`\`bash
/ocbs restore --latest
/ocbs restore --checkpoint <checkpoint_id>
\`\`\`

**Parameters:**
- \`--latest\` - Restore from the latest backup (default)
- \`--checkpoint <id>\` - Restore from a specific checkpoint
- \`--target <dir>\` - Target directory for restore (default: ~/.openclaw)

### list
List available backups.

\`\`\`bash
/ocbs list
/ocbs list --scope config
\`\`\`

**Parameters:**
- \`--scope <scope>\` - Filter by scope

### status
Show backup status and statistics.

\`\`\`bash
/ocbs status
\`\`\`

### clean
Clean up old backups.

\`\`\`bash
/ocbs clean
/ocbs clean --scope config
\`\`\`

**Parameters:**
- \`--scope <scope>\` - Filter by scope

### checkpoint
Create a checkpoint for auto-restore with optional web server.

\`\`\`bash
/ocbs checkpoint "Before major change" --serve
\`\`\`

**Parameters:**
- \`--reason <reason>\` - Reason for the checkpoint
- \`--serve\` - Start web server and return restore URL
- \`--expiry <minutes>\` - Restore link expiration (default: 24 hours)
- \`--host <host>\` - Override host for restore URL (auto-detects: Tailscale, localhost, custom domain)

**Restore Workflow with Serve:**

When \`--serve\` is used, a web server starts and a restore URL is returned:

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
- 24-hour expiration timer

## CLI Commands (outside of skill)

These commands can be run directly from terminal:

\`\`\`bash
# Create backup
ocbs backup --scope config --reason "Manual backup"

# Restore from latest
ocbs restore --latest

# Restore specific checkpoint
ocbs restore --checkpoint <id>

# Create checkpoint with web server
ocbs checkpoint "Pre-update snapshot" --serve --expiry 60 --host 100.90.22.52

# List backups
ocbs list

# Show status
ocbs status

# Clean old backups
ocbs clean --scope config+session
\`\`\`

## Storage

OCBS stores all data in \`~/.config/ocbs/\` by default:

\`\`\`
~/.config/ocbs/
├── index.db           # SQLite index (backups, chunks, checkpoints, serve_records)
├── packs/             # Content-addressable chunk storage
├── config.json        # Integration settings
└── backup.log         # Cron job output
\`\`\`

## Connection Detection

The \`--host\` parameter and web server auto-detect the best connection type:

1. **Custom domain** - If configured in OpenClaw gateway config
2. **Tailscale** - If Tailscale IP (100.x.x.x) is available
3. **Localhost** - Fallback for local access

## Integration

### Cron
Automatic backups can be configured via cron:

\`\`\`bash
ocbs integration setup-cron --schedule daily --scope config
\`\`\`

### Heartbeat
Health check for auto-restore can be configured:

\`\`\`bash
ocbs integration setup-heartbeat --enabled --timeout 30
\`\`\`

## Troubleshooting

### "Too many open files" error
This was fixed in v0.1.0 with batch processing. Restore now handles large backups (13,000+ files) without hitting file descriptor limits.

### Schema mismatch
The \`serve_records\` table uses \`checkpoint_id\` (not \`backup_id\`) to match checkpoint table schema.
