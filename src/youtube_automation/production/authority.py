"""Convergent cross-checkout authority discovery, runtime cutover, and maintenance exclusion (Issue #59).

Covers accepted Track A requirements D1, D2, D3, and D8:
- Convergent authority discovery across checkouts and workspaces.
- Fail-closed boundaries on ambiguous, damaged, or incompatible authority.
- Runtime cutover excluding incompatible older clients.
- Explicit maintenance and migration controls that reject stale fencing generations.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

MINIMUM_SCHEMA_GENERATION = 1
MAXIMUM_SCHEMA_GENERATION = 1


class AuthorityError(Exception):
    """Base exception for resource authority failures."""


class MissingAuthorityError(AuthorityError):
    """Raised when a registered or configured authority database is missing on disk, requiring recovery rather than silent replacement."""


class AmbiguousAuthorityError(AuthorityError):
    """Raised when conflicting authority pointers exist across environment and configuration."""


class DamagedAuthorityError(AuthorityError):
    """Raised when the authority database or configuration is corrupt, unreadable, or invalid."""


class IncompatibleAuthorityError(AuthorityError):
    """Raised when the authority database has an incompatible or unsupported schema generation."""


class MaintenanceExclusionError(AuthorityError):
    """Raised when authority is locked for maintenance, excluding client claims."""


class StaleFencingGenerationError(AuthorityError):
    """Raised when a stale lease fence or former holder attempts to claim or advance state."""


@dataclasses.dataclass(frozen=True)
class AuthorityConfig:
    database_path: Path
    schema_generation: int = MINIMUM_SCHEMA_GENERATION
    maintenance_mode: bool = False
    maintenance_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_path": str(self.database_path.resolve().as_posix()),
            "schema_generation": self.schema_generation,
            "maintenance_mode": self.maintenance_mode,
            "maintenance_reason": self.maintenance_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthorityConfig:
        raw_path = data.get("database_path")
        if not raw_path or not isinstance(raw_path, str):
            raise DamagedAuthorityError(f"Authority config missing valid 'database_path': {data}")
        return cls(
            database_path=Path(raw_path),
            schema_generation=int(data.get("schema_generation", MINIMUM_SCHEMA_GENERATION)),
            maintenance_mode=bool(data.get("maintenance_mode", False)),
            maintenance_reason=str(data.get("maintenance_reason", "")),
        )


@dataclasses.dataclass(frozen=True)
class AuthorityResolution:
    database_path: Path
    source: str  # "ENV", "CONFIG", or "DEFAULT"
    schema_generation: int
    is_maintenance_excluded: bool
    maintenance_reason: str = ""
    authority_epoch: str = ""


def validate_authority_schema(
    conn: sqlite3.Connection,
    target_path: Path | str,
    *,
    require_execution: bool = False,
) -> None:
    """Validate that candidate database schema conforms to supported invariants before any writes."""
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    user_tables = {t for t in tables if not t.startswith("sqlite_")}
    if not user_tables:
        return

    if "jobs" not in user_tables:
        raise IncompatibleAuthorityError(
            f"Foreign or unrecognized database schema at {target_path} (tables: {sorted(user_tables)}); "
            f"missing required jobs table"
        )
    unrecognized = sorted(user_tables - {"jobs", "events"})
    if unrecognized:
        raise IncompatibleAuthorityError(
            f"Foreign or unrecognized database schema at {target_path} (tables: {sorted(user_tables)}); "
            f"unrecognized tables present: {unrecognized}"
        )

    cols_info = conn.execute("PRAGMA table_info(jobs)").fetchall()
    cols = {r[1] for r in cols_info}
    if require_execution:
        required_cols = {"key", "recipe", "state", "fence", "owner", "expires", "attempts", "detail"}
        if not required_cols.issubset(cols):
            missing = sorted(required_cols - cols)
            raise IncompatibleAuthorityError(
                f"Foreign or partial schema in jobs table at {target_path}: "
                f"missing required columns: {missing} (found: {sorted(cols)})"
            )
    else:
        required_obs = {"key", "state", "attempts", "fence", "detail"}
        if not required_obs.issubset(cols):
            missing = sorted(required_obs - cols)
            raise IncompatibleAuthorityError(
                f"Foreign or unrecognized schema in jobs table at {target_path}: "
                f"missing required columns: {missing} (found: {sorted(cols)})"
            )

    pk_cols = [r[1] for r in cols_info if r[5] > 0]
    has_unique_key = (pk_cols == ["key"])
    if not has_unique_key:
        for idx in conn.execute("PRAGMA index_list(jobs)").fetchall():
            unique = bool(idx[2])
            is_partial = bool(idx[4]) if len(idx) > 4 else False
            if unique and not is_partial:
                idx_cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()]
                if idx_cols == ["key"]:
                    has_unique_key = True
                    break
    if not has_unique_key:
        raise IncompatibleAuthorityError(
            f"Foreign or incompatible schema in jobs table at {target_path}: "
            f"missing primary key or unique constraint on key (unconditional key uniqueness required)"
        )

    def _is_ineffective_default(val: Any) -> bool:
        if val is None:
            return True
        val_str = str(val).strip().upper()
        return val_str in ("NULL", "(NULL)")

    if require_execution or {"recipe", "state", "fence", "attempts", "detail"}.issubset(cols):
        col_defaults = {r[1]: r[4] for r in cols_info}
        col_notnull = {r[1]: r[3] for r in cols_info}
        for req_dflt_col in ["fence", "attempts", "detail"]:
            if req_dflt_col in cols and _is_ineffective_default(col_defaults.get(req_dflt_col)):
                raise IncompatibleAuthorityError(
                    f"Foreign or incompatible schema in jobs table at {target_path}: "
                    f"missing required default value for column {req_dflt_col!r}"
                )
        for col_name, notnull in col_notnull.items():
            if col_name not in {"key", "recipe", "state"} and notnull == 1 and _is_ineffective_default(col_defaults.get(col_name)):
                raise IncompatibleAuthorityError(
                    f"Foreign or incompatible schema in jobs table at {target_path}: "
                    f"column {col_name!r} is NOT NULL but lacks a default value"
                )

        # Functional qualification on isolated candidate connection
        sp_name = f"_schema_qual_{uuid.uuid4().hex[:8]}"
        canary_key = f"__schema_probe_{uuid.uuid4().hex}__"
        try:
            conn.execute(f"SAVEPOINT {sp_name}")
            try:
                # 1. Verify insertion with unsupplied defaults
                conn.execute(
                    "INSERT INTO jobs(key, recipe, state) VALUES(?, '__probe_recipe__', 'PENDING')",
                    (canary_key,),
                )
                probe_row = conn.execute(
                    "SELECT fence, attempts, detail FROM jobs WHERE key=?",
                    (canary_key,),
                ).fetchone()
                if probe_row is None or probe_row[0] is None or probe_row[1] is None or probe_row[2] is None:
                    raise IncompatibleAuthorityError(
                        f"Foreign or incompatible schema in jobs table at {target_path}: "
                        f"insertion defaults produced NULL in required execution columns"
                    )
                try:
                    int(probe_row[0])
                    int(probe_row[1])
                except (ValueError, TypeError) as err:
                    raise IncompatibleAuthorityError(
                        f"Foreign or incompatible schema in jobs table at {target_path}: "
                        f"numeric default values cannot be parsed as integers: {err}"
                    ) from err

                # 2. Verify unconditional key uniqueness across states
                duplicate_allowed = False
                try:
                    conn.execute(
                        "INSERT INTO jobs(key, recipe, state) VALUES(?, '__probe_recipe__', 'RUNNING')",
                        (canary_key,),
                    )
                    duplicate_allowed = True
                except sqlite3.IntegrityError:
                    pass

                if duplicate_allowed:
                    raise IncompatibleAuthorityError(
                        f"Foreign or incompatible schema in jobs table at {target_path}: "
                        f"key column is not unconditionally unique across states"
                    )
            finally:
                conn.execute(f"ROLLBACK TO {sp_name}")
                conn.execute(f"RELEASE {sp_name}")
        except IncompatibleAuthorityError:
            raise
        except sqlite3.IntegrityError as err:
            raise IncompatibleAuthorityError(
                f"Foreign or incompatible schema in jobs table at {target_path}: "
                f"functional insertion qualification failed: {err}"
            ) from err
        except sqlite3.OperationalError as err:
            if "readonly" in str(err).lower():
                pass
            else:
                raise IncompatibleAuthorityError(
                    f"Foreign or incompatible schema in jobs table at {target_path}: "
                    f"database operational error during schema qualification: {err}"
                ) from err
        except sqlite3.Error as err:
            raise IncompatibleAuthorityError(
                f"Foreign or incompatible schema in jobs table at {target_path}: "
                f"database error during schema qualification: {err}"
            ) from err

    if "events" in user_tables:
        ev_cols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
        required_events = {"id", "at", "key", "state", "detail"}
        if not required_events.issubset(ev_cols):
            missing = sorted(required_events - ev_cols)
            err_kind = "partial" if require_execution else "unrecognized"
            raise IncompatibleAuthorityError(
                f"Foreign or {err_kind} schema in events table at {target_path}: "
                f"missing required columns: {missing} (found: {sorted(ev_cols)})"
            )


def discover_authority(
    env_override: str | Path | None = None,
    config_path: Path | None = None,
    default_root: Path | None = None,
    *,
    enforce_maintenance: bool = True,
) -> AuthorityResolution:
    """Convergently discover the authoritative production database across checkouts.

    Fails closed on:
    - Ambiguous authority: environment pointer conflicts with configuration file.
    - Damaged authority: corrupt file, invalid JSON, or broken SQLite header.
    - Incompatible authority: schema generation is older than minimum supported.
    - Maintenance exclusion: maintenance mode is active on the shared resource.
    """
    env_val = env_override or os.environ.get("YOUTUBE_AUTOMATION_AUTHORITY_DB")
    env_db: Path | None = Path(env_val).resolve() if env_val else None

    root = default_root or Path(__file__).resolve().parents[3]
    if config_path is None:
        for candidate in [root / ".authority.json", root / "config" / "authority.json"]:
            if candidate.is_file():
                config_path = candidate
                break

    cfg: AuthorityConfig | None = None
    if config_path and config_path.is_file():
        try:
            cfg_text = config_path.read_text(encoding="utf-8")
            cfg_data = json.loads(cfg_text)
            cfg = AuthorityConfig.from_dict(cfg_data)
        except (json.JSONDecodeError, OSError) as err:
            raise DamagedAuthorityError(f"Authority configuration at {config_path} is damaged: {err}") from err

    # 1. Ambiguity Detection: ENV and CONFIG must not point to differing locations
    if env_db is not None and cfg is not None:
        if env_db != cfg.database_path.resolve():
            raise AmbiguousAuthorityError(
                f"Conflicting authority configuration: ENV points to {env_db} but config points to {cfg.database_path}"
            )

    # Determine resolved path and source
    if env_db is not None:
        target_path = env_db
        source_type = "ENV"
        generation = cfg.schema_generation if cfg else MINIMUM_SCHEMA_GENERATION
        maint_mode = cfg.maintenance_mode if cfg else False
        maint_reason = cfg.maintenance_reason if cfg else ""
    elif cfg is not None:
        target_path = cfg.database_path.resolve()
        source_type = "CONFIG"
        generation = cfg.schema_generation
        maint_mode = cfg.maintenance_mode
        maint_reason = cfg.maintenance_reason
    else:
        root = default_root or Path(__file__).resolve().parents[3]
        target_path = (root / ".runtime" / "adaptive.sqlite3").resolve()
        if not target_path.exists() and (root / "adaptive.sqlite3").exists():
            target_path = (root / "adaptive.sqlite3").resolve()
        source_type = "DEFAULT"
        generation = MINIMUM_SCHEMA_GENERATION
        maint_mode = False
        maint_reason = ""

    # 2. Check for Maintenance Mode
    maintenance_lock = target_path.parent / "MAINTENANCE.lock"
    if maintenance_lock.is_file():
        maint_mode = True
        try:
            maint_reason = maintenance_lock.read_text(encoding="utf-8").strip() or "Active MAINTENANCE.lock present"
        except OSError:
            maint_reason = "Active MAINTENANCE.lock present"

    if enforce_maintenance and maint_mode:
        raise MaintenanceExclusionError(
            f"Authority at {target_path} is currently locked for maintenance: {maint_reason}"
        )

    # 3. Check for Missing Registered Authority (Enrollment vs Recovery)
    if source_type in ("ENV", "CONFIG") and not target_path.exists():
        raise MissingAuthorityError(
            f"Registered authority database at {target_path} is missing on disk; "
            f"refusing silent empty replacement to preserve historical state"
        )
    elif source_type == "DEFAULT" and not target_path.exists():
        root = default_root or Path(__file__).resolve().parents[3]
        enrollment_marker = root / ".authority_enrolled.json"
        if enrollment_marker.is_file():
            raise MissingAuthorityError(
                f"Default authority database at {target_path} is missing on disk after prior enrollment; "
                f"refusing silent empty replacement to preserve historical state"
            )

    # 4. Check for Incompatible Schema Generation
    if generation < MINIMUM_SCHEMA_GENERATION or generation > MAXIMUM_SCHEMA_GENERATION:
        raise IncompatibleAuthorityError(
            f"Authority schema generation {generation} is incompatible with required minimum {MINIMUM_SCHEMA_GENERATION} "
            f"(supported range [{MINIMUM_SCHEMA_GENERATION}, {MAXIMUM_SCHEMA_GENERATION}])"
        )

    # 5. Check for Physical Database Damage and Compatibility if file exists (strictly non-mutating)
    if target_path.exists():
        if target_path.stat().st_size < 100:
            raise DamagedAuthorityError(f"Authority database at {target_path} is truncated or damaged (<100 bytes)")
        try:
            with target_path.open("rb") as f:
                header = f.read(100)
                if len(header) < 100 or header[:16] != b"SQLite format 3\x00":
                    raise DamagedAuthorityError(f"Authority file at {target_path} is not a valid SQLite database")
                # SQLite header offset 60-64 stores user_version as a 4-byte big-endian integer
                db_version = int.from_bytes(header[60:64], "big")
                if db_version > 0 and (db_version < MINIMUM_SCHEMA_GENERATION or db_version > MAXIMUM_SCHEMA_GENERATION):
                    raise IncompatibleAuthorityError(
                        f"Database user_version {db_version} is incompatible with supported range "
                        f"[{MINIMUM_SCHEMA_GENERATION}, {MAXIMUM_SCHEMA_GENERATION}]"
                    )
        except OSError as err:
            raise DamagedAuthorityError(f"Cannot read authority database at {target_path}: {err}") from err

        # Verify schema identity: reject foreign or unrecognized databases lacking the required jobs table or columns
        try:
            with tempfile.TemporaryDirectory() as chk_tmp:
                chk_db = Path(chk_tmp) / target_path.name
                shutil.copyfile(target_path, chk_db)
                for s_ext in ["-wal", "-shm"]:
                    s_file = target_path.with_name(f"{target_path.name}{s_ext}")
                    if s_file.exists():
                        try:
                            shutil.copyfile(s_file, Path(chk_tmp) / s_file.name)
                        except OSError:
                            pass
                with closing(sqlite3.connect(chk_db)) as chk_conn:
                    validate_authority_schema(chk_conn, target_path, require_execution=False)
        except IncompatibleAuthorityError:
            raise
        except Exception as err:
            raise IncompatibleAuthorityError(f"Failed to inspect authority database schema at {target_path}: {err}") from err

    # Discover or derive active authority epoch
    epoch_file = target_path.parent / ".authority_epoch"
    auth_epoch = ""
    if epoch_file.is_file():
        try:
            auth_epoch = epoch_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    if not auth_epoch:
        receipt_file = target_path.parent / "RESTORATION_RECEIPT.json"
        if receipt_file.is_file():
            try:
                r_data = json.loads(receipt_file.read_text(encoding="utf-8"))
                auth_epoch = str(r_data.get("authority_epoch", ""))
            except Exception:
                pass
    if not auth_epoch and target_path.exists():
        auth_epoch = "init-epoch"

    return AuthorityResolution(
        database_path=target_path,
        source=source_type,
        schema_generation=generation,
        is_maintenance_excluded=maint_mode,
        maintenance_reason=maint_reason,
        authority_epoch=auth_epoch,
    )


def validate_fencing_generation(current_fence: int, proposed_fence: int) -> int:
    """Validate that a lease fence update strictly advances generation, rejecting stale holders."""
    if proposed_fence <= current_fence:
        raise StaleFencingGenerationError(
            f"Stale fencing generation rejected: proposed fence {proposed_fence} <= current {current_fence}"
        )
    return proposed_fence


def set_maintenance_mode(
    authority_dir: Path,
    enabled: bool,
    reason: str = "Scheduled administrative maintenance",
) -> None:
    """Explicitly engage or disengage maintenance exclusion on an authority directory."""
    authority_dir = authority_dir.resolve()
    lock_file = authority_dir / "MAINTENANCE.lock"
    if enabled:
        lock_file.write_text(reason, encoding="utf-8")
    else:
        if lock_file.exists():
            lock_file.unlink()
