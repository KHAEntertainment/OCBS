"""
Web server for serving OCBS restore pages with token-based authentication.
"""

import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from .core import OCBSCore


class RestorePageServer:
    """HTTP server for serving restore pages with token authentication."""
    
    def __init__(self, state_dir: Optional[Path] = None, port: int = 18789, host: str = "localhost"):
        self.port = port
        self.host = host
        self.core = OCBSCore(state_dir=state_dir)
        self.server: Optional[HTTPServer] = None
        self._serve_thread: Optional[threading.Thread] = None
        self._active_tokens: dict[str, dict] = {}  # token -> {checkpoint_id, expires_at, used}
    
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
    
    def _mark_proceeded(self, token: str):
        """Mark a token as proceeded."""
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                "UPDATE serve_records SET proceeded = 1 WHERE token = ?",
                (token,)
            )
    
    def _mark_used(self, token: str):
        """Mark a token as used (restore button clicked)."""
        with sqlite3.connect(self.core.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                "UPDATE serve_records SET used = 1 WHERE token = ?",
                (token,)
            )
    
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
        
        reason = checkpoint_info.get('reason', 'No reason provided')
        checkpoint_timestamp = datetime.fromisoformat(checkpoint_info['checkpoint_timestamp'])
        
        status_message = ""
        button_disabled = ""
        button_class = "btn-primary"
        
        if is_restored:
            status_message = """
            <div class="alert alert-success">
                <strong>✓ Restore Completed!</strong><br>
                Your system has been restored to the checkpoint.
                The gateway should restart automatically.
            </div>
            """
            button_disabled = "disabled"
            button_class = "btn-disabled"
        elif is_used or is_expired:
            status_message = """
            <div class="alert alert-warning">
                <strong>⚠️ This restore page has expired or been used.</strong><br>
                Please request a new link from your agent.
            </div>
            """
            button_disabled = "disabled"
            button_class = "btn-disabled"
        elif is_proceeded:
            status_message = """
            <div class="alert alert-info">
                <strong>✓ Acknowledged!</strong><br>
                The agent has been notified that you received this link.
                You may proceed with the change. If things go wrong, 
                come back and click the restore button.
            </div>
            """
        
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
        .btn-danger {{
            background: #dc3545;
            color: white;
            font-size: 18px;
            padding: 20px;
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
        .divider {{
            display: flex;
            align-items: center;
            margin: 24px 0;
            color: #999;
        }}
        .divider::before, .divider::after {{
            content: '';
            flex: 1;
            height: 1px;
            background: #ddd;
        }}
        .divider span {{ padding: 0 16px; }}
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
                <span class="info-value">{checkpoint_info['scope']}</span>
            </div>
        </div>
        
        <div class="warning">
            ⚠️ This will restore your system to the state before the change.
            Only click the restore button if something went wrong!
        </div>
        
        {status_message}
        
        <form action="/proceed" method="POST">
            <input type="hidden" name="token" value="{token}">
            <button type="submit" class="btn btn-primary" {button_disabled}>
                ✓ I received this - proceed with change
            </button>
        </form>
        
        <div class="divider"><span>OR</span></div>
        
        <form action="/restore" method="POST">
            <input type="hidden" name="token" value="{token}">
            <button type="submit" class="btn btn-danger" {button_disabled} 
                    onclick="return confirm('Are you sure you want to RESTORE? This will revert changes!');">
                🔴 RESTORE & RESTART GATEWAY
                <span class="spinner" id="restore-spinner"></span>
            </button>
        </form>
        
        <p class="expiry">Link expires in {hours}h {minutes}m</p>
    </div>
    
    <script>
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
    
    def start(self, background: bool = False):
        """Start the HTTP server.
        
        Args:
            background: If True, run in background thread. If False, block.
        """
        global server_instance
        server_instance = self
        
        class RestoreHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress logging
            
            def do_GET(self):
                if self.path.startswith('/restore/'):
                    token = self.path[9:]  # Remove '/restore/'
                    serve_record = server_instance._validate_token(token)
                    
                    if not serve_record:
                        self.send_error(404, "Invalid or expired link")
                        return
                    
                    checkpoint_info = server_instance._get_checkpoint_info(
                        serve_record['checkpoint_id']
                    )
                    
                    if not checkpoint_info:
                        self.send_error(404, "Checkpoint not found")
                        return
                    
                    expires_at = serve_record['expires_at']
                    is_expired = expires_at < datetime.now()
                    is_used = serve_record['used']
                    is_proceeded = serve_record['proceeded']
                    is_restored = serve_record['restored']
                    
                    html = server_instance._get_html_page(
                        token, checkpoint_info, expires_at, is_expired, is_used, is_proceeded, is_restored
                    )
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.end_headers()
                    self.wfile.write(html.encode())
                else:
                    self.send_error(404, "Not Found")
            
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
                    
                    token = params                    
                    token = params.get('token')
                    if token:
                        server_instance._mark_proceeded(token)
                        
                        # In a real implementation, this would notify the agent
                        # For now, we just mark it as proceeded
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html')
                        self.end_headers()
                        response = b"<html><body><h1>Acknowledged!</h1><p>The agent has been notified. You may proceed with the change.</p></body></html>"
                        self.wfile.write(response)
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
                    
                    token = params.get('token')
                    if token:
                        # Perform restore
                        checkpoint_id = server_instance._validate_token(token)
                        if checkpoint_id:
                            checkpoint_id = checkpoint_id.get('checkpoint_id')
                            if checkpoint_id:
                                server_instance.core.restore(checkpoint_id=checkpoint_id)
                                server_instance._mark_restored(token)
                                
                                self.send_response(200)
                                self.send_header('Content-Type', 'text/html')
                                self.end_headers()
                                response = b"<html><body><h1>Restore Complete!</h1><p>Your system has been restored to the checkpoint.</p></body></html>"
                                self.wfile.write(response)
                                return
                        
                        self.send_error(404, "Invalid token")
                    else:
                        self.send_error(400, "Missing token")
                else:
                    self.send_error(404, "Not Found")
        
        # Create and start the server
        # Bind to all interfaces for accessibility; URL host is what the user sees
        self.server = HTTPServer(('0.0.0.0', self.port), RestoreHandler)
        
        # Run in background thread if requested
        if background:
            self._serve_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self._serve_thread.start()
        else:
            # Block and serve forever
            self.server.serve_forever()
    
    def stop(self):
        """Stop the HTTP server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
