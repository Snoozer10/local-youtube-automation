"""Offline adapter for the production voice-direction stage.

This staged entry point accepts a reviewed response supplied by its caller. It
never selects a provider or initiates transport; the production stage owns
context checks, tag policy, candidate provenance, and acceptance guards.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from youtube_automation.production import direction_stage

_SOURCE_AUDIO_RECEIPT = "source_audio_receipt.json"

direction_inputs = direction_stage.direction_inputs
direction_prompt = direction_stage.direction_prompt


def _verified_run_dir(run_dir: str | Path) -> Path:
    path = Path(run_dir)
    if (path / _SOURCE_AUDIO_RECEIPT).exists():
        raise direction_stage.VoiceDirectionError(
            "Imported raw narration cannot enter voice direction"
        )
    direction_stage.direction_inputs(path)
    return path


def ensure_direction_candidate(run_dir: str | Path, reviewed_response: str) -> dict[str, Any]:
    """Build or resume a candidate using only the supplied offline response."""
    verified_run = _verified_run_dir(run_dir)
    if not isinstance(reviewed_response, str):
        raise TypeError("reviewed_response must be supplied as text")

    calls = 0

    def offline_response(_prompt: str) -> str:
        nonlocal calls
        if calls:
            raise RuntimeError("offline response may be consumed only once")
        calls += 1
        return reviewed_response

    return direction_stage.ensure_direction_candidate(verified_run, offline_response)


def accept_direction(
    run_dir: str | Path,
    *,
    reviewer: str,
    candidate_sha256: str,
) -> Path:
    """Delegate approval to the production stage's hash-bound guard."""
    verified_run = _verified_run_dir(run_dir)
    return direction_stage.accept_direction(
        verified_run,
        reviewer=reviewer,
        candidate_sha256=candidate_sha256,
    )