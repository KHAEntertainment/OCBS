"""
Notification module for OCBS to send webhook notifications to OpenClaw Gateway.

Uses the /hooks/wake endpoint which requires a simple 'text' field.
Does NOT require custom hook mapping configuration.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages notifications to OpenClaw Gateway via webhook or file-based fallback."""

    # Default Gateway port for OpenClaw
    DEFAULT_GATEWAY_PORT = 18789

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".config" / "ocbs"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_gateway_url(self) -> str:
        """Get the Gateway webhook URL from environment or default."""
        # Check for explicit URL first
        if os.environ.get("OCBS_WEBHOOK_URL"):
            return os.environ["OCBS_WEBHOOK_URL"]

        # Check for custom port
        port = os.environ.get("OPENCLAW_GATEWAY_PORT", self.DEFAULT_GATEWAY_PORT)

        # Check for localhost vs remote
        host = os.environ.get("OCBS_WEBHOOK_HOST", "127.0.0.1")

        return f"http://{host}:{port}/hooks/wake"

    def _get_auth_token(self) -> Optional[str]:
        """Get authentication token from environment or config."""
        # Check environment variable first
        token = os.environ.get("OCBS_WEBHOOK_TOKEN")
        if token:
            return token

        # Try to get from OCBS config (where save_notification_config stores it)
        ocbs_config_file = self.state_dir / "config.json"
        if ocbs_config_file.exists():
            try:
                with open(ocbs_config_file) as f:
                    config = json.load(f)
                    token = config.get("webhook_token")
                    if token:
                        return token
            except (json.JSONDecodeError, OSError):
                pass

        # Try to get from OpenClaw config
        openclaw_config = Path.home() / ".openclaw" / "openclaw.json"
        if openclaw_config.exists():
            try:
                with open(openclaw_config) as f:
                    config = json.load(f)
                    # Try gateway auth token
                    token = config.get("gateway", {}).get("auth", {}).get("token")
                    if token:
                        return token
            except (json.JSONDecodeError, OSError):
                pass

        return None

    def _send_webhook(self, payload: dict) -> bool:
        """Send webhook to OpenClaw Gateway /hooks/wake endpoint.

        Payload format for /hooks/wake:
        {
            "text": "Notification message",  # required
            "mode": "now"                    # optional: "now" or "next-heartbeat"
        }

        Returns True if successful, False otherwise.
        """
        import urllib.request
        import urllib.error

        url = self._get_gateway_url()
        token = self._get_auth_token()

        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
        }

        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                if 200 <= response.status < 300:
                    logger.info(f"Webhook notification sent successfully: {response.status}")
                    return True
                else:
                    logger.warning(f"Webhook returned non-success status: {response.status}")
                    return False
        except urllib.error.HTTPError as e:
            logger.warning(f"Webhook HTTP error: {e.code} - {e.reason}")
            return False
        except urllib.error.URLError as e:
            logger.warning(f"Webhook connection failed: {e.reason}")
            return False
        except Exception as e:
            logger.warning(f"Webhook unexpected error: {e}")
            return False

    def _write_file_notification(self, notification: dict) -> bool:
        """Write notification to file as fallback when webhook fails."""
        try:
            notify_dir = self.state_dir / "notifications"
            notify_dir.mkdir(parents=True, exist_ok=True)

            # Use timestamp-based filename to avoid collisions
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            notify_file = notify_dir / f"ocbs_{timestamp}.json"

            notification["_ocbs_meta"] = {
                "created_at": datetime.now().isoformat(),
                "type": "webhook_fallback",
            }

            with open(notify_file, "w") as f:
                json.dump(notification, f, indent=2)

            logger.info(f"File notification written: {notify_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to write file notification: {e}")
            return False

    def notify(
        self,
        text: str,
        mode: str = "now",
        allow_fallback: bool = True,
    ) -> bool:
        """Send a notification to OpenClaw Gateway.

        Args:
            text: The notification message (required for /hooks/wake endpoint)
            mode: "now" for immediate wake, "next-heartbeat" for deferred
            allow_fallback: Whether to write file notification if webhook fails

        Returns:
            True if notification was sent successfully (via webhook or file)
        """
        # Validate text is not empty
        if not text or not text.strip():
            logger.warning("Cannot send notification with empty text")
            return False

        # Send to /hooks/wake with proper payload format
        payload = {
            "text": text.strip(),
            "mode": mode,
        }

        if self._send_webhook(payload):
            return True

        # Fallback to file-based notification
        if allow_fallback:
            logger.info("Falling back to file notification")
            return self._write_file_notification({"text": text, "mode": mode})

        return False

    def notify_backup_complete(
        self,
        backup_id: str,
        scope: str,
        file_count: int,
        reason: str = "",
    ) -> bool:
        """Send backup completion notification.

        Args:
            backup_id: The backup identifier
            scope: Backup scope (minimal, config, etc.)
            file_count: Number of files backed up
            reason: Optional reason for backup

        Returns:
            True if notification sent successfully
        """
        text = f"OCBS Backup completed - ID: {backup_id}, Scope: {scope}, Files: {file_count}"
        if reason:
            text = f"{text}, Reason: {reason}"

        return self.notify(text)

    def notify_restore_complete(
        self,
        backup_id: str,
        file_count: int,
        target_dir: str = "~/.openclaw",
    ) -> bool:
        """Send restore completion notification.

        Args:
            backup_id: The backup that was restored
            file_count: Number of files restored
            target_dir: Where files were restored to

        Returns:
            True if notification sent successfully
        """
        text = f"OCBS Restore completed - Backup: {backup_id}, Files: {file_count}, Target: {target_dir}"
        return self.notify(text)

    def notify_checkpoint_created(
        self,
        checkpoint_id: str,
        backup_id: str,
        reason: str = "",
    ) -> bool:
        """Send checkpoint creation notification.

        Args:
            checkpoint_id: The checkpoint identifier
            backup_id: The backup this checkpoint references
            reason: Optional reason for checkpoint

        Returns:
            True if notification sent successfully
        """
        text = f"OCBS Checkpoint created - ID: {checkpoint_id}, Backup: {backup_id}"
        if reason:
            text = f"{text}, Reason: {reason}"

        return self.notify(text)

    def notify_proceed(self, checkpoint_id: str, token: str) -> bool:
        """Send proceed notification when user acknowledges checkpoint.

        This uses the standard /hooks/wake endpoint with a simple status message.
        The OpenClaw agent should monitor for proceed notifications via polling
        the file-based notification directory or by being woken up.

        Args:
            checkpoint_id: The checkpoint that was acknowledged
            token: The proceed token

        Returns:
            True if notification sent successfully
        """
        text = f"OCBS Proceed: User acknowledged checkpoint {checkpoint_id}"
        success = self.notify(text)

        # Always write a specific proceed notification file for agent polling
        # This ensures the proceed file is created regardless of webhook success
        try:
            notify_dir = self.state_dir / "proceed_notifications"
            notify_dir.mkdir(parents=True, exist_ok=True)
            proceed_file = notify_dir / f"{token}.json"
            proceed_data = {
                "token": token,
                "checkpoint_id": checkpoint_id,
                "proceeded_at": datetime.now().isoformat(),
                "status": "pending_agent_poll",
            }
            with open(proceed_file, "w") as f:
                json.dump(proceed_data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write proceed notification file: {e}")

        return success

    def test_notification(self) -> bool:
        """Send a test notification to verify Gateway connectivity.

        Returns:
            True if test notification was received successfully
        """
        return self.notify("OCBS Test notification - Gateway connectivity verified", mode="now")


# Module-level convenience functions
_default_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Get the default notification manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = NotificationManager()
    return _default_manager


def notify(text: str, mode: str = "now") -> bool:
    """Send a notification using the default manager."""
    return get_notification_manager().notify(text, mode)


def notify_backup_complete(backup_id: str, scope: str, file_count: int, reason: str = "") -> bool:
    """Send backup complete notification using the default manager."""
    return get_notification_manager().notify_backup_complete(backup_id, scope, file_count, reason)


def notify_restore_complete(backup_id: str, file_count: int, target_dir: str = "~/.openclaw") -> bool:
    """Send restore complete notification using the default manager."""
    return get_notification_manager().notify_restore_complete(backup_id, file_count, target_dir)


def notify_checkpoint_created(checkpoint_id: str, backup_id: str, reason: str = "") -> bool:
    """Send checkpoint created notification using the default manager."""
    return get_notification_manager().notify_checkpoint_created(checkpoint_id, backup_id, reason)


def notify_proceed(checkpoint_id: str, token: str) -> bool:
    """Send proceed notification using the default manager."""
    return get_notification_manager().notify_proceed(checkpoint_id, token)


def test_notification() -> bool:
    """Send a test notification using the default manager."""
    return get_notification_manager().test_notification()