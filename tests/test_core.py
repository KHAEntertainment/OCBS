"""
Tests for OCBS core functionality.
"""

import os
import json
import sqlite3
import tarfile
import tempfile
import pytest
from pathlib import Path
from datetime import datetime

from ocbs.core import BackupManifest, BackupScope, BackupSource, OCBSCore


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

    def test_run_native_backup_dry_run(self, ocbs, monkeypatch):
        """Test native backup dry-run path."""

        class Result:
            returncode = 0
            stdout = json.dumps({"archive": "/tmp/native-backup.tar.gz"})
            stderr = ""

        def fake_run(args, capture_output, text, timeout, check):
            assert "--dry-run" in args
            assert "--json" in args
            return Result()

        monkeypatch.setattr("subprocess.run", fake_run)

        archive = ocbs._run_native_backup(BackupScope.CONFIG, dry_run=True)
        assert archive == Path("/tmp/native-backup.tar.gz")

    def test_chunk_archive(self, ocbs, temp_state_dir):
        """Test chunking a native archive into OCBS storage."""

        archive_path = temp_state_dir / "native.tar.gz"
        source_dir = temp_state_dir / "archive-src"
        source_dir.mkdir()
        (source_dir / ".openclaw").mkdir()
        (source_dir / ".openclaw" / "config").mkdir()
        (source_dir / ".openclaw" / "config" / "settings.json").write_text('{"test": true}')
        (source_dir / "manifest.json").write_text('{"ignored": true}')

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(source_dir / ".openclaw", arcname=".openclaw")
            tar.add(source_dir / "manifest.json", arcname="manifest.json")

        manifest = ocbs._chunk_archive(archive_path, BackupScope.CONFIG, "native test")

        assert manifest.scope == BackupScope.CONFIG
        assert ".openclaw/config/settings.json" in manifest.paths
        assert "manifest.json" not in manifest.paths
        assert len(manifest.chunk_ids) == 1

    def test_backup_native_falls_back_to_direct(self, ocbs, sample_files, temp_state_dir, monkeypatch):
        """Test native source falls back to direct when CLI is unavailable."""

        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)

        def fake_native(scope, dry_run=False):
            raise FileNotFoundError("missing openclaw")

        monkeypatch.setattr(ocbs, "_run_native_backup", fake_native)

        try:
            manifest = ocbs.backup(BackupScope.CONFIG, "fallback test", source=BackupSource.NATIVE)
            assert any('config' in path for path in manifest.paths)
            assert manifest.reason == "fallback test"
        finally:
            if original_home:
                os.environ['HOME'] = original_home

    def test_config_default_source(self, temp_state_dir):
        """Test config loading for default source."""

        config_path = temp_state_dir / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "defaultSource": "native",
                    "nativeBackupDir": str(temp_state_dir / "native-cache"),
                }
            )
        )

        ocbs = OCBSCore(state_dir=temp_state_dir)

        assert ocbs._resolve_backup_source(None) == BackupSource.NATIVE
        assert ocbs.native_backup_dir == temp_state_dir / "native-cache"
        assert ocbs.native_backup_dir.exists()


class TestRestore:
    """Tests for restore functionality with batch processing."""
    
    def test_restore_basic(self, ocbs, sample_files, temp_state_dir):
        """Test basic restore functionality."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            # Create backup
            backup = ocbs.backup(BackupScope.CONFIG, "test restore")
            
            # Modify a file
            config_file = sample_files / "config" / "settings.json"
            original_content = config_file.read_text()
            config_file.write_text('{"modified": true}')
            
            # Restore
            result = ocbs.restore(backup.backup_id)
            
            assert result is True
            # File should be restored to original
            restored_content = config_file.read_text()
            assert restored_content == original_content
        finally:
            if original_home:
                os.environ['HOME'] = original_home
    
    def test_restore_batch_processing(self, ocbs, temp_state_dir):
        """Test restore handles many files without 'too many open files' error."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            # Create many files to test batch processing
            openclaw_home = temp_state_dir / ".openclaw"
            openclaw_home.mkdir(exist_ok=True)
            config_dir = openclaw_home / "config"
            config_dir.mkdir(exist_ok=True)
            
            # Create 1000+ files to trigger batching
            for i in range(1100):
                (config_dir / f"file_{i:04d}.json").write_text(f'{{"id": {i}}}')
            
            # Backup
            backup = ocbs.backup(BackupScope.CONFIG, "batch test")
            
            # Delete all files
            for f in config_dir.glob("*.json"):
                f.unlink()
            
            # Restore - this should not fail with "too many open files"
            result = ocbs.restore(backup.backup_id)
            
            assert result is True
            # Verify files restored
            restored_files = list(config_dir.glob("*.json"))
            assert len(restored_files) == 1100
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
            backup = ocbs.backup(BackupScope.CONFIG, "checkpoint test")
            checkpoint_id = ocbs.create_checkpoint("test checkpoint")
            
            # Modify files
            config_file = sample_files / "config" / "settings.json"
            config_file.write_text('{"modified": true}')
            
            # Restore from checkpoint
            result = ocbs.restore(checkpoint_id=checkpoint_id)
            
            assert result is True
            # File should be restored
            restored_content = config_file.read_text()
            assert "modified" not in restored_content
        finally:
            if original_home:
                os.environ['HOME'] = original_home
    
    def test_restore_missing_backup(self, ocbs):
        """Test restore with missing backup raises error."""
        with pytest.raises(ValueError, match="No files found for backup_id"):
            ocbs.restore(backup_id="nonexistent")
    
    def test_restore_continues_on_error(self, ocbs, sample_files, temp_state_dir):
        """Test restore continues even if some files fail."""
        import os
        original_home = os.environ.get('HOME')
        os.environ['HOME'] = str(temp_state_dir)
        
        try:
            backup = ocbs.backup(BackupScope.CONFIG, "error test")
            
            # Make pack file unreadable to cause error
            pack_file = list(ocbs.packs_dir.glob("*.pack"))[0]
            original_perms = pack_file.stat().st_mode
            pack_file.chmod(0o000)
            
            try:
                # Should not raise, should continue
                result = ocbs.restore(backup.backup_id)
                # Result may be True even with warnings logged
            finally:
                pack_file.chmod(original_perms)
        finally:
            if original_home:
                os.environ['HOME'] = original_home

class TestServeRecords:
    """Tests for serve record accessors."""

    def test_get_checkpoint_serves_handles_missing_table(self, ocbs):
        """Test serve lookups recover if the serve_records table is absent."""

        with sqlite3.connect(ocbs.db_path) as conn:
            conn.execute("DROP TABLE serve_records")

        assert ocbs.get_checkpoint_serves() == []


class TestBackupScope:
    """Tests for BackupScope enum."""
    
    def test_scope_values(self):
        """Test scope enum values."""
        assert BackupScope.CONFIG.value == "config"
        assert BackupScope.CONFIG_SESSION.value == "config+session"
        assert BackupScope.CONFIG_SESSION_WORKSPACE.value == "config+session+workspace"


class TestBackupSource:
    """Tests for BackupSource enum."""

    def test_source_values(self):
        """Test source enum values."""

        assert BackupSource.DIRECT.value == "direct"
        assert BackupSource.NATIVE.value == "native"


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
