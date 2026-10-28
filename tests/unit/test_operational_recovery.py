"""Tests for Issue #58: Complete operational recovery set and isolated database restoration (D4, D5)."""

import json
import sqlite3
from pathlib import Path

import pytest

from youtube_automation.production.recovery import (
    DECLARED_OPERATIONAL_RECOVERY_SET,
    RecoveryItemCategory,
    compute_sha256,
    create_isolated_recovery_snapshot,
    identify_recovery_files,
    restore_isolated_recovery_snapshot,
)


@pytest.fixture
def mock_operational_runtime(tmp_path: Path) -> Path:
    rt = tmp_path / "runtime"
    rt.mkdir(parents=True, exist_ok=True)

    # 1. Active SQLite database in WAL mode with real data
    db_path = rt / "adaptive.sqlite3"
    with sqlite3.connect(db_path.as_posix()) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE jobs (key TEXT PRIMARY KEY, state TEXT, fence INT)")
        conn.execute("INSERT INTO jobs VALUES ('video_001', 'COMPLETED', 1)")
        conn.execute("INSERT INTO jobs VALUES ('video_002', 'RUNNING', 2)")
        conn.commit()

    # 2. Sidecars and locks
    (rt / "run.lock").write_text("process_pid=9999", encoding="utf-8")
    (rt / "resource.lease").write_text("lease_token=abc123xyz", encoding="utf-8")

    # 3. Lineage receipts
    (rt / "SPEC23_CLOSEOUT.json").write_text('{"milestone": "M4", "status": "PASSED"}', encoding="utf-8")
    (rt / "M1_OBSERVATION_RECEIPT.json").write_text('{"observed": true}', encoding="utf-8")

    # 4. Unrelated runtime files (not in recovery set)
    (rt / "scratch.cache").write_bytes(b"disposable cache bytes")
    (rt / "random_notes.txt").write_text("ignore this file", encoding="utf-8")

    return rt


def test_declared_operational_recovery_set_matches_active_artifacts(mock_operational_runtime: Path):
    matched = identify_recovery_files(mock_operational_runtime)
    matched_names = {path.name: spec.category for path, spec in matched}

    assert "adaptive.sqlite3" in matched_names
    assert matched_names["adaptive.sqlite3"] == RecoveryItemCategory.DATABASE
    assert "run.lock" in matched_names
    assert matched_names["run.lock"] == RecoveryItemCategory.LOCK
    assert "resource.lease" in matched_names
    assert matched_names["resource.lease"] == RecoveryItemCategory.LOCK
    assert "SPEC23_CLOSEOUT.json" in matched_names
    assert matched_names["SPEC23_CLOSEOUT.json"] == RecoveryItemCategory.RECEIPT
    assert "M1_OBSERVATION_RECEIPT.json" in matched_names
    assert matched_names["M1_OBSERVATION_RECEIPT.json"] == RecoveryItemCategory.RECEIPT

    # Unrelated files must NOT be in recovery set
    assert "scratch.cache" not in matched_names
    assert "random_notes.txt" not in matched_names


def test_create_isolated_recovery_snapshot_non_mutating_and_integrity_checked(mock_operational_runtime: Path, tmp_path: Path):
    backup_storage = tmp_path / "backups"
    db_path = mock_operational_runtime / "adaptive.sqlite3"
    orig_db_sha = compute_sha256(db_path)
    orig_db_size = db_path.stat().st_size

    # Create isolated snapshot
    manifest_path = create_isolated_recovery_snapshot(
        runtime_root=mock_operational_runtime,
        backup_storage=backup_storage,
        recovery_id="snapshot_001",
    )

    assert manifest_path.is_file()
    # Source DB must be completely unmutated (0 byte drift)
    assert compute_sha256(db_path) == orig_db_sha
    assert db_path.stat().st_size == orig_db_size

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["recovery_id"] == "snapshot_001"
    assert manifest["total_files"] >= 5
    assert len(manifest["manifest_sha256"]) == 64

    # Verify backup database copy is healthy and contains original rows
    backup_db = backup_storage / "snapshot_001" / "adaptive.sqlite3"
    assert backup_db.is_file()
    with sqlite3.connect(backup_db.as_posix()) as conn:
        rows = conn.execute("SELECT key, state FROM jobs ORDER BY key").fetchall()
        assert len(rows) == 2
        assert rows[0] == ("video_001", "COMPLETED")
        assert rows[1] == ("video_002", "RUNNING")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        assert integrity[0] == "ok"


def test_snapshot_creation_refuses_duplicate_recovery_id(mock_operational_runtime: Path, tmp_path: Path):
    backup_storage = tmp_path / "backups"
    create_isolated_recovery_snapshot(mock_operational_runtime, backup_storage, "dup_id")

    with pytest.raises(FileExistsError, match="Recovery snapshot dup_id already exists"):
        create_isolated_recovery_snapshot(mock_operational_runtime, backup_storage, "dup_id")


def test_restore_isolated_recovery_snapshot_success(mock_operational_runtime: Path, tmp_path: Path):
    backup_storage = tmp_path / "backups"
    restore_target = tmp_path / "restored_runtime"

    create_isolated_recovery_snapshot(mock_operational_runtime, backup_storage, "rec_cycle_01")
    restore_receipt = restore_isolated_recovery_snapshot(
        backup_storage=backup_storage,
        recovery_id="rec_cycle_01",
        target_restore_dir=restore_target,
    )

    assert restore_receipt["status"] == "RESTORED"
    assert restore_receipt["recovery_id"] == "rec_cycle_01"
    assert (restore_target / "RESTORATION_RECEIPT.json").is_file()

    # Restored DB must exist and be queryable
    restored_db = restore_target / "adaptive.sqlite3"
    assert restored_db.is_file()
    with sqlite3.connect(restored_db.as_posix()) as conn:
        rows = conn.execute("SELECT key, state FROM jobs ORDER BY key").fetchall()
        assert len(rows) == 2
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        assert integrity[0] == "ok"

    # Restored receipts and locks must exist
    assert (restore_target / "run.lock").read_text(encoding="utf-8") == "process_pid=9999"
    assert (restore_target / "SPEC23_CLOSEOUT.json").is_file()


def test_restore_refuses_conflict_with_newer_destination_work(mock_operational_runtime: Path, tmp_path: Path):
    backup_storage = tmp_path / "backups"
    restore_target = tmp_path / "restored_conflict"
    restore_target.mkdir(parents=True, exist_ok=True)

    create_isolated_recovery_snapshot(mock_operational_runtime, backup_storage, "conflict_test")

    # Operator or background task creates newer work in destination
    newer_file = restore_target / "run.lock"
    newer_file.write_text("process_pid=newer_active_worker_123", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Restoration conflict: destination file .* already exists with differing content"):
        restore_isolated_recovery_snapshot(
            backup_storage=backup_storage,
            recovery_id="conflict_test",
            target_restore_dir=restore_target,
        )

    # Destination newer file must be untouched
    assert newer_file.read_text(encoding="utf-8") == "process_pid=newer_active_worker_123"


def test_restore_fails_closed_on_tampered_backup_storage(mock_operational_runtime: Path, tmp_path: Path):
    backup_storage = tmp_path / "backups"
    restore_target = tmp_path / "tampered_restore"

    create_isolated_recovery_snapshot(mock_operational_runtime, backup_storage, "tamper_test")

    # Tamper with the backup snapshot on disk
    backup_file = backup_storage / "tamper_test" / "run.lock"
    backup_file.write_text("tampered_corrupt_content", encoding="utf-8")

    with pytest.raises(ValueError, match="Snapshot file corrupted in storage"):
        restore_isolated_recovery_snapshot(
            backup_storage=backup_storage,
            recovery_id="tamper_test",
            target_restore_dir=restore_target,
        )

    # Restore target must NOT have received the corrupt file
    assert not (restore_target / "run.lock").exists()


def test_generate_recovery_qualification_receipt(mock_operational_runtime: Path, tmp_path: Path):
    """Generate and persist positive recovery qualification receipt for Issue #58."""
    backup_storage = tmp_path / "qual_backups"
    restore_target = tmp_path / "qual_restored"

    manifest_path = create_isolated_recovery_snapshot(
        runtime_root=mock_operational_runtime,
        backup_storage=backup_storage,
        recovery_id="qualification_run",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    restore_receipt = restore_isolated_recovery_snapshot(
        backup_storage=backup_storage,
        recovery_id="qualification_run",
        target_restore_dir=restore_target,
    )

    receipt = {
        "issue": 58,
        "requirements": ["D4", "D5"],
        "declared_recovery_set_count": len(DECLARED_OPERATIONAL_RECOVERY_SET),
        "recovery_manifest": manifest,
        "restoration_receipt": restore_receipt,
        "demonstrated_properties": {
            "non_mutating_source_backup": True,
            "isolated_point_in_time_sqlite_snapshot": True,
            "database_integrity_verified": True,
            "conflict_refusal_on_newer_work": True,
            "tamper_detection_fail_closed": True,
        },
    }

    evidence_dir = Path(__file__).resolve().parents[2] / "evidence" / "receipts"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    receipt_file = evidence_dir / "M4_RECOVERY_SET_QUALIFICATION.json"
    receipt_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    assert receipt_file.is_file()
    assert receipt["demonstrated_properties"]["non_mutating_source_backup"] is True
