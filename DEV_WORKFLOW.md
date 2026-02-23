# OCBS Development Workflow

This document describes the safe development workflow for OCBS.

## Directory Structure

```
~/dev/ocbs/          # Cloned from GitHub (development)
~/.config/ocbs/       # Local state (10MB, currently used by installed skill)
~/.openclaw/skills/ocbs_backup/  # Installed skill (DO NOT EDIT)
~/projects/ocbs-improvements/  # Notes + improvements (old work)
```

## Development Flow

### 1. Clone or Pull Latest

```bash
cd ~/dev/ocbs
git pull origin main
```

### 2. Make Changes

Edit code in `~/dev/ocbs/`

### 3. Test Locally

```bash
# Create temporary state directory for testing
mkdir -p /tmp/ocbs-test

# Run OCBS with test state
cd ~/dev/ocbs
OCBS_STATE_DIR=/tmp/ocbs-test python3 -m ocbs.core backup --scope config
```

### 4. Install Test Version

```bash
# Create a test skill installation
mkdir -p ~/.openclaw/skills/ocbs_backup-test
cp -r ~/dev/ocbs/skill ~/.openclaw/skills/ocbs_backup-test
cp -r ~/dev/ocbs/src ~/.openclaw/skills/ocbs_backup-test/

# Edit skill.json to use test name (optional)
```

### 5. Test via OpenClaw

Use `/ocbs backup --scope config` commands in OpenClaw with the test skill.

### 6. Verify Then Cleanup

```bash
# Remove test skill
rm -rf ~/.openclaw/skills/ocbs_backup-test

# Clean test state
rm -rf /tmp/ocbs-test
```

## Deployment Flow

### Option A: Publish to ClawHub (Recommended)

```bash
cd ~/dev/ocbs
npm version patch  # Update version
git commit -am "Release v0.x.y"
git tag v0.x.y
git push origin main --tags

# Publish via ClawHub (if configured)
clawhub publish
```

### Option B: Direct Skill Install (Quick Testing)

```bash
# Backup existing installed skill first
cp -r ~/.openclaw/skills/ocbs_backup ~/.openclaw/skills/ocbs_backup.backup

# Install dev version
cp -r ~/dev/ocbs/skill ~/.openclaw/skills/ocbs_backup
cp -r ~/dev/ocbs/src ~/.openclaw/skills/ocbs_backup/

# Test and restore if needed
rm -rf ~/.openclaw/skills/ocbs_backup
mv ~/.openclaw/skills/ocbs_backup.backup ~/.openclaw/skills/ocbs_backup
```

## Key Rules

- ✅ **NEVER edit `~/.openclaw/skills/ocbs_backup/` directly**
- ✅ **Always test in isolated environment** before deploying
- ✅ **Keep backups** of installed versions (`~/.openclaw/skills/ocbs_backup.backup`)
- ✅ **Commit changes** to `~/dev/ocbs/` regularly
- ✅ **Use version tags** for releases

## Current Status

- **Installed:** `~/.openclaw/skills/ocbs_backup/` (v0.1.0)
- **Dev:** `~/dev/ocbs/` (cloned from main)
- **Production:** Skill published via ClawHub (if available)
