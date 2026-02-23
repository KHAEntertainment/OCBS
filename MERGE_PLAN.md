# OCBS Merge Plan

## Source: Feb 15 Improvements

**Location:** `~/projects/ocbs-improvements/`
**Status:** Unmerged changes from 2026-02-15 session

### Implemented Features

1. **Restore page UI with Step 1/Step 2 flow**
   - HTML UI for restore workflow
   - Timer display showing "Work underway"
   - File-based proceed notification system

2. **Two restart options**
   - "Restart Gateway" button
   - "Restore Backup" button

3. **File-based proceed notification**
   - JSON files in `~/.config/ocbs/proceed_notifications/`

4. **MINIMAL backup scope** (~10 files vs 837)
   - New limited scope concept (likely adds `BackupScope.MINIMAL`)
   - Critical files only for Pi storage constraints

5. **Webhook notification** (needs gateway hook config fix)
   - Not completed yet — depends on OpenClaw gateway

### GitHub Reference
- PR: https://github.com/KHAEntertainment/OCBS/pull/1
- Issue: https://github.com/KHAEntertainment/OCBS/issues/2

---

## Current Dev Repo State

**Location:** `~/dev/ocbs/` (fresh clone from main branch)

### Core Files

| File | Lines | Notes |
|-------|--------|--------|
| `core.py` | 376 | Has BackupScope enum (3 levels) |
| `cli.py` | ~140 | CLI commands (backup, restore, status, list, clean, checkpoint) |
| `skill.py` | ~100 | Skill manifest and command handlers |
| `integration.py` | ~180 | Cron and heartbeat integration |
| `__init__.py` | ~10 | Package init |

### Missing Features (need to merge)

- [ ] MINIMAL scope in BackupScope enum
- [ ] Restore page UI HTML/templates
- [ ] "Work underway" timer logic
- [ ] Step 1/Step 2 flow handler
- [ ] File-based proceed notification system
- [ ] Webhook integration

---

## Merge Strategy

### Option A: Clean Merge (Recommended)

1. **Review current main branch** on GitHub
2. **Pull latest changes**
   ```bash
   cd ~/dev/ocbs && git pull origin main
   ```
3. **Identify conflicts** between Feb 15 work and any upstream changes
4. **Resolve conflicts** manually or with merge tool
5. **Test thoroughly** before merging

### Option B: Branch-Based Merge

1. **Create feature branch** for Feb 15 improvements
   ```bash
   cd ~/dev/ocbs
   git checkout -b feature/feb15-improvements
   ```
2. **Apply changes** to feature branch
3. **Merge into main**
   ```bash
   git checkout main
   git merge feature/feb15-improvements
   ```

---

## Questions to Resolve

1. **MINIMAL scope:**
   - What files should be included? (10 critical files vs 837 all files)
   - Is this a new BackupScope.MINIMAL value?

2. **Restore page:**
   - Where is the HTML/template?
   - How does it integrate with skill commands?

3. **Timer logic:**
   - Is this in skill.py or separate handler?

4. **Proceed notification:**
   - Already seeing JSON files in `~/.config/ocbs/proceed_notifications/`
   - Is this just skill side or requires core changes?

5. **Webhook integration:**
   - What gateway hook format is expected?
   - Does OCBS need to register hooks with OpenClaw?

---

## Next Steps

1. **Answer questions above** to clarify what needs to be merged
2. **Choose merge strategy** (A or B)
3. **Implement missing features** in dev branch
4. **Test locally** with `OCBS_STATE_DIR=/tmp/ocbs-test`
5. **Version bump and publish** when ready
