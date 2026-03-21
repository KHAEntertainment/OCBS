"""
Integration tests for OCBS cron and heartbeat integration.
"""

import json
import os
import tempfile
from pathlib import Path
from ocbs.integration import OCBSIntegration


class TestIntegration:
    """Test integration utilities."""
    
    def test_get_default_config(self):
        """Test getting default configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            config = integration.get_config()
            
            assert config['auto_backup_enabled'] == False
            assert config['auto_backup_scope'] == 'config'
            assert config['auto_backup_schedule'] == 'daily'
            assert config['auto_restore_enabled'] == False
            assert config['heartbeat_check_enabled'] == False
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            
            config = {
                'auto_backup_enabled': True,
                'auto_backup_scope': 'config+session',
                'auto_backup_schedule': 'weekly'
            }
            integration.save_config(config)
            
            loaded = integration.get_config()
            assert loaded['auto_backup_enabled'] == True
            assert loaded['auto_backup_scope'] == 'config+session'
            assert loaded['auto_backup_schedule'] == 'weekly'
    
    def test_setup_cron_daily(self):
        """Test setting up daily cron job."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            result = integration.setup_cron(schedule='daily', scope='config')
            
            assert 'Cron job configured' in result
            
            # Check config was updated
            config = integration.get_config()
            assert config['auto_backup_enabled'] == True
            assert config['auto_backup_schedule'] == 'daily'
    
    def test_setup_cron_weekly(self):
        """Test setting up weekly cron job."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            result = integration.setup_cron(schedule='weekly', scope='config+session')
            
            assert 'Cron job configured' in result
    
    def test_remove_cron(self):
        """Test removing cron job."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            
            # Setup first
            integration.setup_cron(schedule='daily', scope='config')
            
            # Remove
            result = integration.remove_cron()
            assert 'Cron job removed' in result
            
            # Check config was updated
            config = integration.get_config()
            assert config['auto_backup_enabled'] == False
    
    def test_setup_heartbeat_check(self):
        """Test setting up heartbeat check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            result = integration.setup_heartbeat_check(enabled=True, timeout_minutes=45)
            
            assert 'Heartbeat check enabled' in result
            
            config = integration.get_config()
            assert config['heartbeat_check_enabled'] == True
            assert config['auto_restore_timeout'] == 45
    
    def test_check_gateway_health_no_status(self):
        """Test checking gateway health when no status file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            health = integration.check_gateway_health()
            
            assert health['running'] == False
            assert health['healthy'] == False
    
    def test_get_integration_status(self):
        """Test getting full integration status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            
            # Setup some options
            integration.setup_cron(schedule='daily', scope='config')
            integration.setup_heartbeat_check(enabled=True, timeout_minutes=30)
            
            status = integration.get_integration_status()
            
            assert status['auto_backup']['enabled'] == True
            assert status['auto_backup']['schedule'] == 'daily'
            assert status['heartbeat']['enabled'] == True
    
    def test_should_auto_restore_disabled(self):
        """Test auto-restore when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            integration = OCBSIntegration(state_dir=Path(tmpdir))
            
            # Don't enable auto-restore
            result = integration.should_auto_restore()
            
            assert result == False


class TestSkillInterface:
    """Test skill interface functions."""
    
    def test_backup_skill_function(self):
        """Test backup function signature."""
        from ocbs.skill import OCBSBackupSkill
        
        skill = OCBSBackupSkill()
        
        # Verify skill has required methods
        assert hasattr(skill, 'backup')
        assert hasattr(skill, 'restore')
        assert hasattr(skill, 'status')
        assert hasattr(skill, 'list')
        assert hasattr(skill, 'clean')
        assert hasattr(skill, 'checkpoint')

    def test_backup_skill_supports_source(self):
        """Test skill manifest exposes backup source parameter."""

        from ocbs.skill import SKILL_MANIFEST

        params = SKILL_MANIFEST['commands']['backup']['parameters']
        assert 'source' in params
        assert params['source']['enum'] == ['direct', 'native']
    
    def test_skill_manifest(self):
        """Test skill manifest structure."""
        from ocbs.skill import SKILL_MANIFEST
        
        assert SKILL_MANIFEST['name'] == 'ocbs_backup'
        assert 'commands' in SKILL_MANIFEST
        assert 'backup' in SKILL_MANIFEST['commands']
        assert 'restore' in SKILL_MANIFEST['commands']


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
