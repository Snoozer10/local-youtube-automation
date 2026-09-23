"""Journaled, dependency-aware deactivation for changed stage recipes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from youtube_automation.core.utils import atomic_write_json

from .ledger import publication_guard

_STAGE_PATTERNS: dict[str, tuple[str, ...]] = {
    "analyze": (
        "episode_brief.json",
        "adaptive_writing_receipt.json",
        "breaked_paragraphs.txt",
        "final_output.txt",
        "refined_script.txt",
        "source_audio_receipt.json",
        "full_episode_voice.wav",
        "voice_generation_manifest.json",
        "audio_manifest.json",
        "timeline.json",
        "shot_plan.json",
        "shot_plan.partial.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "active_master.json",
        "adaptive_thumbnail_receipt.json",
    ),
    "write": (
        "adaptive_writing_receipt.json",
        "breaked_paragraphs.txt",
        "final_output.txt",
        "refined_script.txt",
        "source_audio_receipt.json",
        "full_episode_voice.wav",
        "voice_generation_manifest.json",
        "audio_manifest.json",
        "voice_chapters/*",
        "polished_chapters/*",
        "audacity_voice/*",
        "timeline.json",
        "shot_plan.json",
        "shot_plan.partial.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "active_master.json",
        "adaptive_thumbnail_receipt.json",
    ),
    "source-audio": (
        "adaptive_writing_receipt.json",
        "breaked_paragraphs.txt",
        "final_output.txt",
        "refined_script.txt",
        "source_audio_receipt.json",
        "full_episode_voice.wav",
        "timeline.json",
        "shot_plan.json",
        "shot_plan.partial.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "active_master.json",
        "adaptive_thumbnail_receipt.json",
    ),
    "plan": (
        "shot_plan.json",
        "shot_plan.partial.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "active_master.json",
    ),
    "generate": (
        "asset_receipts/*.json",
        "adaptive_review/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "active_master.json",
    ),
    "report": ("adaptive_review/*",),
    "preview": ("adaptive_preview.json", "editorial_approval.json", "active_master.json"),
    "approve": ("editorial_approval.json", "active_master.json"),
    "render": ("active_master.json",),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _journal_path(root: Path) -> Path:
    return root / ".publication_journal" / "stage-invalidation.json"


def _load_journal(root: Path) -> dict[str, Any] | None:
    path = _journal_path(root)
    if not path.exists():
        return None
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("files"), list):
        raise ValueError("Invalid stage-invalidation journal")
    return payload


def reconcile_invalidation(run_dir: str | Path) -> list[str]:
    """Finish an interrupted deactivation before any stage can publish."""
    root = Path(run_dir).resolve()
    payload = _load_journal(root)
    if payload is None:
        return []
    archived: list[str] = []
    with publication_guard():
        for item in payload["files"]:
            relative = Path(item["source"])
            archive_relative = Path(item["archive"])
            source = (root / relative).resolve()
            archive = (root / archive_relative).resolve()
            if not source.is_relative_to(root) or not archive.is_relative_to(root):
                raise ValueError("Invalid path in stage-invalidation journal")
            expected = item["sha256"]
            if source.exists() and archive.exists():
                raise RuntimeError(f"Both active and archived stage outputs exist: {relative}")
            if source.exists():
                if not source.is_file() or _sha256(source) != expected:
                    raise ValueError(f"Active stage output changed during invalidation: {relative}")
                archive.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, archive)
            if not archive.is_file() or _sha256(archive) != expected:
                raise ValueError(f"Archived stage output is missing or corrupt: {relative}")
            archived.append(relative.as_posix())
        _journal_path(root).unlink()
    return archived


def invalidate_stage(
    run_dir: str | Path,
    stage: str,
    previous_recipe: str,
    next_recipe: str,
) -> list[str]:
    """Archive mutable activations for a changed stage and every downstream stage."""
    if stage not in _STAGE_PATTERNS:
        raise ValueError(f"Unknown adaptive stage: {stage}")
    root = Path(run_dir).resolve()
    reconcile_invalidation(root)
    if previous_recipe == next_recipe:
        return []
    transition = f"{previous_recipe[:12]}-to-{next_recipe[:12]}"
    records: list[dict[str, str]] = []
    seen: set[Path] = set()
    for pattern in _STAGE_PATTERNS[stage]:
        for source in sorted(root.glob(pattern)):
            if not source.is_file() or source in seen:
                continue
            seen.add(source)
            relative = source.relative_to(root)
            archive = Path(".adaptive_history") / transition / stage / relative
            records.append(
                {
                    "source": relative.as_posix(),
                    "archive": archive.as_posix(),
                    "sha256": _sha256(source),
                }
            )
    if not records:
        return []
    journal = _journal_path(root)
    journal.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        str(journal),
        {
            "version": 1,
            "stage": stage,
            "previous_recipe": previous_recipe,
            "next_recipe": next_recipe,
            "files": records,
        },
    )
    return reconcile_invalidation(root)
