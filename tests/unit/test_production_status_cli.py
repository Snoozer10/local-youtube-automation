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


def test_status_cli_maintenance_canary_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Issue #55 / #56: Maintenance lock containing sensitive canary tokens or prose must be projected safely without leaks."""
    db_dir = tmp_path / "privacy"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "adaptive.sqlite3"
    _create_rollback_fixture(db_path, populate=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    canary = "Bearer sk-status-canary-123 Our acquisition target is Orion"
    (db_dir / "MAINTENANCE.lock").write_text(canary, encoding="utf-8")

    from youtube_automation.production import ledger
    monkeypatch.setattr(cli, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db_path))

    cli.main(["status", "--run-dir", str(run_dir)])
    out = capsys.readouterr().out

    assert "sk-status-canary-123" not in out, "Credential canary must be sanitized from public status display"
    assert "Our acquisition target is Orion" not in out, "Private prose must be sanitized from public status display"
    assert "MaintenanceExclusionError" in out or "locked for maintenance" in out
    assert "Ledger Status: UNAVAILABLE" in out


def test_status_cli_uncommitted_exclusive_writer_reports_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Issue #55/#56 / Spec 4: Uncommitted exclusive transaction must report BUSY, avoiding dirty read."""
    import subprocess
    import sys
    import time

    from youtube_automation.production import ledger

    root = tmp_path / "dirty_read"
    root.mkdir()
    db = root / "adaptive.sqlite3"
    run_dir = root / "run"
    run_dir.mkdir()

    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA user_version=1")
    conn.execute("CREATE TABLE jobs(key TEXT PRIMARY KEY, state TEXT, attempts INTEGER, fence INTEGER, detail TEXT)")
    conn.executemany("INSERT INTO jobs VALUES(?,?,?,?,?)", [(f"job-{i:03d}", "CANCELLED", 1, 1, "X"*1024) for i in range(20)])
    conn.commit()
    conn.close()

    ready = root / "writer.ready"
    release = root / "writer.release"

    child_code = (
        'import sqlite3,sys,time;from pathlib import Path;c=sqlite3.connect(sys.argv[1],isolation_level=None);'
        'c.execute("PRAGMA cache_size=1");c.execute("PRAGMA cache_spill=ON");c.execute("BEGIN EXCLUSIVE");'
        'c.execute("UPDATE jobs SET state=\'SUCCEEDED\'");Path(sys.argv[2]).write_text("ready");'
        'deadline=time.monotonic()+10;\nwhile not Path(sys.argv[3]).exists() and time.monotonic()<deadline:time.sleep(.01)\n'
        'c.execute("ROLLBACK");c.close()'
    )

    child = subprocess.Popen([sys.executable, "-I", "-B", "-c", child_code, str(db), str(ready), str(release)])
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "Writer failed to acquire lock and update"

        monkeypatch.setattr(cli, "resource_database", ledger._unpatched_resource_database)
        monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
        monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db))

        cli.main(["status", "--run-dir", str(run_dir)])
        out = capsys.readouterr().out

        assert "Ledger Status: UNAVAILABLE (database busy)" in out
        assert "Database is locked by another process" in out
        assert "[SUCCEEDED]" not in out, "Uncommitted transaction must not be reported as succeeded"
    finally:
        release.touch()
        child.communicate(timeout=10)


def test_status_cli_default_discovery_is_strictly_non_mutating(tmp_path: Path, monkeypatch, capsys):
    """Issue #55/#56 / Spec R3: Status CLI observation of DEFAULT authority must never create .authority_enrolled.json."""
    import hashlib
    import sqlite3

    from youtube_automation.production import authority, cli, ledger

    r = tmp_path / "default-status-nonmutating"
    r.mkdir()
    (r / ".runtime").mkdir()
    (r / "run").mkdir()
    db = r / ".runtime" / "adaptive.sqlite3"

    c = sqlite3.connect(db)
    c.execute("PRAGMA user_version=1")
    c.execute("CREATE TABLE jobs(key TEXT PRIMARY KEY, state TEXT, attempts INTEGER, fence INTEGER, detail TEXT)")
    c.execute("INSERT INTO jobs VALUES(?, ?, ?, ?, ?)", ("example", "CANCELLED", 1, 1, "{}"))
    c.commit()
    c.close()

    monkeypatch.setattr(authority, "__file__", str(r / "src" / "youtube_automation" / "production" / "authority.py"))
    monkeypatch.delenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", raising=False)
    monkeypatch.setattr(cli, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)

    before_files = {p.relative_to(r).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob("*") if p.is_file()}

    cli.main(["status", "--run-dir", str(r / "run")])
    out = capsys.readouterr().out

    assert "Ledger Status: POPULATED" in out
    after_files = {p.relative_to(r).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob("*") if p.is_file()}

    assert not (r / ".authority_enrolled.json").exists()
    assert set(after_files) - set(before_files) == set()
    assert before_files[".runtime/adaptive.sqlite3"] == after_files[".runtime/adaptive.sqlite3"]


def test_status_cli_uncommitted_spill_rollback_reports_busy_not_succeeded(tmp_path: Path, monkeypatch, capsys):
    """Issue #55/#56 / Spec R4: Real external writer spilling uncommitted rows and rolling back must be detected as busy."""
    import inspect
    import sqlite3
    import subprocess
    import sys
    import time

    from youtube_automation.production import cli, ledger

    root = tmp_path / "observer-dirty-read-v3"
    root.mkdir()
    db = root / "adaptive.sqlite3"
    run_dir = root / "run"
    run_dir.mkdir()

    real_connect = sqlite3.connect
    c = real_connect(db)
    c.execute("PRAGMA journal_mode=DELETE")
    c.execute("PRAGMA user_version=1")
    c.execute("CREATE TABLE jobs(key TEXT PRIMARY KEY, state TEXT, attempts INTEGER, fence INTEGER, detail TEXT)")
    c.executemany("INSERT INTO jobs VALUES(?,?,?,?,?)", [(f"job-{i:03d}", "CANCELLED", 1, 1, "X"*4096) for i in range(200)])
    c.commit()
    c.close()

    ready = root / "writer.ready"
    release = root / "writer.release"
    child = None

    child_code = (
        'import sqlite3,sys,time;from pathlib import Path;'
        'c=sqlite3.connect(sys.argv[1],isolation_level=None);'
        'c.execute("PRAGMA cache_size=1");c.execute("PRAGMA cache_spill=ON");c.execute("BEGIN EXCLUSIVE");'
        'c.execute("UPDATE jobs SET state=?,detail=?",("SUCCEEDED","Y"*4096));'
        'Path(sys.argv[2]).write_text("ready");'
        'deadline=time.monotonic()+10;\n'
        'while not Path(sys.argv[3]).exists() and time.monotonic()<deadline: time.sleep(.01)\n'
        'c.execute("ROLLBACK");c.close()'
    )

    class AuditCursor(sqlite3.Cursor):
        def execute(self, sql, *args):
            self.audit_sql = sql
            return super().execute(sql, *args)

        def fetchall(self):
            rows = super().fetchall()
            if getattr(self, "audit_sql", "").startswith("SELECT key, state"):
                release.touch()
                if child is not None:
                    child.wait(timeout=10)
            return rows

    class AuditConnection(sqlite3.Connection):
        def cursor(self, *args, **kwargs):
            kwargs["factory"] = AuditCursor
            return super().cursor(*args, **kwargs)

    def intercept_connect(*args, **kwargs):
        nonlocal child
        if child is None and inspect.currentframe().f_back.f_code.co_name == "observe_ledger" and str(args[0]).startswith(db.as_uri()):
            child = subprocess.Popen([sys.executable, "-I", "-B", "-c", child_code, str(db), str(ready), str(release)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.monotonic() + 5
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "Writer did not become ready"
        if inspect.currentframe().f_back.f_code.co_name == "observe_ledger":
            kwargs["factory"] = AuditConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", intercept_connect)
    monkeypatch.setattr(cli, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db))

    try:
        cli.main(["status", "--run-dir", str(run_dir)])
        out = capsys.readouterr().out
        assert "Ledger Status: UNAVAILABLE (database busy)" in out
        assert "[SUCCEEDED]" not in out
    finally:
        release.touch()
        if child is not None:
            child.communicate(timeout=10)
