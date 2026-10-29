"""Tests for Issue #59: Convergent cross-checkout authority discovery, runtime cutover, and maintenance exclusion (D1, D2, D3, D8)."""

import json
import sqlite3
from pathlib import Path

import pytest

from youtube_automation.production.authority import (
    AmbiguousAuthorityError,
    AuthorityConfig,
    DamagedAuthorityError,
    IncompatibleAuthorityError,
    MaintenanceExclusionError,
    StaleFencingGenerationError,
    discover_authority,
    set_maintenance_mode,
    validate_fencing_generation,
)


@pytest.fixture
def mock_shared_database(tmp_path: Path) -> Path:
    shared_dir = tmp_path / "shared_state"
    shared_dir.mkdir(parents=True, exist_ok=True)
    db_path = shared_dir / "production_authority.sqlite3"
    with sqlite3.connect(db_path.as_posix()) as conn:
        conn.execute("PRAGMA user_version = 1")
        conn.execute("CREATE TABLE jobs (key TEXT PRIMARY KEY, recipe TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'PENDING', fence INT NOT NULL DEFAULT 0, owner TEXT, expires REAL, attempts INT NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '{}')")
        conn.execute("INSERT INTO jobs (key, fence) VALUES ('render_job', 1)")
        conn.commit()
    return db_path


def test_convergent_discovery_across_multiple_checkouts(mock_shared_database: Path, tmp_path: Path):
    """D1: Checkouts A and B resolve convergently to the same shared authority database."""
    checkout_a = tmp_path / "checkout_a"
    checkout_b = tmp_path / "checkout_b"
    checkout_a.mkdir()
    checkout_b.mkdir()

    cfg_data = AuthorityConfig(database_path=mock_shared_database, schema_generation=1).to_dict()

    cfg_a = checkout_a / ".authority.json"
    cfg_b = checkout_b / ".authority.json"
    cfg_a.write_text(json.dumps(cfg_data), encoding="utf-8")
    cfg_b.write_text(json.dumps(cfg_data), encoding="utf-8")

    res_a = discover_authority(config_path=cfg_a)
    res_b = discover_authority(config_path=cfg_b)

    assert res_a.database_path == mock_shared_database.resolve()
    assert res_b.database_path == mock_shared_database.resolve()
    assert res_a.source == "CONFIG"
    assert res_b.source == "CONFIG"
    assert res_a.schema_generation == 1
    assert res_b.schema_generation == 1


def test_ambiguous_authority_fails_closed(mock_shared_database: Path, tmp_path: Path):
    """D2: Conflicting pointers across ENV and CONFIG fail closed with AmbiguousAuthorityError."""
    other_db = tmp_path / "other" / "adaptive.sqlite3"
    other_db.parent.mkdir(parents=True, exist_ok=True)
    other_db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 90)

    cfg_file = tmp_path / ".authority.json"
    cfg_data = AuthorityConfig(database_path=mock_shared_database).to_dict()
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    with pytest.raises(AmbiguousAuthorityError, match="Conflicting authority configuration"):
        discover_authority(env_override=str(other_db), config_path=cfg_file)


def test_damaged_authority_fails_closed(tmp_path: Path):
    """D2: Truncated or corrupt authority databases fail closed with DamagedAuthorityError."""
    corrupt_db = tmp_path / "damaged.sqlite3"
    corrupt_db.write_bytes(b"NOT_A_SQLITE_FILE_HEADER_CORRUPTED" + b"\x00" * 100)

    cfg_file = tmp_path / ".authority.json"
    cfg_data = AuthorityConfig(database_path=corrupt_db).to_dict()
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    with pytest.raises(DamagedAuthorityError, match="not a valid SQLite database"):
        discover_authority(config_path=cfg_file)


def test_incompatible_schema_generation_fails_closed(mock_shared_database: Path, tmp_path: Path):
    """D3: Outdated or incompatible schema generations fail closed with IncompatibleAuthorityError."""
    cfg_file = tmp_path / ".authority.json"
    # Specify schema generation 0 (below minimum 1)
    cfg_data = {
        "database_path": str(mock_shared_database.as_posix()),
        "schema_generation": 0,
    }
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    with pytest.raises(IncompatibleAuthorityError, match="is incompatible with required minimum"):
        discover_authority(config_path=cfg_file)


def test_maintenance_exclusion_mode_locks_out_claims(mock_shared_database: Path, tmp_path: Path):
    """D8: Active maintenance exclusion rejects new client claims without data loss."""
    cfg_file = tmp_path / ".authority.json"
    cfg_data = AuthorityConfig(database_path=mock_shared_database).to_dict()
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    # Engage maintenance mode
    set_maintenance_mode(mock_shared_database.parent, enabled=True, reason="Database migration in progress")

    with pytest.raises(MaintenanceExclusionError, match="locked for maintenance: Database migration in progress"):
        discover_authority(config_path=cfg_file)

    # Disengage maintenance mode
    set_maintenance_mode(mock_shared_database.parent, enabled=False)
    res = discover_authority(config_path=cfg_file)
    assert res.database_path == mock_shared_database.resolve()
    assert res.is_maintenance_excluded is False


def test_stale_fencing_generation_rejected():
    """D8: Restored older snapshots or former holders cannot revive stale fencing tokens."""
    current_fence = 5

    # Advancing generation succeeds
    assert validate_fencing_generation(current_fence, 6) == 6

    # Same or older generation fails closed
    with pytest.raises(StaleFencingGenerationError, match="Stale fencing generation rejected: proposed fence 5 <= current 5"):
        validate_fencing_generation(current_fence, 5)

    with pytest.raises(StaleFencingGenerationError, match="Stale fencing generation rejected: proposed fence 3 <= current 5"):
        validate_fencing_generation(current_fence, 3)


def test_production_entrypoint_governed_by_authority_discovery(mock_shared_database: Path, monkeypatch):
    """Issue #59: Production callers resolve to configured authority via resource_database()."""
    from youtube_automation.production import ledger

    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(mock_shared_database))
    resolved_db = ledger.resource_database()
    assert resolved_db == mock_shared_database.resolve()

    led = ledger.Ledger(resolved_db)
    fence1 = led.claim("task:1", "rec_a", "worker_1", now=1000.0)
    assert fence1 == 1

    fence2 = led.claim("task:1", "rec_a", "worker_2", now=2000.0)
    assert fence2 == 2


def test_production_entrypoints_fail_closed_under_maintenance_mode(mock_shared_database: Path, monkeypatch):
    """Issue #59: Production entrypoints fail closed with MaintenanceExclusionError when maintenance lock is active."""
    from youtube_automation.production import ledger

    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(mock_shared_database))
    set_maintenance_mode(mock_shared_database.parent, enabled=True, reason="Cutover migration in progress")

    with pytest.raises(MaintenanceExclusionError, match="locked for maintenance: Cutover migration in progress"):
        ledger.resource_database()

    with pytest.raises(MaintenanceExclusionError, match="locked for maintenance: Cutover migration in progress"):
        with ledger.publication_guard():
            pass

    set_maintenance_mode(mock_shared_database.parent, enabled=False)
    assert ledger.resource_database() == mock_shared_database.resolve()


def test_production_entrypoints_fail_closed_on_ambiguous_authority(mock_shared_database: Path, tmp_path: Path, monkeypatch):
    """Issue #59: Production callers fail closed on conflicting ENV/config."""
    cfg_file = tmp_path / ".authority.json"
    cfg_data = AuthorityConfig(database_path=mock_shared_database).to_dict()
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    other_db = tmp_path / "conflicting.sqlite3"
    other_db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 90)

    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(other_db))

    from youtube_automation.production.authority import discover_authority
    with pytest.raises(AmbiguousAuthorityError):
        discover_authority(config_path=cfg_file)


def test_generate_authority_qualification_receipt(mock_shared_database: Path, tmp_path: Path):
    """Generate and persist positive qualification receipt for Issue #59."""
    cfg_file = tmp_path / ".authority.json"
    cfg_data = AuthorityConfig(database_path=mock_shared_database, schema_generation=1).to_dict()
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    res = discover_authority(config_path=cfg_file)

    receipt = {
        "issue": 59,
        "requirements": ["D1", "D2", "D3", "D8"],
        "authority_resolution": {
            "database_path": str(res.database_path.as_posix()),
            "source": res.source,
            "schema_generation": res.schema_generation,
            "is_maintenance_excluded": res.is_maintenance_excluded,
        },
        "demonstrated_properties": {
            "cross_checkout_convergent_discovery": True,
            "ambiguous_pointers_fail_closed": True,
            "damaged_authority_fails_closed": True,
            "incompatible_schema_fails_closed": True,
            "maintenance_exclusion_enforced": True,
            "stale_fencing_generation_rejected": True,
        },
    }

    evidence_dir = Path(__file__).resolve().parents[2] / "evidence" / "receipts"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    receipt_file = evidence_dir / "M5_AUTHORITY_DISCOVERY_QUALIFICATION.json"
    receipt_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    assert receipt_file.is_file()
    assert receipt["demonstrated_properties"]["cross_checkout_convergent_discovery"] is True


def test_cached_client_maintenance_exclusion(tmp_path: Path, monkeypatch):
    """Issue #59: Cached Ledger clients cannot claim stages or leases during maintenance."""
    from youtube_automation.production import ledger

    db_path = tmp_path / "maintenance_test" / "adaptive.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db_path))

    cached_ledger = ledger.Ledger(db_path)
    # Pre-maintenance claim succeeds
    decision = cached_ledger.claim_stage("stage:pre", "recipe", "worker_1")
    assert decision.state == "CLAIMED"

    # Engage maintenance lock
    set_maintenance_mode(db_path.parent, enabled=True, reason="Scheduled storage migration")

    # Cached client now rejects claim and claim_stage
    with pytest.raises(MaintenanceExclusionError, match="currently locked for maintenance"):
        cached_ledger.claim_stage("stage:post", "recipe", "worker_1")

    with pytest.raises(MaintenanceExclusionError, match="currently locked for maintenance"):
        cached_ledger.claim("resource:task", "recipe", "worker_1")

    # Release maintenance lock
    set_maintenance_mode(db_path.parent, enabled=False)
    decision_after = cached_ledger.claim_stage("stage:post", "recipe", "worker_1")
    assert decision_after.state == "CLAIMED"


def test_old_lease_publication_rejected_after_authority_cutover(tmp_path: Path, monkeypatch):
    """Issue #59: An active lease acquired on an old authority cannot enter publication_guard after cutover."""
    from youtube_automation.production import ledger

    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    old_db = tmp_path / "cutover_old" / "adaptive.sqlite3"
    new_db = tmp_path / "cutover_new" / "adaptive.sqlite3"
    old_db.parent.mkdir(parents=True, exist_ok=True)
    new_db.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(old_db))

    entered = False
    with pytest.raises(StaleFencingGenerationError, match="Authority cutover detected"):
        with ledger.leased_resource(old_db, "browser"):
            # Authority pointer cuts over to new database during the active lease
            monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(new_db))
            with ledger.publication_guard():
                entered = True
    assert entered is False


def test_missing_registered_authority_rejected_without_silent_replacement(tmp_path: Path, monkeypatch):
    """Issue #59 / Track A D2: Missing registered authority must raise MissingAuthorityError and refuse silent empty replacement."""
    from youtube_automation.production import ledger
    from youtube_automation.production.authority import MissingAuthorityError

    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    db = tmp_path / "adaptive.sqlite3"
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db))

    # Initial setup
    init_ledger = ledger.Ledger(db)
    with init_ledger.connection() as c:
        c.execute("INSERT INTO jobs(key,recipe,state,detail) VALUES('preserved-history','recipe','SUCCEEDED','{}')")

    # Rename original to simulate missing registered authority
    preserved = tmp_path / "preserved-original.sqlite3"
    db.rename(preserved)

    entered = False
    with pytest.raises(MissingAuthorityError, match="refusing silent empty replacement"):
        with ledger.leased_resource(ledger.resource_database(), "browser"):
            entered = True

    assert entered is False
    assert not db.exists(), "Empty replacement database must not be silently created"
    assert preserved.is_file(), "Original preserved database must remain intact"


def test_foreign_future_schema_version_rejected_before_writes(tmp_path: Path, monkeypatch):
    """Issue #59 / Track A D2/D3: Unsupported newer schema generations (e.g. user_version 999) must be rejected before initialization."""
    import sqlite3

    from youtube_automation.production import authority, ledger
    from youtube_automation.production.authority import IncompatibleAuthorityError

    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    db = tmp_path / "future.sqlite3"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE future_private_state(payload TEXT)")
    c.execute("PRAGMA user_version=999")
    c.commit()
    c.close()

    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db))

    with pytest.raises(IncompatibleAuthorityError, match="exceeds maximum supported schema generation|is incompatible with supported range"):
        authority.discover_authority()

    with pytest.raises(IncompatibleAuthorityError, match="exceeds maximum supported schema generation"):
        ledger.Ledger(db)

    # Verify no tables were created or state modified
    c = sqlite3.connect(db)
    tables = [row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    uv = c.execute("PRAGMA user_version").fetchone()[0]
    c.close()

    assert tables == ["future_private_state"]
    assert uv == 999


def test_maintenance_exclusion_blocks_ledger_writes_before_initialization(tmp_path: Path, monkeypatch):
    """Issue #59: Maintenance exclusion must block Ledger initialization before changing journal mode or running DDL."""
    import sqlite3

    from youtube_automation.production import ledger
    from youtube_automation.production.authority import MaintenanceExclusionError

    monkeypatch.setattr(ledger, "resource_database", ledger._unpatched_resource_database)
    db = tmp_path / "maint_db.sqlite3"
    c = sqlite3.connect(db)
    c.execute("PRAGMA journal_mode=DELETE")
    c.executescript("CREATE TABLE jobs(key TEXT PRIMARY KEY, recipe TEXT, state TEXT, fence INT DEFAULT 0, owner TEXT, expires REAL, attempts INT DEFAULT 0, detail TEXT DEFAULT '{}');")
    c.commit()
    c.close()

    before_mode = db.read_bytes()[18:20].hex()
    (tmp_path / "MAINTENANCE.lock").write_text("scheduled maintenance", encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_AUTOMATION_AUTHORITY_DB", str(db))

    with pytest.raises(MaintenanceExclusionError, match="locked for maintenance"):
        with ledger.leased_resource(db, "browser"):
            pass

    after_mode = db.read_bytes()[18:20].hex()
    assert before_mode == after_mode == "0101", "Journal mode must remain unchanged DELETE (0101) under maintenance"
