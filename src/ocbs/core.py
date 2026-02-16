"""
Core backup logic for OCBS.
"""

import hashlib
import json
import os
import sqlite3
import xxhash
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class BackupScope(Enum):
    MINIMAL = "minimal"
    CONFIG = "config"
    CONFIG_SESSION = "config+session"
    CONFIG_SESSION_WORKSPACE = "config+session+workspace"


@dataclass
class FileChunk:
    """Represents a content-addressable file chunk."""
    chunk_id: str  # SHA-256 hash of content
    size: int
    content: bytes
    file_path: str  # Original relative path


@dataclass
class BackupManifest:
    """Metadata about a backup."""
    backup_id: str
    scope: BackupScope
    timestamp: datetime
    reason: str = ""
    paths: list[str] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)


def get_openclaw_home() -> Path:
    """Get OpenClaw home directory, respecting HOME env var."""
    # Use os.path.expanduser to respect HOME env var changes
    home = Path(os.path.expanduser("~"))
    return home / ".openclaw"


class OCBSCore:
    """Core OCBS backup engine."""
    
    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".config" / "ocbs"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.packs_dir = self.state_dir / "packs"
        self.packs_dir.mkdir(exist_ok=True)
        self.db_path = self.state_dir / "index.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite index."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    size INTEGER,
                    pack_file TEXT,
                    offset INTEGER,
                    created_at TEXT
                );
                
                CREATE TABLE IF NOT EXISTS backups (
                    backup_id TEXT PRIMARY KEY,
                    scope TEXT,
                    timestamp TEXT,
                    reason TEXT,
                    UNIQUE(backup_id)
                );
                
                CREATE TABLE IF NOT EXISTS backup_files (
                    backup_id TEXT,
                    file_path TEXT,
                    chunk_id TEXT,
                    PRIMARY KEY (backup_id, file_path),
                    FOREIGN KEY (backup_id) REFERENCES backups(backup_id),
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
                );
                
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    backup_id TEXT,
                    reason TEXT,
                    timestamp TEXT,
                    active INTEGER DEFAULT 1,
                    FOREIGN KEY (backup_id) REFERENCES backups(backup_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON chunks(chunk_id);
                CREATE INDEX IF NOT EXISTS idx_backup_timestamp ON backups(timestamp);
            """)
    
    def _compute_content_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute hash for file using xxhash for speed."""
        h = xxhash.xxh64()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    
    def _get_paths_for_scope(self, scope: BackupScope) -> list[Path]:
        """Get paths to backup based on scope."""
        openclaw_home = get_openclaw_home()
        paths = []
        
        if scope == BackupScope.MINIMAL:
            # Minimal scope: only include essential config files (~10-20 files)
            # Include: openclaw.json, auth-profiles.json, agent configs, telegram credentials
            essential_files = [
                openclaw_home / "openclaw.json",
                openclaw_home / "auth-profiles.json",
                openclaw_home / "identity.json",
                openclaw_home / "credentials" / "telegram-token",
                openclaw_home / "credentials" / "telegram-chat-id",
            ]
            paths.extend([f for f in essential_files if f.exists()])
        elif scope in (BackupScope.CONFIG, BackupScope.CONFIG_SESSION, BackupScope.CONFIG_SESSION_WORKSPACE):
            paths.extend([
                openclaw_home / "config",
                openclaw_home / "credentials",
            ])
        
        if scope in (BackupScope.CONFIG_SESSION, BackupScope.CONFIG_SESSION_WORKSPACE):
            paths.append(openclaw_home / "sessions")
        
        if scope == BackupScope.CONFIG_SESSION_WORKSPACE:
            paths.append(openclaw_home / "workspace")
        
        return paths
    
    def _collect_files(self, paths: list[Path]) -> list[Path]:
        """Collect all files from paths recursively."""
        files = []
        for path in paths:
            if path.exists():
                if path.is_file():
                    files.append(path)
                elif path.is_dir():
                    for root, _, filenames in os.walk(path):
                        for f in filenames:
                            files.append(Path(root) / f)
        return files
    
    def _create_chunk(self, content: bytes, file_path: str) -> tuple[FileChunk, bool]:
        """Create or find existing chunk. Returns (chunk, is_new)."""
        chunk_id = self._compute_content_hash(content)
        
        # Check if chunk already exists
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                "SELECT chunk_id FROM chunks WHERE chunk_id = ?",
                (chunk_id,)
            )
            if cursor.fetchone():
                return FileChunk(chunk_id, len(content), b"", file_path), False
        
        return FileChunk(chunk_id, len(content), content, file_path), True
    
    def _write_chunk_to_pack(self, chunk: FileChunk) -> tuple[str, int]:
        """Write chunk to pack file. Returns (pack_file, offset)."""
        pack_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".pack"
        pack_path = self.packs_dir / pack_name
        
        with open(pack_path, 'ab') as f:
            offset = f.tell()
            f.write(chunk.content)
        
        return pack_name, offset
    
    def _index_chunk(self, chunk: FileChunk, pack_file: str, offset: int):
        """Index chunk in database."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                """INSERT OR IGNORE INTO chunks 
                   (chunk_id, size, pack_file, offset, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (chunk.chunk_id, chunk.size, pack_file, offset, datetime.now().isoformat())
            )
    
    def backup(self, scope: BackupScope, reason: str = "") -> BackupManifest:
        """Perform a backup for the given scope."""
        backup_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        timestamp = datetime.now()
        
        manifest = BackupManifest(
            backup_id=backup_id,
            scope=scope,
            timestamp=timestamp,
            reason=reason
        )
        
        paths = self._get_paths_for_scope(scope)
        files = self._collect_files(paths)
        
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            
            # Create backup record
            conn.execute(
                """INSERT INTO backups (backup_id, scope, timestamp, reason)
                   VALUES (?, ?, ?, ?)""",
                (backup_id, scope.value, timestamp.isoformat(), reason)
            )
            
            for file_path in files:
                rel_path = file_path.relative_to(Path.home())
                content = file_path.read_bytes()
                
                chunk, is_new = self._create_chunk(content, str(rel_path))
                manifest.chunk_ids.append(chunk.chunk_id)
                manifest.paths.append(str(rel_path))
                
                if is_new:
                    pack_file, offset = self._write_chunk_to_pack(chunk)
                    # Index chunk in same connection
                    conn.execute(
                        """INSERT OR IGNORE INTO chunks 
                           (chunk_id, size, pack_file, offset, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (chunk.chunk_id, chunk.size, pack_file, offset, datetime.now().isoformat())
                    )
                
                # Record file in backup
                conn.execute(
                    """INSERT INTO backup_files (backup_id, file_path, chunk_id)
                       VALUES (?, ?, ?)""",
                    (backup_id, str(rel_path), chunk.chunk_id)
                )
        
        # Run cleanup after backup
        self.cleanup(scope)
        
        return manifest
    
    def _get_old_backups(self, scope: BackupScope, retention: dict) -> list[str]:
        """Get backup IDs to remove based on retention policy."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            # Get all backup IDs for scope, ordered by timestamp
            cursor = conn.execute(
                """SELECT backup_id, timestamp FROM backups 
                   WHERE scope = ? ORDER BY timestamp DESC""",
                (scope.value,)
            )
            all_backups = cursor.fetchall()
        
        if not all_backups:
            return []
        
        now = datetime.now()
        to_remove = set()
        
        for backup_id, ts in all_backups:
            dt = datetime.fromisoformat(ts)
            age_days = (now - dt).days
            
            # Keep all backups within daily retention
            if age_days <= retention['daily']:
                continue
            # For older backups, apply weekly/monthly retention
            elif age_days <= retention['weekly'] * 7:
                # Weekly retention: keep only one per week
                week_key = f"{dt.year}-{dt.isocalendar()[1]}"
                if hasattr(self, '_cleanup_week_keys'):
                    self._cleanup_week_keys.add(week_key)
                else:
                    self._cleanup_week_keys = {week_key}
                    # This is the first backup this week, keep it
                    continue
                to_remove.add(backup_id)
            elif age_days <= retention['monthly'] * 30:
                # Monthly retention: keep only one per month
                month_key = f"{dt.year}-{dt.month}"
                if hasattr(self, '_cleanup_month_keys'):
                    self._cleanup_month_keys.add(month_key)
                else:
                    self._cleanup_month_keys = {month_key}
                    # This is the first backup this month, keep it
                    continue
                to_remove.add(backup_id)
            else:
                to_remove.add(backup_id)
        
        # Reset keys for next call
        if hasattr(self, '_cleanup_week_keys'):
            del self._cleanup_week_keys
        if hasattr(self, '_cleanup_month_keys'):
            del self._cleanup_month_keys
        
        return list(to_remove)
    
    def cleanup(self, scope: Optional[BackupScope] = None):
        """Run cleanup based on retention policy."""
        retention = {
            'daily': 7,
            'weekly': 4,
            'monthly': 12
        }
        
        scopes = [scope] if scope else list(BackupScope)
        
        for s in scopes:
            old_backup_ids = self._get_old_backups(s, retention)
            if old_backup_ids:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "DELETE FROM backup_files WHERE backup_id IN ({})".format(
                            ",".join("?" * len(old_backup_ids))
                        ),
                        old_backup_ids
                    )
                    conn.execute(
                        "DELETE FROM backups WHERE backup_id IN ({})".format(
                            ",".join("?" * len(old_backup_ids))
                        ),
                        old_backup_ids
                    )
    
    def list_backups(self, scope: Optional[BackupScope] = None) -> list[BackupManifest]:
        """List available backups."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            if scope:
                cursor = conn.execute(
                    "SELECT backup_id, scope, timestamp, reason FROM backups WHERE scope = ? ORDER BY timestamp DESC",
                    (scope.value,)
                )
            else:
                cursor = conn.execute(
                    "SELECT backup_id, scope, timestamp, reason FROM backups ORDER BY timestamp DESC"
                )
            
            return [
                BackupManifest(
                    backup_id=bid,
                    scope=BackupScope(s),
                    timestamp=datetime.fromisoformat(ts),
                    reason=reason
                )
                for bid, s, ts, reason in cursor.fetchall()
            ]
    
    def get_backup(self, backup_id: str) -> Optional[BackupManifest]:
        """Get a specific backup."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                "SELECT backup_id, scope, timestamp, reason FROM backups WHERE backup_id = ?",
                (backup_id,)
            )
            row = cursor.fetchone()
            if row:
                return BackupManifest(
                    backup_id=row[0],
                    scope=BackupScope(row[1]),
                    timestamp=datetime.fromisoformat(row[2]),
                    reason=row[3]
                )
        return None
    
    def get_latest_backup(self, scope: Optional[BackupScope] = None) -> Optional[BackupManifest]:
        """Get the most recent backup."""
        backups = self.list_backups(scope)
        return backups[0] if backups else None
    
    def status(self) -> dict:
        """Get backup status."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            total_backups = conn.execute("SELECT COUNT(*) FROM backups").fetchone()[0]
            total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            pack_size = sum(f.stat().st_size for f in self.packs_dir.glob("*.pack"))
            
            cursor = conn.execute(
                "SELECT scope, COUNT(*), MAX(timestamp) FROM backups GROUP BY scope"
            )
            scope_info = {s.value: {'count': 0, 'latest': None} for s in BackupScope}
            for s, count, latest in cursor.fetchall():
                scope_info[s] = {'count': count, 'latest': latest}
        
        return {
            'total_backups': total_backups,
            'total_chunks': total_chunks,
            'pack_size_bytes': pack_size,
            'scope_info': scope_info,
            'state_dir': str(self.state_dir)
        }
    
    def create_checkpoint(self, reason: str = "") -> str:
        """Create a checkpoint from the latest backup."""
        latest = self.get_latest_backup()
        if not latest:
            raise ValueError("No backups available to checkpoint")
        
        checkpoint_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_cp"
        
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                """INSERT INTO checkpoints (checkpoint_id, backup_id, reason, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (checkpoint_id, latest.backup_id, reason, datetime.now().isoformat())
            )
        
        return checkpoint_id
    
    def restore(self, backup_id: Optional[str] = None, checkpoint_id: Optional[str] = None,
                target_dir: Optional[Path] = None) -> bool:
        """Restore from a backup or checkpoint."""
        target_dir = target_dir or get_openclaw_home()

        # Resolve backup_id from checkpoint if needed
        if checkpoint_id:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                cursor = conn.execute(
                    "SELECT backup_id FROM checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,)
                )
                row = cursor.fetchone()
                if row:
                    backup_id = row[0]

        if not backup_id:
            latest = self.get_latest_backup()
            if latest:
                backup_id = latest.backup_id
            else:
                raise ValueError("No backup specified and no backups available")

        # Single connection for entire restore operation
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")

            # Get all files with their chunk metadata in a single query
            cursor = conn.execute(
                """SELECT bf.file_path, c.pack_file, c.offset, c.size
                   FROM backup_files bf
                   JOIN chunks c ON bf.chunk_id = c.chunk_id
                   WHERE bf.backup_id = ?""",
                (backup_id,)
            )
            files = cursor.fetchall()

        # Process files with single connection for chunk lookups
        # Process in batches to avoid memory pressure with large backups
        BATCH_SIZE = 500

        for i in range(0, len(files), BATCH_SIZE):
            batch = files[i:i + BATCH_SIZE]

            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")

                for file_path, pack_file, offset, chunk_size in batch:
                    pack_path = self.packs_dir / pack_file

                    # Read exactly chunk_size bytes from pack
                    try:
                        with open(pack_path, 'rb') as f:
                            f.seek(offset)
                            content = f.read(chunk_size)

                        # Write file
                        full_path = target_dir / file_path
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        full_path.write_bytes(content)
                    except (FileNotFoundError, OSError) as e:
                        # Log but continue with other files
                        print(f"Warning: Failed to restore {file_path}: {e}")
                        continue

        return True
    
    def get_checkpoints(self) -> list[dict]:
        """Get all active checkpoints."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                """SELECT checkpoint_id, backup_id, reason, timestamp 
                   FROM checkpoints WHERE active = 1 ORDER BY timestamp DESC"""
            )
            return [
                {
                    'checkpoint_id': row[0],
                    'backup_id': row[1],
                    'reason': row[2],
                    'timestamp': row[3]
                }
                for row in cursor.fetchall()
            ]
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[dict]:
        """Get a specific checkpoint."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                """SELECT checkpoint_id, backup_id, reason, timestamp, active
                   FROM checkpoints WHERE checkpoint_id = ?""",
                (checkpoint_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'checkpoint_id': row[0],
                    'backup_id': row[1],
                    'reason': row[2],
                    'timestamp': row[3],
                    'active': bool(row[4])
                }
        return None
    
    def add_checkpoint_serve_info(self, checkpoint_id: str, token: str, expires_at: str) -> bool:
        """Add serve endpoint reference to a checkpoint record."""
        # Create serve_records table if not exists
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
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
            
            # Check if token already exists
            cursor = conn.execute(
                "SELECT token FROM serve_records WHERE token = ?",
                (token,)
            )
            if cursor.fetchone():
                return False
            
            conn.execute(
                """INSERT INTO serve_records (token, checkpoint_id, created_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (token, checkpoint_id, datetime.now().isoformat(), expires_at)
            )
            return True
    
    def get_checkpoint_serves(self, checkpoint_id: str) -> list[dict]:
        """Get all serve records for a checkpoint."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                """SELECT token, checkpoint_id, created_at, expires_at, used, proceeded, restored
                   FROM serve_records WHERE checkpoint_id = ? ORDER BY created_at DESC""",
                (checkpoint_id,)
            )
            return [
                {
                    'token': row[0],
                    'checkpoint_id': row[1],
                    'created_at': row[2],
                    'expires_at': row[3],
                    'used': bool(row[4]),
                    'proceeded': bool(row[5]),
                    'restored': bool(row[6])
                }
                for row in cursor.fetchall()
            ]
