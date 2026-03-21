# OCBS Native Backup Integration Plan

**Status:** Phase 2 Implemented  
**Created:** 2026-03-20  
**Priority:** Medium

## Background

OpenClaw v2026.3.8 introduced a built-in `openclaw backup` command that creates tar.gz archives with manifests. OCBS already provides incremental, content-addressable backups with advanced features (checkpoints, auto-restore, auto-cleanup, restore server).

This document outlines integration strategies for making OCBS work with OpenClaw's native backup system, similar to how ClawVault integrates modularly with OpenClaw credential management.

## OpenClaw Native Backup Overview

```bash
# Create backup
openclaw backup create                    # Full tar.gz archive
openclaw backup create --verify           # Create + validate
openclaw backup create --only-config      # Minimal: config only
openclaw backup create --no-include-workspace  # Exclude workspaces
openclaw backup create --dry-run --json   # Preview without writing

# Verify backup
openclaw backup verify <archive>          # Validate structure + manifest
```

**Characteristics:**
- **Format:** Full `.tar.gz` archives (not incremental)
- **Scope:** config, credentials, sessions, workspaces (optional)
- **Output:** Timestamped archives with embedded `manifest.json`
- **Bypasses config preflight** for recovery scenarios
- **No deduplication** - each backup is full copy

## OCBS Current Architecture

**Characteristics:**
- **Format:** Incremental, content-addressable chunks (SHA-256)
- **Storage:** SQLite index + pack files (~16MB for 5 backups)
- **Features:**
  - Checkpoints with auto-restore
  - Auto-cleanup (7 daily, 4 weekly, 12 monthly)
  - Restore server with web UI
  - Webhook notifications
  - Dual interface (skill + CLI)
- **Isolation:** State in `~/.config/ocbs/` (separate from `~/.openclaw/`)

## Integration Options

### Option 1: Coexistence (Current State) ✅

Both systems run independently; user chooses based on use case.

**Pros:**
- Zero integration work
- Max flexibility for users
- OCBS remains pure incremental
- Can use native for one-off full backups before upgrades

**Cons:**
- No unified interface
- Users must understand both systems
- Duplicate storage if both used heavily

**Use Cases:**
- Native: Pre-upgrade snapshots, archive exports
- OCBS: Automated daily backups, rollback guardrails

---

### Option 2: Native as OCBS Storage Backend ⭐ **RECOMMENDED**

OCBS optionally wraps OpenClaw native backups as a storage source, while preserving OCBS features.

**Architecture:**

```
OCBS Core Layer
    ├── Source A: Direct file reads (current) ──→ Chunks + Index
    └── Source B: Native archives (new) ──→ Extract + Chunk + Index
         (runs openclaw backup create internally)
```

**Implementation:**

```python
# New backup source in core.py
class BackupSource(Enum):
    DIRECT = "direct"      # Current: read files directly
    NATIVE = "native"       # New: wrap openclaw backup create

# In OCBSBackupEngine.backup()
def backup(self, scope: BackupScope, source: BackupSource = BackupSource.DIRECT):
    if source == BackupSource.NATIVE:
        # Run native backup
        archive_path = self._run_native_backup(scope)
        # Extract and chunk archive
        return self._chunk_archive(archive_path)
    else:
        # Current direct file read path
        return self._backup_direct(scope)
```

**Pros:**
- OCBS keeps all features (checkpoints, auto-restore, auto-cleanup, UI)
- Leverages native's reliable tar.gz generation
- User can switch between direct/native per backup
- Native handles path resolution and manifest generation
- OCBS adds incremental layer on top of native archives

**Cons:**
- Requires native backup CLI to be available
- Slightly more complex backup path (two-stage)
- Temporary storage during extraction

**Configuration:**

```bash
# Use native as source for this backup
ocbs backup --scope config --source native

# Set default in ~/.config/ocbs/config.json
{
  "defaultSource": "native",
  "nativeBackupDir": "/tmp/ocbs-native-cache"
}
```

**Skill Commands:**

```bash
/ocbs backup --source native              # Use native generator
/ocbs backup --source direct              # Direct file reads (current)
/ocbs config --set defaultSource=native   # Set default
```

---

### Option 3: Skill Wrapping (Temporary Placeholder)

Expose native backup through OCBS skill without changing core engine.

**Implementation:**

```python
# In skill.py - add native backup commands
@skill.command("native-backup")
def native_backup(scope: str = "config"):
    """Run OpenClaw native backup via OCBS skill."""
    args = ["openclaw", "backup", "create"]
    if scope == "config":
        args.append("--only-config")
    elif scope == "config+session":
        args.append("--no-include-workspace")
    
    result = subprocess.run(args, capture_output=True, text=True)
    return f"Native backup created: {result.stdout}"

@skill.command("native-verify")
def native_verify(archive: str):
    """Verify a native backup archive."""
    result = subprocess.run(
        ["openclaw", "backup", "verify", archive],
        capture_output=True, text=True
    )
    return result.stdout or result.stderr
```

**Pros:**
- Quick to implement (no core changes)
- Unified skill interface
- Can schedule native backups via OCBS cron

**Cons:**
- No OCBS features (incremental, checkpoints, auto-cleanup)
- Native archives remain full-size tar.gz
- No deduplication between native backups

**Timeline:** Implement first as Option 3, then migrate to Option 2 when native backend is ready.

---

## Proposed Implementation Plan

### Phase 1: Quick Win (Option 3) - 1-2 days
- [ ] Add `native-backup` command to skill.py
- [ ] Add `native-verify` command to skill.py
- [ ] Update SKILL.md with native command docs
- [ ] Add cron integration for scheduled native backups
- [ ] Test native backup wrapping

### Phase 2: Native Backend (Option 2) - 3-5 days
- [x] Add `BackupSource.NATIVE` enum to core.py
- [x] Implement `_run_native_backup()` method
- [x] Implement `_chunk_archive()` for extraction
- [x] Add `--source` flag to CLI backup command
- [x] Add `defaultSource` config option
- [x] Update skill commands to support `--source` parameter
- [x] Integration tests for native source path
- [x] Documentation updates

### Phase 3: Unified Experience - 2-3 days
- [ ] Hybrid mode: direct for config, native for workspace
- [ ] Smart source selection based on scope/schedule
- [ ] Native archive caching between backups
- [ ] Performance comparison metrics

---

## Open Questions

1. **Caching strategy for native archives:**
   - Keep extracted chunks between runs?
   - Cache tar.gz in `~/.config/ocbs/native-cache/`?
   - Tradeoff: disk usage vs backup speed

2. **Error handling when native CLI unavailable:**
   - Fallback to direct source automatically?
   - Fail fast with clear error?
   - Configurable fallback policy?

3. **Version compatibility:**
   - Does native backup format change between OpenClaw versions?
   - Need OCBS to detect and adapt to different manifest schemas?

4. **Webhook integration with native backups:**
   - Should OCBS send webhooks for native backup completion?
   - Only when wrapped by OCBS, or also for standalone native backups?

---

## Related Issues

- GitHub Issue #6 (Feature Request: Native Backup Integration)
- OpenClaw CLI docs: https://docs.openclaw.ai/cli/backup

---

## Decision Matrix

| Criteria | Option 1 | Option 2 | Option 3 |
|----------|----------|----------|----------|
| Implementation effort | Zero | Medium | Low |
| User complexity | High | Medium | Low |
| Feature preservation | N/A (both) | Full | None |
| Incremental storage | ✅ OCBS only | ✅ Hybrid | ❌ Full tar.gz |
| Unified interface | ❌ | ✅ | ⚠️ Partial |
| Development timeline | N/A | 1-2 weeks | 1-2 days |

**Recommendation:** Start with Option 3 (quick win), migrate to Option 2 for full feature set.

---

*Document owner: Billy Brenner*  
*Last updated: 2026-03-20*
