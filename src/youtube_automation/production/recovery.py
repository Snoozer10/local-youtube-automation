"""Operational recovery set definition and isolated database backup/restoration (Issue #58).

Covers accepted Track A requirements D4 and D5:
- Declared complete operational recovery set for SQLite databases, sidecars, locks, and lineage receipts.
- Non-mutating point-in-time snapshot backup using SQLite's online backup API.
- Verified isolated restoration refusing conflicts with newer destination work.
- Positive recovery verification receipts.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any


class RecoveryItemCategory(str, enum.Enum):
    DATABASE = "DATABASE"
    JOURNAL = "JOURNAL"
    LOCK = "LOCK"
    RECEIPT = "RECEIPT"
    CONFIGURATION = "CONFIGURATION"


@dataclasses.dataclass(frozen=True)
class RecoveryItemSpec:
    pattern: str
    category: RecoveryItemCategory
    description: str
    is_database: bool = False
    required: bool = False


# Declared Complete Operational Recovery Set Specification
DECLARED_OPERATIONAL_RECOVERY_SET: tuple[RecoveryItemSpec, ...] = (
    RecoveryItemSpec(
        pattern="adaptive.sqlite3",
        category=RecoveryItemCategory.DATABASE,
        description="Active production coordination ledger and job state database",
        is_database=True,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*.sqlite",
        category=RecoveryItemCategory.DATABASE,
        description="Operational SQLite state databases",
        is_database=True,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*.sqlite3",
        category=RecoveryItemCategory.DATABASE,
        description="Operational SQLite state databases (sqlite3 extension)",
        is_database=True,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*-wal",
        category=RecoveryItemCategory.JOURNAL,
        description="SQLite Write-Ahead Log journal sidecar",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*-shm",
        category=RecoveryItemCategory.JOURNAL,
        description="SQLite Write-Ahead Log shared-memory index sidecar",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*-journal",
        category=RecoveryItemCategory.JOURNAL,
        description="SQLite rollback journal sidecar",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*.lock",
        category=RecoveryItemCategory.LOCK,
        description="Active process coordination lock files",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*.lease",
        category=RecoveryItemCategory.LOCK,
        description="Resource coordination lease state files",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*RECEIPT*.json",
        category=RecoveryItemCategory.RECEIPT,
        description="Immutable operational completion and verification receipts",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*CLOSEOUT*.json",
        category=RecoveryItemCategory.RECEIPT,
        description="Milestone and spec closeout evidence records",
        is_database=False,
        required=False,
    ),
)


def compute_sha256(path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclasses.dataclass(frozen=True)
class RecoveryFileEntry:
    relative_path: str
    category: RecoveryItemCategory
    sha256: str
    size_bytes: int
    is_database: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "category": self.category.value,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "is_database": self.is_database,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecoveryFileEntry:
        return cls(
            relative_path=data["relative_path"],
            category=RecoveryItemCategory(data["category"]),
            sha256=data["sha256"],
            size_bytes=data["size_bytes"],
            is_database=data.get("is_database", False),
        )


@dataclasses.dataclass(frozen=True)
class RecoveryManifest:
    recovery_id: str
    created_at: str
    runtime_root: str
    files: tuple[RecoveryFileEntry, ...]
    manifest_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "created_at": self.created_at,
            "runtime_root": self.runtime_root,
            "total_files": len(self.files),
            "total_bytes": sum(f.size_bytes for f in self.files),
            "files": [f.to_dict() for f in self.files],
        }


def identify_recovery_files(runtime_root: Path) -> list[tuple[Path, RecoveryItemSpec]]:
    """Scan runtime root and match files against declared operational recovery set specification."""
    if not runtime_root.is_dir():
        return []

    matched: list[tuple[Path, RecoveryItemSpec]] = []
    seen_paths: set[Path] = set()

    for file_path in sorted(runtime_root.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(runtime_root)

        # Skip backup and archive storage directories
        rel_parts = rel.parts
        if any(part in (".archive", "archive_storage", ".backups", "recovery_storage") for part in rel_parts):
            continue

        for spec in DECLARED_OPERATIONAL_RECOVERY_SET:
            if file_path in seen_paths:
                continue
            # Match pattern against filename or relative path
            if rel.match(spec.pattern) or file_path.match(spec.pattern):
                matched.append((file_path, spec))
                seen_paths.add(file_path)
                break

    return matched


def create_isolated_recovery_snapshot(
    runtime_root: Path,
    backup_storage: Path,
    recovery_id: str,
) -> Path:
    """Create a verified point-in-time recovery snapshot without mutating live production state.

    Uses SQLite online backup API for active databases, ensuring a consistent point-in-time
    snapshot even if database is active or WAL mode is in use, without locking concurrent readers.
    """
    import re
    if not re.match(r"^[a-zA-Z0-9_\-]{1,64}$", recovery_id):
        raise ValueError(f"Invalid recovery_id: {recovery_id!r}")

    runtime_root = runtime_root.resolve()
    backup_storage = backup_storage.resolve()
    snapshot_dir = backup_storage / recovery_id

    if snapshot_dir.exists():
        manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"
        if manifest_path.is_file():
            raise FileExistsError(f"Recovery snapshot {recovery_id} already exists with completed manifest")
        raise FileExistsError(f"Recovery snapshot directory {snapshot_dir} already exists")

    matched_items = identify_recovery_files(runtime_root)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Collect all databases being backed up to recognize associated sidecars
    database_paths = {p.resolve() for p, spec in matched_items if spec.is_database}
    file_entries: list[RecoveryFileEntry] = []

    try:
        for file_path, spec in matched_items:
            rel = file_path.relative_to(runtime_root)
            dest_path = snapshot_dir / rel

            if spec.is_database:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                # Online backup via SQLite API: creates a clean, consistent standalone database
                # copy that checkpoints any WAL state into the backup file without mutating source.
                source_uri = f"file:{file_path.resolve().as_posix()}?mode=ro"
                with sqlite3.connect(source_uri, uri=True, timeout=10) as src_conn:
                    with sqlite3.connect(dest_path.resolve().as_posix(), timeout=10) as dst_conn:
                        src_conn.backup(dst_conn)
                        # Switch backup copy to clean rollback journal mode, removing transient sidecars
                        dst_conn.execute("PRAGMA journal_mode=DELETE")

                # Verify database integrity on the backup copy
                with sqlite3.connect(f"file:{dest_path.resolve().as_posix()}?mode=ro", uri=True) as chk_conn:
                    integrity = chk_conn.execute("PRAGMA integrity_check").fetchone()
                    if not integrity or integrity[0] != "ok":
                        raise RuntimeError(f"Backup copy of database {file_path} failed integrity check: {integrity}")

                sha = compute_sha256(dest_path)
                size = dest_path.stat().st_size
                file_entries.append(
                    RecoveryFileEntry(
                        relative_path=rel.as_posix(),
                        category=spec.category,
                        sha256=sha,
                        size_bytes=size,
                        is_database=True,
                    )
                )
            elif spec.category == RecoveryItemCategory.JOURNAL:
                # If this journal/sidecar belongs to a database backed up above, its state is already
                # safely checkpointed into the consolidated standalone backup database.
                is_subsumed = any(
                    file_path.name in (f"{db.name}-wal", f"{db.name}-shm", f"{db.name}-journal")
                    for db in database_paths
                )
                if is_subsumed:
                    # Captured within the standalone database backup; record entry without separate file copy
                    continue
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(file_path), str(dest_path))
                sha = compute_sha256(dest_path)
                size = dest_path.stat().st_size
                file_entries.append(
                    RecoveryFileEntry(
                        relative_path=rel.as_posix(),
                        category=spec.category,
                        sha256=sha,
                        size_bytes=size,
                        is_database=False,
                    )
                )
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(file_path), str(dest_path))
                sha = compute_sha256(dest_path)
                size = dest_path.stat().st_size
                file_entries.append(
                    RecoveryFileEntry(
                        relative_path=rel.as_posix(),
                        category=spec.category,
                        sha256=sha,
                        size_bytes=size,
                        is_database=False,
                    )
                )

        # Write manifest atomically
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest = RecoveryManifest(
            recovery_id=recovery_id,
            created_at=created_at,
            runtime_root=str(runtime_root),
            files=tuple(file_entries),
        )

        manifest_data = manifest.to_dict()
        manifest_bytes = json.dumps(manifest_data, indent=2).encode("utf-8")
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_data["manifest_sha256"] = manifest_sha

        manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"
        tmp_manifest = snapshot_dir / ".RECOVERY_MANIFEST.tmp"
        tmp_manifest.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        os.replace(str(tmp_manifest), str(manifest_path))

        return manifest_path

    except Exception:
        # Clean up failed snapshot to avoid leaving corrupt/partial directories
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise


def restore_isolated_recovery_snapshot(
    backup_storage: Path,
    recovery_id: str,
    target_restore_dir: Path,
) -> dict[str, Any]:
    """Restore a verified recovery snapshot into an isolated target directory.

    Strictly refuses restoration if destination files already exist with differing content,
    preventing any overwriting or loss of newer resumed work.
    """
    backup_storage = backup_storage.resolve()
    target_restore_dir = target_restore_dir.resolve()
    snapshot_dir = backup_storage / recovery_id
    manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(f"Recovery manifest missing: {manifest_path}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_files = manifest_data.get("files", [])
    entries = [RecoveryFileEntry.from_dict(f) for f in raw_files]

    # Step 1: Pre-validation of backup snapshot integrity
    for entry in entries:
        src_path = snapshot_dir / entry.relative_path
        if not src_path.is_file():
            raise FileNotFoundError(f"Snapshot file missing from backup storage: {src_path}")
        current_sha = compute_sha256(src_path)
        if current_sha != entry.sha256:
            raise ValueError(
                f"Snapshot file corrupted in storage: {src_path} (hash {current_sha} != manifest {entry.sha256})"
            )

    # Step 2: Conflict detection at destination to protect newer work
    for entry in entries:
        dest_path = target_restore_dir / entry.relative_path
        if dest_path.is_file():
            dest_sha = compute_sha256(dest_path)
            if dest_sha != entry.sha256:
                raise FileExistsError(
                    f"Restoration conflict: destination file {dest_path} already exists with differing content "
                    f"(hash {dest_sha} != snapshot {entry.sha256})"
                )

    # Step 3: Perform verified restoration
    restored_entries: list[dict[str, Any]] = []
    target_restore_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        src_path = snapshot_dir / entry.relative_path
        dest_path = target_restore_dir / entry.relative_path

        if dest_path.is_file() and compute_sha256(dest_path) == entry.sha256:
            # Already identical; skip copy
            restored_entries.append(entry.to_dict())
            continue

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src_path), str(dest_path))

        restored_sha = compute_sha256(dest_path)
        if restored_sha != entry.sha256:
            raise ValueError(
                f"Restored file {dest_path} hash mismatch: {restored_sha} != {entry.sha256}"
            )

        if entry.is_database:
            # Verify database integrity on restored copy
            with sqlite3.connect(f"file:{dest_path.resolve().as_posix()}?mode=ro", uri=True) as chk_conn:
                integrity = chk_conn.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise RuntimeError(f"Restored database {dest_path} failed integrity check: {integrity}")

        restored_entries.append(entry.to_dict())

    # Step 4: Write restoration verification receipt in restore directory
    receipt_data = {
        "status": "RESTORED",
        "recovery_id": recovery_id,
        "restored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest_sha256": manifest_data.get("manifest_sha256", ""),
        "total_files": len(restored_entries),
        "restored_files": restored_entries,
    }
    receipt_path = target_restore_dir / "RESTORATION_RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt_data, indent=2), encoding="utf-8")

    return receipt_data
