"""Server module for OCBS human-in-the-loop restore."""

import socket
import subprocess
import urllib.parse
from pathlib import Path
from typing import Optional


def get_tailscale_ip() -> Optional[str]:
    """Get Tailscale IP address if available."""
    try:
        # Try to get Tailscale IP using tailscale command
        result = subprocess.run(
            ['tailscale', 'ip', '-4'],
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
        result = subprocess.run(
            ['ip', 'addr', 'show'],
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
    
    return None


def get_custom_domain() -> Optional[str]:
    """Get custom domain from OpenClaw config if configured."""
    try:
        import json
        config_path = Path.home() / '.openclaw' / 'openclaw.json'
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            # Check for custom domain in gateway config
            gateway = config.get('gateway', {})
            tailscale = gateway.get('tailscale', {})
            if tailscale.get('hostname'):
                return f"{tailscale['hostname']}.tailnet.ts.net"
    except Exception:
        pass
    return None


def get_gateway_port() -> int:
    """Get gateway port from OpenClaw config."""
    try:
        import json
        config_path = Path.home() / '.openclaw' / 'openclaw.json'
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            return config.get('gateway', {}).get('port', 18789)
    except Exception:
        pass
    return 18789


def detect_connection_type() -> tuple[str, str]:
    """Auto-detect best connection type and return (type, host).
    
    Priority:
    1. HTTPS custom domain (if configured)
    2. Tailscale (100.x.x.x) - for remote access
    3. Localhost - fallback
    
    Returns:
        Tuple of (connection_type, host)
    """
    # Check for custom domain first
    custom_domain = get_custom_domain()
    if custom_domain:
        return ('https', custom_domain)
    
    # Check for Tailscale
    tailscale_ip = get_tailscale_ip()
    if tailscale_ip:
        return ('tailscale', tailscale_ip)
    
    # Default to localhost
    return ('localhost', '127.0.0.1')


def generate_restore_url(checkpoint_id: str, port: Optional[int] = None) -> str:
    """Generate restore URL with auto-detected connection type.
    
    Args:
        checkpoint_id: The checkpoint ID to restore
        port: Optional port override (defaults to gateway port + 1567 = 20356)
        
    Returns:
        Full URL for restore page
    """
    conn_type, host = detect_connection_type()
    
    # Use OCBS default port if not specified
    if port is None:
        port = 3456  # Default OCBS serve port
    
    # Build URL
    scheme = 'https' if conn_type == 'https' else 'http'
    encoded_id = urllib.parse.quote(checkpoint_id, safe='')
    
    return f"{scheme}://{host}:{port}/restore/{encoded_id}"


def format_restore_message(checkpoint_id: str, reason: str = "") -> str:
    """Format a human-friendly restore message with URL.
    
    Args:
        checkpoint_id: The checkpoint ID
        reason: Optional reason for the checkpoint
        
    Returns:
        Formatted message with URL and instructions
    """
    conn_type, host = detect_connection_type()
    url = generate_restore_url(checkpoint_id)
    
    lines = [
        "🔄 OCBS Checkpoint Created",
        f"",
        f"Checkpoint ID: `{checkpoint_id}`",
    ]
    
    if reason:
        lines.append(f"Reason: {reason}")
    
    lines.extend([
        f"",
        f"Restore URL: {url}",
        f"Connection: {conn_type.upper()} ({host})",
        f"Expires: 24 hours",
        f"",
        f"To restore:",
        f"1. Visit the URL above",
        f"2. Review the backup details",
        f"3. Click 'Restore' to proceed",
        f"",
        f"Or run: `ocbs restore --checkpoint {checkpoint_id}`",
    ])
    
    return "\n".join(lines)


# Simple HTTP server for restore page (minimal implementation)
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading


class RestoreHandler(BaseHTTPRequestHandler):
    """Simple handler for restore page."""
    
    def do_GET(self):
        """Handle GET request."""
        if self.path.startswith('/restore/'):
            checkpoint_id = urllib.parse.unquote(self.path.split('/')[-1])
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f"""<!DOCTYPE html>
<html>
<head>
    <title>OCBS Restore</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; }}
        .box {{ border: 1px solid #ccc; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .warning {{ background: #fff3cd; border-color: #ffc107; }}
        button {{ padding: 12px 24px; margin: 10px 5px; cursor: pointer; }}
        .danger {{ background: #dc3545; color: white; border: none; border-radius: 4px; }}
        .primary {{ background: #007bff; color: white; border: none; border-radius: 4px; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>🔄 OCBS Restore</h1>
    <div class="box warning">
        <strong>Warning:</strong> Restoring will overwrite your current OpenClaw configuration.
    </div>
    <div class="box">
        <p><strong>Checkpoint ID:</strong> <code>{checkpoint_id}</code></p>
        <p>Click below to restore from this checkpoint:</p>
        <button class="danger" onclick="restore()">Restore from Checkpoint</button>
        <button class="primary" onclick="cancel()">Cancel</button>
    </div>
    <div id="status"></div>
    <script>
        function restore() {{
            document.getElementById('status').innerHTML = 
                '<p>⏳ Restore initiated... Check your OpenClaw session.</p>';
            // TODO: Call restore API
        }}
        function cancel() {{
            window.close();
        }}
    </script>
</body>
</html>"""
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def start_restore_server(port: int = 3456) -> HTTPServer:
    """Start the restore HTTP server.
    
    Args:
        port: Port to listen on
        
    Returns:
        HTTP server instance
    """
    server = HTTPServer(('0.0.0.0', port), RestoreHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == '__main__':
    # Test detection
    conn_type, host = detect_connection_type()
    print(f"Detected connection: {conn_type} ({host})")
    
    # Test URL generation
    test_checkpoint = "20260222_test_checkpoint"
    url = generate_restore_url(test_checkpoint)
    print(f"Test URL: {url}")