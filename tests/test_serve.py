"""Tests for OCBS serve functionality."""

import pytest
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.ocbs.core import OCBSCore, BackupScope
from src.ocbs.serve import RestorePageServer


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create a temporary state directory."""
    return tmp_path / "ocbs_test"


@pytest.fixture
def core(temp_state_dir):
    """Create a test core instance."""
    return OCBSCore(state_dir=temp_state_dir)


@pytest.fixture
def server(temp_state_dir):
    """Create a test server instance."""
    return RestorePageServer(state_dir=temp_state_dir, port=18790)


class TestRestorePageServer:
    """Tests for RestorePageServer."""
    
    def test_server_init(self, server):
        """Test server initialization."""
        assert server.port == 18790
        assert server._active_tokens == {}
    
    def test_generate_token(self, server):
        """Test token generation."""
        token1 = server._generate_token()
        token2 = server._generate_token()
        
        assert len(token1) > 32
        assert token1 != token2
    
    def test_serve_checkpoint_invalid(self, server):
        """Test serving a non-existent checkpoint."""
        with pytest.raises(ValueError, match="Checkpoint not found"):
            server.serve_checkpoint("nonexistent_cp")
    
    def test_serve_checkpoint_valid(self, server, core):
        """Test serving a valid checkpoint."""
        # Create a backup first
        core.backup(BackupScope.CONFIG, "Test backup for checkpoint")
        
        # Create checkpoint
        checkpoint_id = core.create_checkpoint("Test checkpoint")
        
        # Serve checkpoint
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        assert token is not None
        assert len(token) > 32
    
    def test_get_restore_url(self, server):
        """Test getting restore URL."""
        token = "test_token_123"
        url = server.get_restore_url(token)
        
        assert url == f"http://localhost:{server.port}/restore/{token}"
    
    def test_validate_token(self, server, core):
        """Test token validation."""
        # Create backup and checkpoint
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Test")
        
        # Serve checkpoint
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        # Validate token
        record = server._validate_token(token)
        
        assert record is not None
        assert record['checkpoint_id'] == checkpoint_id
        assert record['used'] == False
        assert record['proceeded'] == False
        assert record['restored'] == False
    
    def test_validate_invalid_token(self, server):
        """Test validation of invalid token."""
        record = server._validate_token("invalid_token")
        assert record is None
    
    def test_validate_expired_token(self, server, core):
        """Test validation of expired token."""
        # Create backup and checkpoint
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Test")
        
        # Serve with very short expiry (already expired)
        with patch('src.ocbs.serve.datetime') as mock_dt:
            mock_dt.now.return_value = datetime.now() - timedelta(hours=5)
            token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        record = server._validate_token(token)
        assert record is None
    
    def test_mark_proceeded(self, server, core):
        """Test marking token as proceeded."""
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Test")
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        server._mark_proceeded(token)
        
        record = server._validate_token(token)
        assert record['proceeded'] == True
    
    def test_mark_used(self, server, core):
        """Test marking token as used."""
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Test")
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        server._mark_used(token)
        
        record = server._validate_token(token)
        assert record['used'] == True
    
    def test_get_checkpoint_info(self, server, core):
        """Test getting checkpoint info."""
        core.backup(BackupScope.CONFIG, "Test backup")
        checkpoint_id = core.create_checkpoint("Before update")
        
        info = server._get_checkpoint_info(checkpoint_id)
        
        assert info is not None
        assert info['checkpoint_id'] == checkpoint_id
        assert info['reason'] == "Before update"
        assert 'file_count' in info
        assert info['scope'] == 'config'
    
    def test_get_checkpoint_info_not_found(self, server):
        """Test getting info for non-existent checkpoint."""
        info = server._get_checkpoint_info("nonexistent_cp")
        assert info is None
    
    def test_get_active_serves_empty(self, server):
        """Test getting active serves when none exist."""
        serves = server.get_active_serves()
        assert serves == []
    
    def test_html_page_generation(self, server, core):
        """Test HTML page generation."""
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Before update")
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        checkpoint_info = server._get_checkpoint_info(checkpoint_id)
        token_record = server._validate_token(token)
        html = server._get_html_page(token, checkpoint_info, token_record['expires_at'])
        
        # Check page contains expected elements
        assert "OCBS Emergency Restore" in html
        assert "Before update" in html
        assert "RESTORE & RESTART GATEWAY" in html
        assert "I received this - proceed with change" in html
        assert token in html
        # Check for form actions that include the token
        assert 'action="/proceed"' in html
        assert 'action="/restore"' in html
    
    def test_html_page_proceeded_state(self, server, core):
        """Test HTML page in proceeded state."""
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Before update")
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        server._mark_proceeded(token)
        
        checkpoint_info = server._get_checkpoint_info(checkpoint_id)
        token_record = server._validate_token(token)
        html = server._get_html_page(token, checkpoint_info, token_record['expires_at'], is_proceeded=True)
        
        assert "Acknowledged" in html
        assert "proceed with the change" in html
    
    def test_html_page_restored_state(self, server, core):
        """Test HTML page in restored state."""
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Before update")
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        checkpoint_info = server._get_checkpoint_info(checkpoint_id)
        token_record = server._validate_token(token)
        html = server._get_html_page(token, checkpoint_info, token_record['expires_at'], is_restored=True)
        
        assert "Restore Completed" in html


class TestServeIntegration:
    """Integration tests for serve functionality."""
    
    def test_checkpoint_serve_workflow(self, core, server):
        """Test full checkpoint and serve workflow."""
        # Create backup
        core.backup(BackupScope.CONFIG, "Pre-change backup")
        
        # Create checkpoint
        checkpoint_id = core.create_checkpoint("Before software update")
        
        # Serve restore page
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        url = server.get_restore_url(token)
        
        # Validate
        record = server._validate_token(token)
        assert record is not None
        assert record['checkpoint_id'] == checkpoint_id
        assert "localhost" in url
        assert token in url
        
        # Simulate user clicking "proceed"
        server._mark_proceeded(token)
        
        record = server._validate_token(token)
        assert record['proceeded'] == True
        
        # Simulate user clicking "restore" (failure case)
        server._mark_used(token)
        server._mark_restored(token)
        
        record = server._validate_token(token)
        assert record['used'] == True
        assert record['restored'] == True
    
    def test_multiple_checkpoints(self, core, server):
        """Test serving multiple checkpoints."""
        # Create multiple checkpoints
        for i in range(3):
            core.backup(BackupScope.CONFIG, f"Backup {i}")
            cp_id = core.create_checkpoint(f"Checkpoint {i}")
            token = server.serve_checkpoint(cp_id, expires_hours=4)
            
            # Verify each token is valid
            record = server._validate_token(token)
            assert record is not None
            assert record['checkpoint_id'] == cp_id


class TestServeExpiry:
    """Tests for serve expiry functionality."""
    
    def test_expiry_calculation(self, core, server):
        """Test expiry time calculation."""
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Test")
        
        token = server.serve_checkpoint(checkpoint_id, expires_hours=4)
        
        record = server._validate_token(token)
        expires_at = record['expires_at']
        
        # Should expire in approximately 4 hours
        # expires_at is already a datetime object from _validate_token
        now = datetime.now()
        diff_hours = (expires_at - now).total_seconds() / 3600
        
        assert 3.9 < diff_hours < 4.1  # Allow small tolerance
    
    def test_custom_expiry(self, core, server):
        """Test custom expiry times."""
        core.backup(BackupScope.CONFIG, "Test")
        checkpoint_id = core.create_checkpoint("Test")
        
        # 24 hours
        token_24h = server.serve_checkpoint(checkpoint_id, expires_hours=24)
        record_24h = server._validate_token(token_24h)
        expires_24h = record_24h['expires_at']  # Already a datetime
        
        # 1 hour
        token_1h = server.serve_checkpoint(checkpoint_id, expires_hours=1)
        record_1h = server._validate_token(token_1h)
        expires_1h = record_1h['expires_at']  # Already a datetime
        
        # 24h should expire later than 1h
        assert expires_24h > expires_1h