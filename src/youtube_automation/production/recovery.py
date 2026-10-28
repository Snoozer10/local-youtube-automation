"""Operational recovery set definition and isolated database backup/restoration (Issue #58).

Covers accepted Track A requirements D4 and D5:
- Declared complete operational recovery set for SQLite databases, sidecars, locks, inputs, plans, and receipts.
- Non-mutating point-in-time snapshot backup using binary file preservation without source mutation.
- Verified isolated restoration refusing conflicts with newer destination work, rejecting traversal and invalid digests.
- Positive recovery verification receipts and stage reconciliation.
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
    INPUT = "INPUT"
    PLAN = "PLAN"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"
    EVIDENCE = "EVIDENCE"
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
        pattern="*receipt*.json",
        category=RecoveryItemCategory.RECEIPT,
        description="Operational receipts (lowercase pattern)",
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
    RecoveryItemSpec(
        pattern="*closeout*.json",
        category=RecoveryItemCategory.RECEIPT,
        description="Milestone closeout evidence records (lowercase pattern)",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="youtube_urls.txt",
        category=RecoveryItemCategory.INPUT,
        description="Canonical URL and channel input configuration",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*input*.json",
        category=RecoveryItemCategory.INPUT,
        description="Canonical run and stage input payloads",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*brief*.json",
        category=RecoveryItemCategory.INPUT,
        description="Canonical episode and topic brief specifications",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*plan*.json",
        category=RecoveryItemCategory.PLAN,
        description="Channel, topic, or episode production execution plans",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*approval*.json",
        category=RecoveryItemCategory.APPROVAL,
        description="Reviewer and gate approval records",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*rejection*.json",
        category=RecoveryItemCategory.REJECTION,
        description="Reviewer and gate rejection and triage records",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*journal*.json",
        category=RecoveryItemCategory.JOURNAL,
        description="Resumable execution journals and clip transaction logs",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*evidence*.json",
        category=RecoveryItemCategory.EVIDENCE,
        description="Channel and study evidence bundles",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*authority*.json",
        category=RecoveryItemCategory.CONFIGURATION,
        description="Cross-checkout authority configuration and pointers",
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
    authority_pointer: str = ""
    authority_generation: int = 1
    schema_version: int = 1
    protocol_version: str = "1.0"
    stage: str = "PRODUCTION"
    project_run_id: str = ""
    consistency_boundary: str = "POINT_IN_TIME_ISOLATED"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "recovery_id": self.recovery_id,
            "created_at": self.created_at,
            "runtime_root": self.runtime_root,
            "authority_pointer": self.authority_pointer,
            "authority_generation": self.authority_generation,
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "stage": self.stage,
            "project_run_id": self.project_run_id,
            "consistency_boundary": self.consistency_boundary,
            "total_files": len(self.files),
            "total_bytes": sum(f.size_bytes for f in self.files),
            "files": [f.to_dict() for f in self.files],
        }
        if self.manifest_sha256:
            d["manifest_sha256"] = self.manifest_sha256
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecoveryManifest:
        raw_files = data.get("files", [])
        return cls(
            recovery_id=data["recovery_id"],
            created_at=data["created_at"],
            runtime_root=data.get("runtime_root", ""),
            files=tuple(RecoveryFileEntry.from_dict(f) for f in raw_files),
            manifest_sha256=data.get("manifest_sha256", ""),
            authority_pointer=data.get("authority_pointer", ""),
            authority_generation=int(data.get("authority_generation", 1)),
            schema_version=int(data.get("schema_version", 1)),
            protocol_version=str(data.get("protocol_version", "1.0")),
            stage=str(data.get("stage", "PRODUCTION")),
            project_run_id=str(data.get("project_run_id", "")),
            consistency_boundary=str(data.get("consistency_boundary", "POINT_IN_TIME_ISOLATED")),
        )


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

    Uses byte-level file preservation without opening SQLite connections against the live source,
    guaranteeing 0 byte changes, 0 sidecar creations, and 0 directory mutations in source.
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

    file_entries: list[RecoveryFileEntry] = []

    # Bind authority metadata into manifest
    authority_ptr = ""
    authority_gen = 1
    try:
        from youtube_automation.production.authority import discover_authority
        resolution = discover_authority(default_root=runtime_root, enforce_maintenance=False)
        authority_ptr = str(resolution.database_path)
        authority_gen = resolution.schema_generation
    except Exception:
        pass

    try:
        db_entries: list[tuple[Path, RecoveryItemSpec]] = []
        for file_path, spec in matched_items:
            rel = file_path.relative_to(runtime_root)
            dest_path = snapshot_dir / rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Preserve source strictly non-mutating via binary stream copying
            with file_path.open("rb") as sf, dest_path.open("wb") as df:
                while chunk := sf.read(65536):
                    df.write(chunk)
            shutil.copystat(file_path, dest_path)

            sha = compute_sha256(dest_path)
            size = dest_path.stat().st_size
            file_entries.append(
                RecoveryFileEntry(
                    relative_path=rel.as_posix(),
                    category=spec.category,
                    sha256=sha,
                    size_bytes=size,
                    is_database=spec.is_database,
                )
            )
            if spec.is_database:
                db_entries.append((dest_path, spec))

        # Step 2: Verify database integrity on the backup copies in isolated backup storage
        for dest_path, spec in db_entries:
            with sqlite3.connect(f"{dest_path.as_uri()}?mode=ro&immutable=1", uri=True) as chk_conn:
                integrity = chk_conn.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise RuntimeError(f"Backup copy of database {dest_path} failed integrity check: {integrity}")

        # Write manifest atomically with validated SHA-256
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest = RecoveryManifest(
            recovery_id=recovery_id,
            created_at=created_at,
            runtime_root=str(runtime_root),
            files=tuple(file_entries),
            authority_pointer=authority_ptr,
            authority_generation=authority_gen,
            schema_version=1,
            protocol_version="1.0",
            stage="PRODUCTION",
            project_run_id=recovery_id,
            consistency_boundary="POINT_IN_TIME_ISOLATED",
        )

        manifest_data = manifest.to_dict()
        manifest_data.pop("manifest_sha256", None)
        manifest_bytes = json.dumps(manifest_data, indent=2).encode("utf-8")
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_data["manifest_sha256"] = manifest_sha

        manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"
        tmp_manifest = snapshot_dir / ".RECOVERY_MANIFEST.tmp"
        tmp_manifest.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        os.replace(str(tmp_manifest), str(manifest_path))

        return manifest_path

    except Exception:
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise


def restore_isolated_recovery_snapshot(
    backup_storage: Path,
    recovery_id: str,
    target_restore_dir: Path,
) -> dict[str, Any]:
    """Restore a verified recovery snapshot into an isolated target directory.

    Strictly refuses restoration if:
    - Manifest digest does not match its contents.
    - Manifest entries attempt path traversal escaping the target destination.
    - Destination already has a RESTORATION_RECEIPT.json (protects prior evidence).
    - Destination files already exist with differing content (protects newer resumed work).
    """
    backup_storage = backup_storage.resolve()
    target_restore_dir = target_restore_dir.resolve()
    snapshot_dir = backup_storage / recovery_id
    manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(f"Recovery manifest missing: {manifest_path}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Step 1: Pre-validate manifest digest
    recorded_sha = manifest_data.get("manifest_sha256")
    if not recorded_sha:
        raise ValueError(f"Recovery manifest missing 'manifest_sha256': {manifest_path}")

    payload = {k: v for k, v in manifest_data.items() if k != "manifest_sha256"}
    computed_sha = hashlib.sha256(json.dumps(payload, indent=2).encode("utf-8")).hexdigest()
    if recorded_sha != computed_sha:
        raise ValueError(
            f"Recovery manifest digest mismatch: recorded {recorded_sha} != computed {computed_sha}"
        )

    # Step 2: Validate file paths for containment (prevent directory traversal)
    raw_files = manifest_data.get("files", [])
    entries = [RecoveryFileEntry.from_dict(f) for f in raw_files]

    snapshot_dir_resolved = snapshot_dir.resolve()
    target_restore_dir_resolved = target_restore_dir.resolve()

    for entry in entries:
        rel_path = entry.relative_path
        rel_p = Path(rel_path)
        if rel_p.is_absolute() or ".." in rel_p.parts:
            raise ValueError(f"Path traversal detected in manifest: {rel_path}")

        src_path = (snapshot_dir / rel_path).resolve()
        dest_path = (target_restore_dir / rel_path).resolve()

        if not src_path.is_relative_to(snapshot_dir_resolved):
            raise ValueError(f"Source file escapes snapshot directory: {rel_path}")
        if not dest_path.is_relative_to(target_restore_dir_resolved):
            raise ValueError(f"Destination file escapes restore directory: {rel_path}")

    # Step 3: Protect existing restoration receipts in destination directory
    receipt_path = target_restore_dir / "RESTORATION_RECEIPT.json"
    if receipt_path.exists():
        raise FileExistsError(
            f"Restoration conflict: destination receipt {receipt_path} already exists; preserving existing evidence"
        )

    # Step 4: Pre-validation of backup snapshot file existence and hashes
    for entry in entries:
        src_path = snapshot_dir / entry.relative_path
        if not src_path.is_file():
            raise FileNotFoundError(f"Snapshot file missing from backup storage: {src_path}")
        current_sha = compute_sha256(src_path)
        if current_sha != entry.sha256:
            raise ValueError(
                f"Snapshot file corrupted in storage: {src_path} (hash {current_sha} != manifest {entry.sha256})"
            )

    # Step 5: Conflict detection at destination to protect newer work
    for entry in entries:
        dest_path = target_restore_dir / entry.relative_path
        if dest_path.is_file():
            dest_sha = compute_sha256(dest_path)
            if dest_sha != entry.sha256:
                raise FileExistsError(
                    f"Restoration conflict: destination file {dest_path} already exists with differing content "
                    f"(hash {dest_sha} != snapshot {entry.sha256})"
                )

    # Step 6: Perform verified restoration
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
        with src_path.open("rb") as sf, dest_path.open("wb") as df:
            while chunk := sf.read(65536):
                df.write(chunk)
        shutil.copystat(src_path, dest_path)

        restored_sha = compute_sha256(dest_path)
        if restored_sha != entry.sha256:
            raise ValueError(
                f"Restored file {dest_path} hash mismatch: {restored_sha} != {entry.sha256}"
            )

        if entry.is_database:
            # Verify database integrity on restored copy
            with sqlite3.connect(f"{dest_path.as_uri()}?mode=ro&immutable=1", uri=True) as chk_conn:
                integrity = chk_conn.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise RuntimeError(f"Restored database {dest_path} failed integrity check: {integrity}")

        restored_entries.append(entry.to_dict())

    # Step 7: Write restoration verification receipt in restore directory
    receipt_data = {
        "status": "RESTORED",
        "recovery_id": recovery_id,
        "restored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest_sha256": manifest_data.get("manifest_sha256", ""),
        "total_files": len(restored_entries),
        "restored_files": restored_entries,
    }
    receipt_path.write_text(json.dumps(receipt_data, indent=2), encoding="utf-8")

    return receipt_data
