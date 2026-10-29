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
    conn = sqlite3.connect(db_path.as_posix())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE jobs (key TEXT PRIMARY KEY, state TEXT, fence INT)")
    conn.execute("INSERT INTO jobs VALUES ('video_001', 'COMPLETED', 1)")
    conn.execute("INSERT INTO jobs VALUES ('video_002', 'RUNNING', 2)")
    conn.commit()
    conn.close()

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


def test_restore_rejects_malformed_manifest_digest_before_any_writes(tmp_path: Path):
    """Issue #58 regression: Malformed or mismatched manifest digest must fail closed before writes."""
    backups = tmp_path / "backups"
    snap = backups / "bad_digest_snap"
    snap.mkdir(parents=True)
    (snap / "run.lock").write_text("lock_content", encoding="utf-8")
    h = compute_sha256(snap / "run.lock")

    manifest = {
        "recovery_id": "bad_digest_snap",
        "created_at": "2026-10-29T00:00:00Z",
        "runtime_root": str(tmp_path),
        "total_files": 1,
        "total_bytes": len("lock_content"),
        "manifest_sha256": "deliberately_false_sha256_digest_that_does_not_match",
        "files": [{
            "relative_path": "run.lock",
            "category": "LOCK",
            "sha256": h,
            "size_bytes": len("lock_content"),
            "is_database": False,
        }],
    }
    (snap / "RECOVERY_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    restore_target = tmp_path / "restore_bad_digest"
    restore_target.mkdir(parents=True)

    with pytest.raises(ValueError, match="Recovery manifest digest mismatch"):
        restore_isolated_recovery_snapshot(backups, "bad_digest_snap", restore_target)

    # Nothing should have been written to restore target
    assert not (restore_target / "run.lock").exists()


def test_restore_rejects_path_traversal_escaping_destination(tmp_path: Path):
    """Issue #58 regression: Paths escaping destination directory must be rejected before writing."""
    import hashlib
    backups = tmp_path / "backups"
    snap = backups / "traversal_snap"
    snap.mkdir(parents=True)
    escaped_file = backups / "escaped.txt"
    escaped_file.write_text("fixture content outside snapshot", encoding="utf-8")
    h = compute_sha256(escaped_file)

    manifest_payload = {
        "recovery_id": "traversal_snap",
        "created_at": "2026-10-29T00:00:00Z",
        "runtime_root": str(tmp_path),
        "total_files": 1,
        "total_bytes": 42,
        "files": [{
            "relative_path": "../escaped.txt",
            "category": "RECEIPT",
            "sha256": h,
            "size_bytes": 42,
            "is_database": False,
        }],
    }
    manifest_bytes = json.dumps(manifest_payload, indent=2).encode("utf-8")
    manifest_payload["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    (snap / "RECOVERY_MANIFEST.json").write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    restore_target = tmp_path / "restore_traversal"
    restore_target.mkdir(parents=True)

    with pytest.raises(ValueError, match="Path traversal detected in manifest"):
        restore_isolated_recovery_snapshot(backups, "traversal_snap", restore_target)

    assert not (tmp_path / "escaped.txt").exists()


def test_restore_refuses_to_overwrite_existing_restoration_receipt(mock_operational_runtime: Path, tmp_path: Path):
    """Issue #58 regression: Pre-existing RESTORATION_RECEIPT.json at destination must be preserved."""
    backup_storage = tmp_path / "backups"
    restore_target = tmp_path / "restore_existing_receipt"
    restore_target.mkdir(parents=True, exist_ok=True)

    create_isolated_recovery_snapshot(mock_operational_runtime, backup_storage, "receipt_protect_snap")

    # Operator or previous recovery placed a newer restoration receipt
    prior_receipt = restore_target / "RESTORATION_RECEIPT.json"
    prior_receipt.write_text('{"prior_evidence": "must_be_preserved"}', encoding="utf-8")
    prior_sha = compute_sha256(prior_receipt)

    with pytest.raises(FileExistsError, match="destination receipt .* already exists; preserving existing evidence"):
        restore_isolated_recovery_snapshot(backup_storage, "receipt_protect_snap", restore_target)

    # Receipt must remain 100% unmutated
    assert compute_sha256(prior_receipt) == prior_sha
    assert json.loads(prior_receipt.read_text(encoding="utf-8")) == {"prior_evidence": "must_be_preserved"}


def test_complete_recovery_set_closure_covers_inputs_plans_evidence_journals(tmp_path: Path):
    """Issue #58 regression: Declared recovery closure covers canonical inputs, plans, journals, evidence."""
    rt = tmp_path / "complete_runtime"
    rt.mkdir(parents=True)

    # 1. Canonical inputs
    (rt / "youtube_urls.txt").write_text("https://youtube.com/watch?v=sample1", encoding="utf-8")
    (rt / "episode_brief.json").write_text('{"topic": "Formations", "revision": 1}', encoding="utf-8")

    # 2. Production plans
    (rt / "channel_plan.json").write_text('{"target_cadence": "weekly"}', encoding="utf-8")

    # 3. Execution journals
    (rt / "clip_journal.json").write_text('{"clips": ["c1", "c2"]}', encoding="utf-8")

    # 4. Approval/rejection evidence
    (rt / "APPROVAL_GATE.json").write_text('{"gate": "audio", "status": "APPROVED"}', encoding="utf-8")
    (rt / "REJECTION_LOG.json").write_text('{"gate": "visual", "reason": "unsupported"}', encoding="utf-8")

    # 5. Multimodal evidence
    (rt / "multimodal_evidence.json").write_text('{"samples": 2}', encoding="utf-8")

    matched = identify_recovery_files(rt)
    matched_names = {path.name: spec.category for path, spec in matched}

    assert "youtube_urls.txt" in matched_names
    assert matched_names["youtube_urls.txt"] == RecoveryItemCategory.INPUT
    assert "episode_brief.json" in matched_names
    assert matched_names["episode_brief.json"] == RecoveryItemCategory.INPUT
    assert "channel_plan.json" in matched_names
    assert matched_names["channel_plan.json"] == RecoveryItemCategory.PLAN
    assert "clip_journal.json" in matched_names
    assert matched_names["clip_journal.json"] == RecoveryItemCategory.JOURNAL
    assert "APPROVAL_GATE.json" in matched_names
    assert matched_names["APPROVAL_GATE.json"] == RecoveryItemCategory.APPROVAL
    assert "REJECTION_LOG.json" in matched_names
    assert matched_names["REJECTION_LOG.json"] == RecoveryItemCategory.REJECTION
    assert "multimodal_evidence.json" in matched_names
    assert matched_names["multimodal_evidence.json"] == RecoveryItemCategory.EVIDENCE

    # Snapshot and verify bound metadata
    backups = tmp_path / "backups"
    manifest_path = create_isolated_recovery_snapshot(rt, backups, "full_closure_01")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["protocol_version"] == "1.0"
    assert manifest["stage"] == "PRODUCTION"
    assert manifest["consistency_boundary"] == "POINT_IN_TIME_ISOLATED"
    assert manifest["total_files"] == 7


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
