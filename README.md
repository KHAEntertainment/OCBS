# OCBS - OpenClaw Backup System

[![ClawHub](https://img.shields.io/badge/clawhub?style=flat-square)](https://clawhub.com/skills/ocbs)
[![PyPI](https://img.shields.io/pypi/v/ocbs?style=flat-square)](https://pypi.org/project/ocbs/)

Incremental backup system for OpenClaw with restore capability and native backup integration.

## Installation

### via NPM (Recommended)

```bash
pipx install ocbs
```

### via ClowHub Skill

OCBS is available as a skill in [ClawHub](https://clawhub.com/skills/ocbs):

```bash
clawhub install ocbs
```

## Features

- **Incremental backups** - Content-addressable chunk storage with SHA-256 deduplication
- **Multiple scopes** - config, config+session, config+session+workspace, minimal
- **Checkpoint system** - Create restore points with auto-restore
- **Restore server** - Web UI for human-in-the-loop restore workflow
- **Native backup integration** - Wrap OpenClaw's `openclaw backup create` as storage backend
- **Automatic cleanup** - Retention policy (7 daily, 4 weekly, 12 monthly)
- **Skill interface** - Available as OpenClaw skill for chat commands

## Usage

```bash
# Create incremental backup
ocbs backup --scope config --reason "Before major update"

# Create checkpoint with restore page
ocbs checkpoint "Pre-upgrade snapshot" --serve --expires 4h

# Restore from latest backup
ocbs restore --latest

# Restore from specific checkpoint
ocbs restore --checkpoint 20260211_120000_cp

# List all backups
ocbs list --scope config+session

# Show status
ocbs status

# Clean up old backups
ocbs clean --scope config
```

## Configuration

OCBS stores data in `~/.config/ocbs/`:

```bash
# Backup directory
~/.config/ocbs/backups/

# Database
~/.config/ocbs/ocbs.db

# State files
~/.config/ocbs/state/
```

## Native Backup Integration

OCBS can optionally use OpenClaw's native backup as a storage source:

```bash
# Using native backup as backend
ocbs backup --source native --scope config+session

# Or set as default in config
echo 'defaultSource = "native"' >> ~/.config/ocbs/config.json
```

When using native source, OCBS:
1. Runs `openclaw backup create` to generate tar.gz archive
2. Extracts and chunks the archive into OCBS incremental storage
3. All OCBS features work (checkpoints, auto-cleanup, etc.)

## Development

```bash
# Install development dependencies
pip install -e '.[dev]'

# Run tests
pytest

# Build distribution
python -m build

# Install locally for testing
pip install -e .
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details

## Links

- [GitHub Repository](https://github.com/KHAEntertainment/OCBS)
- [ClawHub Skill](https://clawhub.com/skills/ocbs)
- [Issues](https://github.com/KHAEntertainment/OCBS/issues)
