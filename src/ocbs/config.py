"""
Unified configuration management for OCBS.
Handles schedule.yaml and ocbs.yaml configuration files.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict, fields
from enum import Enum
import yaml

# Configure module logger
logger = logging.getLogger(__name__)


class BackupScope(Enum):
    """Backup scope options."""
    CONFIG = "config"
    CONFIG_SESSION = "config+session"
    CONFIG_SESSION_WORKSPACE = "config+session+workspace"


class RetentionPolicy(Enum):
    """Retention policy levels."""
    MINIMAL = "minimal"  # 3 daily, 2 weekly
    STANDARD = "standard"  # 7 daily, 4 weekly, 12 monthly
    AGGRESSIVE = "aggressive"  # 14 daily, 8 weekly, 24 monthly


class HeartbeatMode(Enum):
    """Heartbeat monitoring modes."""
    DISABLED = "disabled"
    PASSIVE = "passive"  # Check periodically, alert on failure
    ACTIVE = "active"  # Proactive monitoring with auto-actions


@dataclass
class ScheduleConfig:
    """Configuration for a scheduled backup."""
    id: str
    name: str
    scope: str
    cron_expression: str
    enabled: bool = True
    retention_policy: str = "standard"
    auto_cleanup: bool = True
    notify_on_complete: bool = False
    notify_channel: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ScheduleConfig':
        # Filter to only known fields to avoid TypeError on unknown keys
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class HeartbeatConfig:
    """Configuration for heartbeat monitoring."""
    mode: str = "disabled"
    check_interval_seconds: int = 300  # 5 minutes
    failure_threshold: int = 3  # Failures before alerting
    recovery_threshold: int = 2  # Successes before clear
    timeout_seconds: int = 60  # Gateway response timeout
    auto_backup_on_failure: bool = False
    auto_backup_scope: str = "config"
    notify_on_status_change: bool = True
    notify_channel: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HeartbeatConfig':
        # Filter to only known fields to avoid TypeError on unknown keys
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class OCBSConfig:
    """Main OCBS configuration."""
    version: str = "1.0"
    default_scope: str = "config"
    default_retention: str = "standard"
    schedules: List[dict] = field(default_factory=list)
    heartbeat: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'OCBSConfig':
        # Filter to only known fields to avoid TypeError on unknown keys
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


class OCBSConfigManager:
    """Manages OCBS configuration files."""
    
    SCHEDULE_FILE = "schedule.yaml"
    OCBS_FILE = "ocbs.yaml"
    
    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".config" / "ocbs"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.schedule_file = self.state_dir / self.SCHEDULE_FILE
        self.ocbs_file = self.state_dir / self.OCBS_FILE
    
    # =========================================================================
    # Schedule Configuration (schedule.yaml)
    # =========================================================================
    
    def load_schedules(self) -> Dict[str, ScheduleConfig]:
        """Load all schedules from schedule.yaml."""
        schedules = {}
        
        if self.schedule_file.exists():
            try:
                with open(self.schedule_file, 'r') as f:
                    data = yaml.safe_load(f) or {}
                    schedules_raw = data.get('schedules', [])
                    for s in schedules_raw:
                        schedule = ScheduleConfig.from_dict(s)
                        schedules[schedule.id] = schedule
            except Exception as e:
                # Log error but don't fail
                logger.warning(f"Failed to load schedules from {self.schedule_file}: {e}")
        
        return schedules
    
    def save_schedules(self, schedules: Dict[str, ScheduleConfig]):
        """Save all schedules to schedule.yaml."""
        data = {
            'version': '1.0',
            'schedules': [s.to_dict() for s in schedules.values()]
        }
        
        with open(self.schedule_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, indent=2)
    
    def get_schedule(self, schedule_id: str) -> Optional[ScheduleConfig]:
        """Get a specific schedule by ID."""
        schedules = self.load_schedules()
        return schedules.get(schedule_id)
    
    def add_schedule(self, schedule: ScheduleConfig) -> bool:
        """Add a new schedule."""
        schedules = self.load_schedules()
        
        if schedule.id in schedules:
            return False
        
        schedules[schedule.id] = schedule
        self.save_schedules(schedules)
        return True
    
    def update_schedule(self, schedule_id: str, updates: dict) -> bool:
        """Update an existing schedule."""
        schedules = self.load_schedules()
        
        if schedule_id not in schedules:
            return False
        
        schedule = schedules[schedule_id]
        for key, value in updates.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)
        
        self.save_schedules(schedules)
        return True
    
    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule."""
        schedules = self.load_schedules()
        
        if schedule_id not in schedules:
            return False
        
        del schedules[schedule_id]
        self.save_schedules(schedules)
        return True
    
    def enable_schedule(self, schedule_id: str) -> bool:
        """Enable a schedule."""
        return self.update_schedule(schedule_id, {'enabled': True})
    
    def disable_schedule(self, schedule_id: str) -> bool:
        """Disable a schedule."""
        return self.update_schedule(schedule_id, {'enabled': False})
    
    def get_enabled_schedules(self) -> List[ScheduleConfig]:
        """Get all enabled schedules."""
        schedules = self.load_schedules()
        return [s for s in schedules.values() if s.enabled]
    
    # =========================================================================
    # OCBS Configuration (ocbs.yaml)
    # =========================================================================
    
    def load_ocbs_config(self) -> OCBSConfig:
        """Load main OCBS configuration."""
        if self.ocbs_file.exists():
            try:
                with open(self.ocbs_file, 'r') as f:
                    data = yaml.safe_load(f) or {}
                    return OCBSConfig.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load config from {self.ocbs_file}: {e}")
        
        return OCBSConfig()
    
    def save_ocbs_config(self, config: OCBSConfig):
        """Save main OCBS configuration."""
        with open(self.ocbs_file, 'w') as f:
            yaml.dump(config.to_dict(), f, default_flow_style=False, indent=2)
    
    def update_ocbs_config(self, updates: dict):
        """Update main OCBS configuration."""
        config = self.load_ocbs_config()
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.save_ocbs_config(config)
    
    # =========================================================================
    # Heartbeat Configuration
    # =========================================================================
    
    def load_heartbeat_config(self) -> HeartbeatConfig:
        """Load heartbeat configuration."""
        config = self.load_ocbs_config()
        heartbeat_data = config.heartbeat or {}
        return HeartbeatConfig.from_dict(heartbeat_data)
    
    def save_heartbeat_config(self, heartbeat: HeartbeatConfig):
        """Save heartbeat configuration."""
        config = self.load_ocbs_config()
        config.heartbeat = heartbeat.to_dict()
        self.save_ocbs_config(config)
    
    def update_heartbeat_config(self, updates: dict):
        """Update heartbeat configuration."""
        config = self.load_heartbeat_config()
        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.save_heartbeat_config(config)
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_config_path(self, config_type: str) -> Optional[Path]:
        """Get the path to a configuration file."""
        if config_type == 'schedule':
            return self.schedule_file if self.schedule_file.exists() else None
        elif config_type == 'ocbs':
            return self.ocbs_file if self.ocbs_file.exists() else None
        return None
    
    def export_config(self, config_type: str) -> Optional[str]:
        """Export configuration as YAML string."""
        if config_type == 'schedule':
            schedules = self.load_schedules()
            data = {'schedules': [s.to_dict() for s in schedules.values()]}
            return yaml.dump(data, default_flow_style=False, indent=2)
        elif config_type == 'ocbs':
            config = self.load_ocbs_config()
            return yaml.dump(config.to_dict(), default_flow_style=False, indent=2)
        elif config_type == 'all':
            schedules = self.load_schedules()
            config = self.load_ocbs_config()
            return yaml.dump({
                'schedules': [s.to_dict() for s in schedules.values()],
                'ocbs_config': config.to_dict()
            }, default_flow_style=False, indent=2)
        return None


# =============================================================================
# Configuration Constants
# =============================================================================

# Retention policies
RETENTION_POLICIES = {
    'minimal': {
        'daily': 3,
        'weekly': 2,
        'monthly': 0
    },
    'standard': {
        'daily': 7,
        'weekly': 4,
        'monthly': 12
    },
    'aggressive': {
        'daily': 14,
        'weekly': 8,
        'monthly': 24
    }
}

# Schedule presets
SCHEDULE_PRESETS = {
    'hourly': {
        'cron': '0 * * * *',
        'description': 'Every hour'
    },
    'daily': {
        'cron': '0 2 * * *',
        'description': 'Every day at 2 AM'
    },
    'twice_daily': {
        'cron': '0 2,14 * * *',
        'description': 'Twice daily at 2 AM and 2 PM'
    },
    'weekly': {
        'cron': '0 2 * * 0',
        'description': 'Every Sunday at 2 AM'
    },
    'monthly': {
        'cron': '0 2 1 * *',
        'description': 'First day of each month at 2 AM'
    }
}

# Scope options for display
SCOPE_OPTIONS = [
    ('config', 'Config only', 'OpenClaw config and credentials'),
    ('config+session', 'Config + Session', 'Config, credentials, and sessions'),
    ('config+session+workspace', 'Full backup', 'Everything including workspace')
]

# Heartbeat mode descriptions
HEARTBEAT_MODES = [
    ('disabled', 'Disabled', 'No heartbeat monitoring'),
    ('passive', 'Passive', 'Check periodically, alert on failure'),
    ('active', 'Active', 'Proactive monitoring with auto-actions')
]

# Retention policy descriptions
RETENTION_OPTIONS = [
    ('minimal', 'Minimal', '3 daily, 2 weekly'),
    ('standard', 'Standard', '7 daily, 4 weekly, 12 monthly'),
    ('aggressive', 'Aggressive', '14 daily, 8 weekly, 24 monthly')
]