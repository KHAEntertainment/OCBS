"""
CLI commands for serving OCBS restore pages.
"""

import os
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Optional

import click

from .core import OCBSCore
from .serve import RestorePageServer


# Environment variable for default host
OCBS_SERVE_HOST = os.environ.get('OCBS_SERVE_HOST', 'localhost')


@click.group()
def serve():
    """Commands for serving restore pages."""
    pass


@serve.command()
@click.option('--checkpoint', '-c', required=True, help='Checkpoint ID to serve')
@click.option('--expires', '-e', default='4h', 
              help='Link expiry time (e.g., 4h, 1d, 30m)')
@click.option('--port', '-p', default=18789, type=int, help='Port to serve on')
@click.option('--host', '-H', default=OCBS_SERVE_HOST, 
              help=f'Host for URL (default: {OCBS_SERVE_HOST}, or set OCBS_SERVE_HOST env var)')
@click.option('--background', '-b', is_flag=True, help='Run server in background')
@click.pass_context
def start(ctx, checkpoint, expires, port, host, background):
    """Serve a checkpoint restore page."""
    core = ctx.obj['core']
    
    # Parse expiry time
    expires_hours = _parse_expiry(expires)
    if expires_hours <= 0:
        click.echo(f"Invalid expiry time: {expires}", err=True)
        sys.exit(1)
    
    server = RestorePageServer(state_dir=core.state_dir, port=port, host=host)
    
    try:
        token = server.serve_checkpoint(checkpoint, expires_hours)
        url = server.get_restore_url(token)
        
        click.echo(f"Restore page created for checkpoint: {checkpoint}")
        click.echo(f"URL: {url}")
        click.echo(f"Expires in: {expires}")
        
        if background:
            server.start(background=True)
            click.echo(f"Server running in background on port {port}")
            # Keep the server running briefly to ensure it starts
            time.sleep(1)
        else:
            click.echo(f"\nPress Ctrl+C to stop the server")
            try:
                server.start()
            except KeyboardInterrupt:
                click.echo("\nServer stopped")
                
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@serve.command()
@click.pass_context
def status(ctx):
    """Show active restore page status."""
    core = ctx.obj['core']
    server = RestorePageServer(state_dir=core.state_dir)
    
    serves = server.get_active_serves()
    
    if not serves:
        click.echo("No active restore pages")
        return
    
    click.echo(f"Active restore pages ({len(serves)}):")
    for serve in serves:
        expires_at = serve['expires_at']
        remaining = _format_remaining(expires_at)
        
        status_icon = "○"
        if serve['restored']:
            status_icon = "✓"
        elif serve['proceeded']:
            status_icon = "●"
        elif serve['used']:
            status_icon = "◐"
        
        click.echo(f"  {status_icon} {serve['checkpoint_id'][:20]}...")
        click.echo(f"      Token: {serve['token']}")
        click.echo(f"      Created: {serve['created_at'][:19]}")
        click.echo(f"      Expires: {remaining}")
        click.echo(f"      Proceeded: {serve['proceeded']}")
        click.echo(f"      Restored: {serve['restored']}")


@serve.command()
@click.argument('token')
@click.pass_context
def revoke(ctx, token):
    """Revoke a restore page token."""
    # This would require adding a revoke method to the server
    click.echo(f"Revoke token: {token}")
    click.echo("Note: Full token revocation requires database access")


def _parse_expiry(expires: str) -> float:
    """Parse expiry string to hours."""
    expires = expires.strip().lower()
    
    multipliers = {
        's': 1/3600,  # seconds
        'm': 1/60,    # minutes
        'h': 1,       # hours
        'd': 24,      # days
        'w': 168,     # weeks
    }
    
    for suffix, mult in multipliers.items():
        if expires.endswith(suffix):
            try:
                value = float(expires[:-1])
                return value * mult
            except ValueError:
                return 0
    
    # Try parsing as plain hours
    try:
        return float(expires)
    except ValueError:
        return 0


def _format_remaining(expires_at: str) -> str:
    """Format remaining time from expiry timestamp."""
    from datetime import datetime
    expires = datetime.fromisoformat(expires_at)
    remaining = expires - datetime.now()
    
    if remaining.total_seconds() <= 0:
        return "Expired"
    
    hours = int(remaining.total_seconds() // 3600)
    minutes = int((remaining.total_seconds() % 3600) // 60)
    
    if hours > 24:
        days = hours // 24
        return f"{days}d {hours % 24}h"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def add_commands_to_cli(cli):
    """Add serve commands to the main CLI."""
    cli.add_command(serve)
