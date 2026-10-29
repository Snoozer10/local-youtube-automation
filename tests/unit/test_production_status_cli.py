"""Tests for genuinely non-mutating production status CLI (Issue #56)."""

import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest

from youtube_automation.production import cli


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_snapshot(directory: Path) -> dict[str, Any]:
    if not directory.exists():
        return {}
    snapshot: dict[str, Any] = {}
    for entry in directory.iterdir():
        if entry.is_file():
            snapshot[entry.name] = (entry.stat().st_size, entry.stat().st_mtime_ns)
        elif entry.is_dir():
            snapshot[entry.name] = _dir_snapshot(entry)
    return snapshot


def _create_rollback_fixture(db_path: Path, populate: bool = True) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute(
            """
            CREATE TABLE jobs (
                key TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                fence INTEGER NOT NULL,
                detail TEXT
            );
            """
        )
        if populate:
            secret_detail = json.dumps({
                "layer": "pipeline",
                "kind": "runtime",
                "exception": "GeminiError",
                "error": "Bearer sk-secret-token-12345 should never appear in output",
                "canary": "\u202e\u2603\u2728",
            })
            ok_detail = json.dumps({
                "stage": "write",
                "fence": 10,
                "layer": "core",
                "kind": "runtime",
                "exception": "RuntimeError",
                "error": "Stage circuit is open",
            })
            conn.execute(
                "INSERT INTO jobs (key, state, attempts, fence, detail) VALUES (?, ?, ?, ?, ?)",
                ("stage:write", "SUCCEEDED", 1, 10, ok_detail),
            )
            conn.execute(
                "INSERT INTO jobs (key, state, attempts, fence, detail) VALUES (?, ?, ?, ?, ?)",
                ("stage:plan", "FAILED", 2, 11, secret_detail),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_status_cli_populated_rollback_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "ledger" / "adaptive.sqlite3"
    _create_rollback_fixture(db_path, populate=True)

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)

    before_hash = _hash_file(db_path)
    before_dir = _dir_snapshot(db_path.parent)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    after_hash = _hash_file(db_path)
    after_dir = _dir_snapshot(db_path.parent)

    assert after_hash == before_hash, "Status execution mutated database file contents"
    assert after_dir == before_dir, "Status execution created or removed directory sidecars"

    assert "Ledger Status: POPULATED (2 jobs recorded)" in out
    assert "[SUCCEEDED] stage=stage:write attempts=1" in out
    assert "[FAILED] stage=stage:plan attempts=2" in out
    assert "sk-secret-token" not in out, "Sensitive credentials leaked into stdout"
    assert "\u2603" not in out, "Unicode canary leaked into stdout"
    assert "[pipeline/runtime] GeminiError" in out, "Safe summary did not project correctly"


def test_status_cli_compatible_empty_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "ledger" / "empty.sqlite3"
    _create_rollback_fixture(db_path, populate=False)

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)

    before_hash = _hash_file(db_path)
    before_dir = _dir_snapshot(db_path.parent)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert _hash_file(db_path) == before_hash
    assert _dir_snapshot(db_path.parent) == before_dir

    assert "Ledger Status: EMPTY" in out
    assert "No production jobs recorded in compatible ledger." in out


def test_status_cli_absent_database_and_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    absent_db = tmp_path / "nonexistent_dir" / "absent.sqlite3"

    monkeypatch.setattr(cli, "resource_database", lambda: absent_db)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert not absent_db.parent.exists(), "Status execution created absent parent directory"
    assert not absent_db.exists(), "Status execution created absent database file"

    assert "Ledger Status: UNAVAILABLE (database file does not exist)" in out
    assert "Database file is absent" in out
    assert "Next action:" in out


def test_status_cli_damaged_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "corrupt.sqlite3"
    db_path.write_bytes(b"This is not a SQLite database header at all.")

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)

    before_hash = _hash_file(db_path)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert _hash_file(db_path) == before_hash
    assert "Ledger Status: UNAVAILABLE (corrupted or unreadable database)" in out
    assert "Next action:" in out


def test_status_cli_unsupported_wal_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "wal_ledger.sqlite3"

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE jobs (key TEXT PRIMARY KEY, state TEXT);")
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)

    before_hash = _hash_file(db_path)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert _hash_file(db_path) == before_hash
    assert "Ledger Status: UNAVAILABLE (unsupported WAL layout)" in out
    assert "pre-access refusal" in out.lower() or "wal" in out.lower()
    assert "Next action:" in out


def test_status_cli_foreign_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "foreign.sqlite3"

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("CREATE TABLE users (id INT, name TEXT);")
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)

    before_hash = _hash_file(db_path)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert _hash_file(db_path) == before_hash
    assert "Ledger Status: UNAVAILABLE (foreign or incompatible schema)" in out
    assert "jobs" in out


def test_status_cli_busy_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "busy.sqlite3"
    _create_rollback_fixture(db_path, populate=True)

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)

    # Hold an exclusive lock
    locker = sqlite3.connect(str(db_path), timeout=0.1)
    try:
        locker.execute("BEGIN EXCLUSIVE;")

        cli.main(["status", "--run-dir", str(run_dir)])
        out = capsys.readouterr().out

        assert "Ledger Status: UNAVAILABLE (database busy)" in out
    finally:
        locker.close()


def test_status_cli_read_only_os_permission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "readonly_os.sqlite3"
    _create_rollback_fixture(db_path, populate=True)

    # Set OS file read-only permission
    os.chmod(db_path, stat.S_IREAD)
    try:
        monkeypatch.setattr(cli, "resource_database", lambda: db_path)
        cli.main(["status", "--run-dir", str(run_dir)])
        out = capsys.readouterr().out

        assert "Ledger Status: POPULATED (2 jobs recorded)" in out
        assert "[SUCCEEDED]" in out
    finally:
        os.chmod(db_path, stat.S_IREAD | stat.S_IWRITE)


def test_status_cli_truncation_indication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "many_jobs.sqlite3"
    _create_rollback_fixture(db_path, populate=False)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=DELETE;")
        for i in range(60):
            conn.execute(
                "INSERT INTO jobs (key, state, attempts, fence, detail) VALUES (?, ?, ?, ?, ?)",
                (f"job_{i:03d}", "PENDING", 0, 1, ""),
            )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)
    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert "Ledger Status: POPULATED (60 jobs recorded)" in out
    assert "[truncated: 50 of 60 jobs shown; partial view]" in out


def test_status_cli_filename_with_hash_metacharacter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Issue #55 / #56: Database path with URI metacharacters (#, spaces) must not create sibling files or fail schema."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "ledger#private %20.sqlite3"
    _create_rollback_fixture(db_path, populate=True)

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)

    before_hash = _hash_file(db_path)
    before_dir = _dir_snapshot(db_path.parent)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    after_hash = _hash_file(db_path)
    after_dir = _dir_snapshot(db_path.parent)

    assert after_hash == before_hash
    assert after_dir == before_dir
    assert not (tmp_path / "ledger").exists(), "Created unintended truncated sibling file!"
    assert "Ledger Status: POPULATED (2 jobs recorded)" in out


def test_status_cli_damaged_btree_valid_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Issue #55 / #56: Damaged btree with valid SQLite header safely returns DAMAGED without unhandled DatabaseError."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "damaged_btree.sqlite3"
    _create_rollback_fixture(db_path, populate=True)

    # Corrupt page-1 btree
    raw = bytearray(db_path.read_bytes())
    raw[100] = 0
    db_path.write_bytes(raw)

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)
    before_hash = _hash_file(db_path)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert _hash_file(db_path) == before_hash
    assert "Ledger Status: UNAVAILABLE (corrupted or unreadable database)" in out


def test_status_cli_incompatible_columns_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Issue #55 / #56: Missing required columns in jobs table returns UNSUPPORTED_SCHEMA, not DAMAGED."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "incompatible_cols.sqlite3"

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("CREATE TABLE jobs (key TEXT PRIMARY KEY, state TEXT);")
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(cli, "resource_database", lambda: db_path)
    before_hash = _hash_file(db_path)

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert _hash_file(db_path) == before_hash
    assert "Ledger Status: UNAVAILABLE (foreign or incompatible schema)" in out
    assert "missing required columns" in out


def test_status_cli_wal_missing_shm_unmocked_authority_discovery_non_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Issue #55 / #56: Exercise public status CLI with unmocked authority discovery on WAL without SHM.
    Verifies that neither authority discovery nor observation creates or mutates sidecars."""
    import gc
    import subprocess
    import sys

    wal_dir = tmp_path / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    db_path = wal_dir / "adaptive.sqlite3"
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    child = (
        'import sqlite3,sys,os; '
        'c=sqlite3.connect(sys.argv[1]); '
        'c.execute("PRAGMA journal_mode=WAL"); '
        'c.execute("CREATE TABLE jobs(key TEXT PRIMARY KEY,state TEXT,attempts INTEGER,fence INTEGER,detail TEXT)"); '
        'c.commit(); '
        'c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); '
        'c.execute("INSERT INTO jobs VALUES(?,?,?,?,?)",("kept","SUCCEEDED",1,1,"{}")); '
        'c.commit(); '
        'os._exit(0)'
    )
    res = subprocess.run([sys.executable, "-I", "-B", "-c", child, str(db_path)], capture_output=True)
    assert res.returncode == 0, res.stderr

    # Remove the SHM file so it is absent
    shm_path = db_path.with_name(f"{db_path.name}-shm")
    assert shm_path.is_file()
    shm_path.unlink()

    from youtube_automation.production import ledger
    monkeypatch.setattr(cli, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db_path))

    before = _dir_snapshot(wal_dir)
    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out
    gc.collect()
    after = _dir_snapshot(wal_dir)

    assert before == after, f"Status execution created or modified files: {set(after) ^ set(before)}"
    assert not shm_path.exists(), "Status execution created unintended .sqlite3-shm file"
    assert "Ledger Status: UNAVAILABLE (unsupported WAL layout)" in out


def test_status_cli_damaged_database_unmocked_authority_discovery_graceful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Issue #55 / #56: Exercise public status CLI on damaged file through unmocked authority resolution.
    Verifies graceful UNAVAILABLE output without unhandled DamagedAuthorityError crash."""
    damaged_dir = tmp_path / "damaged"
    damaged_dir.mkdir(parents=True, exist_ok=True)
    db_path = damaged_dir / "damaged.sqlite3"
    db_path.write_bytes(b"not a database")
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    from youtube_automation.production import ledger
    monkeypatch.setattr(cli, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db_path))

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert "Ledger Status: UNAVAILABLE (corrupted or unreadable database)" in out
    assert "Authority resolution failure" in out
