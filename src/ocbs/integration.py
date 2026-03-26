"""
Integration utilities for OCBS with cron and heartbeat.
"""

import json
from pathlib import Path
from datetime import datetime


class OCBSIntegration:
    """Integration utilities for OCBS."""
    
    def __init__(self, state_dir: Path = None):
        self.state_dir = state_dir or Path.home() / ".config" / "ocbs"
        self.config_file = self.state_dir / "config.json"
    
    def get_config(self) -> dict:
        """Load OCBS configuration."""
        if self.config_file.exists():
            with open(self.config_file) as f:
                return json.load(f)
        return {
            'auto_backup_enabled': False,
            'auto_backup_scope': 'config',
            'auto_backup_schedule': 'daily',
            'auto_restore_enabled': False,
            'auto_restore_timeout': 30,  # minutes
            'heartbeat_check_enabled': False
        }
    
    def save_config(self, config: dict):
        """Save OCBS configuration."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setup_cron(self, schedule: str = 'daily', scope: str = 'config'):
        """Generate cron job entries for automatic backups.
        
        Args:
            schedule: Cron schedule (daily, weekly, or cron expression)
            scope: Backup scope
        """
        config = self.get_config()
        config['auto_backup_enabled'] = True
        config['auto_backup_schedule'] = schedule
        config['auto_backup_scope'] = scope
        self.save_config(config)
        
        # Generate cron entry
        if schedule == 'daily':
            cron_expr = '0 2 * * *'  # 2 AM daily
        elif schedule == 'weekly':
            cron_expr = '0 2 * * 0'  # 2 AM Sunday
        else:
            cron_expr = schedule
        
        # Create cron job file
        cron_dir = Path.home() / '.config' / 'cron.d'
        cron_dir.mkdir(parents=True, exist_ok=True)
        
        cron_file = cron_dir / 'ocbs-backup'
        cron_content = f"""# OCBS automatic backup
{cron_expr} ocbs backup --scope {scope} >> ~/.config/ocbs/backup.log 2>&1
"""
        
        with open(cron_file, 'w') as f:
            f.write(cron_content)
        
        return f"Cron job configured: {cron_expr} ocbs backup --scope {scope}"
    
    def remove_cron(self):
        """Remove OCBS cron job."""
        cron_file = Path.home() / '.config' / 'cron.d' / 'ocbs-backup'
        if cron_file.exists():
            cron_file.unlink()
        
        config = self.get_config()
        config['auto_backup_enabled'] = False
        self.save_config(config)
        
        return "Cron job removed"
    
    def setup_heartbeat_check(self, enabled: bool = True, timeout_minutes: int = 30):
        """Configure heartbeat-based health check for auto-restore.
        
        Args:
            enabled: Enable heartbeat integration
            timeout_minutes: Timeout before auto-restore triggers
        """
        config = self.get_config()
        config['heartbeat_check_enabled'] = enabled
        config['auto_restore_timeout'] = timeout_minutes
        self.save_config(config)
        
        return f"Heartbeat check enabled: {timeout_minutes} minute timeout"
    
    def check_gateway_health(self) -> dict:
        """Check gateway health status.
        
        Returns dict with health information.
        """
        # Check if gateway is running
        gateway_status_file = Path.home() / '.openclaw' / 'gateway_status.json'
        
        if gateway_status_file.exists():
            with open(gateway_status_file) as f:
                status = json.load(f)
                return {
                    'running': status.get('running', False),
                    'last_heartbeat': status.get('last_heartbeat'),
                    'healthy': True
                }
        
        # Alternative: check for running process
        return {
            'running': False,
            'last_heartbeat': None,
            'healthy': False
        }
    
    def should_auto_restore(self) -> bool:
        """Check if auto-restore should be triggered."""
        config = self.get_config()
        
        if not config.get('auto_restore_enabled', False):
            return False
        
        if not config.get('heartbeat_check_enabled', False):
            return False
        
        health = self.check_gateway_health()
        
        if not health.get('healthy', False):
            return True
        
        # Check heartbeat timeout
        last_heartbeat = health.get('last_heartbeat')
        if last_heartbeat:
            last_dt = datetime.fromisoformat(last_heartbeat)
            timeout_minutes = config.get('auto_restore_timeout', 30)
            if (datetime.now() - last_dt).total_seconds() > timeout_minutes * 60:
                return True
        
        return False
    
    def get_integration_status(self) -> dict:
        """Get full integration status."""
        config = self.get_config()

        return {
            'auto_backup': {
                'enabled': config.get('auto_backup_enabled', False),
                'schedule': config.get('auto_backup_schedule', None),
                'scope': config.get('auto_backup_scope', None)
            },
            'auto_restore': {
                'enabled': config.get('auto_restore_enabled', False),
                'timeout_minutes': config.get('auto_restore_timeout', 30)
            },
            'heartbeat': {
                'enabled': config.get('heartbeat_check_enabled', False)
            },
            'notifications': {
                'enabled': config.get('notification_enabled', False),
                'webhook_url': config.get('webhook_url', 'http://127.0.0.1:18789/hooks/wake'),
                'webhook_host': config.get('webhook_host', '127.0.0.1'),
            }
        }

    def get_notification_config(self) -> dict:
        """Get notification configuration."""
        config = self.get_config()
        return {
            'notification_enabled': config.get('notification_enabled', False),
            'webhook_url': config.get('webhook_url', 'http://127.0.0.1:18789/hooks/wake'),
            'webhook_host': config.get('webhook_host', '127.0.0.1'),
            'webhook_token': config.get('webhook_token', ''),
        }

    def save_notification_config(self, notification_config: dict) -> bool:
        """Save notification configuration.

        Args:
            notification_config: Dict with notification settings

        Returns:
            True if saved successfully
        """
        config = self.get_config()
        config['notification_enabled'] = notification_config.get('notification_enabled', False)
        config['webhook_url'] = notification_config.get('webhook_url', 'http://127.0.0.1:18789/hooks/wake')
        config['webhook_host'] = notification_config.get('webhook_host', '127.0.0.1')
        config['webhook_token'] = notification_config.get('webhook_token', '')
        self.save_config(config)
        return True

    def setup_notifications(self, enabled: bool = True, webhook_host: str = '127.0.0.1') -> str:
        """Configure notification settings.

        Args:
            enabled: Enable webhook notifications
            webhook_host: Host where OpenClaw Gateway is running

        Returns:
            Status message
        """
        config = self.get_config()
        config['notification_enabled'] = enabled
        config['webhook_host'] = webhook_host
        # Default port is 18789 (OpenClaw default)
        config['webhook_url'] = f'http://{webhook_host}:18789/hooks/wake'
        self.save_config(config)

        if enabled:
            return f'Notifications enabled - Gateway webhook at {config["webhook_url"]}'
        else:
            return 'Notifications disabled'
