"""Journaled, dependency-aware deactivation for changed stage recipes."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from youtube_automation.core.utils import atomic_write_json

from .ledger import publication_guard

_STAGE_PATTERNS: dict[str, tuple[str, ...]] = {
    "analyze": (
        "audio_adoption_receipt.json",
        "episode_brief.json",
        "voice_direction.candidate.json",
        ".voice_direction_publication.json",
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
        "shot_plan.semantic.partial.json",
        "editorial_review.json",
        "editorial_rejections/*.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "visual_audit.json",
        "visual_inspection/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "preview_scorecard.json",
        "active_master.json",
        "adaptive_thumbnail_receipt.json",
    ),
    "write": (
        "audio_adoption_receipt.json",
        "voice_direction.candidate.json",
        ".voice_direction_publication.json",
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
        "shot_plan.semantic.partial.json",
        "editorial_review.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "visual_audit.json",
        "visual_inspection/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "preview_scorecard.json",
        "active_master.json",
        "adaptive_thumbnail_receipt.json",
    ),
    "source-audio": (
        "audio_adoption_receipt.json",
        "voice_direction.candidate.json",
        ".voice_direction_publication.json",
        "adaptive_writing_receipt.json",
        "breaked_paragraphs.txt",
        "final_output.txt",
        "refined_script.txt",
        "source_audio_receipt.json",
        "full_episode_voice.wav",
        "timeline.json",
        "shot_plan.json",
        "shot_plan.partial.json",
        "shot_plan.semantic.partial.json",
        "editorial_review.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "visual_audit.json",
        "visual_inspection/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "preview_scorecard.json",
        "active_master.json",
        "adaptive_thumbnail_receipt.json",
    ),
    "adopt-polished-audio": (
        "image_timestamps.txt.sha256", "timestamped_transcript.txt.sha256",
        "timestamped_transcript.srt.sha256", "subtitle_chunks.srt.sha256",
        "timeline.json", "shot_plan.json", "shot_plan.partial.json",
        "shot_plan.semantic.partial.json", "editorial_review.json", "flow_prompts.json",
        "adaptive_review/*", "visual_audit.json", "visual_inspection/*",
        "adaptive_preview.json", "editorial_approval.json", "preview_scorecard.json",
        "active_master.json", "adaptive_thumbnail_receipt.json",
    ),
    "plan": (
        "shot_plan.json",
        "shot_plan.partial.json",
        "shot_plan.semantic.partial.json",
        "editorial_review.json",
        "asset_receipts/*.json",
        "adaptive_review/*",
        "visual_audit.json",
        "visual_inspection/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "preview_scorecard.json",
        "active_master.json",
        "adaptive_thumbnail_receipt.json",
    ),
    "generate": (
        "asset_receipts/*.json",
        "adaptive_review/*",
        "visual_audit.json",
        "visual_inspection/*",
        "adaptive_preview.json",
        "editorial_approval.json",
        "preview_scorecard.json",
        "active_master.json",
    ),
    "report": ("adaptive_review/*",),
    "preview": (
        "adaptive_preview.json",
        "preview_scorecard.json",
        "editorial_approval.json",
        "active_master.json",
    ),
    "approve": ("preview_scorecard.json", "editorial_approval.json", "active_master.json"),
    "render": ("active_master.json",),
    "direct": ("voice_direction.candidate.json", ".voice_direction_publication.json"),
    "accept-direction": (),
}


@dataclass(frozen=True)
class InvalidationFile:
    source: str
    archive: str
    sha256: str


@dataclass(frozen=True)
class InvalidationExpectation:
    stage: str
    previous_recipe: str
    next_recipe: str
    files: tuple[InvalidationFile, ...]


class InvalidationConflictError(ValueError):
    """A pending invalidation journal does not match its pinned owner."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _journal_path(root: Path) -> Path:
    return root / ".publication_journal" / "stage-invalidation.json"


def has_pending_invalidation(run_dir: str | Path) -> bool:
    return _load_journal(Path(run_dir).resolve()) is not None


def stage_output_paths(run_dir: str | Path, stage: str) -> list[Path]:
    """List current stage outputs in invalidation pattern order, without hashing."""
    if stage not in _STAGE_PATTERNS:
        raise ValueError(f"Unknown adaptive stage: {stage}")
    root = Path(run_dir).resolve()
    paths: list[Path] = []
    seen: set[Path] = set()
    for pattern in _STAGE_PATTERNS[stage]:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def stage_archive_destination(
    run_dir: str | Path, stage: str, previous_recipe: str, next_recipe: str, source: str | Path
) -> Path:
    """Return the canonical archive destination for one contained stage output."""
    if stage not in _STAGE_PATTERNS:
        raise ValueError(f"Unknown adaptive stage: {stage}")
    root = Path(run_dir).resolve()
    relative = Path(source)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Stage output paths must stay inside the run")
    if not (root / relative).resolve().is_relative_to(root):
        raise ValueError("Stage output paths must stay inside the run")
    return Path(".adaptive_history") / f"{previous_recipe[:12]}-to-{next_recipe[:12]}" / stage / relative


def _load_journal(root: Path) -> dict[str, Any] | None:
    path = _journal_path(root)
    if not path.exists():
        return None
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("files"), list):
        raise ValueError("Invalid stage-invalidation journal")
    return payload


def reconcile_invalidation(
    run_dir: str | Path, *, expected: InvalidationExpectation | None = None
) -> list[str]:
    """Finish an interrupted deactivation before any stage can publish."""
    root = Path(run_dir).resolve()
    payload = _load_journal(root)
    if payload is None:
        return []
    if expected is not None:
        actual = dict(payload)
        files = actual.get("files")
        if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
            raise InvalidationConflictError("Pending stage-invalidation journal conflicts with its owner")
        sources = [item.get("source") for item in files]
        if any(not isinstance(source, str) for source in sources) or len(sources) != len(set(sources)):
            raise InvalidationConflictError("Pending stage-invalidation journal conflicts with its owner")
        actual["files"] = sorted(files, key=lambda item: item["source"])
        expected_payload = {
            "version": 1,
            "stage": expected.stage,
            "previous_recipe": expected.previous_recipe,
            "next_recipe": expected.next_recipe,
            "files": sorted(
                ({"source": item.source, "archive": item.archive, "sha256": item.sha256} for item in expected.files),
                key=lambda item: item["source"],
            ),
        }
        if actual != expected_payload:
            raise InvalidationConflictError("Pending stage-invalidation journal conflicts with its owner")
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
    *,
    preserve_paths: set[str] | None = None,
) -> list[str]:
    """Archive mutable activations for a changed stage and every downstream stage."""
    if stage not in _STAGE_PATTERNS:
        raise ValueError(f"Unknown adaptive stage: {stage}")
    root = Path(run_dir).resolve()
    reconcile_invalidation(root)
    if previous_recipe == next_recipe:
        return []
    preserved = {Path(value).as_posix() for value in (preserve_paths or set())}
    if any(Path(value).is_absolute() or ".." in Path(value).parts for value in preserved):
        raise ValueError("Preserved invalidation paths must stay inside the run")
    records: list[dict[str, str]] = []
    for source in stage_output_paths(root, stage):
        relative = source.relative_to(root)
        if relative.as_posix() in preserved:
            continue
        archive = stage_archive_destination(root, stage, previous_recipe, next_recipe, relative)
        records.append({"source": relative.as_posix(), "archive": archive.as_posix(), "sha256": _sha256(source)})
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
