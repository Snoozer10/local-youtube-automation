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
from pathlib import Path
from typing import Any

_active_lease: ContextVar[tuple[Ledger, str, str, int] | None] = ContextVar(
    "production_lease", default=None
)


def resource_database() -> Path:
    return Path(__file__).resolve().parents[3] / ".runtime" / "adaptive.sqlite3"


@contextmanager
def publication_guard() -> Iterator[None]:
    """Fence short filesystem publication while a replacement claim is excluded.

    Direct offline callers have no lease; CLI/device entrypoints must hold one.
    Never hold this transaction across browser operations or encoding.
    """
    active = _active_lease.get()
    if active is None:
        yield
        return
    ledger, resource, owner, fence = active
    with ledger.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT * FROM jobs WHERE key=?", (resource,)).fetchone()
            if (
                row is None
                or row["owner"] != owner
                or row["fence"] != fence
                or row["state"] != "RUNNING"
                or row["expires"] <= time.time()
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


@contextmanager
def leased_resource(path: str | Path, resource: str) -> Iterator[None]:
    """Exclusive shared-host resource; callers must not nest the same resource."""
    if _active_lease.get() is not None:
        raise RuntimeError("Nested production leases are not supported")
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(database)
    owner = str(uuid.uuid4())
    fence = ledger.claim(resource, "resource-v1", owner)
    if fence is None:
        raise RuntimeError(f"Resource is busy: {resource}")
    stopped = threading.Event()
    failures = []

    def renew() -> None:
        while not stopped.wait(10):
            try:
                ledger.heartbeat(resource, owner, fence)
            except Exception as exc:
                failures.append(exc)
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    state, detail = "SUCCEEDED", {}
    token = _active_lease.set((ledger, resource, owner, fence))
    try:
        yield
        if failures:
            raise RuntimeError("Resource lease renewal failed") from failures[0]
    except BaseException as exc:
        state, detail = "FAILED", {"error": str(exc)}
        raise
    finally:
        _active_lease.reset(token)
        stopped.set()
        thread.join(timeout=15)
        try:
            ledger.finish(resource, owner, fence, state, detail)
        except RuntimeError:
            if state == "SUCCEEDED":
                raise
