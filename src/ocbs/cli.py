"""
CLI interface for OCBS.
"""

import sys
from pathlib import Path

import click

from .core import BackupSource, BackupScope, OCBSCore
from .serve import format_restore_message, start_restore_server

# Shared scope choices to prevent drift
SCOPE_CHOICES = ['minimal', 'config', 'config+session', 'config+session+workspace']


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
@click.option('--scope', type=click.Choice(SCOPE_CHOICES),
              default='config', help='Backup scope')
@click.option(
    '--source',
    type=click.Choice(['direct', 'native']),
    default=None,
    help='Backup source: direct reads files directly, native wraps openclaw backup create',
)
@click.option('--reason', '-m', default='', help='Reason for backup')
@click.pass_context
def backup(ctx, scope, source, reason):
    """Create a backup."""
    core = ctx.obj['core']
    scope_enum = BackupScope(scope)
    source_enum = BackupSource(source) if source else None
    
    # Guard: prevent minimal scope with native source until implemented
    if scope == "minimal" and source == "native":
        raise click.ClickException(
            "Native backup does not yet support 'minimal' scope. "
            "Use --source direct or choose a different scope."
        )
    
    try:
        manifest = core.backup(scope_enum, reason, source=source_enum)
        click.echo(f"Backup created: {manifest.backup_id}")
        click.echo(f"  Scope: {scope}")
        click.echo(f"  Source: {(source_enum or core.get_default_source()).value}")
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
        elif latest:
            backup = core.get_latest_backup()
            if backup:
                core.restore(backup_id=backup.backup_id, target_dir=Path(target) if target else None)
                click.echo(f"Restored from latest backup: {backup.backup_id}")
            else:
                click.echo("No backups available", err=True)
                sys.exit(1)
        else:
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
@click.option('--scope', type=click.Choice(SCOPE_CHOICES),
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
@click.option('--scope', type=click.Choice(SCOPE_CHOICES),
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
@click.option('--serve', '-s', is_flag=True, help='Start web server and show restore URL')
@click.pass_context
def checkpoint(ctx, reason, serve):
    """Create a checkpoint for auto-restore capability."""
    core = ctx.obj['core']
    
    try:
        checkpoint_id = core.create_checkpoint(reason)
        
        if serve:
            # Start restore server
            start_restore_server()
            # Show formatted message with URL
            click.echo(format_restore_message(checkpoint_id, reason))
        else:
            click.echo(f"Checkpoint created: {checkpoint_id}")
            click.echo(f"  Reason: {reason}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option('--scope', type=click.Choice(SCOPE_CHOICES),
              default='config', help='Backup scope')
@click.option('--verify', is_flag=True, help='Verify archive after creation')
@click.option('--output', '-o', type=click.Path(exists=False, file_okay=False, dir_okay=True),
              help='Output directory for the archive')
def native_backup(scope, verify, output):
    """Run OpenClaw native backup to create a tar.gz archive."""
    import subprocess

    # Fail fast until minimal scope semantics are implemented for native backup
    if scope == "minimal":
        raise click.ClickException(
            "Native backup does not yet support 'minimal' scope. "
            "Use 'config', 'config+session', or 'config+session+workspace'."
        )

    args = ["openclaw", "backup", "create"]

    if scope == "config":
        args.append("--only-config")
    elif scope == "config+session":
        args.append("--no-include-workspace")
    # Full scope uses no flags

    if verify:
        args.append("--verify")

    if output:
        args.extend(["--output", output])

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode != 0:
            click.echo(f"Native backup failed: {result.stderr}", err=True)
            sys.exit(1)

        click.echo(f"Native backup created successfully:\n{result.stdout}")
    except subprocess.TimeoutExpired:
        click.echo("Error: Native backup timed out (10 minutes)", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Error: openclaw command not found. Ensure OpenClaw is installed.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error running native backup: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument('archive', type=click.Path(exists=True))
def native_verify(archive):
    """Verify a native backup archive."""
    import subprocess

    try:
        result = subprocess.run(
            ["openclaw", "backup", "verify", archive],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            click.echo(f"Verification failed: {result.stderr}", err=True)
            sys.exit(1)

        click.echo(f"Archive verified successfully:\n{result.stdout}")
    except subprocess.TimeoutExpired:
        click.echo("Error: Verification timed out", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo("Error: openclaw command not found. Ensure OpenClaw is installed.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error verifying archive: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()