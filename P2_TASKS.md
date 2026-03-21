# Phase 2 Tasks: Native Backend Integration

## Overview
Add native backup as a storage source option in OCBS core, extracting and chunking native tar.gz archives while preserving all OCBS features.

## Tasks

### 1. Add BackupSource Enum
**File:** `src/ocbs/core.py`
- [ ] Add `BackupSource` enum with `DIRECT` and `NATIVE` values
- [ ] Update type hints throughout core.py to support BackupSource
- [ ] Add import for new enum

### 2. Implement Native Backup Runner
**File:** `src/ocbs/core.py` in `OCBSBackupEngine` class
- [ ] Add `_run_native_backup(scope: BackupScope) -> Path` method
- [ ] Map BackupScope to native flags:
  - CONFIG → `--only-config`
  - CONFIG_SESSION → `--no-include-workspace`
  - FULL → default (no flags)
- [ ] Run `openclaw backup create` via subprocess
- [ ] Return path to generated tar.gz archive
- [ ] Add error handling and timeout (10 min)
- [ ] Add dry-run support for testing

### 3. Implement Archive Chunker
**File:** `src/ocbs/core.py` in `OCBSBackupEngine` class
- [ ] Add `_chunk_archive(archive_path: Path) -> BackupManifest` method
- [ ] Extract tar.gz to temporary directory
- [ ] Walk extracted files and compute SHA-256 hashes
- [ ] Store chunks in pack files (reuse existing chunk storage)
- [ ] Create BackupManifest with all paths
- [ ] Store manifest in SQLite index
- [ ] Clean up temporary extraction directory
- [ ] Handle large archives (13K+ files) with batch processing

### 4. Update Backup Method
**File:** `src/ocbs/core.py`
- [ ] Modify `backup()` method signature to accept `source: BackupSource` parameter
- [ ] Add conditional logic:
  ```python
  if source == BackupSource.NATIVE:
      archive_path = self._run_native_backup(scope)
      return self._chunk_archive(archive_path)
  else:
      return self._backup_direct(scope)  # Existing logic
  ```
- [ ] Set default `source=BackupSource.DIRECT`

### 5. Add CLI --source Flag
**File:** `src/ocbs/cli.py`
- [ ] Add `--source` argument to `backup` command
- [ ] Map string values to BackupSource enum
- [ ] Add help text explaining native vs direct
- [ ] Validate source value before proceeding

### 6. Add Config Support
**File:** `src/ocbs/core.py`
- [ ] Add `defaultSource` to config schema
- [ ] Implement config loading from `~/.config/ocbs/config.json`
- [ ] Fallback to DIRECT if config not set
- [ ] Add `nativeBackupDir` config option for caching
- [ ] Create native cache directory if configured

### 7. Update Skill Commands
**File:** `src/ocbs/skill.py`
- [ ] Add `--source` parameter to `backup` command in skill
- [ ] Pass source parameter through to core.backup()
- [ ] Update SKILL_MANIFEST with source parameter
- [ ] Add error handling for unavailable native CLI

### 8. Integration Tests
**File:** `tests/test_core.py`
- [ ] Add test for `BackupSource.NATIVE` enum
- [ ] Add test for `_run_native_backup()` with dry-run
- [ ] Add test for `_chunk_archive()` with mock archive
- [ ] Add test for `backup(source=BackupSource.NATIVE)`
- [ ] Add test for config loading with defaultSource

### 9. Documentation Updates
**Files:** `SKILL.md`, `README.md`, `NATIVE_INTEGRATION.md`
- [ ] Document `--source` flag usage in SKILL.md
- [ ] Update README with native backend section
- [ ] Update NATIVE_INTEGRATION.md Phase 2 checklist
- [ ] Add examples for switching between direct/native

## Testing Checklist

- [ ] Native backup generates valid tar.gz archive
- [ ] Archive extraction works without errors
- [ ] Chunking produces deduplicated chunks (SHA-256)
- [ ] BackupManifest records all paths correctly
- [ ] SQLite index stores manifest and chunks
- [ ] CLI `--source native` flag works
- [ ] Skill `backup --source native` works
- [ ] Config `defaultSource=native` works
- [ ] Fallback to direct when native CLI unavailable
- [ ] Dry-run mode for testing without actual backups
- [ ] Large workspace backups (13K+ files) complete successfully

## Deliverables

- [ ] Updated core.py with native backend support
- [ ] Updated cli.py with --source flag
- [ ] Updated skill.py with source parameter
- [ ] Integration tests passing
- [ ] Documentation updated
- [ ] Ready for PR to master

---

*Created: 2026-03-20*
*Branch: feature/phase2-native-backend*
