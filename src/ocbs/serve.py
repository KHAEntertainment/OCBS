"""
Web server for serving OCBS restore pages with token-based authentication.
"""

import shutil
import socket
import subprocess
import urllib.parse
from http.server import HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from .core import OCBSCore

def get_tailscale_ip() -> Optional[str]:
    """Get Tailscale IP address if available."""
    try:
        # Resolve absolute path for tailscale command
        tailscale_path = shutil.which('tailscale')
        if tailscale_path:
            # Try to get Tailscale IP using tailscale command
            result = subprocess.run(
                [tailscale_path, 'ip', '-4'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                ip = result.stdout.strip()
                # Validate it's a Tailscale IP (100.x.x.x)
                if ip.startswith('100.'):
                    return ip
    except (subprocess.SubprocessError, FileNotFoundError, TimeoutError):
        pass
    
    # Fallback: check network interfaces
    try:
        # Resolve absolute path for ip command
        ip_path = shutil.which('ip')
        if ip_path:
            result = subprocess.run(
                [ip_path, 'addr', 'show'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'inet 100.' in line:
                        # Extract IP from line like "inet 100.104.73.51/32..."
                        parts = line.split()
                        for part in parts:
                            if part.startswith('100.'):
                                return part.split('/')[0]
    except (subprocess.SubprocessError, FileNotFoundError, TimeoutError):
        pass
    
    def _generate_token(self) -> str:
        """Generate a secure random token."""
        return secrets.token_urlsafe(32)
    
    def _create_serve_record(self, checkpoint_id: str, expires_hours: int = 4) -> str:
        """Create a serve record for a checkpoint and return the token."""
        token = self._generate_token()
        expires_at = datetime.now() + timedelta(hours=expires_hours)
        
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            
            # Create serve_records table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS serve_records (
                    token TEXT PRIMARY KEY,
                    checkpoint_id TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    used INTEGER DEFAULT 0,
                    proceeded INTEGER DEFAULT 0,
                    restored INTEGER DEFAULT 0,
                    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
                )
            """)
            
            conn.execute(
                """INSERT INTO serve_records (token, checkpoint_id, created_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (token, checkpoint_id, datetime.now().isoformat(), expires_at.isoformat())
            )
        
        self._active_tokens[token] = {
            'checkpoint_id': checkpoint_id,
            'expires_at': expires_at,
            'used': False
        }
        
        return token
    
    def _get_checkpoint_info(self, checkpoint_id: str) -> Optional[dict]:
        """Get checkpoint details including backup info."""
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            
            cursor = conn.execute(
                """SELECT c.checkpoint_id, c.backup_id, c.reason, c.timestamp,
                          b.scope, b.timestamp, b.reason
                   FROM checkpoints c
                   JOIN backups b ON c.backup_id = b.backup_id
                   WHERE c.checkpoint_id = ? AND c.active = 1""",
                (checkpoint_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Get file count
            cursor = conn.execute(
                "SELECT COUNT(*) FROM backup_files WHERE backup_id = ?",
                (row[1],)
            )
            file_count = cursor.fetchone()[0]
            
            return {
                'checkpoint_id': row[0],
                'backup_id': row[1],
                'reason': row[2],
                'checkpoint_timestamp': row[3],
                'scope': row[4],
                'backup_timestamp': row[5],
                'reason_text': row[6],
                'file_count': file_count
            }
    
    def _validate_token(self, token: str) -> Optional[dict]:
        """Validate a token and return serve record if valid."""
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            
            # Ensure table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS serve_records (
                    token TEXT PRIMARY KEY,
                    checkpoint_id TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    used INTEGER DEFAULT 0,
                    proceeded INTEGER DEFAULT 0,
                    restored INTEGER DEFAULT 0,
                    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
                )
            """)
            
            cursor = conn.execute(
                """SELECT token, checkpoint_id, expires_at, used, proceeded, restored
                   FROM serve_records WHERE token = ?""",
                (token,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            expires_at = datetime.fromisoformat(row[2])
            if expires_at < datetime.now():
                return None
            
            return {
                'token': row[0],
                'checkpoint_id': row[1],
                'expires_at': expires_at,
                'used': bool(row[3]),
                'proceeded': bool(row[4]),
                'restored': bool(row[5])
            }
    
    def _mark_proceeded(self, token: str, checkpoint_id: str):
        """Mark a token as proceeded and send webhook notification."""
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                "UPDATE serve_records SET proceeded = 1 WHERE token = ?",
                (token,)
            )

        # Send webhook notification to gateway
        self._send_webhook_notification(token, checkpoint_id)
    
    def _write_proceed_notification(self, token: str, checkpoint_id: str = None):
        """Write a notification file when user clicks 'I received this'."""
        import os
        from datetime import datetime
        
        # Create notification directory
        notify_dir = Path.home() / ".config" / "ocbs" / "proceed_notifications"
        notify_dir.mkdir(parents=True, exist_ok=True)
        
        # Write notification file with timestamp
        notify_file = notify_dir / f"{token}.json"
        notification = {
            "token": token,
            "checkpoint_id": checkpoint_id,
            "proceeded_at": datetime.now().isoformat(),
            "status": "pending_agent_poll"
        }
        
        with open(notify_file, 'w') as f:
            json.dump(notification, f)
    
    def _send_webhook_notification(self, token: str, checkpoint_id: str = None):
        """Send webhook notification to gateway when user clicks proceed."""
        import urllib.request
        import urllib.error
        
        # Get webhook URL from environment or use default
        webhook_url = os.environ.get('OCBS_WEBHOOK_URL', 'http://localhost:18789/hooks/ocbs-proceed')
        webhook_token = os.environ.get('OCBS_WEBHOOK_TOKEN', 'ocbs-webhook-secret')
        
        payload = json.dumps({
            "message": f"OCBS Proceed: User acknowledged checkpoint {checkpoint_id}. Token: {token}",
            "token": token,
            "checkpoint_id": checkpoint_id,
            "action": "proceed"
        }).encode('utf-8')
        
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {webhook_token}'
            },
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                print(f"Webhook notification sent: {response.status}")
        except urllib.error.URLError as e:
            print(f"Webhook notification failed: {e}")
            # Fall back to file notification
            self._write_proceed_notification(token, checkpoint_id)
    
    def get_pending_proceed_notifications(self) -> list[dict]:
        """Get all pending proceed notifications (for agent polling)."""
        notify_dir = Path.home() / ".config" / "ocbs" / "proceed_notifications"
        if not notify_dir.exists():
            return []
        
        notifications = []
        for f in notify_dir.glob("*.json"):
            try:
                with open(f, 'r') as nf:
                    notifications.append(json.load(nf))
            except (json.JSONDecodeError, IOError):
                continue
        
        return notifications
    
    def clear_proceed_notification(self, token: str):
        """Clear a proceed notification after agent has processed it."""
        notify_dir = Path.home() / ".config" / "ocbs" / "proceed_notifications"
        notify_file = notify_dir / f"{token}.json"
        if notify_file.exists():
            notify_file.unlink()
    
    def _mark_used(self, token: str) -> bool:
        """Mark a token as used (restore button clicked) atomically.

        Returns True if the token was successfully marked as used,
        False if it was already used or doesn't exist.
        """
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                "UPDATE serve_records SET used = 1 WHERE token = ? AND used = 0",
                (token,)
            )
            return cursor.rowcount > 0
    
    def _mark_restored(self, token: str):
        """Mark a restore as completed."""
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                "UPDATE serve_records SET restored = 1 WHERE token = ?",
                (token,)
            )
    
    def get_active_serves(self) -> list[dict]:
        """Get all active serve records."""
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            
            # Ensure table exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS serve_records (
                    token TEXT PRIMARY KEY,
                    checkpoint_id TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    used INTEGER DEFAULT 0,
                    proceeded INTEGER DEFAULT 0,
                    restored INTEGER DEFAULT 0,
                    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id)
                )
            """)
            
            cursor = conn.execute(
                """SELECT token, checkpoint_id, created_at, expires_at, used, proceeded, restored
                   FROM serve_records WHERE expires_at > ? ORDER BY created_at DESC""",
                (datetime.now().isoformat(),)
            )
            
            return [
                {
                    'token': row[0][:8] + '...',  # Truncate for display
                    'checkpoint_id': row[1],
                    'created_at': row[2],
                    'expires_at': row[3],
                    'used': bool(row[4]),
                    'proceeded': bool(row[5]),
                    'restored': bool(row[6])
                }
                for row in cursor.fetchall()
            ]
    
    def serve_checkpoint(self, checkpoint_id: str, expires_hours: int = 4) -> str:
        """Create a serve page for a checkpoint and return the URL token."""
        # Verify checkpoint exists
        info = self._get_checkpoint_info(checkpoint_id)
        if not info:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        
        token = self._create_serve_record(checkpoint_id, expires_hours)
        return token
    
    def get_restore_url(self, token: str) -> str:
        """Get the full restore URL for a token."""
        return f"http://{self.host}:{self.port}/restore/{token}"
    
    def _get_html_page(self, token: str, checkpoint_info: dict, expires_at: datetime, 
                       is_expired: bool = False, is_used: bool = False, 
                       is_proceeded: bool = False, is_restored: bool = False) -> str:
        """Generate the restore page HTML."""
        remaining = expires_at - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        
        reason = html_module.escape(checkpoint_info.get('reason', 'No reason provided'))
        checkpoint_timestamp = datetime.fromisoformat(checkpoint_info['checkpoint_timestamp'])
        escaped_scope = html_module.escape(checkpoint_info.get('scope', ''))
        
        status_message = ""
        step1_button_class = "btn-step"
        step1_button_text = "Step 1: I received this - start changes"
        step1_button_disabled = ""
        work_underway_display = "none"
        
        if is_restored:
            status_message = """
            <div class="alert alert-success">
                <strong>✓ Restore Completed!</strong><br>
                Your system has been restored to the checkpoint.
                The gateway should restart automatically.
            </div>
            """
            step1_button_disabled = "disabled"
            step1_button_class = "btn-disabled"
        elif is_used or is_expired:
            status_message = """
            <div class="alert alert-warning">
                <strong>⚠️ This restore page has expired or been used.</strong><br>
                Please request a new link from your agent.
            </div>
            """
            step1_button_disabled = "disabled"
            step1_button_class = "btn-disabled"
        elif is_proceeded:
            status_message = """
            <div class="alert alert-info">
                <strong>✓ Work underway!</strong><br>
                The agent has been notified that you received this link.
                If things go wrong, use the restore options below.
            </div>
            """
            step1_button_text = "✅ Work underway"
            work_underway_display = "block"
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OCBS Emergency Restore</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 16px;
            padding: 40px;
            max-width: 600px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        h1 {{
            color: #1a1a2e;
            margin-bottom: 24px;
            font-size: 28px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .icon {{ font-size: 32px; }}
        .info-grid {{
            display: grid;
            gap: 16px;
            margin: 24px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 12px;
        }}
        .info-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .info-item:last-child {{ border-bottom: none; }}
        .info-label {{ color: #666; font-weight: 500; }}
        .info-value {{ color: #1a1a2e; font-weight: 600; }}
        .warning {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 8px;
            padding: 16px;
            margin: 20px 0;
            color: #856404;
        }}
        .btn {{
            width: 100%;
            padding: 16px 24px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-top: 12px;
        }}
        .btn-primary {{
            background: #0d6efd;
            color: white;
        }}
        .btn-primary:hover:not(:disabled) {{
            background: #0b5ed7;
            transform: translateY(-2px);
        }}
        .btn-step {{
            background: #198754;
            color: white;
            font-size: 17px;
        }}
        .btn-step:hover:not(:disabled) {{
            background: #157347;
            transform: translateY(-2px);
        }}
        .btn-restart {{
            background: #6c757d;
            color: white;
        }}
        .btn-restart:hover:not(:disabled) {{
            background: #5a6268;
            transform: translateY(-2px);
        }}
        .btn-danger {{
            background: #dc3545;
            color: white;
            font-size: 17px;
            padding: 18px;
        }}
        .btn-danger:hover:not(:disabled) {{
            background: #c82333;
            transform: translateY(-2px);
        }}
        .btn-disabled {{
            background: #6c757d;
            cursor: not-allowed;
            opacity: 0.6;
        }}
        .btn:disabled {{
            cursor: not-allowed;
            opacity: 0.6;
        }}
        .restore-section {{
            margin-top: 8px;
        }}
        .restore-section-text {{
            color: #666;
            font-size: 14px;
            margin-bottom: 12px;
            text-align: center;
        }}
        .alert {{
            padding: 16px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .alert-success {{ background: #d4edda; color: #155724; }}
        .alert-warning {{ background: #fff3cd; color: #856404; }}
        .alert-info {{ background: #cce5ff; color: #004085; }}
        .expiry {{
            text-align: center;
            color: #666;
            font-size: 14px;
            margin-top: 24px;
        }}
        .spinner {{
            display: none;
            width: 20px;
            height: 20px;
            border: 2px solid #fff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-left: 8px;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        .work-timer {{
            display: {work_underway_display};
            text-align: center;
            color: #0d6efd;
            font-size: 14px;
            margin-top: 8px;
            font-weight: 500;
        }}
        .step-label {{
            display: inline-block;
            background: #0d6efd;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-right: 8px;
        }}
        .step-label.step2 {{
            background: #dc3545;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1><span class="icon">🛡️</span> OCBS Emergency Restore</h1>
        
        <div class="info-grid">
            <div class="info-item">
                <span class="info-label">Checkpoint</span>
                <span class="info-value">{reason}</span>
            </div>
            <div class="info-item">
                <span class="info-label">Created</span>
                <span class="info-value">{checkpoint_timestamp.strftime('%B %d, %Y at %I:%M %p')}</span>
            </div>
            <div class="info-item">
                <span class="info-label">Files to restore</span>
                <span class="info-value">{checkpoint_info['file_count']} files</span>
            </div>
            <div class="info-item">
                <span class="info-label">Scope</span>
                <span class="info-value">{escaped_scope}</span>
            </div>
        </div>
        
        <div class="warning">
            ⚠️ This will restore your system to the state before the change.
            Only use the restore options below if something goes wrong!
        </div>
        
        {status_message}
        
        <form id="proceed-form" action="/proceed" method="POST">
            <input type="hidden" name="token" value="{token}">
            <button type="submit" class="btn {step1_button_class}" {step1_button_disabled} id="step1-btn">
                {step1_button_text}
            </button>
        </form>
        
        <div class="work-timer" id="work-timer">
            ⏱️ Work underway for: <span id="elapsed">0:00</span>
        </div>
        
        <div class="restore-section">
            <p class="restore-section-text">
                If anything goes wrong, you can restore:
            </p>
            
            <form action="/restart" method="POST">
                <input type="hidden" name="token" value="{token}">
                <button type="submit" class="btn btn-restart" {step1_button_disabled}
                        onclick="return confirm('Restart the gateway without restoring? This may help resolve minor issues.');">
                    🔄 Restart Gateway
                </button>
            </form>
            
            <form action="/restore" method="POST">
                <input type="hidden" name="token" value="{token}">
                <button type="submit" class="btn btn-danger" {step1_button_disabled} 
                        onclick="return confirm('Are you sure you want to RESTORE? This will revert all changes!');">
                    <span class="step-label step2">Step 2</span>
                    🔴 Restore Backup & Restart
                    <span class="spinner" id="restore-spinner"></span>
                </button>
            </form>
        </div>
        
        <p class="expiry">Link expires in {hours}h {minutes}m</p>
    </div>
    
    <script>
        // Handle proceed form submission with AJAX
        document.getElementById('proceed-form').addEventListener('submit', function(e) {{
            e.preventDefault();

            const form = this;
            const btn = document.getElementById('step1-btn');
            const token = form.token.value;

            // Submit via fetch
            fetch('/proceed', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                body: 'token=' + encodeURIComponent(token)
            }})
            .then(response => {{
                if (!response.ok) {{
                    throw new Error('Server returned ' + response.status);
                }}
                return response.text();
            }})
            .then(html => {{
                // Parse the response and check for success
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const alertDiv = doc.querySelector('.alert');

                // Only update UI if we got a valid success response
                if (alertDiv && alertDiv.classList.contains('alert-info')) {{
                    // Change button to show work underway
                    btn.innerHTML = '✅ Work underway';
                    btn.disabled = true;
                    document.getElementById('work-timer').style.display = 'block';

                    // Start elapsed timer
                    let seconds = 0;
                    const timerEl = document.getElementById('elapsed');
                    setInterval(function() {{
                        seconds++;
                        const mins = Math.floor(seconds / 60);
                        const secs = seconds % 60;
                        timerEl.textContent = mins + ':' + (secs < 10 ? '0' : '') + secs;
                    }}, 1000);

                    // Update the status alert
                    const currentAlert = document.querySelector('.alert');
                    if (currentAlert) {{
                        currentAlert.innerHTML = alertDiv.innerHTML;
                    }}
                }} else {{
                    // Show error if we didn't get expected success response
                    alert('Failed to proceed. Please try again or refresh the page.');
                }}
            }})
            .catch(err => {{
                console.error('Error:', err);
                alert('Failed to proceed: ' + err.message);
            }});
        }});
        
        // Handle restore form
        document.querySelector('form[action="/restore"]').addEventListener('submit', function(e) {{
            if (!confirm('Are you sure? This will restore from the checkpoint.')) {{
                e.preventDefault();
            }} else {{
                document.getElementById('restore-spinner').style.display = 'inline-block';
            }}
        }});
    </script>
</body>
</html>
"""
    
    def do_GET(self):
        """Handle GET request."""
        if self.path.startswith('/restore/'):
            checkpoint_id = urllib.parse.unquote(self.path.split('/')[-1])
            # HTML-escape checkpoint_id to prevent XSS
            import html
            safe_checkpoint_id = html.escape(checkpoint_id)
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            def do_POST(self):
                if self.path == '/proceed':
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()
                    
                    # Parse form data
                    params = {}
                    for pair in body.split('&'):
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            params[key] = value
                    
                    token = params.get('token')
                    if token:
                        # Validate token FIRST before taking any action
                        serve_record = server_instance._validate_token(token)
                        if not serve_record:
                            self.send_error(404, "Invalid or expired token")
                            return

                        checkpoint_id = serve_record['checkpoint_id']

                        # Mark as proceeded in DB and send webhook notification
                        server_instance._mark_proceeded(token, checkpoint_id)

                        # Write notification file to notify agent (fallback if webhook fails)
                        server_instance._write_proceed_notification(token, checkpoint_id)
                        
                        # Return styled HTML that updates UI via JavaScript
                        proceed_status_html = """
                        <div class="alert alert-info">
                            <strong>✓ Work underway!</strong><br>
                            The agent has been notified that you received this link.
                            If things go wrong, use the restore options below.
                        </div>
                        """
                        response_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OCBS - Proceed Acknowledged</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); 
               min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }}
        .container {{ background: white; border-radius: 16px; padding: 40px; max-width: 500px; width: 100%; 
                     box-shadow: 0 20px 60px rgba(0,0,0,0.3); text-align: center; }}
        h1 {{ color: #198754; margin-bottom: 16px; }}
        p {{ color: #666; margin-bottom: 24px; }}
        .alert {{ padding: 16px; border-radius: 8px; margin: 20px 0; background: #cce5ff; color: #004085; text-align: left; }}
        .btn {{ padding: 12px 24px; background: #0d6efd; color: white; border: none; border-radius: 8px; 
               font-size: 16px; cursor: pointer; }}
    </style>
</head>
<body>
    <h1>🔄 OCBS Restore</h1>
    <div class="box warning">
        <strong>Warning:</strong> Restoring will overwrite your current OpenClaw configuration.
    </div>
    <div class="box">
        <p><strong>Checkpoint ID:</strong> <code>{safe_checkpoint_id}</code></p>
        <p>Click below to restore from this checkpoint:</p>
        <button class="danger" onclick="restore()">Restore from Checkpoint</button>
        <button class="primary" onclick="cancel()">Cancel</button>
    </div>
    <script>
        // Try to update parent window and close popup if opened as separate window
        if (window.opener) {{
            try {{
                window.opener.location.reload();
            }} catch(e) {{}}
        }}
    </script>
</body>
</html>"""
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html')
                        self.end_headers()
                        self.wfile.write(response_html.encode())
                    else:
                        self.send_error(400, "Missing token")
                
                elif self.path == '/restore':
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length).decode()

                    # Parse form data
                    params = {}
                    for pair in body.split('&'):
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            params[key] = value

def start_restore_server(port: Optional[int] = 3456, bind_host: str = '127.0.0.1') -> HTTPServer:
    """Start the restore HTTP server.
    
    Args:
        port: Port to listen on. If None, the default (3456) is used.
        bind_host: Host to bind to (default: 127.0.0.1 for security)
                    Set to '0.0.0.0' to allow remote access (use with caution!)
        
    Returns:
        HTTP server instance
    """
    if port is None:
        port = 3456
    # Validate bind_host for security
    if bind_host == '0.0.0.0':
        print("Warning: Binding to 0.0.0.0 allows remote access. Use only on trusted networks.")
    
    server = HTTPServer((bind_host, port), RestoreHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == '__main__':
    # Test detection
    conn_type, host = detect_connection_type()
    print(f"Detected connection: {conn_type} ({host})")


def format_restore_message(checkpoint_id: str, reason: str,
                          port: int = 18790, host: str = "localhost") -> str:
    """Format a restore message with URL for a checkpoint."""
    return f"""Checkpoint created: {checkpoint_id}
Reason: {reason}

Restore functionality requires server setup.
"""


def generate_restore_url(checkpoint_id: str, port: int = 18790, host: str = "localhost") -> str:
    """Generate a restore URL for a checkpoint."""
    return f"http://{host}:{port}/restore?checkpoint={checkpoint_id}"