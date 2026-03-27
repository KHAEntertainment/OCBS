"""Skill module for OCBS.

When serving restore pages, ensure the URL is accessible to the user:

1. For local access (same machine): host="localhost" (default)
2. For Tailscale access: host="100.x.x.x" (user's Tailscale IP)
3. For remote access via Tailscale serve: set OCBS_SERVE_HOST env var

Examples:
  - Local: ocbs serve start --checkpoint <id>
  - Tailscale: ocbs serve start --checkpoint <id> --host 100.113.254.117
  - Persistent: export OCBS_SERVE_HOST=100.113.254.117

The agent should determine the appropriate host based on:
- User's current access method (local, Tailscale, or remote)
- OpenClaw gateway binding (check gateway config for --tailscale or --bind)
- User preference for this specific operation
"""

import asyncio
import os
import threading
from datetime import timedelta
import subprocess
from pathlib import Path
from typing import Optional

from .core import BackupSource, BackupScope, OCBSCore
from .serve import generate_restore_url, format_restore_message, start_restore_server


class OCBSBackupSkill:
    """Skill that exposes OCBS commands via chat."""
    
    name = "ocbs_backup"
    description = "OpenClaw Backup System - Create and restore backups"
    
    def __init__(self):
        self.core = OCBSCore()
        self.serve_server = None
        self.server_thread = None
        self._serve_lock = threading.Lock()
    
    async def backup(
        self,
        scope: str = "config",
        reason: str = "",
        source: str = None,
    ) -> str:
        """Create a backup.
        
        Args:
            scope: Backup scope (config, config+session, config+session+workspace)
            reason: Optional reason for the backup
            source: Backup source (direct or native)
            
        Returns:
            Status message
        """
        try:
            scope_enum = BackupScope(scope)
            source_enum = BackupSource(source) if source else None
            manifest = self.core.backup(scope_enum, reason, source=source_enum)
            effective_source = source_enum or self.core.get_default_source()
            return (
                f"Backup created: {manifest.backup_id}\n"
                f"  Scope: {scope}\n"
                f"  Source: {effective_source.value}\n"
                f"  Files: {len(manifest.paths)}"
            )
        except ValueError as e:
            return f"Error creating backup: {e}"
        except FileNotFoundError:
            return "Error creating backup: openclaw command not found for native source"
        except Exception as e:
            return f"Error creating backup: {e}"
    
    async def restore(self, latest: bool = True, checkpoint: str = None, 
                      target: str = None) -> str:
        """Restore from a backup.
        
        Args:
            latest: If True, restore from latest backup
            checkpoint: Specific checkpoint ID to restore
            target: Target directory for restore
            
        Returns:
            Status message
        """
        try:
            target_path = Path(target) if target else None
            if checkpoint:
                self.core.restore(checkpoint_id=checkpoint, target_dir=target_path)
                return f"Restored from checkpoint: {checkpoint}"
            elif latest:
                backup = self.core.get_latest_backup()
                if backup:
                    self.core.restore(backup_id=backup.backup_id, target_dir=target_path)
                    return f"Restored from latest backup: {backup.backup_id}"
                return "No backups available"
            return "Please specify --latest or --checkpoint"
        except Exception as e:
            return f"Error restoring: {e}"
    
    async def status(self) -> str:
        """Show backup status."""
        status = self.core.status()
        lines = [
            f"OCBS Status",
            f"  Total backups: {status['total_backups']}",
            f"  Total chunks: {status['total_chunks']}",
            f"  Pack size: {status['pack_size_bytes']} bytes",
        ]
        for scope, info in status['scope_info'].items():
            lines.append(f"  {scope}: {info['count']} backups")
        return "\n".join(lines)
    
    async def list(self, scope: str = None) -> str:
        """List available backups.
        
        Args:
            scope: Optional scope filter
            
        Returns:
            List of backups
        """
        scope_enum = BackupScope(scope) if scope else None
        backups = self.core.list_backups(scope_enum)
        
        if not backups:
            return "No backups found"
        
        lines = [f"Backups ({len(backups)} total):"]
        for b in backups:
            lines.append(f"  {b.backup_id} | {b.scope.value} | {b.timestamp.isoformat()}")
        return "\n".join(lines)
    
    async def clean(self, scope: str = None) -> str:
        """Clean up old backups.
        
        Args:
            scope: Optional scope filter
            
        Returns:
            Status message
        """
        scope_enum = BackupScope(scope) if scope else None
        self.core.cleanup(scope_enum)
        return "Cleanup completed"
    
    async def checkpoint(self, reason: str, serve: bool = False, port: Optional[int] = None) -> str:
        """Create a checkpoint for auto-restore.

        Args:
            reason: Reason for the checkpoint
            serve: If True, start web server and return restore URL

        Returns:
            Checkpoint ID and optionally the restore URL
        """
        try:
            checkpoint_id = self.core.create_checkpoint(reason)

            if serve:
                # Start restore server
                start_restore_server(port=port)
                # Return formatted message with auto-detected URL
                return format_restore_message(checkpoint_id, reason)

            return f"Checkpoint created: {checkpoint_id}\n  Reason: {reason}"
        except ValueError as e:
            return f"Error: {e}"
    
    async def serve(self, checkpoint: str, expires: str = "4h", 
                   host: str = "localhost") -> str:
        """Serve a restore page for a checkpoint.
        
        Args:
            checkpoint: Checkpoint ID to serve
            expires: Expiry time for the restore page (e.g., "4h", "1d")
            host: Host for the restore URL (use Tailscale IP for remote access)
                  Can also be set via OCBS_SERVE_HOST environment variable
            
        Returns:
            Restore URL and status
        """
        try:
            expires_hours = self._parse_expiry(expires)
            if expires_hours <= 0:
                return f"Invalid expiry: {expires}"
            
            effective_host = self._resolve_host(host)
            self._ensure_serve_server(effective_host)
            token = self.serve_server.serve_checkpoint(checkpoint, expires_hours)
            url = self.serve_server.get_restore_url(token)
            
            return (f"Restore page created for checkpoint: {checkpoint}\n"
                    f"  URL: {url}\n"
                    f"  Expires: {expires}\n"
                    f"  Host: {effective_host}")
        except ValueError as e:
            return f"Error: {e}"
    
    def _parse_expiry(self, expires: str) -> float:
        """Parse expiry string to hours."""
        expires = expires.strip().lower()
        
        multipliers = {
            's': 1/3600,
            'm': 1/60,
            'h': 1,
            'd': 24,
            'w': 168,
        }
        
        for suffix, mult in multipliers.items():
            if expires.endswith(suffix):
                try:
                    return float(expires[:-1]) * mult
                except ValueError:
                    return 0

        try:
            return float(expires)
        except ValueError:
            return 0

    async def poll_proceed_notifications(self, clear: bool = True) -> str:
        """Poll for proceed notifications from restore pages.

        Agents should call this periodically to check if the user has
        clicked "I received this" on any restore pages.

        Args:
            clear: If True, clear the notification files after reading (default)

        Returns:
            List of pending proceed notifications or empty string
        """
        if not self.serve_server:
            return "No active serve server"

        notifications = self.serve_server.get_pending_proceed_notifications()

        if not notifications:
            return "No pending proceed notifications"

        result_lines = [f"Pending proceed notifications ({len(notifications)}):"]
        for notif in notifications:
            result_lines.append(f"  Token: {notif['token'][:16]}...")
            result_lines.append(f"    Checkpoint: {notif['checkpoint_id']}")
            result_lines.append(f"    Proceeded at: {notif['proceeded_at']}")

        if clear:
            for notif in notifications:
                self.serve_server.clear_proceed_notification(notif['token'])

        return "\n".join(result_lines)

    async def native_backup(self, scope: str = "config", verify: bool = False,
                           output: str = None) -> str:
        """Run OpenClaw native backup via OCBS skill.

        Args:
            scope: Backup scope (config, config+session, full)
            verify: If True, verify archive after creation
            output: Optional output directory path

        Returns:
            Status message with archive path
        """
        try:
            # Build native backup command
            args = ["openclaw", "backup", "create"]

            # Map OCBS scopes to native flags
            if scope == "config":
                args.append("--only-config")
            elif scope == "config+session":
                args.append("--no-include-workspace")
            # Full scope (config+session+workspace) uses default

            if verify:
                args.append("--verify")

            if output:
                args.extend(["--output", output])

            # Run native backup
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for large workspaces
            )

            if result.returncode != 0:
                return f"Native backup failed: {result.stderr}"

            return f"Native backup created successfully:\n{result.stdout}"

        except subprocess.TimeoutExpired:
            return "Error: Native backup timed out (10 minutes)"
        except FileNotFoundError:
            return "Error: openclaw command not found. Ensure OpenClaw is installed."
        except Exception as e:
            return f"Error running native backup: {e}"

    async def native_verify(self, archive: str) -> str:
        """Verify a native backup archive.

        Args:
            archive: Path to the native backup archive

        Returns:
            Verification result
        """
        try:
            result = subprocess.run(
                ["openclaw", "backup", "verify", archive],
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout for verification
            )

            if result.returncode != 0:
                return f"Verification failed: {result.stderr}"

            return f"✅ Archive verified successfully:\n{result.stdout}"

        except subprocess.TimeoutExpired:
            return "Error: Verification timed out"
        except FileNotFoundError:
            return "Error: openclaw command not found. Ensure OpenClaw is installed."
        except Exception as e:
            return f"Error verifying archive: {e}"


# Skill manifest for OpenClaw skill system
SKILL_MANIFEST = {
    "name": "ocbs_backup",
    "version": "0.1.0",
    "description": "OpenClaw Backup System - Create and restore backups",
    "commands": {
        "backup": {
            "description": "Create a backup",
            "parameters": {
                "scope": {
                    "type": "string",
                    "enum": ["minimal", "config", "config+session", "config+session+workspace"],
                    "default": "config",
                    "description": "Backup scope"
                },
                "reason": {
                    "type": "string",
                    "default": "",
                    "description": "Reason for backup"
                },
                "source": {
                    "type": "string",
                    "enum": ["direct", "native"],
                    "default": None,
                    "description": "Backup source"
                }
            }
        },
        "restore": {
            "description": "Restore from a backup",
            "parameters": {
                "latest": {
                    "type": "boolean",
                    "default": True,
                    "description": "Restore from latest backup"
                },
                "checkpoint": {
                    "type": "string",
                    "default": None,
                    "description": "Specific checkpoint ID"
                },
                "target": {
                    "type": "string",
                    "default": None,
                    "description": "Target directory for restore"
                }
            }
        },
        "status": {
            "description": "Show backup status",
            "parameters": {}
        },
        "list": {
            "description": "List available backups",
            "parameters": {
                "scope": {
                    "type": "string",
                    "default": None,
                    "description": "Optional scope filter"
                }
            }
        },
        "clean": {
            "description": "Clean up old backups",
            "parameters": {
                "scope": {
                    "type": "string",
                    "default": None,
                    "description": "Optional scope filter"
                }
            }
        },
        "checkpoint": {
            "description": "Create a checkpoint for auto-restore",
            "parameters": {
                "reason": {
                    "type": "string",
                    "description": "Reason for checkpoint"
                },
                "serve": {
                    "type": "boolean",
                    "default": False,
                    "description": "Create a restore page URL"
                },
                "expires": {
                    "type": "string",
                    "default": "4h",
                    "description": "Expiry time for restore page (e.g., 4h, 1d)"
                },
                "host": {
                    "type": "string",
                    "default": "localhost",
                    "description": "Host for restore URL (use Tailscale IP for remote access)"
                }
            }
        },
        "serve": {
            "description": "Serve a restore page for a checkpoint",
            "parameters": {
                "checkpoint": {
                    "type": "string",
                    "description": "Checkpoint ID to serve"
                },
                "expires": {
                    "type": "string",
                    "default": "4h",
                    "description": "Expiry time for the restore page"
                },
                "host": {
                    "type": "string",
                    "default": "localhost",
                    "description": "Host for restore URL (use Tailscale IP for remote access)"
                }
            }
        },
        "poll-proceed": {
            "description": "Poll for proceed notifications from restore pages",
            "parameters": {
                "clear": {
                    "type": "boolean",
                    "default": True,
                    "description": "Clear notifications after reading"
                }
            }
        },
        "native-backup": {
            "description": "Run OpenClaw native backup",
            "parameters": {
                "scope": {
                    "type": "string",
                    "enum": ["config", "config+session", "config+session+workspace"],
                    "default": "config",
                    "description": "Backup scope"
                },
                "verify": {
                    "type": "boolean",
                    "default": False,
                    "description": "Verify archive after creation"
                },
                "output": {
                    "type": "string",
                    "default": None,
                    "description": "Output directory path"
                }
            }
        },
        "native-verify": {
            "description": "Verify a native backup archive",
            "parameters": {
                "archive": {
                    "type": "string",
                    "description": "Path to the native backup archive"
                }
            }
        }
    }
}