"""Tests for Issue #40: Runtime retention classification and reversible archiving."""

import json
from pathlib import Path

import pytest

from youtube_automation.production.cli import main as cli_main
from youtube_automation.production.retention import (
    RetentionCategory,
    ReversibleArchiveCycle,
    classify_runtime_directory,
    compute_sha256,
    dry_run_retention,
)


@pytest.fixture
def mock_runtime_dir(tmp_path: Path) -> Path:
    rt = tmp_path / "runtime"
    rt.mkdir(parents=True, exist_ok=True)

    # Active state
    (rt / "adaptive.sqlite3").write_bytes(b"SQLite format 3\x00active db bytes")
    (rt / "adaptive.sqlite3-wal").write_bytes(b"wal journal sidecar bytes")
    (rt / "adaptive.sqlite3-shm").write_bytes(b"shm index sidecar bytes")
    (rt / "run.lock").write_text("process_lock", encoding="utf-8")

    # Immutable evidence
    (rt / "SPEC23_CLOSEOUT.json").write_text('{"status": "PASSED"}', encoding="utf-8")
    (rt / "AUDIT_RECEIPT.json").write_text('{"verified": true}', encoding="utf-8")
    (rt / "rejection_log.txt").write_text("Rejection note", encoding="utf-8")

    # Rebuildable cache
    (rt / "intermediate_frames.cache").write_bytes(b"cached frame bytes 12345")
    (rt / "temp_scratch.cache").write_bytes(b"cached temp bytes 67890")

    # Unknown preserve
    (rt / "unrecognized_weights.bin").write_bytes(b"model weights mystery")
    (rt / "random_notes.md").write_text("# Notes", encoding="utf-8")

    return rt


def test_classify_runtime_directory_categorizes_correctly_and_preserves_unknowns(mock_runtime_dir: Path):
    candidates = classify_runtime_directory(mock_runtime_dir)
    by_name = {c.path.name: c for c in candidates}

    assert by_name["adaptive.sqlite3"].category == RetentionCategory.ACTIVE_STATE
    assert by_name["adaptive.sqlite3-wal"].category == RetentionCategory.ACTIVE_STATE
    assert by_name["adaptive.sqlite3-shm"].category == RetentionCategory.ACTIVE_STATE
    assert by_name["run.lock"].category == RetentionCategory.ACTIVE_STATE

    assert by_name["SPEC23_CLOSEOUT.json"].category == RetentionCategory.IMMUTABLE_EVIDENCE
    assert by_name["AUDIT_RECEIPT.json"].category == RetentionCategory.IMMUTABLE_EVIDENCE
    assert by_name["rejection_log.txt"].category == RetentionCategory.IMMUTABLE_EVIDENCE

    assert by_name["intermediate_frames.cache"].category == RetentionCategory.REBUILDABLE_CACHE
    assert by_name["temp_scratch.cache"].category == RetentionCategory.REBUILDABLE_CACHE

    assert by_name["unrecognized_weights.bin"].category == RetentionCategory.UNKNOWN_PRESERVE
    assert by_name["random_notes.md"].category == RetentionCategory.UNKNOWN_PRESERVE


def test_dry_run_makes_zero_modifications(mock_runtime_dir: Path):
    # Snapshot all file hashes before dry run
    before_hashes = {p.name: compute_sha256(p) for p in mock_runtime_dir.rglob("*") if p.is_file()}

    report = dry_run_retention(mock_runtime_dir)

    assert report["dry_run"] is True
    assert report["total_files"] == 11
    assert len(report["disposable_files"]) == 2
    assert len(report["protected_files"]) == 9

    # Verify zero files modified
    after_hashes = {p.name: compute_sha256(p) for p in mock_runtime_dir.rglob("*") if p.is_file()}
    assert before_hashes == after_hashes


def test_refusal_to_archive_active_state_or_protected_evidence(mock_runtime_dir: Path):
    candidates = classify_runtime_directory(mock_runtime_dir)
    active_candidates = [c for c in candidates if c.category == RetentionCategory.ACTIVE_STATE]

    storage = mock_runtime_dir.parent / "archive_storage"
    cycle = ReversibleArchiveCycle(mock_runtime_dir, storage)

    with pytest.raises(PermissionError, match="Refusing to archive protected or unknown files"):
        cycle.archive_candidates("illegal_cycle", active_candidates)

    # Assert active database was not moved or deleted
    assert (mock_runtime_dir / "adaptive.sqlite3").is_file()


def test_bounded_archive_and_byte_verified_restoration(mock_runtime_dir: Path):
    candidates = classify_runtime_directory(mock_runtime_dir)
    disposable = [c for c in candidates if c.category == RetentionCategory.REBUILDABLE_CACHE]
    assert len(disposable) == 2

    frame_orig_sha = compute_sha256(mock_runtime_dir / "intermediate_frames.cache")
    temp_orig_sha = compute_sha256(mock_runtime_dir / "temp_scratch.cache")

    storage = mock_runtime_dir.parent / "archive_storage"
    cycle = ReversibleArchiveCycle(mock_runtime_dir, storage)

    # 1. Archive
    result = cycle.archive_candidates("cohort_01", disposable)
    assert result["status"] == "COMPLETED"
    assert result["archived_count"] == 2

    # Files must be gone from source
    assert not (mock_runtime_dir / "intermediate_frames.cache").exists()
    assert not (mock_runtime_dir / "temp_scratch.cache").exists()

    # Archived receipt must exist
    receipt_file = storage / "cohort_01" / "ARCHIVE_RECEIPT.json"
    assert receipt_file.is_file()

    # 2. Restore
    restore_res = cycle.restore_archive("cohort_01")
    assert restore_res["status"] == "RESTORED"
    assert restore_res["restored_count"] == 2

    # Files must be restored with exact original digests
    assert (mock_runtime_dir / "intermediate_frames.cache").is_file()
    assert (mock_runtime_dir / "temp_scratch.cache").is_file()
    assert compute_sha256(mock_runtime_dir / "intermediate_frames.cache") == frame_orig_sha
    assert compute_sha256(mock_runtime_dir / "temp_scratch.cache") == temp_orig_sha

    # Cycle dir removed after clean restoration
    assert not (storage / "cohort_01").exists()


def test_interruption_detection_and_safe_rollback(mock_runtime_dir: Path):
    storage = mock_runtime_dir.parent / "archive_storage"
    storage.mkdir(parents=True, exist_ok=True)
    cycle = ReversibleArchiveCycle(mock_runtime_dir, storage)

    cache_file = mock_runtime_dir / "intermediate_frames.cache"
    orig_sha = compute_sha256(cache_file)
    cycle_dir = storage / "interrupted_cycle"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    dest_file = cycle_dir / "intermediate_frames.cache"

    # Simulate interruption: file was moved, journal exists with IN_PROGRESS status
    cache_file.rename(dest_file)

    journal_data = {
        "cycle_id": "interrupted_cycle",
        "status": "IN_PROGRESS",
        "runtime_root": str(mock_runtime_dir),
        "cycle_dir": str(cycle_dir),
        "entries": [{
            "source": str(cache_file.resolve()),
            "relative": "intermediate_frames.cache",
            "dest": str(dest_file.resolve()),
            "sha256": orig_sha,
            "size_bytes": dest_file.stat().st_size,
            "moved": True,
        }],
    }
    journal_path = storage / ".archive_journal_interrupted_cycle.json"
    journal_path.write_text(json.dumps(journal_data), encoding="utf-8")

    # Execute rollback
    rollback_res = cycle.rollback_interrupted_cycle("interrupted_cycle")
    assert rollback_res["status"] == "ROLLED_BACK"

    # File must be restored to source and byte-verified
    assert cache_file.is_file()
    assert compute_sha256(cache_file) == orig_sha
    assert not journal_path.exists()
    assert not cycle_dir.exists()


def test_cli_retention_stage(mock_runtime_dir: Path, capsys: pytest.CaptureFixture[str]):
    # 1. Dry run via CLI
    cli_main(["retention", "--dry-run", "--runtime-dir", str(mock_runtime_dir)])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["dry_run"] is True
    assert report["total_files"] == 11
    assert len(report["disposable_files"]) == 2

    # 2. Archive via CLI
    cli_main(["retention", "--archive-cohort", "cli_cycle", "--runtime-dir", str(mock_runtime_dir)])
    out = capsys.readouterr().out
    arch_res = json.loads(out)
    assert arch_res["status"] == "COMPLETED"
    assert arch_res["archived_count"] == 2
    assert not (mock_runtime_dir / "intermediate_frames.cache").exists()

    # 3. Restore via CLI
    cli_main(["retention", "--restore-cohort", "cli_cycle", "--runtime-dir", str(mock_runtime_dir)])
    out = capsys.readouterr().out
    rest_res = json.loads(out)
    assert rest_res["status"] == "RESTORED"
    assert rest_res["restored_count"] == 2
    assert (mock_runtime_dir / "intermediate_frames.cache").is_file()
