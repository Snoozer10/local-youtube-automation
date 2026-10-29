"""Single-host SQLite leases with fencing; stale workers cannot finish newer claims."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from youtube_automation.core import failure_record

_Lease = tuple[Any, ...]
_active_leases: ContextVar[tuple[_Lease, ...]] = ContextVar(
    "production_leases", default=()
)


_publication_scope: ContextVar[tuple[str, tuple[_Lease, ...]] | None] = ContextVar(
    "publication_scope", default=None
)


def lease_database() -> Path:
    """Use the current claim domain when nesting a new resource lease."""
    active = _active_leases.get()
    if active:
        return Path(active[0][0].path)
    return resource_database()


@dataclass(frozen=True)
class StageClaim:
    state: Literal["CLAIMED", "SUCCEEDED", "BUSY", "BLOCKED"]
    fence: int | None = None


def resource_database() -> Path:
    from youtube_automation.production.authority import discover_authority
    resolution = discover_authority()
    return resolution.database_path

_unpatched_resource_database = resource_database


@contextmanager
def publication_guard() -> Iterator[None]:
    """Serialize short publications across direct callers and every claim ledger."""
    active = _active_leases.get()
    from youtube_automation.production.authority import (
        MaintenanceExclusionError,
        StaleFencingGenerationError,
    )
    try:
        publication_path = resource_database().resolve()
        epoch_file = publication_path.parent / ".authority_epoch"
        current_epoch = ""
        if epoch_file.is_file():
            try:
                current_epoch = epoch_file.read_text(encoding="utf-8").strip()
            except OSError:
                pass
        if not current_epoch:
            receipt_file = publication_path.parent / "RESTORATION_RECEIPT.json"
            if receipt_file.is_file():
                try:
                    r_data = json.loads(receipt_file.read_text(encoding="utf-8"))
                    current_epoch = str(r_data.get("authority_epoch", ""))
                except Exception:
                    pass
        if not current_epoch:
            current_epoch = "init-epoch"
    except Exception as exc:
        for item in active:
            auth_domain = item[4] if len(item) > 4 else None
            if auth_domain is not None:
                raise StaleFencingGenerationError(
                    f"Authority cutover detected: lease was acquired under authority {auth_domain} "
                    f"but current authority has changed or is unavailable: {exc}"
                ) from exc
        raise

    # Enforce maintenance exclusion at publication boundary
    maint_lock = publication_path.parent / "MAINTENANCE.lock"
    if maint_lock.is_file():
        try:
            maint_reason = maint_lock.read_text(encoding="utf-8").strip() or "Active MAINTENANCE.lock present"
        except OSError:
            maint_reason = "Active MAINTENANCE.lock present"
        raise MaintenanceExclusionError(
            f"Authority at {publication_path} is currently locked for maintenance: {maint_reason}"
        )

    nested = _publication_scope.get()
    if nested is not None:
        if nested != (str(publication_path), active):
            raise RuntimeError("Nested publication cannot change its lease or database domain")
        yield
        return

    # Reject leases that were acquired under stale authority or before cutover
    for item in active:
        claim_ledger = item[0]
        auth_domain = item[4] if len(item) > 4 else None
        if auth_domain is not None and Path(auth_domain).resolve() != publication_path:
            raise StaleFencingGenerationError(
                f"Authority cutover detected: lease was acquired under authority {auth_domain} "
                f"but current authority has changed to {publication_path}; publication rejected"
            )
        lease_db = Path(claim_ledger.path).resolve()
        lease_epoch = item[5] if len(item) > 5 else None
        if auth_domain is not None and lease_db == Path(auth_domain).resolve() and lease_db != publication_path:
            raise StaleFencingGenerationError(
                f"Authority cutover detected: active lease database {lease_db} "
                f"does not match current authority {publication_path}; publication rejected"
            )
        if lease_epoch and current_epoch and lease_epoch != current_epoch:
            raise StaleFencingGenerationError(
                f"Stale authority epoch: lease was acquired under epoch {lease_epoch} "
                f"but current authority epoch is {current_epoch} (restoration occurred); publication rejected"
            )

    databases = {str(Path(item[0].path).resolve()) for item in active}
    if len(databases) > 1:
        raise RuntimeError("Nested production leases must share one ledger")
    publication_path.parent.mkdir(parents=True, exist_ok=True)
    # Always lock the fixed installation database first, even for a custom claim DB.
    mutex = Ledger(publication_path)
    claim_ledger = active[0][0] if active else mutex
    with ExitStack() as stack:
        publication = stack.enter_context(mutex.connection())
        publication.execute("BEGIN IMMEDIATE")
        claims = publication
        if Path(claim_ledger.path).resolve() != publication_path:
            claims = stack.enter_context(claim_ledger.connection())
            claims.execute("BEGIN IMMEDIATE")
        token = _publication_scope.set((str(publication_path), active))
        try:
            now = time.time()
            for item in active:
                resource, owner, fence = item[1], item[2], item[3]
                row = claims.execute("SELECT * FROM jobs WHERE key=?", (resource,)).fetchone()
                if (row is None or row["owner"] != owner or row["fence"] != fence
                        or row["state"] != "RUNNING" or row["expires"] <= now):
                    raise RuntimeError("Lost production lease; publication blocked")
            yield
            if claims is not publication:
                claims.commit()
            publication.commit()
        except BaseException:
            if claims is not publication:
                claims.rollback()
            publication.rollback()
            raise
        finally:
            _publication_scope.reset(token)


class Ledger:
    def get_authority_epoch(self) -> str:
        p = Path(self.path).resolve()
        epoch_file = p.parent / ".authority_epoch"
        if epoch_file.is_file():
            try:
                val = epoch_file.read_text(encoding="utf-8").strip()
                if val:
                    return val
            except OSError:
                pass
        receipt_file = p.parent / "RESTORATION_RECEIPT.json"
        if receipt_file.is_file():
            try:
                r_data = json.loads(receipt_file.read_text(encoding="utf-8"))
                val = str(r_data.get("authority_epoch", "")).strip()
                if val:
                    return val
            except Exception:
                pass
        return "init-epoch"

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.generation: int = 1
        p = Path(self.path)

        # 1. Maintenance exclusion check BEFORE any connection or writes
        self._check_maintenance()

        # 2. Schema compatibility validation
        if p.is_file():
            try:
                with p.open("rb") as f:
                    h = f.read(100)
                    if len(h) >= 100:
                        self.generation = int.from_bytes(h[60:64], "big") or 1
                        if self.generation > 1:
                            from youtube_automation.production.authority import (
                                IncompatibleAuthorityError,
                            )

                            raise IncompatibleAuthorityError(
                                f"Database user_version {self.generation} exceeds maximum supported schema generation 1"
                            )
            except OSError:
                pass

            from youtube_automation.production.authority import IncompatibleAuthorityError
            try:
                with tempfile.TemporaryDirectory() as chk_tmp:
                    chk_db = Path(chk_tmp) / p.name
                    shutil.copyfile(p, chk_db)
                    for s_ext in ["-wal", "-shm"]:
                        s_file = p.with_name(f"{p.name}{s_ext}")
                        if s_file.exists():
                            try:
                                shutil.copyfile(s_file, Path(chk_tmp) / s_file.name)
                            except OSError:
                                pass
                    with closing(sqlite3.connect(chk_db)) as chk_conn:
                        tables = [r[0] for r in chk_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                        if tables:
                            if "jobs" not in tables:
                                raise IncompatibleAuthorityError(
                                    f"Foreign or unrecognized database schema at {p} (tables: {tables}); missing required jobs table"
                                )
                            cols = {r[1] for r in chk_conn.execute("PRAGMA table_info(jobs)").fetchall()}
                            if "key" not in cols:
                                raise IncompatibleAuthorityError(
                                    f"Foreign or unrecognized schema in jobs table at {p}: missing required column 'key' (columns: {cols})"
                                )
            except IncompatibleAuthorityError:
                raise
            except Exception as err:
                raise IncompatibleAuthorityError(f"Failed to inspect authority database schema at {p}: {err}") from err
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                  key TEXT PRIMARY KEY, recipe TEXT NOT NULL, state TEXT NOT NULL,
                  fence INTEGER NOT NULL DEFAULT 0, owner TEXT, expires REAL,
                  attempts INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY, at REAL NOT NULL, key TEXT NOT NULL,
                  state TEXT NOT NULL, detail TEXT NOT NULL);
            """)
        if p.name == "adaptive.sqlite3" and p.parent.name == ".runtime":
            enroll_file = p.parent.parent / ".authority_enrolled.json"
            if not enroll_file.is_file():
                try:
                    enroll_file.write_text(json.dumps({"authority_path": str(p.resolve())}), encoding="utf-8")
                except OSError:
                    pass

    def _check_maintenance(self) -> None:
        """Reject operations if maintenance mode is active on this ledger."""
        maintenance_lock = Path(self.path).parent / "MAINTENANCE.lock"
        if maintenance_lock.is_file():
            try:
                reason = maintenance_lock.read_text(encoding="utf-8").strip() or "Active MAINTENANCE.lock present"
            except OSError:
                reason = "Active MAINTENANCE.lock present"
            from youtube_automation.production.authority import MaintenanceExclusionError
            raise MaintenanceExclusionError(
                f"Authority at {self.path} is currently locked for maintenance: {reason}"
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA synchronous=FULL")
            yield conn

    def claim(
        self, key: str, recipe: str, owner: str, *, seconds: float = 60, now: float | None = None
    ) -> int | None:
        self._check_maintenance()
        now = time.time() if now is None else now
        if seconds <= 0:
            raise ValueError("Lease duration must be positive")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO jobs(key,recipe,state) VALUES(?,?,'PENDING')",
                    (key, recipe),
                )
                row = conn.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
                if row["state"] == "RUNNING" and row["expires"] > now:
                    conn.rollback()
                    return None
                from youtube_automation.production.authority import validate_fencing_generation
                current_fence = int(row["fence"])
                fence = validate_fencing_generation(current_fence, current_fence + 1)
                conn.execute(
                    "UPDATE jobs SET recipe=?,state='RUNNING',fence=?,owner=?,expires=?,attempts=attempts+1 WHERE key=?",
                    (recipe, fence, owner, now + seconds, key),
                )
                conn.execute(
                    "INSERT INTO events(at,key,state,detail) VALUES(?,?,'RUNNING',?)",
                    (now, key, json.dumps({"fence": fence, "owner": owner})),
                )
                conn.commit()
                return fence
            except BaseException:
                conn.rollback()
                raise

    def heartbeat(
        self, key: str, owner: str, fence: int, *, seconds: float = 60, now: float | None = None
    ) -> None:
        now = time.time() if now is None else now
        with self.connection() as conn:
            updated = conn.execute(
                "UPDATE jobs SET expires=? WHERE key=? AND owner=? AND fence=? AND state='RUNNING' AND expires>?",
                (now + seconds, key, owner, fence, now),
            ).rowcount
            if updated != 1:
                raise RuntimeError("Lost production lease")

    def claim_stage(
        self,
        key: str,
        recipe: str,
        owner: str,
        *,
        seconds: float = 60,
        max_attempts: int = 3,
        force: bool = False,
        now: float | None = None,
    ) -> StageClaim:
        self._check_maintenance()
        now = time.time() if now is None else now
        if seconds <= 0 or max_attempts <= 0:
            raise ValueError("Lease duration and maximum attempts must be positive")
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO jobs(key,recipe,state) VALUES(?,?,'PENDING')",
                    (key, recipe),
                )
                row = conn.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
                if row["state"] == "RUNNING" and row["expires"] > now:
                    conn.rollback()
                    return StageClaim("BUSY")
                if row["recipe"] != recipe or force:
                    conn.execute(
                        "UPDATE jobs SET recipe=?,state='PENDING',owner=NULL,expires=NULL,attempts=0,detail='{}' WHERE key=?",
                        (recipe, key),
                    )
                    row = conn.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
                if row["state"] == "SUCCEEDED":
                    conn.rollback()
                    return StageClaim("SUCCEEDED")
                if int(row["attempts"]) >= max_attempts:
                    detail = json.dumps(
                        {"error": "stage circuit open", "max_attempts": max_attempts}
                    )
                    conn.execute(
                        "UPDATE jobs SET state='BLOCKED',owner=NULL,expires=NULL,detail=? WHERE key=?",
                        (detail, key),
                    )
                    conn.execute(
                        "INSERT INTO events(at,key,state,detail) VALUES(?,?,'BLOCKED',?)",
                        (now, key, detail),
                    )
                    conn.commit()
                    return StageClaim("BLOCKED")
                from youtube_automation.production.authority import validate_fencing_generation
                current_fence = int(row["fence"])
                fence = validate_fencing_generation(current_fence, current_fence + 1)
                conn.execute(
                    "UPDATE jobs SET recipe=?,state='RUNNING',fence=?,owner=?,expires=?,attempts=attempts+1 WHERE key=?",
                    (recipe, fence, owner, now + seconds, key),
                )
                conn.execute(
                    "INSERT INTO events(at,key,state,detail) VALUES(?,?,'RUNNING',?)",
                    (now, key, json.dumps({"fence": fence, "owner": owner, "recipe": recipe})),
                )
                conn.commit()
                return StageClaim("CLAIMED", fence)
            except BaseException:
                conn.rollback()
                raise

    def finish(
        self,
        key: str,
        owner: str,
        fence: int,
        state: str,
        detail: dict[str, Any],
        *,
        now: float | None = None,
    ) -> None:
        if state not in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            raise ValueError("Invalid terminal state")
        now = time.time() if now is None else now
        encoded = json.dumps(detail, ensure_ascii=False)
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            updated = conn.execute(
                "UPDATE jobs SET state=?,detail=?,expires=NULL WHERE key=? AND owner=? AND fence=? AND state='RUNNING' AND expires>?",
                (state, encoded, key, owner, fence, now),
            ).rowcount
            if updated != 1:
                conn.rollback()
                raise RuntimeError("Stale worker cannot finish this job")
            conn.execute(
                "INSERT INTO events(at,key,state,detail) VALUES(?,?,?,?)",
                (now, key, state, encoded),
            )
            conn.commit()

    def status(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY key")]

    def get(self, key: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
            return dict(row) if row is not None else None


def _build_safe_terminal_detail(
    *,
    detail: dict[str, Any] | None,
    key: str,
    fence: int,
    exc: BaseException,
) -> dict[str, Any]:
    from youtube_automation.core import failure_record

    stage_val = (detail or {}).get("stage") or key
    stage = str(stage_val)
    frame = failure_record.innermost_project_frame(exc)
    layer = failure_record.classify_layer(exc, stage, frame)
    kind = failure_record.error_kind(exc, layer)
    exc_name = type(exc).__name__
    raw_msg = str(exc)

    known = failure_record.match_known_issue(
        {
            "exception": exc_name,
            "message": raw_msg,
            "layer": layer,
            "frame": frame,
        }
    )

    safe_err = failure_record.project_safe_message(
        raw_msg,
        exc_name=exc_name,
        layer=layer,
        kind=kind,
        known_issue=known,
    )

    safe_detail: dict[str, Any] = {
        "stage": failure_record._clean(stage, 80),
        "fence": fence,
        "layer": layer,
        "kind": kind,
        "exception": failure_record._clean(exc_name, 80),
        "error": safe_err,
    }
    if frame:
        safe_detail["frame"] = frame
    if known:
        safe_detail["known_issue"] = known.get("id")
    if detail and "run" in detail:
        safe_detail["run"] = failure_record._safe_repo_path(detail["run"])
    if detail and "recipe" in detail:
        safe_detail["recipe"] = failure_record._clean(str(detail["recipe"]), 80)
    return safe_detail


@contextmanager
def _maintained_claim(
    ledger: Ledger,
    key: str,
    owner: str,
    fence: int,
    *,
    seconds: float,
    detail: dict[str, Any] | None = None,
    auth_epoch: str | None = None,
) -> Iterator[None]:
    active = _active_leases.get()
    ledger_path = str(Path(ledger.path).resolve())
    if any(str(Path(item[0].path).resolve()) == ledger_path and item[1] == key for item in active):
        raise RuntimeError(f"Nested claim for the same production key is not supported: {key}")
    stopped = threading.Event()
    failures: list[Exception] = []

    def renew() -> None:
        while not stopped.wait(10):
            try:
                ledger.heartbeat(key, owner, fence, seconds=seconds)
            except Exception as exc:
                failures.append(exc)
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    state = "SUCCEEDED"
    terminal_detail = dict(detail or {})
    auth_domain = str(resource_database().resolve())
    if auth_epoch is None:
        auth_epoch = ledger.get_authority_epoch()
    token = _active_leases.set(active + ((ledger, key, owner, fence, auth_domain, auth_epoch),))
    try:
        yield
        if failures:
            raise RuntimeError("Resource lease renewal failed") from failures[0]
    except BaseException as exc:
        state = "FAILED"
        terminal_detail = _build_safe_terminal_detail(
            detail=detail,
            key=key,
            fence=fence,
            exc=exc,
        )
        raise
    finally:
        _active_leases.reset(token)
        stopped.set()
        thread.join(timeout=15)
        try:
            ledger.finish(key, owner, fence, state, terminal_detail)
        except RuntimeError:
            if state == "SUCCEEDED":
                raise


@contextmanager
def leased_resource(path: str | Path, resource: str) -> Iterator[None]:
    """Exclusive shared-host resource; distinct claims may nest and fence publication."""
    if _publication_scope.get() is not None:
        raise RuntimeError("Cannot acquire a production lease during publication")
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(database)
    owner = str(uuid.uuid4())
    claim_epoch = ledger.get_authority_epoch()
    fence = ledger.claim(resource, "resource-v1", owner)
    if fence is None:
        raise RuntimeError(f"Resource is busy: {resource}")
    with _maintained_claim(ledger, resource, owner, fence, seconds=60, auth_epoch=claim_epoch):
        yield


@contextmanager
def owned_resource(path: str | Path, resource: str) -> Iterator[None]:
    """Acquire a resource, or reuse its fenced claim in the same current context."""
    if _publication_scope.get() is not None:
        raise RuntimeError("Cannot acquire a production lease during publication")
    database = Path(path).resolve()
    active = _active_leases.get()
    if any(Path(item[0].path).resolve() != database for item in active):
        raise RuntimeError("Nested production leases must share one ledger")
    owned = any(item[1] == resource for item in active)
    scope = nullcontext() if owned else leased_resource(database, resource)
    with scope:
        # Reuse the existing all-claim owner/fence/expiry validation. The mutex
        # is released before any expensive work, and checked again afterwards.
        with publication_guard():
            pass
        yield
        with publication_guard():
            pass


@contextmanager
def durable_stage(
    path: str | Path,
    key: str,
    recipe: str,
    *,
    max_attempts: int = 3,
    force: bool = False,
    detail: dict[str, Any] | None = None,
) -> Iterator[bool]:
    """Claim one content-bound stage and record its one selected body failure."""
    if _publication_scope.get() is not None:
        raise RuntimeError("Cannot acquire a production lease during publication")
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(database)
    owner = str(uuid.uuid4())
    decision = ledger.claim_stage(
        key,
        recipe,
        owner,
        max_attempts=max_attempts,
        force=force,
    )
    if decision.state == "SUCCEEDED":
        yield False
        return
    if decision.state == "BUSY":
        raise RuntimeError(f"Stage is already running: {key}")
    if decision.state == "BLOCKED":
        raise RuntimeError(
            f"Stage circuit is open after {max_attempts} failed attempts: {key}; use --force-retry after correcting the cause"
        )
    assert decision.fence is not None
    stage_detail = detail or {}
    stage_name = str(stage_detail.get("stage") or key)
    run_dir = stage_detail.get("run")
    claim_epoch = ledger.get_authority_epoch()
    with _maintained_claim(
        ledger,
        key,
        owner,
        decision.fence,
        seconds=60,
        detail=detail,
        auth_epoch=claim_epoch,
    ):
        with failure_record.capture(stage_name, run_dir=run_dir):
            yield True
