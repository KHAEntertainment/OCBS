# OCBS Phase 2: Native Backend Integration

## Context
This task implements Phase 2 of OCBS native backup integration (see NATIVE_INTEGRATION.md). Phase 1 (skill wrapping) is complete and committed to master (e7fd874).

## Task Description
Add native backup as a storage source option in OCBS core engine. When users run `ocbs backup --source native`, OCBS will:

1. Run `openclaw backup create` to generate a tar.gz archive
2. Extract the archive to a temporary directory
3. Walk the extracted files and chunk them (SHA-256 deduplication)
4. Store chunks in pack files (reusing existing storage)
5. Create BackupManifest and store in SQLite index

This preserves all OCBS features (incremental, checkpoints, auto-cleanup) while leveraging native's reliable tar.gz generation.

## Working Directory
```
/tmp/ocbs-phase2/  # Git worktree for feature/phase2-native-backend branch
```

## Task Breakdown

See `P2_TASKS.md` for full checklist. Key components:

1. **BackupSource Enum** - Add DIRECT/NATIVE enum to core.py
2. **Native Backup Runner** - `_run_native_backup()` method to run openclaw backup create
3. **Archive Chunker** - `_chunk_archive()` method to extract and chunk archives
4. **CLI Flag** - Add `--source` flag to backup command
5. **Config Support** - `defaultSource` and `nativeBackupDir` config options
6. **Skill Updates** - Pass `--source` parameter through to core
7. **Tests** - Integration tests for native path
8. **Documentation** - Update SKILL.md, README.md

## Implementation Notes

- Reuse existing chunk storage (`_store_chunk()`, `_write_pack_file()`)
- Use batch processing for large archives (13K+ files) to avoid file descriptor limits
- Handle subprocess errors and timeouts (10 minutes for backup)
- Add dry-run support for testing without creating backups
- Fallback to DIRECT source if native CLI unavailable

## Testing Checklist
- Native backup generates valid tar.gz
- Archive extraction works
- Chunking produces deduplicated chunks
- BackupManifest records paths correctly
- CLI `--source native` works
- Skill `backup --source native` works
- Config `defaultSource=native` works
- Large workspace backups (13K+ files) succeed

## Deliverables
- Updated core.py with native backend
- Updated cli.py with --source flag
- Updated skill.py with source parameter
- Integration tests passing
- Documentation updated
- Ready for PR to master

## Branch Info
- Base branch: master (commit e7fd874)
- Feature branch: feature/phase2-native-backend
- Worktree: /tmp/ocbs-phase2

## Reference
- Integration plan: `/tmp/ocbs-phase2/NATIVE_INTEGRATION.md`
- Task checklist: `/tmp/ocbs-phase2/P2_TASKS.md`
- GitHub Issue: https://github.com/KHAEntertainment/OCBS/issues/6
