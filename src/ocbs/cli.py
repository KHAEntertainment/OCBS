"""
CLI interface for OCBS.
"""

import sys
from pathlib import Path

import click

from .core import OCBSCore, BackupScope
from .serve_cli import serve, status as serve_status, revoke as serve_revoke


@click.group()
@click.option('--state-dir', type=click.Path(exists=False, file_okay=False, dir_okay=True),
              help='Override state directory (default: ~/.config/ocbs)')
@click.pass_context
def main(ctx, state_dir):
    """OpenClaw Backup System - Incremental backup with restore capability."""
    ctx.ensure_object(dict)
    state_path = Path(state_dir) if state_dir else None
    ctx.obj['core'] = OCBSCore(state_dir=state_path)


@main.command()
@click.option('--scope', type=click.Choice(['minimal', 'config', 'config+session', 'config+session+workspace']),
              default='config', help='Backup scope')
@click.option('--reason', '-m', default='', help='Reason for backup')
@click.pass_context
def backup(ctx, scope, reason):
    """Create a backup."""
    core = ctx.obj['core']
    scope_enum = BackupScope(scope)
    
    try:
        manifest = core.backup(scope_enum, reason)
        click.echo(f"Backup created: {manifest.backup_id}")
        click.echo(f"  Scope: {scope}")
        click.echo(f"  Files: {len(manifest.paths)}")
        click.echo(f"  Reason: {reason or 'N/A'}")
    except Exception as e:
        click.echo(f"Error creating backup: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option('--latest', is_flag=True, help='Restore from latest backup')
@click.option('--checkpoint', '-c', help='Restore from specific checkpoint')
@click.option('--target', '-t', type=click.Path(exists=False, file_okay=False, dir_okay=True),
              help='Target directory for restore')
@click.pass_context
def restore(ctx, latest, checkpoint, target):
    """Restore from a backup."""
    core = ctx.obj['core']
    
    try:
        if checkpoint:
            core.restore(checkpoint_id=checkpoint, target_dir=Path(target) if target else None)
            click.echo(f"Restored from checkpoint: {checkpoint}")
        else:
            # Default to latest backup if no checkpoint specified
            backup = core.get_latest_backup()
            if backup:
                core.restore(backup_id=backup.backup_id, target_dir=Path(target) if target else None)
                click.echo(f"Restored from latest backup: {backup.backup_id}")
            else:
                click.echo("No backups available", err=True)
                sys.exit(1)
    except Exception as e:
        click.echo(f"Error restoring: {e}", err=True)
        sys.exit(1)


@main.command()
@click.pass_context
def status(ctx):
    """Show backup status."""
    core = ctx.obj['core']
    status = core.status()
    
    click.echo(f"OCBS Status")
    click.echo(f"  State directory: {status['state_dir']}")
    click.echo(f"  Total backups: {status['total_backups']}")
    click.echo(f"  Total chunks: {status['total_chunks']}")
    click.echo(f"  Pack size: {status['pack_size_bytes']} bytes")
    
    for scope, info in status['scope_info'].items():
        click.echo(f"  {scope}: {info['count']} backups, latest: {info['latest'] or 'N/A'}")


@main.command()
@click.option('--scope', type=click.Choice(['minimal', 'config', 'config+session', 'config+session+workspace']),
              help='Filter by scope')
@click.pass_context
def list(ctx, scope):
    """List available backups."""
    core = ctx.obj['core']
    scope_enum = BackupScope(scope) if scope else None
    
    backups = core.list_backups(scope_enum)
    
    if not backups:
        click.echo("No backups found")
        return
    
    click.echo(f"Backups ({len(backups)} total):")
    for b in backups:
        click.echo(f"  {b.backup_id} | {b.scope.value} | {b.timestamp.isoformat()} | {b.reason}")


@main.command()
@click.option('--scope', type=click.Choice(['minimal', 'config', 'config+session', 'config+session+workspace']),
              help='Cleanup specific scope')
@click.pass_context
def clean(ctx, scope):
    """Clean up old backups based on retention policy."""
    core = ctx.obj['core']
    scope_enum = BackupScope(scope) if scope else None
    
    core.cleanup(scope_enum)
    click.echo("Cleanup completed")


@main.command()
@click.argument('reason')
@click.option('--serve', is_flag=True, help='Serve restore page immediately')
@click.option('--expires', '-e', default='4h', help='Link expiry time (e.g., 4h, 1d, 30m)')
@click.option('--host', '-H', default=None, help='Host for URL (default: localhost)')
@click.pass_context
def checkpoint(ctx, reason, serve, expires, host):
    """Create a checkpoint for auto-restore capability."""
    core = ctx.obj['core']
    
    try:
        checkpoint_id = core.create_checkpoint(reason)
        click.echo(f"Checkpoint created: {checkpoint_id}")
        click.echo(f"  Reason: {reason}")
        
        # If --serve is specified, start the restore page server
        if serve:
            from .serve import RestorePageServer
            from .serve_cli import _parse_expiry
            
            host = host or 'localhost'
            expires_hours = _parse_expiry(expires)
            if expires_hours <= 0:
                click.echo(f"Invalid expiry time: {expires}", err=True)
                sys.exit(1)
            
            server = RestorePageServer(state_dir=core.state_dir, host=host)
            token = server.serve_checkpoint(checkpoint_id, expires_hours)
            url = server.get_restore_url(token)
            
            click.echo(f"\nRestore page created:")
            click.echo(f"  URL: {url}")
            click.echo(f"  Expires in: {expires}")
            click.echo(f"\nPress Ctrl+C to stop the server")
            try:
                server.start()
            except KeyboardInterrupt:
                click.echo("\nServer stopped")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Add serve commands
main.add_command(serve, 'serve')
main.add_command(serve_status, 'serve-status')
main.add_command(serve_revoke, 'serve-revoke')


if __name__ == '__main__':
    main()
