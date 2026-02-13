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

## Human-in-the-Loop Restore Page (Recommended)

**Purpose:** Safe, accessible emergency restore for risky changes. Human controls the restore decision via a web interface.

### Why This Approach?

- **Safety** — No false positive auto-restores; human decides
- **Accessibility** — Works from Telegram/WhatsApp without terminal access
- **Transparency** — Shows exactly what will be restored
- **Confirmation gate** — Change doesn't proceed until human acknowledges
- **Simple UX** — Single button click, no CLI knowledge needed

### User Flow

```
1. Agent: ocbs checkpoint "Before upgrading to 2026.2.7"
2. Agent: ocbs serve-checkpoint --expires 4h
3. OCBS: Creates temporary restore page at http://localhost:18789/restore/abc123
4. OCBS: Sends link via Telegram/WhatsApp to user
5. User: Opens link, sees backup details, clicks "I received this - proceed"
6. OCBS: Confirms receipt, tells agent "human approved - proceed with change"
7. Agent: Makes change, restarts gateway
8. Scenario A (Success): Gateway comes back → User closes page, done
   Scenario B (Failure): Things break → User clicks "Restore & Restart"
9. OCBS: Runs restore from checkpoint, restarts gateway, sends confirmation
```

### Page Content

```
┌─────────────────────────────────────────────┐
│  OCBS Emergency Restore                      │
├─────────────────────────────────────────────┤
│  Checkpoint: Before upgrading to 2026.2.7   │
│  Created: Today at 2:30 PM                  │
│  Files to restore: OpenClaw config (~2MB)   │
│                                             │
│  ⚠️ This will restore your system to the    │
│     state before the change.                │
│                                             │
│  [ I received this - proceed with change ]  │
│  ──────────────────────── OR ───────────────│
│  [ 🔴 RESTORE & RESTART GATEWAY ]           │
│                                             │
│  Expires in: 3h 42m                         │
└─────────────────────────────────────────────┘
```

### Technical Implementation

| Component | Specification |
|-----------|---------------|
| **Serving** | Loopback only by default (`localhost:18789`) |
| **Remote access** | Tailscale serve optional for off-device access |
| **Expiry** | Default 4 hours, configurable via `--expires` |
| **Auth** | Token in URL path (`/restore/<token>`) prevents unauthorized access |
| **One-time use** | Restore button disables after use or expiry |
| **Gateway restart** | Optional auto-restart after restore, or manual |
| **Notifications** | Telegram/WhatsApp confirmation on receipt and restore |

### CLI Commands

```bash
# Create checkpoint + serve restore page
ocbs checkpoint "before update"
ocbs serve --checkpoint <id> --expires 4h

# Or combined
ocbs checkpoint "before update" --serve --expires 4h

# User receives link, clicks through, agent proceeds

# If needed, restore
ocbs restore --checkpoint <id>
```

### Chat Commands

```
/ocbs checkpoint "before update" --serve --expires 4h
→ Creates checkpoint and serves restore page
→ Sends link to user
→ Agent waits for "proceed" confirmation

/ocbs status
→ Shows checkpoint status and active restore pages
```

### Advantages Over Fully Automated

| Fully Automated | Human-in-the-Loop (Chosen) |
|-----------------|---------------------------|
| Risk of false positives | Human decision = no false restores |
| Complex timeout logic | Simple receipt/confirmation flow |
| User may not know it happened | User sees everything, in control |
| Hard to access from mobile chat | Web page works everywhere |
| May restore when user doesn't want to | Human explicitly clicks restore |

### Future: Fully Automated (Optional Add-on)

After the human-in-the-loop approach is stable, a fully automated mode could be added:

- Tiny LLM check: "Is gateway responding? Are there error logs?"
- Auto-restore only on clear failure signatures
- Still notifies human after restore
- Configurable: `auto-restore: true/false`

This would be an **advanced option**, not the default.

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
- [x] Restore approach: Human-in-the-loop web page (not fully automated)
- [x] Restore page serves on loopback by default (Tailscale optional for remote)

### Pending
- [ ] Incremental format: Content-addressable chunks vs tar+index?
- [ ] Retention policy: How many increments to keep per scope?
- [ ] Package format: NPM or UV?
- [ ] Remote backup support? (deferred to future)
- [ ] Cloud provider integration (S3, B2, etc.)

---

*Created: 2026-02-11*
*Updated: 2026-02-12*

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

### Status: ✅ Ready for Testing (with cron/heartbeat & restore page pending implementation)

---

## Roadmap (Post-MVP)

### Phase 1: Human-in-the-Loop Restore Page
- [ ] Web server for serving restore pages (`ocbs serve`)
- [ ] Token-based authentication in URL paths
- [ ] Interactive page with receipt confirmation and restore button
- [ ] Integration with Telegram/WhatsApp for link delivery
- [ ] Expiry management and one-time-use enforcement
- [ ] CLI: `ocbs checkpoint --serve --expires`
- [ ] Chat: `/ocbs checkpoint --serve`
- [ ] Tests for serve, page rendering, restore flow

### Phase 2: Publishing
- [ ] Publish to UV (PyPI)
- [ ] Publish skill to ClawHub
- [ ] Update documentation for package-based install
- [ ] Add GitHub Project with public roadmap

### Phase 3: Remote Backup
- [ ] Cloud provider integrations (S3, B2, Google Cloud Storage)
- [ ] Remote backup push/pull commands
- [ ] Configurable remote retention policies
- [ ] Encrypted remote transfers

### Phase 4: Advanced Features
- [ ] Fully automated restore (LLM-based health check, optional)
- [ ] Selective file restore (pick files from backup)
- [ ] Backup verification/checksum validation
- [ ] Backup comparison (diff between two backups)
- [ ] Import from existing tar.gz backups
- [ ] Multi-schedule support (different scopes at different intervals)
