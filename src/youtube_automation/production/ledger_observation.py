"""Non-mutating SQLite observation for production ledger databases (Issue #55 / #56)."""

from __future__ import annotations

import json
import os
import re
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
    had_wal_pre = wal_sidecar.exists()
    had_shm_pre = shm_sidecar.exists()

    def _check_wal_envelope() -> bool:
        """Return True if any WAL indication or new sidecar appears."""
        try:
            with target.open("rb") as f:
                h = f.read(100)
            if len(h) >= 100 and (h[18] == 2 or h[19] == 2):
                return True
        except OSError:
            pass
        if wal_sidecar.exists() or shm_sidecar.exists():
            return True
        return False

    # AC 3: WAL mode cannot be proven non-mutating on Windows because SQLite
    # touches .db-shm mtime or creates .db-shm files during read-only access.
    # Therefore, all WAL layouts are marked unsupported with a pre-access refusal.
    if is_wal_header or had_wal_pre or had_shm_pre:
        return ObservationDecision(
            status="UNSUPPORTED_WAL",
            message="Database uses WAL layout or has WAL sidecars; pre-access refusal as WAL cannot be proven non-mutating on Windows",
            rows=[],
            supported=False,
        )

    # Connect strictly in read-only mode via URI for rollback journal databases
    uri = f"{target.as_uri()}?mode=ro"
    conn = None
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=busy_timeout_ms / 1000.0)

        # Re-verify layout within observation envelope before executing any queries
        if _check_wal_envelope():
            conn.close()
            conn = None
            return ObservationDecision(
                status="UNSUPPORTED_WAL",
                message="Database uses WAL layout or has WAL sidecars; pre-access refusal as WAL cannot be proven non-mutating on Windows",
                rows=[],
                supported=False,
            )

        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check if 'jobs' table exists
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        )
        if _check_wal_envelope():
            del cur
            conn.close()
            conn = None
            return ObservationDecision(
                status="UNSUPPORTED_WAL",
                message="Database transitioned to WAL layout during observation; refusing as WAL cannot be proven non-mutating on Windows",
                rows=[],
                supported=False,
            )

        if not cur.fetchone():
            return ObservationDecision(
                status="UNSUPPORTED_SCHEMA",
                message="Database does not contain the required 'jobs' table",
                rows=[],
                supported=False,
            )

        cur.execute("PRAGMA table_info(jobs)")
        if _check_wal_envelope():
            del cur
            conn.close()
            conn = None
            return ObservationDecision(
                status="UNSUPPORTED_WAL",
                message="Database transitioned to WAL layout during observation; refusing as WAL cannot be proven non-mutating on Windows",
                rows=[],
                supported=False,
            )

        existing_cols = {row["name"] for row in cur.fetchall()}
        required_cols = {"key", "state", "attempts", "fence", "detail"}
        if not required_cols.issubset(existing_cols):
            missing = sorted(required_cols - existing_cols)
            return ObservationDecision(
                status="UNSUPPORTED_SCHEMA",
                message=f"Database table 'jobs' is missing required columns: {missing}",
                rows=[],
                supported=False,
            )

        cur.execute("SELECT key, state, attempts, fence, detail FROM jobs ORDER BY key")
        if _check_wal_envelope():
            del cur
            conn.close()
            conn = None
            return ObservationDecision(
                status="UNSUPPORTED_WAL",
                message="Database transitioned to WAL layout during observation; refusing as WAL cannot be proven non-mutating on Windows",
                rows=[],
                supported=False,
            )

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

    except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
        msg = str(exc).lower()
        if "locked" in msg or "busy" in msg:
            return ObservationDecision(
                status="BUSY",
                message="Database is locked by another process",
                rows=[],
                supported=False,
            )
        if (
            "malformed" in msg
            or "corrupt" in msg
            or "file is not a database" in msg
            or "disk image" in msg
        ):
            return ObservationDecision(
                status="DAMAGED",
                message=f"Database file is damaged: {exc}",
                rows=[],
                supported=False,
            )
        return ObservationDecision(
            status="DAMAGED",
            message=f"Database error during inspection: {exc}",
            rows=[],
            supported=False,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


_ALLOWED_STATES = {"PENDING", "IN_FLIGHT", "SUCCEEDED", "FAILED", "CANCELLED"}


def project_safe_job(row: dict[str, Any]) -> dict[str, Any]:
    """Project a raw historical job row in memory into safe bounded diagnostics."""
    from youtube_automation.core import failure_record

    raw_key = str(row.get("key") or "unknown")
    key = re.sub(r"[^a-zA-Z0-9_\-:]", "_", raw_key)[:64]

    raw_state = str(row.get("state") or "").upper()
    state = raw_state if raw_state in _ALLOWED_STATES else "UNKNOWN"

    try:
        attempts = max(0, min(9999, int(row.get("attempts", 0))))
    except (TypeError, ValueError):
        attempts = 0

    fence_val = row.get("fence")
    try:
        fence = int(fence_val) if fence_val is not None else None
    except (TypeError, ValueError):
        fence = None

    raw_detail = row.get("detail")
    detail_dict: dict[str, Any] = {}
    if isinstance(raw_detail, dict):
        detail_dict = raw_detail
    elif isinstance(raw_detail, str) and raw_detail.strip():
        # Bound JSON parse length to 16KB
        stripped = raw_detail.strip()
        if len(stripped) <= 16384 and (stripped.startswith("{") or stripped.startswith("[")):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    detail_dict = parsed
                else:
                    detail_dict = {"raw_message": stripped}
            except Exception:
                detail_dict = {"raw_message": stripped}
        else:
            detail_dict = {"raw_message": stripped[:1024]}

    layer = re.sub(r"[^a-zA-Z0-9_\-]", "", str(detail_dict.get("layer") or "unknown"))[:32] or "unknown"
    kind = re.sub(r"[^a-zA-Z0-9_\-]", "", str(detail_dict.get("kind") or "unknown"))[:32] or "unknown"
    exc_name = re.sub(r"[^a-zA-Z0-9_]", "", str(detail_dict.get("exception") or ""))[:64]
    known_val = detail_dict.get("known_issue")
    known_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(known_val))[:64] if known_val else None

    # Error message projection
    err_source = detail_dict.get("error") or detail_dict.get("message") or detail_dict.get("raw_message")
    safe_summary: str | None = None
    if err_source is not None:
        safe_summary = failure_record.project_safe_message(
            str(err_source),
            exc_name=exc_name or "Failure",
            layer=layer,
            kind=kind,
            known_issue={"id": known_id} if known_id else None,
        )

    return {
        "key": key,
        "state": state,
        "attempts": attempts,
        "fence": fence,
        "layer": layer,
        "kind": kind,
        "exception": exc_name or None,
        "summary": safe_summary,
        "known_issue": known_id,
    }


def format_ledger_status(decision: ObservationDecision, *, max_jobs: int = 50) -> str:
    """Render a human-readable, non-mutating status report from an observation decision."""
    lines: list[str] = []
    if decision.status == "POPULATED":
        projected_jobs = [project_safe_job(row) for row in decision.rows]
        total = len(projected_jobs)
        lines.append(f"Ledger Status: POPULATED ({total} jobs recorded)")
        shown_jobs = projected_jobs[:max_jobs]
        for job in shown_jobs:
            parts = [f"  - [{job['state']}] stage={job['key']} attempts={job['attempts']}"]
            if job.get("fence") is not None:
                parts.append(f"fence={job['fence']}")
            if job.get("summary"):
                parts.append(f"detail={job['summary']!r}")
            elif job.get("exception"):
                parts.append(f"exception={job['exception']}")
            if job.get("known_issue"):
                parts.append(f"known_issue={job['known_issue']}")
            lines.append(" ".join(parts))
        if total > max_jobs:
            lines.append(f"  [truncated: {max_jobs} of {total} jobs shown; partial view]")
    elif decision.status == "EMPTY":
        lines.append("Ledger Status: EMPTY")
        lines.append("No production jobs recorded in compatible ledger.")
    elif decision.status == "ABSENT":
        lines.append("Ledger Status: UNAVAILABLE (database file does not exist)")
        lines.append(f"Reason: {decision.message}")
        lines.append("Next action: Run an adaptive generation stage to initialize the production workspace.")
    elif decision.status == "UNSUPPORTED_WAL":
        lines.append("Ledger Status: UNAVAILABLE (unsupported WAL layout)")
        lines.append(f"Reason: {decision.message}")
        lines.append("Next action: Observe offline or configure standard rollback journal mode for safe inspection.")
    elif decision.status == "BUSY":
        lines.append("Ledger Status: UNAVAILABLE (database busy)")
        lines.append(f"Reason: {decision.message}")
        lines.append("Next action: Retry status observation when active operation completes.")
    elif decision.status == "DAMAGED":
        lines.append("Ledger Status: UNAVAILABLE (corrupted or unreadable database)")
        lines.append(f"Reason: {decision.message}")
        lines.append("Next action: Inspect filesystem integrity or restore from authorized backup.")
    elif decision.status == "UNSUPPORTED_SCHEMA":
        lines.append("Ledger Status: UNAVAILABLE (foreign or incompatible schema)")
        lines.append(f"Reason: {decision.message}")
        lines.append("Next action: Verify the database path points to a valid adaptive production ledger.")
    else:
        lines.append(f"Ledger Status: UNAVAILABLE ({decision.status.lower()})")
        lines.append(f"Reason: {decision.message}")
        lines.append("Next action: Verify ledger database configuration and health.")
    return "\n".join(lines)
