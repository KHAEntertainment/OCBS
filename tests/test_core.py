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
