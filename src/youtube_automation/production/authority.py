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
import sqlite3
from pathlib import Path
from typing import Any

MINIMUM_SCHEMA_GENERATION = 1


class AuthorityError(Exception):
    """Base exception for resource authority failures."""


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

    # 3. Check for Incompatible Schema Generation
    if generation < MINIMUM_SCHEMA_GENERATION:
        raise IncompatibleAuthorityError(
            f"Authority schema generation {generation} is incompatible with required minimum {MINIMUM_SCHEMA_GENERATION}"
        )

    # 4. Check for Physical Database Damage if file exists
    if target_path.exists():
        if target_path.stat().st_size < 100:
            raise DamagedAuthorityError(f"Authority database at {target_path} is truncated or damaged (<100 bytes)")
        try:
            with target_path.open("rb") as f:
                header = f.read(16)
                if header != b"SQLite format 3\x00":
                    raise DamagedAuthorityError(f"Authority file at {target_path} is not a valid SQLite database")
        except OSError as err:
            raise DamagedAuthorityError(f"Cannot read authority database at {target_path}: {err}") from err

        # Verify integrity of database tables
        try:
            with sqlite3.connect(f"file:{target_path.as_posix()}?mode=ro", uri=True) as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                if not row or row[0] != "ok":
                    raise DamagedAuthorityError(f"Integrity check failed for authority database: {row}")
                # Check user_version compatibility if set
                db_version = conn.execute("PRAGMA user_version").fetchone()[0]
                if db_version > 0 and db_version < MINIMUM_SCHEMA_GENERATION:
                    raise IncompatibleAuthorityError(
                        f"Database user_version {db_version} is less than required minimum {MINIMUM_SCHEMA_GENERATION}"
                    )
        except sqlite3.DatabaseError as err:
            raise DamagedAuthorityError(f"Authority database failed connection integrity: {err}") from err

    return AuthorityResolution(
        database_path=target_path,
        source=source_type,
        schema_generation=generation,
        is_maintenance_excluded=maint_mode,
        maintenance_reason=maint_reason,
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
