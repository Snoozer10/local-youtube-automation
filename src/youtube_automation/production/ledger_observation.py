"""Non-mutating SQLite observation for production ledger databases (Issue #55 / #56)."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ObservationStatus = Literal[
    "POPULATED",
    "EMPTY",
    "ABSENT",
    "BUSY",
    "DAMAGED",
    "UNSUPPORTED_WAL",
    "UNSUPPORTED_SCHEMA",
]

_SQLITE_MAGIC = b"SQLite format 3\x00"


@dataclass(frozen=True)
class ObservationDecision:
    status: ObservationStatus
    message: str
    rows: list[dict[str, Any]]
    supported: bool


def observe_ledger(path: str | Path | os.PathLike[str], *, busy_timeout_ms: int = 500) -> ObservationDecision:
    """Inspect a ledger database strictly without native mutation.

    Pre-access checks detect absent, damaged, and WAL-mode databases without connecting.
    WAL mode is marked unsupported with a pre-access refusal because SQLite on Windows
    modifies .db-shm timestamps or creates .db-shm files during read-only connection.
    """
    target = Path(path).resolve()
    if not target.is_file():
        return ObservationDecision(
            status="ABSENT",
            message=f"Database file is absent: {target.name}",
            rows=[],
            supported=False,
        )

    # Read the 100-byte SQLite header
    try:
        with target.open("rb") as handle:
            header = handle.read(100)
    except OSError as exc:
        return ObservationDecision(
            status="DAMAGED",
            message=f"Cannot read database header: {type(exc).__name__}",
            rows=[],
            supported=False,
        )

    if len(header) < 100 or not header.startswith(_SQLITE_MAGIC):
        return ObservationDecision(
            status="DAMAGED",
            message="File does not have a valid SQLite 3 header",
            rows=[],
            supported=False,
        )

    # Bytes 18 and 19 indicate file format write and read versions
    # 1 = legacy/rollback journal, 2 = WAL mode
    write_version = header[18]
    read_version = header[19]
    is_wal_header = (write_version == 2 or read_version == 2)

    wal_sidecar = target.with_name(f"{target.name}-wal")
    shm_sidecar = target.with_name(f"{target.name}-shm")
    has_wal = wal_sidecar.exists()
    has_shm = shm_sidecar.exists()

    # AC 3: WAL mode cannot be proven non-mutating on Windows because SQLite
    # touches .db-shm mtime or creates .db-shm files during read-only access.
    # Therefore, all WAL layouts are marked unsupported with a pre-access refusal.
    if is_wal_header or has_wal or has_shm:
        return ObservationDecision(
            status="UNSUPPORTED_WAL",
            message="Database uses WAL layout or has WAL sidecars; pre-access refusal as WAL cannot be proven non-mutating on Windows",
            rows=[],
            supported=False,
        )

    # Connect strictly in read-only mode via URI for rollback journal databases
    uri = f"file:{target.as_posix()}?mode=ro"
    conn = None
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=busy_timeout_ms / 1000.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check if 'jobs' table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        )
        if not cur.fetchone():
            return ObservationDecision(
                status="UNSUPPORTED_SCHEMA",
                message="Database does not contain the required 'jobs' table",
                rows=[],
                supported=False,
            )

        cur.execute("SELECT key, state, attempts, fence, detail FROM jobs ORDER BY key")
        rows = [dict(row) for row in cur.fetchall()]

        if not rows:
            return ObservationDecision(
                status="EMPTY",
                message="Compatible ledger database is empty (0 jobs)",
                rows=[],
                supported=True,
            )

        return ObservationDecision(
            status="POPULATED",
            message=f"Compatible ledger database observed ({len(rows)} jobs)",
            rows=rows,
            supported=True,
        )

    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            return ObservationDecision(
                status="BUSY",
                message="Database is locked by another process",
                rows=[],
                supported=False,
            )
        if "malformed" in msg or "corrupt" in msg or "file is not a database" in msg:
            return ObservationDecision(
                status="DAMAGED",
                message=f"Database file is damaged: {exc}",
                rows=[],
                supported=False,
            )
        return ObservationDecision(
            status="DAMAGED",
            message=f"Operational error during inspection: {exc}",
            rows=[],
            supported=False,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
