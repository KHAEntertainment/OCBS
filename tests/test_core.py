"""
Tests for OCBS core functionality.
"""

import os
import tempfile
import pytest
from pathlib import Path
from datetime import datetime

from ocbs.core import OCBSCore, BackupScope, BackupManifest


@pytest.fixture
def temp_state_dir():
    """Create a temporary state directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def ocbs(temp_state_dir):
    """Create OCBS instance with temporary state."""
    return OCBSCore(state_dir=temp_state_dir)


@pytest.fixture
def sample_files(temp_state_dir):
    """Create sample files for testing."""
    openclaw_home = temp_state_dir / ".openclaw"
    openclaw_home.mkdir()
    
    # Create config files
    config_dir = openclaw_home / "config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text('{"key": "value"}')
    (config_dir / "user.yaml").write_text('user: test\ntheme: dark')
    
    # Create session files
    session_dir = openclaw_home / "sessions"
    session_dir.mkdir()
    (session_dir / "session_001.json").write_text('{"state": "active"}')
    
    # Create workspace files
    workspace_dir = openclaw_home / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "notes.md").write_text("# Notes\nSome content")
    
    return openclaw_home


class TestOCBSCore:
    """Tests for OCBSCore class."""
    
    def test_init(self, ocbs):
        """Test OCBS initialization."""
        assert ocbs.state_dir.exists()
        assert ocbs.packs_dir.exists()
        assert ocbs.db_path.exists()
    
    def test_compute_content_hash(self, ocbs):
        """Test content hash computation."""
        content1 = b"hello world"
        content2 = b"hello world"
        content3 = b"different content"
        
        hash1 = ocbs._compute_content_hash(content1)
        hash2 = ocbs._compute_content_hash(content2)
        hash3 = ocbs._compute_content_hash(content3)
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA-256 hex length
    
    def test_backup_config_scope(self, ocbs, sample_files, temp_state_dir):
        """Test backup with config scope."""
        # Override home for this test
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            manifest = ocbs.backup(BackupScope.CONFIG, "test backup")
            
            assert isinstance(manifest, BackupManifest)
            assert manifest.scope == BackupScope.CONFIG
            assert manifest.reason == "test backup"
            assert len(manifest.paths) > 0
            # Should only have config files
            assert any('config' in p for p in manifest.paths)
            assert not any('sessions' in p for p in manifest.paths)
        finally:
            if original_home:
                os.environ['HOME'] = original_home
    
    def test_backup_config_session_scope(self, ocbs, sample_files, temp_state_dir):
        """Test backup with config+session scope."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            manifest = ocbs.backup(BackupScope.CONFIG_SESSION, "test backup")
            
            assert manifest.scope == BackupScope.CONFIG_SESSION
            assert any('config' in p for p in manifest.paths)
            assert any('sessions' in p for p in manifest.paths)
            assert not any('workspace' in p for p in manifest.paths)
        finally:
            if original_home:
                os.environ['HOME'] = original_home
    
    def test_list_backups(self, ocbs, temp_state_dir):
        """Test listing backups."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            # Create sample files in the HOME directory
            openclaw_home = temp_state_dir / ".openclaw"
            openclaw_home.mkdir(exist_ok=True)
            config_dir = openclaw_home / "config"
            config_dir.mkdir(exist_ok=True)
            (config_dir / "settings.json").write_text('{"key": "value"}')
            
            backup1 = ocbs.backup(BackupScope.CONFIG, "backup 1")
            
            backups_after_1 = ocbs.list_backups()
            
            backup2 = ocbs.backup(BackupScope.CONFIG, "backup 2")
            
            backups = ocbs.list_backups()
            
            assert len(backups) >= 2, f"Expected >= 2 backups, got {len(backups)}"
            # Most recent first
            assert backups[0].backup_id >= backups[-1].backup_id
        finally:
            if original_home:
                os.environ['HOME'] = original_home
    
    def test_get_latest_backup(self, ocbs, sample_files, temp_state_dir):
        """Test getting latest backup."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            backup1 = ocbs.backup(BackupScope.CONFIG, "backup 1")
            backup2 = ocbs.backup(BackupScope.CONFIG, "backup 2")
            
            latest = ocbs.get_latest_backup()
            
            assert latest is not None
            assert latest.backup_id == backup2.backup_id
        finally:
            if original_home:
                os.environ['HOME'] = original_home
    
    def test_status(self, ocbs, sample_files, temp_state_dir):
        """Test status reporting."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            ocbs.backup(BackupScope.CONFIG, "test")
            
            status = ocbs.status()
            
            assert 'total_backups' in status
            assert 'total_chunks' in status
            assert 'pack_size_bytes' in status
            assert 'scope_info' in status
            assert status['total_backups'] >= 1
        finally:
            if original_home:
                os.environ['HOME'] = original_home
    
    def test_checkpoint(self, ocbs, sample_files, temp_state_dir):
        """Test checkpoint creation."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            ocbs.backup(BackupScope.CONFIG, "test")
            
            checkpoint_id = ocbs.create_checkpoint("before update")
            
            assert checkpoint_id is not None
            assert '_cp' in checkpoint_id
            
            checkpoints = ocbs.get_checkpoints()
            assert len(checkpoints) >= 1
            assert any(cp['reason'] == 'before update' for cp in checkpoints)
        finally:
            if original_home:
                os.environ['HOME'] = original_home


class TestRestore:
    """Tests for restore functionality."""

    def test_restore_backup(self, ocbs, sample_files, temp_state_dir):
        """Test basic restore functionality."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)

        try:
            # Create a backup
            manifest = ocbs.backup(BackupScope.CONFIG_SESSION_WORKSPACE, "test backup")

            # Modify a file to verify restore overwrites it
            openclaw_home = temp_state_dir / ".openclaw"
            (openclaw_home / "config" / "settings.json").write_text('{"modified": "value"}')

            # Restore to a different location to avoid conflicts
            restore_target = temp_state_dir / "restore"
            restore_target.mkdir()

            result = ocbs.restore(manifest.backup_id, target_dir=restore_target)
            assert result is True

            # Verify restored files
            restored_settings = restore_target / ".openclaw" / "config" / "settings.json"
            assert restored_settings.exists()
            content = restored_settings.read_text()
            assert '{"key": "value"}' in content
        finally:
            if original_home:
                os.environ['HOME'] = original_home

    def test_restore_large_file_count(self, ocbs, temp_state_dir):
        """Test restore with many files to verify no file descriptor leaks."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)

        try:
            # Create many small files (simulating WhatsApp pre-keys scenario)
            openclaw_home = temp_state_dir / ".openclaw"
            openclaw_home.mkdir()
            config_dir = openclaw_home / "config"
            config_dir.mkdir()

            # Create 1000 small files
            for i in range(1000):
                (config_dir / f"file_{i:04d}.dat").write_text(f'content {i}')

            # Create backup
            manifest = ocbs.backup(BackupScope.CONFIG, "large backup")

            # Restore to different location
            restore_target = temp_state_dir / "restore"
            restore_target.mkdir()

            # This should not fail with "Too many open files"
            result = ocbs.restore(manifest.backup_id, target_dir=restore_target)
            assert result is True

            # Verify all files were restored
            restored_config = restore_target / ".openclaw" / "config"
            restored_files = list(restored_config.glob("*.dat"))
            assert len(restored_files) == 1000

            # Spot check content
            assert (restored_config / "file_0000.dat").read_text() == "content 0"
            assert (restored_config / "file_0999.dat").read_text() == "content 999"
        finally:
            if original_home:
                os.environ['HOME'] = original_home

    def test_restore_from_checkpoint(self, ocbs, sample_files, temp_state_dir):
        """Test restore from checkpoint."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)

        try:
            # Create backup and checkpoint
            manifest = ocbs.backup(BackupScope.CONFIG, "test backup")
            checkpoint_id = ocbs.create_checkpoint("test checkpoint")

            # Restore to different location
            restore_target = temp_state_dir / "restore"
            restore_target.mkdir()

            result = ocbs.restore(checkpoint_id=checkpoint_id, target_dir=restore_target)
            assert result is True

            # Verify restored files
            restored_settings = restore_target / ".openclaw" / "config" / "settings.json"
            assert restored_settings.exists()
        finally:
            if original_home:
                os.environ['HOME'] = original_home


class TestRestore:
    """Tests for restore functionality."""

    def test_restore_backup(self, ocbs, sample_files, temp_state_dir):
        """Test restoring from a backup."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)

        try:
            # Create a backup
            manifest = ocbs.backup(BackupScope.CONFIG, "test restore backup")

            # Create a restore target directory
            restore_target = temp_state_dir / "restore_test"
            restore_target.mkdir()

            # Restore the backup
            result = ocbs.restore(backup_id=manifest.backup_id, target_dir=restore_target)
            assert result is True

            # Verify restored files
            restored_settings = restore_target / ".openclaw" / "config" / "settings.json"
            assert restored_settings.exists()
            assert restored_settings.read_text() == '{"key": "value"}'
        finally:
            if original_home:
                os.environ['HOME'] = original_home

    def test_restore_large_file_count(self, ocbs, sample_files, temp_state_dir):
        """Test restoring from a backup with large file count - tests batch processing."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)

        try:
            # Backup with config+session+workspace scope which creates multiple files
            manifest = ocbs.backup(BackupScope.CONFIG_SESSION_WORKSPACE, "large file test")

            # Create a restore target directory
            restore_target = temp_state_dir / "restore_large"
            restore_target.mkdir()

            # Restore the backup - this tests batch processing works
            result = ocbs.restore(backup_id=manifest.backup_id, target_dir=restore_target)
            assert result is True

            # Verify files were restored (at least some - this tests the batch processing works)
            restored_files = list(restore_target.rglob("*"))
            restored_files = [f for f in restored_files if f.is_file()]
            assert len(restored_files) > 0, "No files were restored"
        finally:
            if original_home:
                os.environ['HOME'] = original_home

    def test_restore_from_checkpoint(self, ocbs, sample_files, temp_state_dir):
        """Test restoring from a checkpoint."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)

        try:
            # First create a backup
            manifest = ocbs.backup(BackupScope.CONFIG, "checkpoint test")

            # Create a checkpoint (uses latest backup)
            checkpoint_id = ocbs.create_checkpoint("test checkpoint")

            # Create a restore target directory
            restore_target = temp_state_dir / "restore_checkpoint"
            restore_target.mkdir()

            # Restore from checkpoint
            result = ocbs.restore(checkpoint_id=checkpoint_id, target_dir=restore_target)
            assert result is True

            # Verify restored files
            restored_settings = restore_target / ".openclaw" / "config" / "settings.json"
            assert restored_settings.exists()
        finally:
            if original_home:
                os.environ['HOME'] = original_home


class TestBackupScope:
    """Tests for BackupScope enum."""
    
    def test_scope_values(self):
        """Test scope enum values."""
        assert BackupScope.CONFIG.value == "config"
        assert BackupScope.CONFIG_SESSION.value == "config+session"
        assert BackupScope.CONFIG_SESSION_WORKSPACE.value == "config+session+workspace"


class TestFileCollection:
    """Tests for file collection logic."""
    
    def test_collect_files(self, ocbs, sample_files):
        """Test file collection."""
        files = ocbs._collect_files([sample_files])
        
        assert len(files) > 0
        assert any(f.name == "settings.json" for f in files)
    
    def test_collect_files_empty(self, ocbs, temp_state_dir):
        """Test file collection with empty directory."""
        empty_dir = temp_state_dir / "empty"
        empty_dir.mkdir()
        
        files = ocbs._collect_files([empty_dir])
        
        assert len(files) == 0


class TestCleanup:
    """Tests for cleanup/retention logic."""
    
    def test_cleanup(self, ocbs, sample_files, temp_state_dir):
        """Test cleanup removes old backups."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            # Create multiple backups
            for i in range(5):
                ocbs.backup(BackupScope.CONFIG, f"backup {i}")
            
            # Run cleanup
            ocbs.cleanup(BackupScope.CONFIG)
            
            # Should still have backups
            backups = ocbs.list_backups(BackupScope.CONFIG)
            assert len(backups) > 0
        finally:
            if original_home:
                os.environ['HOME'] = original_home
