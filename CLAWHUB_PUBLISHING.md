# OCBS - ClawHub Publishing

## Overview

OCBS is packaged and published to [ClawHub](https://clawhub.com/skills/ocbs) via NPM.

## Installation for Users

```bash
pipx install ocbs
```

## Setup Instructions for Maintainer

### 1. NPM Token Setup

1. Generate your NPM token:
   ```bash
   npm token create
   ```

2. Add token to GitHub repository as a secret:
   - Go to: https://github.com/KHAEntertainment/OCBS/settings/secrets/actions/new
   - Name: `NPM_TOKEN`
   - Value: [your NPM token from step 1]

### 2. Version Updates

When releasing a new version:

1. Update version in `pyproject.toml`:
   ```toml
   [project]
   version = "0.2.0"  # Next version
   ```

2. Commit and push:
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.2.0"
   git push origin master
   ```

3. Tag the release:
   ```bash
   git tag -a v0.2.0 master
   git push origin v0.2.0
   ```

4. GitHub Actions will automatically:
   - Build the package
   - Publish to NPM under the same version
   - Update ClawHub skill page

### 3. Manual Publish (if needed)

If GitHub Actions fail, you can publish manually:

```bash
# Install ClawHub
pip install clawhub

# Publish to ClawHub
clawhub publish
```

## Package Structure

```
ocbs/
├── .github/
│   └── workflows/
│       └── npm-publish.yml      # GitHub Actions for auto-publishing
├── src/
│   └── ocbs/
│       ├── __init__.py
│       ├── cli.py
│       ├── core.py
│       ├── skill.py
│       └── serve.py
├── skill/
│   └── skill.json              # OpenClaw skill manifest
├── pyproject.toml                 # Build configuration
├── LICENSE
├── README.md
└── SKILL.md                        # ClawHub skill documentation
```

## ClawHub Skill Manifest

The `skill/skill.json` file defines the OpenClaw skill interface:

- Commands: `backup`, `restore`, `status`, `list`, `clean`, `checkpoint`, `serve`
- Parameters: scopes, reasons, targets, expiry, host
- Capabilities: cron, heartbeat, auto-restore

## Testing

Before releasing:

```bash
# Install in test environment
pipx install --python 3.11 ocbs-test

# Run test suite
pytest tests/ -v --cov

# Verify skill manifest
python -m ocbs.skill
```

## Release Checklist

- [ ] Version updated in `pyproject.toml`
- [ ] Changelog updated in README.md
- [ ] All tests passing
- [ ] Documentation updated
- [ ] NPM token in GitHub secrets
- [ ] Tag pushed with format `vX.Y.Z`
- [ ] GitHub Actions workflow verified

## Troubleshooting

**Publish fails with "403 Forbidden":**
- Check NPM_TOKEN secret is set correctly
- Verify token has publish permissions

**Package not building:**
- Ensure `pyproject.toml` has `[build-system]` configured
- Check all dependencies are valid versions

---

*For questions or issues, [open an issue](https://github.com/KHAEntertainment/OCBS/issues)*
