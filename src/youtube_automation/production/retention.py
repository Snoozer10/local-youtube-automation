"""Runtime retention classification and reversible archiving (Issue #40)."""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


class RetentionCategory(str, enum.Enum):
    ACTIVE_STATE = "ACTIVE_STATE"          # Active DBs, sidecars, leases, jobs, locks
    IMMUTABLE_EVIDENCE = "IMMUTABLE_EVIDENCE"  # Completion reports, receipts, preimages, audits
    REBUILDABLE_CACHE = "REBUILDABLE_CACHE"  # Verified disposable intermediate caches
    UNKNOWN_PRESERVE = "UNKNOWN_PRESERVE"    # Unrecognized files; must be preserved by default


@dataclasses.dataclass(frozen=True)
class RetentionCandidate:
    path: Path
    category: RetentionCategory
    size_bytes: int
    sha256: str
    rationale: str
    owner: str = "production"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path.as_posix()),
            "category": self.category.value,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "rationale": self.rationale,
            "owner": self.owner,
        }


def compute_sha256(path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def classify_entry(path: Path, root: Path) -> RetentionCandidate:
    """Classify a single runtime entry by purpose, active references, and retention policy."""
    rel = path.relative_to(root).as_posix().lower()
    size = path.stat().st_size if path.is_file() else 0
    file_sha = compute_sha256(path) if path.is_file() else ""

    # 1. Active State & Locks: databases, sidecars, leases, process locks
    if any(rel.endswith(ext) for ext in (".sqlite", ".sqlite3", "-wal", "-shm", ".db", ".lock", ".lease")):
        return RetentionCandidate(
            path=path,
            category=RetentionCategory.ACTIVE_STATE,
            size_bytes=size,
            sha256=file_sha,
            rationale="Active operational database, journal sidecar, or coordination lock",
            owner="production.core",
        )
    if "adaptive.sqlite3" in rel or "runtime_state" in rel:
        return RetentionCandidate(
            path=path,
            category=RetentionCategory.ACTIVE_STATE,
            size_bytes=size,
            sha256=file_sha,
            rationale="Active system state ledger or state checkpoint",
            owner="production.core",
        )

    # 2. Immutable Evidence: completion reports, audit records, preimages, verification receipts
    if any(k in rel for k in ("receipt", "closeout", "preimage", "evidence", "audit", "failure", "rejection", "report")):
        return RetentionCandidate(
            path=path,
            category=RetentionCategory.IMMUTABLE_EVIDENCE,
            size_bytes=size,
            sha256=file_sha,
            rationale="Immutable completion, rejection, diagnostic, or verification evidence",
            owner="auditor",
        )

    # 3. Rebuildable Caches: verified disposable intermediate caches with explicit recipe
    non_disposable_exts = {".json", ".md", ".py", ".sql", ".txt", ".yaml", ".yml", ".sh", ".ps1"}
    has_non_disposable_ext = any(rel.endswith(ext) for ext in non_disposable_exts)

    if not has_non_disposable_ext and (
        rel.endswith(".cache")
        or rel.endswith(".tmp_cache")
        or any(k in rel for k in ("intermediate_frames", "temp_scratch"))
    ):
        return RetentionCandidate(
            path=path,
            category=RetentionCategory.REBUILDABLE_CACHE,
            size_bytes=size,
            sha256=file_sha,
            rationale="Rebuildable intermediate cache with reproducible generation recipe",
            owner="pipeline.worker",
        )

    # 4. Unknown: fail-safe default is preserve
    return RetentionCandidate(
        path=path,
        category=RetentionCategory.UNKNOWN_PRESERVE,
        size_bytes=size,
        sha256=file_sha,
        rationale="Unrecognized purpose; preserved under fail-safe default policy",
        owner="unknown",
    )


def classify_runtime_directory(root: Path) -> list[RetentionCandidate]:
    """Inspect and classify all files within the given runtime root directory, excluding archive storage."""
    if not root.is_dir():
        return []
    candidates: list[RetentionCandidate] = []
    archive_dir_name = ".archive"
    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            rel_parts = entry.relative_to(root).parts
            if archive_dir_name in rel_parts or "archive_storage" in rel_parts:
                continue
            candidates.append(classify_entry(entry, root))
    return candidates


def generate_retention_report(candidates: list[RetentionCandidate]) -> dict[str, Any]:
    """Generate a structured summary report of classified retention candidates."""
    counts: dict[str, int] = {cat.value: 0 for cat in RetentionCategory}
    bytes_by_cat: dict[str, int] = {cat.value: 0 for cat in RetentionCategory}

    for c in candidates:
        counts[c.category.value] += 1
        bytes_by_cat[c.category.value] += c.size_bytes

    return {
        "total_files": len(candidates),
        "total_bytes": sum(c.size_bytes for c in candidates),
        "category_counts": counts,
        "category_bytes": bytes_by_cat,
        "candidates": [c.to_dict() for c in candidates],
    }


def dry_run_retention(root: Path) -> dict[str, Any]:
    """Perform a dry-run retention inspection with zero state modifications."""
    candidates = classify_runtime_directory(root)
    report = generate_retention_report(candidates)
    report["dry_run"] = True
    report["disposable_files"] = [
        c.to_dict() for c in candidates if c.category == RetentionCategory.REBUILDABLE_CACHE
    ]
    report["protected_files"] = [
        c.to_dict() for c in candidates if c.category != RetentionCategory.REBUILDABLE_CACHE
    ]
    return report


class ReversibleArchiveCycle:
    """Manages an atomic, bounded, reversible archive cycle with journaled interruption recovery."""

    def __init__(self, runtime_root: Path, archive_storage: Path) -> None:
        self.runtime_root = runtime_root.resolve()
        self.archive_storage = archive_storage.resolve()

    def _journal_path(self, cycle_id: str) -> Path:
        return self.archive_storage / f".archive_journal_{cycle_id}.json"

    def _write_journal_atomically(self, journal_file: Path, journal_data: dict[str, Any]) -> None:
        import os
        tmp_file = journal_file.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")
        os.replace(str(tmp_file), str(journal_file))

    def archive_candidates(
        self,
        cycle_id: str,
        candidates: list[RetentionCandidate],
    ) -> dict[str, Any]:
        """Execute a reversible archive cycle on eligible REBUILDABLE_CACHE candidates only."""
        import re
        if not re.match(r"^[a-zA-Z0-9_\-]{1,64}$", cycle_id):
            raise ValueError(f"Invalid cycle_id: {cycle_id!r}")

        # 1. Enforce safety policy: reject any protected or unknown candidates
        disallowed = [c for c in candidates if c.category != RetentionCategory.REBUILDABLE_CACHE]
        if disallowed:
            paths = [str(c.path) for c in disallowed]
            raise PermissionError(
                f"Refusing to archive protected or unknown files: {paths}"
            )

        if not candidates:
            return {"cycle_id": cycle_id, "status": "NOOP", "archived_files": []}

        self.archive_storage.mkdir(parents=True, exist_ok=True)
        cycle_dir = self.archive_storage / cycle_id
        cycle_dir.mkdir(parents=True, exist_ok=True)
        journal_file = self._journal_path(cycle_id)

        # 2. Write pre-archive journal with exact source paths and SHA-256 preimages
        journal_entries: list[dict[str, Any]] = []
        for c in candidates:
            rel = c.path.relative_to(self.runtime_root).as_posix()
            dest = cycle_dir / rel
            journal_entries.append({
                "source": str(c.path.resolve()),
                "relative": rel,
                "dest": str(dest.resolve()),
                "sha256": c.sha256,
                "size_bytes": c.size_bytes,
                "moved": False,
            })

        journal_data = {
            "cycle_id": cycle_id,
            "status": "IN_PROGRESS",
            "runtime_root": str(self.runtime_root),
            "cycle_dir": str(cycle_dir),
            "entries": journal_entries,
        }
        self._write_journal_atomically(journal_file, journal_data)

        # 3. Move files to archive directory while updating journal atomically
        for entry in journal_entries:
            src = Path(entry["source"])
            dst = Path(entry["dest"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            entry["moved"] = True
            self._write_journal_atomically(journal_file, journal_data)

        # 4. Finalize receipt and remove active journal
        journal_data["status"] = "COMPLETED"
        receipt_path = cycle_dir / "ARCHIVE_RECEIPT.json"
        receipt_path.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")
        if journal_file.exists():
            journal_file.unlink()

        return {
            "cycle_id": cycle_id,
            "status": "COMPLETED",
            "receipt_path": str(receipt_path),
            "archived_count": len(candidates),
        }

    def rollback_interrupted_cycle(self, cycle_id: str) -> dict[str, Any]:
        """Detect an interrupted archive cycle from its journal and safely restore all files without data loss."""
        journal_file = self._journal_path(cycle_id)
        if not journal_file.is_file():
            return {"cycle_id": cycle_id, "status": "NO_ACTIVE_JOURNAL"}

        journal_data = json.loads(journal_file.read_text(encoding="utf-8"))
        restored: list[str] = []
        all_verified = True

        for entry in journal_data.get("entries", []):
            dst = Path(entry["dest"])
            src = Path(entry["source"])
            expected_sha = entry["sha256"]

            # Reconcile physical filesystem state regardless of moved flag
            if dst.is_file():
                # Verify archive copy
                dst_sha = compute_sha256(dst)
                if dst_sha != expected_sha:
                    all_verified = False
                    raise ValueError(
                        f"Archived file {dst} corrupted: {dst_sha} != {expected_sha}"
                    )
                if src.is_file():
                    src_sha = compute_sha256(src)
                    if src_sha == expected_sha:
                        # Source already restored; clean up dst
                        dst.unlink()
                    else:
                        # Conflict with newer source file! Do not overwrite, fail closed!
                        all_verified = False
                        raise FileExistsError(
                            f"Rollback conflict: source file {src} exists with differing hash: {src_sha} != {expected_sha}"
                        )
                else:
                    src.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(src))
                    restored_sha = compute_sha256(src)
                    if restored_sha != expected_sha:
                        all_verified = False
                        raise ValueError(
                            f"Restored file {src} hash mismatch: {restored_sha} != {expected_sha}"
                        )
                    restored.append(str(src))
            elif src.is_file():
                # File was never moved or already back at source
                src_sha = compute_sha256(src)
                if src_sha != expected_sha:
                    all_verified = False
            else:
                # Missing from both locations!
                all_verified = False
                raise FileNotFoundError(
                    f"File missing from both source and destination during rollback: {src}"
                )

        # Only clean up cycle directory and journal if ALL entries are verified restored
        cycle_dir = Path(journal_data["cycle_dir"])
        if all_verified:
            if cycle_dir.is_dir():
                shutil.rmtree(cycle_dir, ignore_errors=True)
            if journal_file.exists():
                journal_file.unlink()

        return {
            "cycle_id": cycle_id,
            "status": "ROLLED_BACK",
            "restored_files": restored,
        }

    def restore_archive(self, cycle_id: str) -> dict[str, Any]:
        """Restore all archived files from a completed archive receipt, verifying byte-exactness and refusing conflicts."""
        cycle_dir = self.archive_storage / cycle_id
        receipt_path = cycle_dir / "ARCHIVE_RECEIPT.json"
        if not receipt_path.is_file():
            raise FileNotFoundError(f"Archive receipt missing: {receipt_path}")

        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        entries = receipt.get("entries", [])

        # Step 1: Pre-validation of all destinations to prevent overwriting newer resumed work
        for entry in entries:
            dst = Path(entry["dest"])
            src = Path(entry["source"])
            expected_sha = entry["sha256"]

            if not dst.is_file():
                raise FileNotFoundError(f"Archived file missing from storage: {dst}")

            archive_sha = compute_sha256(dst)
            if archive_sha != expected_sha:
                raise ValueError(
                    f"Archived file corrupted: {dst} hash {archive_sha} != {expected_sha}"
                )

            if src.is_file():
                src_sha = compute_sha256(src)
                if src_sha != expected_sha:
                    # Destination has newer or modified content! Refuse overwrite to prevent data loss.
                    raise FileExistsError(
                        f"Restoration conflict: destination file {src} already exists with differing content (hash {src_sha} != archived {expected_sha})"
                    )

        # Step 2: Restore verified entries
        restored: list[str] = []
        for entry in entries:
            dst = Path(entry["dest"])
            src = Path(entry["source"])
            expected_sha = entry["sha256"]

            if src.is_file() and compute_sha256(src) == expected_sha:
                # Already present and identical
                if dst.is_file():
                    dst.unlink()
                restored.append(str(src))
                continue

            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))

            restored_sha = compute_sha256(src)
            if restored_sha != expected_sha:
                raise ValueError(
                    f"Restored file {src} hash mismatch: {restored_sha} != {expected_sha}"
                )
            restored.append(str(src))

        # Remove cycle dir after 100% verified restoration
        shutil.rmtree(cycle_dir, ignore_errors=True)

        return {
            "cycle_id": cycle_id,
            "status": "RESTORED",
            "restored_count": len(restored),
            "restored_files": restored,
        }
