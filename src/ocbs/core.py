"""
Core backup logic for OCBS.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

import xxhash


class BackupScope(Enum):
    MINIMAL = "minimal"
    CONFIG = "config"
    CONFIG_SESSION = "config+session"
    CONFIG_SESSION_WORKSPACE = "config+session+workspace"


class BackupSource(Enum):
    DIRECT = "direct"
    NATIVE = "native"


@dataclass
class FileChunk:
    """Represents a content-addressable file chunk."""

    chunk_id: str
    size: int
    content: bytes
    file_path: str


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

    home = Path(os.path.expanduser("~"))
    return home / ".openclaw"


class OCBSCore:
    """Core OCBS backup engine."""

    DEFAULT_CONFIG = {
        "auto_backup_enabled": False,
        "auto_backup_scope": "config",
        "auto_backup_schedule": "daily",
        "auto_restore_enabled": False,
        "auto_restore_timeout": 30,
        "heartbeat_check_enabled": False,
        "defaultSource": BackupSource.DIRECT.value,
        "nativeBackupDir": None,
    }

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".config" / "ocbs"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.packs_dir = self.state_dir / "packs"
        self.packs_dir.mkdir(exist_ok=True)
        self.db_path = self.state_dir / "index.db"
        self.config_path = self.state_dir / "config.json"
        self.config = self._load_config()
        self.native_backup_dir = self._get_native_backup_dir()
        self._init_db()

    def _load_config(self) -> dict:
        """Load OCBS config, merging with defaults."""

        config = dict(self.DEFAULT_CONFIG)
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    config.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass
        return config

    def _get_native_backup_dir(self) -> Optional[Path]:
        """Return configured native backup cache directory."""

        native_dir = self.config.get("nativeBackupDir")
        if not native_dir:
            return None

        path = Path(native_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve_backup_source(self, source: Optional[BackupSource]) -> BackupSource:
        """Resolve backup source from argument or config."""

        if source is not None:
            return source

        configured = self.config.get("defaultSource", BackupSource.DIRECT.value)
        try:
            return BackupSource(configured)
        except ValueError:
            return BackupSource.DIRECT

    def get_default_source(self) -> BackupSource:
        """Return the configured default backup source."""

        return self._resolve_backup_source(None)

    def _scope_to_native_args(self, scope: BackupScope) -> list[str]:
        """Map OCBS scope to native backup CLI flags."""

        if scope == BackupScope.CONFIG:
            return ["--only-config"]
        if scope == BackupScope.CONFIG_SESSION:
            return ["--no-include-workspace"]
        return []

    def _init_db(self):
        """Initialize SQLite index."""

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.executescript(
                """
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

                CREATE TABLE IF NOT EXISTS serve_records (
                    checkpoint_id TEXT PRIMARY KEY,
                    backup_id TEXT,
                    reason TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (backup_id) REFERENCES backups(backup_id)
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON chunks(chunk_id);
                CREATE INDEX IF NOT EXISTS idx_backup_timestamp ON backups(timestamp);
            """
            )

    def _ensure_serve_records_table(self, conn: sqlite3.Connection):
        """Create serve_records if it is missing in an older or partial DB."""

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS serve_records (
                checkpoint_id TEXT PRIMARY KEY,
                backup_id TEXT,
                reason TEXT,
                timestamp TEXT,
                FOREIGN KEY (backup_id) REFERENCES backups(backup_id)
            )
            """
            )

    def _resolve_restore_path(self, file_path: str, target_dir: Path) -> Path:
        """Resolve a stored backup path into a safe destination under target_dir."""

        rel_path = Path(file_path)
        if rel_path.parts and rel_path.parts[0] == ".openclaw":
            rel_path = Path(*rel_path.parts[1:])

        if rel_path.is_absolute():
            raise ValueError(f"absolute restore paths are not allowed: {file_path}")

        if not rel_path.parts:
            raise ValueError(f"empty restore path is not allowed: {file_path}")

        base_dir = target_dir.resolve()
        full_path = (base_dir / rel_path).resolve()
        if not full_path.is_relative_to(base_dir):
            raise ValueError(f"restore path escapes target directory: {file_path}")

        return full_path

    def _compute_content_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of content."""

        return hashlib.sha256(content).hexdigest()

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute hash for file using xxhash for speed."""

        h = xxhash.xxh64()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _get_paths_for_scope(self, scope: BackupScope) -> list[Path]:
        """Get paths to backup based on scope."""

        openclaw_home = get_openclaw_home()
        paths = []

        if scope in (
            BackupScope.CONFIG,
            BackupScope.CONFIG_SESSION,
            BackupScope.CONFIG_SESSION_WORKSPACE,
        ):
            paths.extend(
                [
                    openclaw_home / "config",
                    openclaw_home / "credentials",
                ]
            )

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
                        for filename in filenames:
                            files.append(Path(root) / filename)
        return files

    def _create_chunk(self, content: bytes, file_path: str) -> tuple[FileChunk, bool]:
        """Create or find existing chunk. Returns (chunk, is_new)."""

        chunk_id = self._compute_content_hash(content)

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                "SELECT chunk_id FROM chunks WHERE chunk_id = ?",
                (chunk_id,),
            )
            if cursor.fetchone():
                return FileChunk(chunk_id, len(content), b"", file_path), False

        return FileChunk(chunk_id, len(content), content, file_path), True

    def _write_chunk_to_pack(self, chunk: FileChunk) -> tuple[str, int]:
        """Write chunk to pack file. Returns (pack_file, offset)."""

        pack_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".pack"
        pack_path = self.packs_dir / pack_name

        with open(pack_path, "ab") as f:
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
                (chunk.chunk_id, chunk.size, pack_file, offset, datetime.now().isoformat()),
            )

    def _record_backup(
        self,
        backup_id: str,
        scope: BackupScope,
        reason: str,
        files: Iterable[tuple[str, bytes]],
    ) -> BackupManifest:
        """Store backup file content and metadata."""

        timestamp = datetime.now()
        manifest = BackupManifest(
            backup_id=backup_id,
            scope=scope,
            timestamp=timestamp,
            reason=reason,
        )

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                """INSERT INTO backups (backup_id, scope, timestamp, reason)
                   VALUES (?, ?, ?, ?)""",
                (backup_id, scope.value, timestamp.isoformat(), reason),
            )

            for relative_path, content in files:
                chunk, is_new = self._create_chunk(content, relative_path)
                manifest.chunk_ids.append(chunk.chunk_id)
                manifest.paths.append(relative_path)

                if is_new:
                    pack_file, offset = self._write_chunk_to_pack(chunk)
                    conn.execute(
                        """INSERT OR IGNORE INTO chunks
                           (chunk_id, size, pack_file, offset, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            chunk.chunk_id,
                            chunk.size,
                            pack_file,
                            offset,
                            datetime.now().isoformat(),
                        ),
                    )

                conn.execute(
                    """INSERT INTO backup_files (backup_id, file_path, chunk_id)
                       VALUES (?, ?, ?)""",
                    (backup_id, relative_path, chunk.chunk_id),
                )

        return manifest

    def _backup_direct(self, scope: BackupScope, reason: str = "") -> BackupManifest:
        """Back up files directly from the OpenClaw home."""

        def _file_gen():
            paths = self._get_paths_for_scope(scope)
            for file_path in self._collect_files(paths):
                rel_path = str(file_path.relative_to(Path.home()))
                yield (rel_path, file_path.read_bytes())

        backup_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return self._record_backup(backup_id, scope, reason, _file_gen())

    def _run_native_backup(self, scope: BackupScope, dry_run: bool = False) -> Path:
        """Run OpenClaw native backup and return the archive path."""

        if self.native_backup_dir:
            output_dir = self.native_backup_dir
            cleanup_output_dir = False
        else:
            output_dir = Path(tempfile.mkdtemp(prefix="ocbs-native-"))
            cleanup_output_dir = True

        args = ["openclaw", "backup", "create", *self._scope_to_native_args(scope)]
        if dry_run:
            args.extend(["--dry-run", "--json"])
        else:
            args.extend(["--output", str(output_dir)])

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except FileNotFoundError as exc:
            if cleanup_output_dir:
                shutil.rmtree(output_dir, ignore_errors=True)
            raise FileNotFoundError(
                "openclaw command not found; native backup source unavailable"
            ) from exc

        if result.returncode != 0:
            if cleanup_output_dir:
                shutil.rmtree(output_dir, ignore_errors=True)
            stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise RuntimeError(f"native backup failed: {stderr}")

        if dry_run:
            try:
                payload = json.loads(result.stdout or "{}")
            except json.JSONDecodeError as exc:
                if cleanup_output_dir:
                    shutil.rmtree(output_dir, ignore_errors=True)
                raise RuntimeError("native backup dry-run did not return valid JSON") from exc

            archive = payload.get("archive") or payload.get("archive_path")
            if not archive:
                archive = str(output_dir / "dry-run-openclaw-backup.tar.gz")
            if cleanup_output_dir:
                shutil.rmtree(output_dir, ignore_errors=True)
            return Path(archive)

        archives = sorted(output_dir.glob("*.tar.gz"), key=lambda path: path.stat().st_mtime)
        if not archives:
            if cleanup_output_dir:
                shutil.rmtree(output_dir, ignore_errors=True)
            raise RuntimeError("native backup did not produce a .tar.gz archive")

        return archives[-1]

    def _safe_extract_archive(self, tar: tarfile.TarFile, extract_dir: Path) -> None:
        """Extract a tar archive safely, rejecting path traversal and link members."""

        extract_dir_resolved = extract_dir.resolve()
        for member in tar.getmembers():
            if member.issym() or member.islnk():
                raise RuntimeError(
                    f"Refusing to extract archive with link entry: {member.name}"
                )
            member_path = (extract_dir / member.name).resolve()
            if not member_path.is_relative_to(extract_dir_resolved):
                raise RuntimeError(
                    f"Refusing to extract path outside target directory: {member.name}"
                )
            tar.extract(member, extract_dir, filter="data")

    def _chunk_archive(self, archive_path: Path, scope: BackupScope, reason: str = "") -> BackupManifest:
        """Extract native archive and store its files as OCBS chunks."""

        backup_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        with tempfile.TemporaryDirectory(prefix="ocbs-extract-") as extract_dir_name:
            extract_dir = Path(extract_dir_name)
            with tarfile.open(archive_path, "r:gz") as tar:
                self._safe_extract_archive(tar, extract_dir)

            def _file_gen():
                for file_path in sorted(extract_dir.rglob("*")):
                    if not file_path.is_file():
                        continue
                    rel_path = file_path.relative_to(extract_dir)
                    if rel_path == Path("manifest.json"):
                        continue
                    yield (str(rel_path), file_path.read_bytes())

            return self._record_backup(backup_id, scope, reason, _file_gen())

    def backup(
        self,
        scope: BackupScope,
        reason: str = "",
        source: Optional[BackupSource] = None,
    ) -> BackupManifest:
        """Perform a backup for the given scope and source."""

        resolved_source = self._resolve_backup_source(source)
        if resolved_source == BackupSource.NATIVE:
            try:
                archive_path = self._run_native_backup(scope)
                try:
                    manifest = self._chunk_archive(archive_path, scope, reason)
                finally:
                    if archive_path.parent.name.startswith("ocbs-native-"):
                        shutil.rmtree(archive_path.parent, ignore_errors=True)
            except FileNotFoundError:
                manifest = self._backup_direct(scope, reason)
        else:
            manifest = self._backup_direct(scope, reason)

        self.cleanup(scope)
        return manifest

    def _get_old_backups(self, scope: BackupScope, retention: dict) -> list[str]:
        """Get backup IDs to remove based on retention policy."""

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                """SELECT backup_id, timestamp FROM backups
                   WHERE scope = ? ORDER BY timestamp DESC""",
                (scope.value,),
            )
            all_backups = cursor.fetchall()

        if not all_backups:
            return []

        now = datetime.now()
        to_remove = set()

        for backup_id, ts in all_backups:
            dt = datetime.fromisoformat(ts)
            age_days = (now - dt).days

            if age_days <= retention["daily"]:
                continue
            if age_days <= retention["weekly"] * 7:
                week_key = f"{dt.year}-{dt.isocalendar()[1]}"
                if hasattr(self, "_cleanup_week_keys"):
                    self._cleanup_week_keys.add(week_key)
                else:
                    self._cleanup_week_keys = {week_key}
                    continue
                to_remove.add(backup_id)
            elif age_days <= retention["monthly"] * 30:
                month_key = f"{dt.year}-{dt.month}"
                if hasattr(self, "_cleanup_month_keys"):
                    self._cleanup_month_keys.add(month_key)
                else:
                    self._cleanup_month_keys = {month_key}
                    continue
                to_remove.add(backup_id)
            else:
                to_remove.add(backup_id)

        if hasattr(self, "_cleanup_week_keys"):
            del self._cleanup_week_keys
        if hasattr(self, "_cleanup_month_keys"):
            del self._cleanup_month_keys

        return list(to_remove)

    def cleanup(self, scope: Optional[BackupScope] = None):
        """Run cleanup based on retention policy."""

        retention = {
            "daily": 7,
            "weekly": 4,
            "monthly": 12,
        }

        scopes = [scope] if scope else list(BackupScope)

        for backup_scope in scopes:
            old_backup_ids = self._get_old_backups(backup_scope, retention)
            if old_backup_ids:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "DELETE FROM backup_files WHERE backup_id IN ({})".format(
                            ",".join("?" * len(old_backup_ids))
                        ),
                        old_backup_ids,
                    )
                    conn.execute(
                        "DELETE FROM backups WHERE backup_id IN ({})".format(
                            ",".join("?" * len(old_backup_ids))
                        ),
                        old_backup_ids,
                    )

    def list_backups(self, scope: Optional[BackupScope] = None) -> list[BackupManifest]:
        """List available backups."""

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            if scope:
                cursor = conn.execute(
                    "SELECT backup_id, scope, timestamp, reason FROM backups WHERE scope = ? ORDER BY timestamp DESC",
                    (scope.value,),
                )
            else:
                cursor = conn.execute(
                    "SELECT backup_id, scope, timestamp, reason FROM backups ORDER BY timestamp DESC"
                )

            return [
                BackupManifest(
                    backup_id=backup_id,
                    scope=BackupScope(scope_value),
                    timestamp=datetime.fromisoformat(timestamp),
                    reason=reason,
                )
                for backup_id, scope_value, timestamp, reason in cursor.fetchall()
            ]

    def get_backup(self, backup_id: str) -> Optional[BackupManifest]:
        """Get a specific backup."""

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            cursor = conn.execute(
                "SELECT backup_id, scope, timestamp, reason FROM backups WHERE backup_id = ?",
                (backup_id,),
            )
            row = cursor.fetchone()
            if row:
                return BackupManifest(
                    backup_id=row[0],
                    scope=BackupScope(row[1]),
                    timestamp=datetime.fromisoformat(row[2]),
                    reason=row[3],
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
            scope_info = {scope.value: {"count": 0, "latest": None} for scope in BackupScope}
            for scope_value, count, latest in cursor.fetchall():
                scope_info[scope_value] = {"count": count, "latest": latest}

        return {
            "total_backups": total_backups,
            "total_chunks": total_chunks,
            "pack_size_bytes": pack_size,
            "scope_info": scope_info,
            "state_dir": str(self.state_dir),
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
                (checkpoint_id, latest.backup_id, reason, datetime.now().isoformat()),
            )

        return checkpoint_id

    def get_checkpoint_serves(self, checkpoint_id: Optional[str] = None) -> list[dict]:
        """Return recorded checkpoint serve entries."""

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._ensure_serve_records_table(conn)

            if checkpoint_id:
                cursor = conn.execute(
                    """SELECT checkpoint_id, backup_id, reason, timestamp
                       FROM serve_records WHERE checkpoint_id = ?
                       ORDER BY timestamp DESC""",
                    (checkpoint_id,),
                )
            else:
                cursor = conn.execute(
                    """SELECT checkpoint_id, backup_id, reason, timestamp
                       FROM serve_records ORDER BY timestamp DESC"""
                )

            return [
                {
                    "checkpoint_id": row[0],
                    "backup_id": row[1],
                    "reason": row[2],
                    "timestamp": row[3],
                }
                for row in cursor.fetchall()
            ]

    def restore(
        self,
        backup_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        target_dir: Optional[Path] = None,
    ) -> bool:
        """Restore from a backup or checkpoint."""

        target_dir = target_dir or get_openclaw_home()

        if checkpoint_id:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                cursor = conn.execute(
                    "SELECT backup_id FROM checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
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

        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")

            # Get all files with their chunk metadata in a single query
            cursor = conn.execute(
                """SELECT bf.file_path, c.pack_file, c.offset, c.size
                   FROM backup_files bf
                   JOIN chunks c ON bf.chunk_id = c.chunk_id
                   WHERE bf.backup_id = ?""",
                (backup_id,),
            )
            files = cursor.fetchall()

        if not files:
            raise ValueError(f"No files found for backup_id: {backup_id}")

        batch_size = 500
        for i in range(0, len(files), batch_size):
            batch = files[i : i + batch_size]
            for file_path, pack_file, offset, chunk_size in batch:
                try:
                    pack_path = self.packs_dir / pack_file
                    with open(pack_path, "rb") as f:
                        f.seek(offset)
                        content = f.read(chunk_size)

                    full_path = self._resolve_restore_path(file_path, target_dir)
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_bytes(content)
                except Exception as exc:
                    print(f"Warning: Failed to restore {file_path}: {exc}")
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
                    "checkpoint_id": row[0],
                    "backup_id": row[1],
                    "reason": row[2],
                    "timestamp": row[3],
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
