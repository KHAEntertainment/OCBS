"""
Integration tests for OCBS CLI and full workflow.
"""

import os
import tempfile
from pathlib import Path
from click.testing import CliRunner
from ocbs.cli import main
from ocbs.core import BackupSource, BackupScope, OCBSCore


class TestCLI:
    """Test CLI interface."""
    
    def test_cli_help(self):
        """Test CLI help output."""
        runner = CliRunner()
        result = runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'OpenClaw Backup System' in result.output
    
    def test_cli_status(self):
        """Test status command."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ['--state-dir', tmpdir, 'status'])
            assert result.exit_code == 0
            assert 'OCBS Status' in result.output
    
    def test_cli_list_no_backups(self):
        """Test list command with no backups."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ['--state-dir', tmpdir, 'list'])
            assert result.exit_code == 0
            assert 'No backups found' in result.output
    
    def test_cli_clean(self):
        """Test clean command."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ['--state-dir', tmpdir, 'clean'])
            assert result.exit_code == 0
            assert 'Cleanup completed' in result.output


class TestFullWorkflow:
    """Test full backup/restore workflow."""
    
    def test_backup_and_list(self):
        """Test backup creation and listing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            home_dir = Path(tmpdir)
            os.environ['HOME'] = str(home_dir)
            
            openclaw_home = home_dir / ".openclaw"
            openclaw_home.mkdir()
            config_dir = openclaw_home / "config"
            config_dir.mkdir()
            (config_dir / "test.json").write_text('{"test": true}')
            
            # Create backup
            runner = CliRunner()
            result = runner.invoke(main, ['--state-dir', tmpdir, 'backup', '--scope', 'config', '--reason', 'test'])
            assert result.exit_code == 0
            assert 'Backup created' in result.output
            
            # List backups
            result = runner.invoke(main, ['--state-dir', tmpdir, 'list'])
            assert result.exit_code == 0
            assert 'test' in result.output
    
    def test_checkpoint_creation(self):
        """Test checkpoint creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir)
            os.environ['HOME'] = str(home_dir)
            
            openclaw_home = home_dir / ".openclaw"
            openclaw_home.mkdir()
            config_dir = openclaw_home / "config"
            config_dir.mkdir()
            (config_dir / "test.json").write_text('{"test": true}')
            
            # Create backup first
            runner = CliRunner()
            runner.invoke(main, ['--state-dir', tmpdir, 'backup', '--scope', 'config'])
            
            # Create checkpoint
            result = runner.invoke(main, ['--state-dir', tmpdir, 'checkpoint', 'before update'])
            assert result.exit_code == 0
            assert 'Checkpoint created' in result.output
            assert '_cp' in result.output

    def test_backup_source_flag(self, monkeypatch):
        """Test backup --source flag reaches the core."""

        runner = CliRunner()
        captured = {}

        def fake_backup(self, scope, reason="", source=None):
            captured["scope"] = scope
            captured["reason"] = reason
            captured["source"] = source
            return type(
                "Manifest",
                (),
                {"backup_id": "backup-1", "paths": ["a"], "scope": scope, "reason": reason},
            )()

        monkeypatch.setattr(OCBSCore, "backup", fake_backup)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                main,
                [
                    '--state-dir',
                    tmpdir,
                    'backup',
                    '--scope',
                    'config',
                    '--source',
                    'native',
                    '--reason',
                    'native test',
                ],
            )

        assert result.exit_code == 0
        assert captured["scope"] == BackupScope.CONFIG
        assert captured["reason"] == "native test"
        assert captured["source"] == BackupSource.NATIVE
        assert "Source: native" in result.output


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
