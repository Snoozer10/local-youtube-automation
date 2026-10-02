"""Single-host SQLite leases with fencing; stale workers cannot finish newer claims."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_Lease = tuple["Ledger", str, str, int]
_active_leases: ContextVar[tuple[_Lease, ...]] = ContextVar(
    "production_leases", default=()
)


@dataclass(frozen=True)
class StageClaim:
    state: Literal["CLAIMED", "SUCCEEDED", "BUSY", "BLOCKED"]
    fence: int | None = None


def resource_database() -> Path:
    return Path(__file__).resolve().parents[3] / ".runtime" / "adaptive.sqlite3"


@contextmanager
def publication_guard() -> Iterator[None]:
    """Fence short filesystem publication while a replacement claim is excluded.

    Direct offline callers have no lease; CLI/device entrypoints must hold one.
    Never hold this transaction across browser operations or encoding.
    """
    active = _active_leases.get()
    if not active:
        yield
        return
    databases = {str(Path(ledger.path).resolve()) for ledger, _, _, _ in active}
    if len(databases) != 1:
        raise RuntimeError("Nested production leases must share one ledger")
    ledger = active[0][0]
    with ledger.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            now = time.time()
            for _, resource, owner, fence in active:
                row = conn.execute("SELECT * FROM jobs WHERE key=?", (resource,)).fetchone()
                if (
                    row is None
                    or row["owner"] != owner
                    or row["fence"] != fence
                    or row["state"] != "RUNNING"
                    or row["expires"] <= now
                ):
                    raise RuntimeError("Lost production lease; publication blocked")
            yield
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


class Ledger:
    def __init__(self, path: str | Path):
        self.path = str(path)
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

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA synchronous=FULL")
            yield conn

    def claim(
        self, key: str, recipe: str, owner: str, *, seconds: float = 60, now: float | None = None
    ) -> int | None:
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
                fence = int(row["fence"]) + 1
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
                fence = int(row["fence"]) + 1
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


@contextmanager
def _maintained_claim(
    ledger: Ledger,
    key: str,
    owner: str,
    fence: int,
    *,
    seconds: float,
    detail: dict[str, Any] | None = None,
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
    token = _active_leases.set(active + ((ledger, key, owner, fence),))
    try:
        yield
        if failures:
            raise RuntimeError("Resource lease renewal failed") from failures[0]
    except BaseException as exc:
        state = "FAILED"
        terminal_detail["error"] = str(exc)
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
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(database)
    owner = str(uuid.uuid4())
    fence = ledger.claim(resource, "resource-v1", owner)
    if fence is None:
        raise RuntimeError(f"Resource is busy: {resource}")
    with _maintained_claim(ledger, resource, owner, fence, seconds=60):
        yield


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
    """Claim one content-bound stage, skip success, and open a bounded failure circuit."""
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
    with _maintained_claim(
        ledger,
        key,
        owner,
        decision.fence,
        seconds=60,
        detail=detail,
    ):
        yield True
