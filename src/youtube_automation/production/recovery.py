"""Operational recovery set definition and isolated database backup/restoration (Issue #58).

Covers accepted Track A requirements D4 and D5:
- Declared complete operational recovery set for SQLite databases, sidecars, locks, inputs, plans, and receipts.
- Non-mutating point-in-time snapshot backup using binary file preservation without source mutation.
- Verified isolated restoration refusing conflicts with newer destination work, rejecting traversal and invalid digests.
- Positive recovery verification receipts and stage reconciliation.
"""

from __future__ import annotations

import contextlib
import dataclasses
import enum
import errno
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from contextlib import closing
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
    RecoveryItemSpec(
        pattern="*timeline*.json",
        category=RecoveryItemCategory.PLAN,
        description="Canonical timeline and scene sequence plans",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*script*.txt",
        category=RecoveryItemCategory.INPUT,
        description="Canonical script text and dialogue inputs",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*script*.json",
        category=RecoveryItemCategory.INPUT,
        description="Structured script payloads",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*.wav",
        category=RecoveryItemCategory.EVIDENCE,
        description="Canonical narration, scratch audio, and audio evidence",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*.mp4",
        category=RecoveryItemCategory.EVIDENCE,
        description="Rendered proof clips and video evidence",
        is_database=False,
        required=False,
    ),
    RecoveryItemSpec(
        pattern="*.png",
        category=RecoveryItemCategory.EVIDENCE,
        description="Frame renderings, storyboard images, and thumbnail evidence",
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


def _extract_references(data: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(data, str):
        refs.append(data)
    elif isinstance(data, dict):
        for _k, v in data.items():
            refs.extend(_extract_references(v))
    elif isinstance(data, list):
        for elem in data:
            refs.extend(_extract_references(elem))
    return refs


def expand_recovery_closure(
    runtime_root: Path,
    base_items: list[tuple[Path, RecoveryItemSpec]],
) -> list[tuple[Path, RecoveryItemSpec]]:
    """Traverse references in databases and JSON artifacts to ensure full operational closure.

    Inspects jobs tables and json payloads (briefs, plans, timelines) for referenced
    canonical files (scripts, audio, images, evidence). If a referenced file exists,
    it is added to the recovery set. If a referenced file is missing, an explicit
    error is raised to prevent incomplete captures.
    """
    closure_items = list(base_items)
    seen_paths = {p.resolve() for p, _ in closure_items}

    media_extensions = {".wav", ".mp3", ".mp4", ".png", ".jpg", ".jpeg", ".webp"}
    doc_extensions = {".txt", ".json", ".md"}
    valid_extensions = media_extensions | doc_extensions

    changed = True
    while changed:
        changed = False
        new_items: list[tuple[Path, RecoveryItemSpec]] = []
        for file_path, spec in list(closure_items):
            discovered_refs: list[str] = []

            # Traverse JSON files
            if file_path.suffix == ".json" and not file_path.name.startswith("RECOVERY_MANIFEST"):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parsed = json.loads(content)
                    discovered_refs.extend(_extract_references(parsed))
                except json.JSONDecodeError:
                    pass
                except Exception as exc:
                    raise RuntimeError(f"Failed extracting references from {file_path}: {exc}") from exc

            # Traverse SQLite databases to discover committed logical state (including committed WAL frames)
            # Always inspect via an isolated temporary directory to ensure zero source sidecar creation or mutation
            elif spec.is_database and file_path.is_file():
                wal_sidecar = file_path.with_name(f"{file_path.name}-wal")
                shm_sidecar = file_path.with_name(f"{file_path.name}-shm")
                import tempfile
                try:
                    with tempfile.TemporaryDirectory() as td_name:
                        td = Path(td_name)
                        inspect_db = td / file_path.name
                        shutil.copy2(file_path, inspect_db)
                        if wal_sidecar.is_file():
                            shutil.copy2(wal_sidecar, td / wal_sidecar.name)
                        if shm_sidecar.is_file():
                            shutil.copy2(shm_sidecar, td / shm_sidecar.name)

                        uri = f"{inspect_db.resolve().as_uri()}?mode=ro"
                        with closing(sqlite3.connect(uri, uri=True)) as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
                            if cur.fetchone():
                                cur.execute("PRAGMA table_info(jobs)")
                                cols = {row[1] for row in cur.fetchall()}
                                query_cols = [c for c in ["key", "recipe", "detail"] if c in cols]
                                if query_cols:
                                    cur.execute(f"SELECT {','.join(query_cols)} FROM jobs")
                                    for row in cur.fetchall():
                                        for val in row:
                                            if isinstance(val, str):
                                                val_s = val.strip()
                                                if val_s.startswith("{") or val_s.startswith("["):
                                                    try:
                                                        discovered_refs.extend(_extract_references(json.loads(val_s)))
                                                    except Exception:
                                                        discovered_refs.append(val)
                                                else:
                                                    discovered_refs.append(val)
                except Exception as exc:
                    if not isinstance(exc, RuntimeError):
                        raise RuntimeError(f"Failed extracting references from database {file_path}: {exc}") from exc
                    raise

            for ref in discovered_refs:
                ref = ref.strip()
                if not ref or len(ref) > 260:
                    continue
                ref_p = Path(ref)
                if ref_p.suffix.lower() not in valid_extensions:
                    continue
                target = (runtime_root / ref_p).resolve()
                if not target.is_relative_to(runtime_root):
                    continue

                if target in seen_paths:
                    continue

                if not target.is_file():
                    raise RuntimeError(
                        f"Incomplete recovery closure: referenced artifact {ref!r} is missing from runtime root {runtime_root}"
                    )

                ext = target.suffix.lower()
                name = target.name.lower()
                if ext in media_extensions:
                    cat = RecoveryItemCategory.EVIDENCE
                elif ext == ".txt":
                    cat = RecoveryItemCategory.INPUT
                elif "timeline" in name:
                    cat = RecoveryItemCategory.PLAN
                elif "script" in name or "brief" in name:
                    cat = RecoveryItemCategory.INPUT
                elif "plan" in name:
                    cat = RecoveryItemCategory.PLAN
                else:
                    cat = RecoveryItemCategory.EVIDENCE

                item_spec = RecoveryItemSpec(
                    pattern=target.name,
                    category=cat,
                    description=f"Referenced operational artifact: {ref}",
                    is_database=False,
                    required=True,
                )
                new_items.append((target, item_spec))
                seen_paths.add(target)
                changed = True

        closure_items.extend(new_items)

    return sorted(closure_items, key=lambda x: str(x[0]))


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

    return expand_recovery_closure(runtime_root, matched)


_WINDOWS_DOS_RESERVED_NAMES: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def _validate_recovery_id(recovery_id: str) -> None:
    """Validate that recovery_id is safe and strictly alphanumeric/hyphen/underscore."""
    if not isinstance(recovery_id, str) or not re.match(r"^[a-zA-Z0-9_\-]{1,64}$", recovery_id):
        raise ValueError(f"Invalid recovery_id: {recovery_id!r}")
    if recovery_id.upper() in _WINDOWS_DOS_RESERVED_NAMES:
        raise ValueError(f"Invalid recovery_id: {recovery_id!r} is a reserved Windows DOS device name")


_active_snapshot_locks: set[Path] = set()
_snapshot_locks_mutex = threading.Lock()


@contextlib.contextmanager
def _acquire_snapshot_lock(lock_path: Path, recovery_id: str):
    """Acquire exclusive non-blocking file lock across processes and threads.

    Guarantees that two concurrent attempts for the same snapshot ID produce
    exactly one owner. Losing attempts fail fast with FileExistsError without
    modifying or touching any snapshot files.
    """
    _validate_recovery_id(recovery_id)
    lock_path = lock_path.resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with _snapshot_locks_mutex:
        if lock_path in _active_snapshot_locks:
            raise FileExistsError(
                f"Recovery snapshot attempt for {recovery_id} is actively owned by another thread"
            )
        _active_snapshot_locks.add(lock_path)

    f = None
    try:
        f = open(lock_path, "a+b")
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as err:
                if err.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                    raise FileExistsError(
                        f"Recovery snapshot attempt for {recovery_id} is actively owned by another process"
                    ) from err
                raise
        else:
            import fcntl
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as err:
                if err.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                    raise FileExistsError(
                        f"Recovery snapshot attempt for {recovery_id} is actively owned by another process"
                    ) from err
                raise
    except BaseException:
        with _snapshot_locks_mutex:
            _active_snapshot_locks.discard(lock_path)
        if f is not None:
            try:
                f.close()
            except OSError:
                pass
        raise

    try:
        yield f
    finally:
        try:
            if f is not None:
                try:
                    if sys.platform == "win32":
                        import msvcrt
                        try:
                            f.seek(0)
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        except OSError:
                            pass
                    else:
                        import fcntl
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        except OSError:
                            pass
                finally:
                    try:
                        f.close()
                    except OSError:
                        pass
        finally:
            with _snapshot_locks_mutex:
                _active_snapshot_locks.discard(lock_path)


def _archive_interrupted_dir(
    backup_storage: Path,
    recovery_id: str,
    snapshot_dir: Path,
) -> Path | None:
    if not snapshot_dir.exists():
        return None

    manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"
    if manifest_path.is_file():
        raise FileExistsError(
            f"Cannot archive completed recovery snapshot {recovery_id}; completed snapshots are immutable"
        )

    ts = int(time.time())
    archive_dir = (backup_storage / f"{recovery_id}.interrupted.{ts}").resolve()
    idx = 1
    while archive_dir.exists():
        archive_dir = (backup_storage / f"{recovery_id}.interrupted.{ts}_{idx}").resolve()
        idx += 1

    if not archive_dir.is_relative_to(backup_storage) or archive_dir == backup_storage:
        raise ValueError(f"Archive directory escapes backup storage: {archive_dir}")

    interrupted_receipt = {
        "status": "INTERRUPTED_ARCHIVED",
        "recovery_id": recovery_id,
        "archived_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "original_path": str(snapshot_dir),
        "archive_path": str(archive_dir),
    }
    receipt_bytes = json.dumps(interrupted_receipt, indent=2).encode("utf-8")

    primary_receipt = snapshot_dir / "INTERRUPTED_RECEIPT.json"
    target_receipt: Path | None = None
    if not primary_receipt.exists():
        try:
            with primary_receipt.open("xb") as rf:
                rf.write(receipt_bytes)
                rf.flush()
                os.fsync(rf.fileno())
            target_receipt = primary_receipt
        except FileExistsError:
            pass  # Fall through to timestamped receipt to retain existing bytes

    if target_receipt is None:
        # Retain preexisting historical receipt bytes; write distinct exclusive operation receipt
        retry_idx = 0
        while True:
            suffix = f".{ts}" if retry_idx == 0 else f".{ts}_{retry_idx}"
            cand = snapshot_dir / f"INTERRUPTED_RECEIPT{suffix}.json"
            try:
                with cand.open("xb") as rf:
                    rf.write(receipt_bytes)
                    rf.flush()
                    os.fsync(rf.fileno())
                target_receipt = cand
                break
            except FileExistsError:
                retry_idx += 1

    shutil.move(str(snapshot_dir), str(archive_dir))
    return archive_dir


def archive_interrupted_snapshot(
    backup_storage: Path,
    recovery_id: str,
) -> Path | None:
    """Explicitly archive an interrupted snapshot attempt, preserving all evidence.

    Refuses if:
    - recovery_id is invalid or attempts traversal / namespace escape.
    - Snapshot already completed (RECOVERY_MANIFEST.json present); completed snapshots are immutable.
    - An attempt is actively running (lock actively held).
    """
    _validate_recovery_id(recovery_id)
    backup_storage = backup_storage.resolve()
    snapshot_dir = (backup_storage / recovery_id).resolve()
    if not snapshot_dir.is_relative_to(backup_storage) or snapshot_dir == backup_storage:
        raise ValueError(f"Snapshot directory escapes backup storage: {recovery_id!r}")

    lock_path = (backup_storage / f".{recovery_id}.lock").resolve()
    if not lock_path.is_relative_to(backup_storage):
        raise ValueError(f"Lock path escapes backup storage: {recovery_id!r}")

    with _acquire_snapshot_lock(lock_path, recovery_id):
        return _archive_interrupted_dir(backup_storage, recovery_id, snapshot_dir)


def _capture_snapshot_contents(
    runtime_root: Path,
    snapshot_dir: Path,
    recovery_id: str,
    matched_items: list[tuple[Path, RecoveryItemSpec]],
    _sync_hook: Callable[[str], None] | None = None,
) -> Path:
    file_entries: list[RecoveryFileEntry] = []

    # Bind truthful authority metadata into manifest
    authority_ptr = ""
    authority_gen = 1
    db_items = [f for f, spec in matched_items if spec.is_database]
    if db_items:
        authority_ptr = str(db_items[0].resolve())
        try:
            with db_items[0].open("rb") as f:
                h = f.read(100)
                if len(h) >= 100:
                    authority_gen = int.from_bytes(h[60:64], "big") or 1
        except OSError:
            pass
    else:
        try:
            from youtube_automation.production.authority import discover_authority
            resolution = discover_authority(default_root=runtime_root, enforce_maintenance=False)
            authority_ptr = str(resolution.database_path)
            authority_gen = resolution.schema_generation
        except Exception:
            pass

    # Truthful project_run_id from jobs table or recovery_id (isolated temp inspection)
    project_run = recovery_id
    if db_items and db_items[0].is_file():
        wal_sidecar = db_items[0].with_name(f"{db_items[0].name}-wal")
        shm_sidecar = db_items[0].with_name(f"{db_items[0].name}-shm")
        import tempfile
        try:
            with tempfile.TemporaryDirectory() as td_name:
                td = Path(td_name)
                inspect_db = td / db_items[0].name
                shutil.copy2(db_items[0], inspect_db)
                if wal_sidecar.is_file():
                    shutil.copy2(wal_sidecar, td / wal_sidecar.name)
                if shm_sidecar.is_file():
                    shutil.copy2(shm_sidecar, td / shm_sidecar.name)
                uri = f"{inspect_db.resolve().as_uri()}?mode=ro"
                with closing(sqlite3.connect(uri, uri=True)) as conn:
                    row = conn.execute("SELECT key FROM jobs LIMIT 1").fetchone()
                    if row and row[0]:
                        project_run = str(row[0])
        except Exception:
            pass

    # Enforce consistency boundary preflight: active rollback journal or transient transaction blocks capture
    for file_path, spec in matched_items:
        if spec.is_database:
            j_file = file_path.with_name(f"{file_path.name}-journal")
            if j_file.exists():
                raise RuntimeError(
                    f"Consistency boundary violation: active rollback journal detected for {file_path.name}; "
                    f"cannot certify coherent committed capture during active transaction"
                )

    # Record pre-copy state for all database and journal files to enforce consistency boundary
    pre_db_state: dict[Path, tuple[int, int, str]] = {}
    for file_path, spec in matched_items:
        if spec.is_database or spec.category == RecoveryItemCategory.JOURNAL:
            pre_db_state[file_path] = (
                file_path.stat().st_size,
                file_path.stat().st_mtime_ns,
                compute_sha256(file_path),
            )

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

            if spec.is_database:
                # Immediate check for journal appearance during copy
                j_file = file_path.with_name(f"{file_path.name}-journal")
                if j_file.exists():
                    raise RuntimeError(
                        f"Consistency boundary violation: transient rollback journal appeared for {file_path.name} during copy; "
                        f"refusing uncommitted capture"
                    )
                # Verify that copied bytes match the pre-copy source hash
                pre_size, _pre_mtime, pre_sha = pre_db_state[file_path]
                if sha != pre_sha or size != pre_size:
                    raise RuntimeError(
                        f"Consistency boundary violation: copied database {dest_path.name} hash {sha} "
                        f"does not match verified source hash {pre_sha}; uncommitted or concurrent spill detected"
                    )

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

        # Enforce consistency boundary: verify that source databases and journals did not mutate concurrently during copy
        for file_path, (pre_size, _pre_mtime, pre_sha) in pre_db_state.items():
            if not file_path.exists():
                raise RuntimeError(
                    f"Consistency boundary violation: source file {file_path.name} was removed during snapshot capture"
                )
            if file_path.is_file():
                j_file = file_path.with_name(f"{file_path.name}-journal")
                if j_file.exists():
                    raise RuntimeError(
                        f"Consistency boundary violation: rollback journal {j_file.name} present after copy"
                    )
            curr_size = file_path.stat().st_size
            curr_sha = compute_sha256(file_path)
            if curr_size != pre_size or curr_sha != pre_sha:
                raise RuntimeError(
                    f"Consistency boundary violation: concurrent database modification detected on {file_path.name} during snapshot capture; "
                    f"refusing capture to prevent mixed-generation inconsistency"
                )

        # Step 2: Enforce logical generation closure: verify that all references required by the captured databases
        # and captured documents exist in the snapshot closure (transitive closure).
        media_extensions = {".wav", ".mp3", ".mp4", ".png", ".jpg", ".jpeg", ".webp"}
        doc_extensions = {".txt", ".json", ".md"}
        valid_extensions = media_extensions | doc_extensions
        captured_rel_paths = {entry.relative_path for entry in file_entries}
        inspected_docs: set[str] = set()
        pending_refs: list[tuple[str, str]] = []

        # 1. Collect references from captured databases (inspecting isolated copy with committed WAL)
        for dest_path, _spec in db_entries:
            with tempfile.TemporaryDirectory() as inspect_tmp:
                inspect_db = Path(inspect_tmp) / dest_path.name
                shutil.copyfile(dest_path, inspect_db)
                for sidecar_ext in ["-wal", "-shm"]:
                    s_file = dest_path.with_name(f"{dest_path.name}{sidecar_ext}")
                    if s_file.exists():
                        try:
                            shutil.copyfile(s_file, Path(inspect_tmp) / s_file.name)
                        except OSError:
                            pass
                with closing(sqlite3.connect(inspect_db)) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
                    if cur.fetchone():
                        cur.execute("PRAGMA table_info(jobs)")
                        cols = {row[1] for row in cur.fetchall()}
                        query_cols = [c for c in ["key", "recipe", "detail"] if c in cols]
                        if query_cols:
                            cur.execute(f"SELECT {','.join(query_cols)} FROM jobs")
                            for row in cur.fetchall():
                                for val in row:
                                    if isinstance(val, str):
                                        val_s = val.strip()
                                        if val_s.startswith("{") or val_s.startswith("["):
                                            try:
                                                for ref in _extract_references(json.loads(val_s)):
                                                    pending_refs.append(("captured database", ref))
                                            except Exception:
                                                pending_refs.append(("captured database", val))
                                        else:
                                            pending_refs.append(("captured database", val))

        # 2. Collect references from captured JSON documents
        for entry in file_entries:
            if entry.relative_path.lower().endswith(".json") and not Path(entry.relative_path).name.startswith("RECOVERY_MANIFEST"):
                doc_file = snapshot_dir / entry.relative_path
                if doc_file.is_file() and entry.relative_path not in inspected_docs:
                    inspected_docs.add(entry.relative_path)
                    try:
                        content = doc_file.read_text(encoding="utf-8")
                        parsed = json.loads(content)
                        for ref in _extract_references(parsed):
                            pending_refs.append((f"captured document {entry.relative_path}", ref))
                    except json.JSONDecodeError:
                        pass
                    except Exception as exc:
                        raise RuntimeError(f"Failed extracting references from captured document {entry.relative_path}: {exc}") from exc

        # 3. Transitively validate all references
        runtime_root_resolved = runtime_root.resolve()
        while pending_refs:
            source_desc, ref = pending_refs.pop(0)
            ref = ref.strip()
            if not ref or len(ref) > 260:
                continue
            ref_p = Path(ref)
            if ref_p.suffix.lower() not in valid_extensions:
                continue
            try:
                target = (runtime_root_resolved / ref_p).resolve()
            except Exception:
                continue
            if not target.is_relative_to(runtime_root_resolved):
                continue
            rel_p = target.relative_to(runtime_root_resolved)
            rel_posix = rel_p.as_posix()
            target_in_snapshot = snapshot_dir / rel_p
            if rel_posix not in captured_rel_paths and not target_in_snapshot.is_file():
                raise RuntimeError(
                    f"Consistency boundary violation: {source_desc} requires referenced artifact {ref!r} "
                    f"not present in snapshot generation; concurrent modification detected"
                )

            # If referenced artifact is a JSON document, traverse its references as well
            if rel_p.suffix.lower() == ".json" and rel_posix not in inspected_docs:
                inspected_docs.add(rel_posix)
                if target_in_snapshot.is_file():
                    try:
                        content = target_in_snapshot.read_text(encoding="utf-8")
                        parsed = json.loads(content)
                        for nested_ref in _extract_references(parsed):
                            pending_refs.append((f"captured document {rel_posix}", nested_ref))
                    except json.JSONDecodeError:
                        pass
                    except Exception as exc:
                        raise RuntimeError(f"Failed extracting references from captured document {rel_posix}: {exc}") from exc

        # Step 3: Verify database integrity on the backup copies in isolated backup storage
        for dest_path, _spec in db_entries:
            with tempfile.TemporaryDirectory() as inspect_tmp:
                inspect_db = Path(inspect_tmp) / dest_path.name
                shutil.copyfile(dest_path, inspect_db)
                for sidecar_ext in ["-wal", "-shm"]:
                    s_file = dest_path.with_name(f"{dest_path.name}{sidecar_ext}")
                    if s_file.exists():
                        try:
                            shutil.copyfile(s_file, Path(inspect_tmp) / s_file.name)
                        except OSError:
                            pass
                with closing(sqlite3.connect(inspect_db)) as chk_conn:
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
            project_run_id=project_run,
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

        if _sync_hook is not None:
            _sync_hook("before_manifest_publish")

        os.replace(str(tmp_manifest), str(manifest_path))

        try:
            (snapshot_dir / ".ATTEMPT.json").unlink(missing_ok=True)
        except OSError:
            pass

        return manifest_path

    except Exception as exc:
        # Preserve failed recovery evidence
        try:
            fail_record = {
                "status": "FAILED",
                "recovery_id": recovery_id,
                "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            fail_manifest = snapshot_dir / "FAILED_SNAPSHOT.json"
            fail_manifest.write_text(json.dumps(fail_record, indent=2), encoding="utf-8")
            try:
                (snapshot_dir / ".ATTEMPT.json").unlink(missing_ok=True)
            except OSError:
                pass
        except Exception:
            pass
        raise


def create_isolated_recovery_snapshot(
    runtime_root: Path,
    backup_storage: Path,
    recovery_id: str,
    *,
    recover_interrupted: bool = False,
    _sync_hook: Callable[[str], None] | None = None,
) -> Path:
    """Create a verified point-in-time recovery snapshot without mutating live production state.

    Uses byte-level file preservation without opening SQLite connections against the live source,
    guaranteeing 0 byte changes, 0 sidecar creations, and 0 directory mutations in source.

    Concurrency and safety guarantees (Issue #58):
    - Exclusive ownership established before creating or modifying any snapshot files.
    - Two concurrent attempts on same recovery_id produce exactly one owner; loser refuses without
      mutating winner's files, manifest, receipts, or failure evidence.
    - Completed snapshots refuse conflicting reuse without modifying existing bytes.
    - Interrupted attempts retain evidence; refuses overwrite unless explicit recover_interrupted=True.
    - Manifest is published atomically only after all closure and integrity checks pass.
    """
    _validate_recovery_id(recovery_id)

    runtime_root = runtime_root.resolve()
    backup_storage = backup_storage.resolve()
    snapshot_dir = (backup_storage / recovery_id).resolve()
    if not snapshot_dir.is_relative_to(backup_storage) or snapshot_dir == backup_storage:
        raise ValueError(f"Snapshot directory escapes backup storage: {recovery_id!r}")

    lock_path = (backup_storage / f".{recovery_id}.lock").resolve()
    if not lock_path.is_relative_to(backup_storage):
        raise ValueError(f"Lock path escapes backup storage: {recovery_id!r}")

    # Pre-check without acquiring lock (fast path for existing completed or unrecovered snapshots)
    if snapshot_dir.exists():
        manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"
        if manifest_path.is_file():
            raise FileExistsError(f"Recovery snapshot {recovery_id} already exists with completed manifest")
        if not recover_interrupted:
            fail_path = snapshot_dir / "FAILED_SNAPSHOT.json"
            if fail_path.is_file():
                raise FileExistsError(
                    f"Recovery snapshot {recovery_id} already exists with recorded failure evidence; refusing overwrite"
                )
            raise FileExistsError(f"Recovery snapshot directory {snapshot_dir} already exists")

    backup_storage.mkdir(parents=True, exist_ok=True)

    with _acquire_snapshot_lock(lock_path, recovery_id):
        if _sync_hook is not None:
            _sync_hook("after_lock_acquired")

        # In-lock check: ensure state did not change while waiting
        if snapshot_dir.exists():
            manifest_path = snapshot_dir / "RECOVERY_MANIFEST.json"
            if manifest_path.is_file():
                raise FileExistsError(f"Recovery snapshot {recovery_id} already exists with completed manifest")
            if not recover_interrupted:
                fail_path = snapshot_dir / "FAILED_SNAPSHOT.json"
                if fail_path.is_file():
                    raise FileExistsError(
                        f"Recovery snapshot {recovery_id} already exists with recorded failure evidence; refusing overwrite"
                    )
                raise FileExistsError(f"Recovery snapshot directory {snapshot_dir} already exists")

            # Explicit recovery requested: archive prior interrupted attempt
            _archive_interrupted_dir(backup_storage, recovery_id, snapshot_dir)

        snapshot_dir.mkdir(parents=True, exist_ok=False)

        # Record attempt ownership marker inside the snapshot directory
        attempt_record = {
            "status": "IN_PROGRESS",
            "recovery_id": recovery_id,
            "pid": os.getpid(),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        (snapshot_dir / ".ATTEMPT.json").write_text(json.dumps(attempt_record, indent=2), encoding="utf-8")

        matched_items = identify_recovery_files(runtime_root)
        return _capture_snapshot_contents(
            runtime_root=runtime_root,
            snapshot_dir=snapshot_dir,
            recovery_id=recovery_id,
            matched_items=matched_items,
            _sync_hook=_sync_hook,
        )


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
    _validate_recovery_id(recovery_id)
    backup_storage = backup_storage.resolve()
    target_restore_dir = target_restore_dir.resolve()
    snapshot_dir = (backup_storage / recovery_id).resolve()
    if not snapshot_dir.is_relative_to(backup_storage) or snapshot_dir == backup_storage:
        raise ValueError(f"Snapshot directory escapes backup storage: {recovery_id!r}")
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

    # Step 6: Perform verified restoration with conflict preservation at write boundary
    try:
        restored_entries: list[dict[str, Any]] = []
        target_restore_dir.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            src_path = snapshot_dir / entry.relative_path
            dest_path = target_restore_dir / entry.relative_path

            if dest_path.is_file():
                dest_sha = compute_sha256(dest_path)
                if dest_sha != entry.sha256:
                    raise FileExistsError(
                        f"Restoration conflict: destination file {dest_path} already exists with differing content "
                        f"(hash {dest_sha} != snapshot {entry.sha256}); preserving newer work"
                    )
                # Already identical; skip copy
                restored_entries.append(entry.to_dict())
                continue

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.resolve().is_relative_to(target_restore_dir_resolved):
                raise ValueError(f"Destination file escapes restore directory: {entry.relative_path}")

            try:
                with src_path.open("rb") as sf, dest_path.open("xb") as df:
                    # Enforce containment through writing: re-verify resolved path while df is open
                    curr_resolved = dest_path.resolve()
                    if not curr_resolved.is_relative_to(target_restore_dir_resolved):
                        try:
                            df.close()
                            # Inspect destination existence without unlinking escaped path to preserve competitor work
                            dest_path.is_file()
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"Restoration destination containment violation: destination path {dest_path} "
                            f"(resolved {curr_resolved}) escaped target root {target_restore_dir_resolved} during open"
                        )
                    while chunk := sf.read(65536):
                        df.write(chunk)
                shutil.copystat(src_path, dest_path)
            except FileExistsError:
                dest_sha = compute_sha256(dest_path)
                if dest_sha != entry.sha256:
                    raise FileExistsError(
                        f"Restoration conflict: destination file {dest_path} appeared concurrently with differing content "
                        f"(hash {dest_sha} != snapshot {entry.sha256}); preserving newer work"
                    ) from None

            restored_sha = compute_sha256(dest_path)
            if restored_sha != entry.sha256:
                raise ValueError(
                    f"Restored file {dest_path} hash mismatch: {restored_sha} != {entry.sha256}"
                )

            if entry.is_database:
                # Verify database integrity on restored copy
                with closing(sqlite3.connect(f"{dest_path.as_uri()}?mode=ro&immutable=1", uri=True)) as chk_conn:
                    integrity = chk_conn.execute("PRAGMA integrity_check").fetchone()
                    if not integrity or integrity[0] != "ok":
                        raise RuntimeError(f"Restored database {dest_path} failed integrity check: {integrity}")

            restored_entries.append(entry.to_dict())

        # Step 7: Advance authority epoch to invalidate prior tokens/leases upon restoration
        import uuid
        restored_epoch = str(uuid.uuid4())
        try:
            (target_restore_dir / ".authority_epoch").write_text(restored_epoch, encoding="utf-8")
        except Exception:
            pass

        # Step 8: Write restoration verification receipt in restore directory (exclusive write)
        receipt_data = {
            "status": "RESTORED",
            "recovery_id": recovery_id,
            "authority_epoch": restored_epoch,
            "restored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "manifest_sha256": manifest_data.get("manifest_sha256", ""),
            "total_files": len(restored_entries),
            "restored_files": restored_entries,
        }
        receipt_bytes = json.dumps(receipt_data, indent=2).encode("utf-8")
        receipt_path_resolved = receipt_path.resolve()
        if not receipt_path_resolved.is_relative_to(target_restore_dir_resolved):
            raise ValueError(f"Restoration receipt escapes restore directory: {receipt_path}")
        try:
            with receipt_path.open("xb") as rf:
                if not receipt_path.resolve().is_relative_to(target_restore_dir_resolved):
                    try:
                        rf.close()
                    except Exception:
                        pass
                    raise RuntimeError(f"Restoration receipt escaped target root during open: {receipt_path}")
                rf.write(receipt_bytes)
        except FileExistsError as err:
            raise FileExistsError(
                f"Restoration conflict: destination receipt {receipt_path} was created concurrently; preserving newer evidence"
            ) from err

        return receipt_data
    except Exception as exc:
        try:
            target_restore_dir.mkdir(parents=True, exist_ok=True)
            fail_record = {
                "status": "FAILED",
                "recovery_id": recovery_id,
                "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            fail_path = target_restore_dir / f"FAILED_RESTORATION_{recovery_id}.json"
            if not fail_path.exists():
                fail_path.write_text(json.dumps(fail_record, indent=2), encoding="utf-8")
        except Exception:
            pass
        raise
