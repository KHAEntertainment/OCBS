# OCBS - OpenClaw Backup System

An incremental backup system that integrates with OpenClaw's skills, crons, and heartbeats while remaining update-agnostic.

## Core Requirements

- **Incremental backups** - file-level, not full tar.gz each time
- **Plugin architecture** - true isolation from core OpenClaw
- **Update agnostic** - OpenClaw core updates cannot break OCBS
- **Uses OpenClaw primitives** - skills, crons, heartbeats, messaging
- **Dual interface** - both skill AND command-based access
- **Distributable** - NPM or UV package, shareable via ClawHub

## Backup Scope Options

User-configurable what gets backed up:

| Scope | Contents | Use Case |
|-------|----------|----------|
| `config` | OpenClaw config, credentials | Minimal/slim setups |
| `config+session` | Config + agent sessions | Day-increment for session history |
| `config+session+workspace` | Everything | Full restore capability |

**Storage consideration:** Onboard storage limits (e.g., Pi) mean full workspace backups can fill space quickly. Scope options help manage this.

## Architecture

### State Location

- **Default:** `~/.config/ocbs/` (XDG-compliant)
- **Configurable** via environment or CLI flag

### Isolation Strategy

1. Separate state directory from `~/.openclaw/`
2. No core file patching — read from OpenClaw paths, write to OCBS paths
3. Skills as interface — OCBS exposes functionality via skill manifest
4. Version detection — detect OpenClaw version, adapt behavior if needed

### Incremental Format

File-level incremental using content-addressable chunks:
- Hash-based deduplication
- Pack files with SQLite/Lua index
- Efficient storage, rsync-friendly

## Hands-Off Auto-Restore (Optional Feature)

**Purpose:** Guardian mode for risky changes. If something breaks, system auto-recovers.

**Triggers:**
1. Gateway doesn't come back online after a change
2. Gateway comes back but agent is inactive/cannot confirm success

**Mechanism:**
- Agent sets a "checkpoint" before making changes
- Configurable timeout (X minutes)
- If no successful confirmation → auto-restore to pre-change state
- Optional — must be explicitly enabled

## Skill Interface (Chat Commands)

Skill exposes backup/restore via chat:

| Command | Action |
|---------|--------|
| `/ocbs backup` | Run immediate backup (uses default scope) |
| `/ocbs backup --scope config+session` | Backup with specific scope |
| `/ocbs restore --latest` | Restore from most recent backup |
| `/ocbs restore --checkpoint <id>` | Restore to specific checkpoint |
| `/ocbs status` | Show backup status, last run, storage used |
| `/ocbs list` | List available backups with timestamps |
| `/ocbs clean` | Trigger auto-cleanup of old backups |
| `/ocbs checkpoint "reason text"` | Create manual checkpoint for auto-restore |

## Auto-Cleanup Function

Essential to prevent storage bloat:

| Retention Level | Keep |
|-----------------|------|
| Daily | Last 7 days |
| Weekly | Last 4 weeks |
| Monthly | Last 12 months |

- Runs automatically with each backup
- Configurable thresholds per scope
- Can be triggered manually: `/ocbs clean`

## Remote Backup (Future Feature)

When community adoption takes hold:

- Cloud storage providers (S3, B2, etc.)
- Offload older backups to cloud for long-term retention
- Local retains recent incrementals, remote keeps archives
- Configurable: `--remote-enabled`, `--remote-provider`, `--remote-retention`

## Distribution

- **Package:** NPM or UV (decision pending)
- **Distribution:** ClawHub for agent installation
- **Agent install flow:** `npm install ocbs` or `uvx ocbs install` → sets up skill, cron jobs, config
## Discussion & Decisions

### Decided ✓
- [x] State location: `~/.config/ocbs/` (default)
- [x] Isolation: No core patching, skill-based interface
- [x] Incremental level: File-level
- [x] Restore interface: Both skill AND command-based
- [x] Backup scopes: Config only, config+session, config+session+workspace

### Pending
- [ ] Incremental format: Content-addressable chunks vs tar+index?
- [ ] Retention policy: How many increments to keep per scope?
- [ ] Package format: NPM or UV?
- [ ] Auto-restore checkpoint mechanism details
- [ ] Remote backup support? (deferred to future)
- [ ] Cloud provider integration (S3, B2, etc.)

---

*Created: 2026-02-11*
*Updated: 2026-02-11*

## Build Log

### 2026-02-11 - Initial Build Complete

**All 29 tests passing**

### Components Delivered:

1. **Core Engine** (`src/ocbs/core.py`)
   - Content-addressable chunk storage (SHA-256)
   - SQLite index for chunks, backups, checkpoints
   - Auto-cleanup retention (7d/4w/12m)
   - Checkpoint system for auto-restore

2. **CLI** (`src/ocbs/cli.py`)
   - Full command suite: backup, restore, status, list, clean, checkpoint
   - Configurable state directory

3. **Skill** (`src/ocbs/skill.py`)
   - Chat-based interface for OpenClaw
   - Skill manifest with all commands documented

4. **Integration** (`src/ocbs/integration.py`)
   - Cron job setup for automated backups
   - Heartbeat-based health checks
   - Auto-restore triggers

5. **Tests** (29 passing)
   - 12 unit tests for core functionality
   - 6 integration tests for CLI
   - 11 tests for integration + skill interface

### Quick Start

```bash
cd /home/openclaw/.openclaw/workspace-coder/OCBS
uv venv && source .venv/bin/activate
uv pip install -e .

# CLI usage
ocbs backup --scope config
ocbs restore --latest
ocbs status

# Install skill
python install_skill.py
```

### Status: ✅ Ready for Testing

---

## Roadmap (Post-MVP)

### Phase 1: Publishing
- [ ] Publish to UV (PyPI)
- [ ] Publish skill to ClawHub
- [ ] Update documentation for package-based install
- [ ] Add GitHub Project with public roadmap

### Phase 2: Remote Backup
- [ ] Cloud provider integrations (S3, B2, Google Cloud Storage)
- [ ] Remote backup push/pull commands
- [ ] Configurable remote retention policies
- [ ] Encrypted remote transfers

### Phase 3: Remote Restore & Webhooks
- [ ] Webhook triggers for backup/restore events
- [ ] Remote restore via API/webhook
- [ ] Cross-device backup sync
- [ ] Real-time backup status notifications

### Phase 4: Enhanced Features
- [ ] Selective file restore (pick files from backup)
- [ ] Backup verification/checksum validation
- [ ] Backup comparison (diff between two backups)
- [ ] Import from existing tar.gz backups
- [ ] Multi-schedule support (different scopes at different intervals)
