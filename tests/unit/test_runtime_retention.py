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


def test_interrupted_cycle_at_physical_move_boundary_safely_rolls_back_without_data_loss(mock_runtime_dir: Path):
    """Issue #40: Real crash window after physical move before moved=True persistence must not lose file on rollback."""
    import shutil
    storage = mock_runtime_dir.parent / "archive_storage_interrupted"
    cycle = ReversibleArchiveCycle(mock_runtime_dir, storage)

    cache_file = mock_runtime_dir / "temp_scratch.cache"
    orig_sha = compute_sha256(cache_file)
    candidates = [c for c in classify_runtime_directory(mock_runtime_dir) if c.path.name == "temp_scratch.cache"]

    original_move = shutil.move
    def crash_after_move(src, dst):
        original_move(src, dst)
        raise RuntimeError("injected crash after physical move before journal persistence")

    shutil.move = crash_after_move
    try:
        cycle.archive_candidates("crash_cycle", candidates)
    except RuntimeError:
        pass
    finally:
        shutil.move = original_move

    archived_file = storage / "crash_cycle" / "temp_scratch.cache"
    assert not cache_file.exists(), "Source file should have been moved before crash"
    assert archived_file.is_file(), "Archived file should be present in archive directory"

    # Rollback must reconcile and restore the physical file despite moved=False in journal
    rollback_res = cycle.rollback_interrupted_cycle("crash_cycle")
    assert rollback_res["status"] == "ROLLED_BACK"
    assert str(cache_file) in rollback_res["restored_files"]
    assert cache_file.is_file(), "CRITICAL DATA LOSS: Source file was not restored!"
    assert compute_sha256(cache_file) == orig_sha, "Restored file hash mismatch!"
    assert not (storage / "crash_cycle").exists(), "Archive directory not cleaned up after complete rollback"


def test_restoration_refuses_conflict_with_newer_resumed_source_work(mock_runtime_dir: Path):
    """Issue #40: Restoration must fail closed with FileExistsError if source file exists with differing content."""
    storage = mock_runtime_dir.parent / "archive_storage_conflict"
    cycle = ReversibleArchiveCycle(mock_runtime_dir, storage)

    cache_file = mock_runtime_dir / "temp_scratch.cache"
    cache_file.write_bytes(b"old cached state")
    candidates = [c for c in classify_runtime_directory(mock_runtime_dir) if c.path.name == "temp_scratch.cache"]

    cycle.archive_candidates("cycle_conflict", candidates)
    assert not cache_file.exists()

    # Operator or background task resumes and creates newer work at source
    newer_bytes = b"newer resumed work that must never be clobbered"
    cache_file.write_bytes(newer_bytes)

    with pytest.raises(FileExistsError, match="Restoration conflict"):
        cycle.restore_archive("cycle_conflict")

    # Source file must be completely untouched
    assert cache_file.read_bytes() == newer_bytes
    # Archive directory and files must remain intact for operator recovery
    assert (storage / "cycle_conflict" / "temp_scratch.cache").is_file()


def test_plans_and_resumable_state_are_preserved_not_classified_as_rebuildable_cache(mock_runtime_dir: Path):
    """Issue #40: Non-cache files (plans, code, json, md) are preserved by default as UNKNOWN_PRESERVE."""
    scratch_dir = mock_runtime_dir / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    plan_file = scratch_dir / "current_plan.json"
    plan_file.write_text('{"resumable": true}', encoding="utf-8")

    notes_file = scratch_dir / "scratch_notes.md"
    notes_file.write_text("# Scratch plan notes", encoding="utf-8")

    from youtube_automation.production.retention import classify_entry
    plan_candidate = classify_entry(plan_file, mock_runtime_dir)
    notes_candidate = classify_entry(notes_file, mock_runtime_dir)

    assert plan_candidate.category == RetentionCategory.UNKNOWN_PRESERVE
    assert notes_candidate.category == RetentionCategory.UNKNOWN_PRESERVE


def test_reclassification_strictly_excludes_archive_storage_directory(mock_runtime_dir: Path):
    """Issue #40: Files inside .archive or archive_storage must be excluded from reclassification."""
    archive_dir = mock_runtime_dir / ".archive" / "cycle_01"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "archived_cache.cache").write_bytes(b"archived data")

    candidates = classify_runtime_directory(mock_runtime_dir)
    candidate_paths = [str(c.path) for c in candidates]

    for p in candidate_paths:
        assert ".archive" not in p, f"Archived file was reclassified: {p}"


def test_incomplete_cycle_reuse_refused_preserving_prior_bytes(tmp_path: Path):
    """F3: Reusing an in-progress cycle ID without completion receipt refuses conflicting reuse and preserves old bytes."""
    import shutil as test_shutil
    runtime = tmp_path / "runtime"
    archive = tmp_path / "archive"
    scratch = runtime / "temp_scratch"
    scratch.mkdir(parents=True)
    f = scratch / "a.cache"
    f.write_bytes(b"first evidence")

    manager = ReversibleArchiveCycle(runtime, archive)
    candidates = classify_runtime_directory(runtime)

    original_move = test_shutil.move

    def interrupt_move(*args, **kw):
        original_move(*args, **kw)
        raise RuntimeError("injected crash after physical move")

    from youtube_automation.production import retention as ret_mod
    ret_mod.shutil.move = interrupt_move
    try:
        manager.archive_candidates(cycle_id="pending", candidates=candidates)
    except RuntimeError:
        pass
    finally:
        ret_mod.shutil.move = original_move

    archived_file = archive / "pending" / "temp_scratch" / "a.cache"
    assert archived_file.exists()
    assert archived_file.read_bytes() == b"first evidence"

    # Conflicting reuse attempt with newer bytes
    f.write_bytes(b"new resumed bytes")
    new_candidates = classify_runtime_directory(runtime)
    result = manager.archive_candidates(cycle_id="pending", candidates=new_candidates)

    assert result["status"] == "REFUSED_ALREADY_EXISTS"
    # Old archived bytes must remain completely intact
    assert archived_file.read_bytes() == b"first evidence"
