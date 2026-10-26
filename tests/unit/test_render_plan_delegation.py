"""Tests verifying production/render.py delegation to VideoCompiler and MediaRunner seam.

Conforms to ADR 0002, ADR 0006, and Ticket 6 (Issue #29).
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from youtube_automation.production import flow, render, review
from youtube_automation.production.contracts import fingerprint
from youtube_automation.production.render import _get_runner, render_plan
from youtube_automation.production.shots import EditorialPolicy, Overlay, Shot, ShotPlan
from youtube_automation.video.runner import FakeMediaRunner, MediaProbeResult


def _make_shot(**updates: Any) -> Shot:
    """Create a fully-specified valid Shot fixture for testing."""
    payload: dict[str, Any] = {
        "shot_id": "s",
        "scene_id": "scene",
        "asset_id": "asset",
        "entity_ids": ["cat"],
        "span_ids": [0],
        "start_frame": 0,
        "end_frame": 180,
        "purpose": "Explain",
        "treatment": "subject_scene",
        "subject": "Cat",
        "visible_state": "Looking at hand",
        "setting": "Garden",
        "framing": "close_up",
        "composition": "Close-up",
    }
    payload.update(updates)
    return Shot.model_validate(payload)


def _setup_mock_run(tmp_path: Path) -> tuple[ShotPlan, dict[str, Any], dict[str, Any]]:
    """Create a minimal valid production run fixture."""
    shot = _make_shot(
        start_frame=0,
        end_frame=30,
        overlays=[Overlay(kind="label", start_frame=0, end_frame=30, text="Cue")],
    )
    timeline = {"audio_file": "voice.wav"}
    (tmp_path / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")

    plan = ShotPlan(
        shots=[shot],
        brief_sha256="a" * 64,
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=30,
        editorial_policy=EditorialPolicy(
            cadence="balanced",
            target_shot_seconds=5,
            max_shot_seconds=10,
            max_consecutive_framing=3,
            max_motion_fraction=0.5,
        ),
    )
    (tmp_path / "shot_plan.json").write_text(plan.model_dump_json(), encoding="utf-8")

    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"canonical mock audio data")

    image = tmp_path / "asset.png"
    Image.new("RGB", (640, 360), "#304560").save(image)

    config = {
        "OUTPUT_WIDTH": 640,
        "OUTPUT_HEIGHT": 360,
        "OUTPUT_FPS": 30,
        "CPU_CRF": 17,
        "ENCODER_FORCE": "libx264",
    }
    return plan, timeline, config


def test_get_runner_default_and_custom() -> None:
    """Verify _get_runner returns explicit runner or defaults correctly."""
    custom_runner = FakeMediaRunner()
    assert _get_runner(custom_runner) is custom_runner

    # When unpatched, returns SubprocessMediaRunner
    default_runner = _get_runner(None)
    assert hasattr(default_runner, "run_ffmpeg")
    assert hasattr(default_runner, "probe")


def test_render_plan_delegates_to_videocompiler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify render_plan constructs CompilationRequest and delegates cleanly."""
    plan, timeline, config = _setup_mock_run(tmp_path)
    brief = SimpleNamespace(version=2, source_sha256="c" * 64)
    assets_map = {"asset": "d" * 64}

    monkeypatch.setattr(render, "load_brief", lambda _: brief)
    monkeypatch.setattr(review, "load_brief", lambda _: brief)
    monkeypatch.setattr(render, "validate_plan", lambda *_: None)
    monkeypatch.setattr(render, "verify_generated_assets", lambda *_: None)
    monkeypatch.setattr(flow, "verify_generated_assets", lambda *_: None)
    monkeypatch.setattr(
        "youtube_automation.production.visual_gate.require_visual_audit",
        lambda *_, **__: None,
    )
    monkeypatch.setattr(render, "asset_storage_id", lambda _: "asset")
    monkeypatch.setattr(
        render,
        "read_shot_receipt",
        lambda *_: {"dimensions": [640, 360], "path": "asset.png", "sha256": assets_map["asset"]},
    )
    monkeypatch.setattr(render, "read_receipt", lambda *_: {"sha256": assets_map["asset"]})
    monkeypatch.setattr(render, "publication_guard", nullcontext)
    monkeypatch.setattr(
        "youtube_automation.production.audio_adoption.capture_audio_state",
        lambda *_, **__: {"valid": True},
    )
    monkeypatch.setattr(
        "youtube_automation.production.audio_adoption.require_adopted_audio_review",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "youtube_automation.production.audio_adoption.assert_current_audio_state",
        lambda *_, **__: None,
    )

    runner = FakeMediaRunner(
        default_total_frames=30,
        default_duration=1.0,
        default_width=640,
        default_height=360,
        default_fps=30.0,
        default_pix_fmt="yuv420p",
    )
    # Seed audio probe
    audio_path = tmp_path / "voice.wav"
    runner.register_probe(
        audio_path,
        MediaProbeResult(
            duration=1.0,
            total_frames=30,
            width=0,
            height=0,
            fps=30.0,
            pix_fmt="",
            color_range="tv",
            has_audio=True,
        ),
    )

    destination = render_plan(tmp_path, config, preview=True, runner=runner)
    assert destination.exists()
    assert destination.name.startswith("preview-")
    assert destination.suffix == ".mp4"

    # Verify adaptive_preview.json was signed
    preview_json = json.loads((tmp_path / "adaptive_preview.json").read_text(encoding="utf-8"))
    assert preview_json["editorial_status"] == "pending"
    assert preview_json["frames"] == 30
    assert "encoder_execution" in preview_json
    assert preview_json["encoder_execution"]["assembly"]["video_codec"] == "libx264"
    assert len(preview_json["encoder_execution"]["clips"]) == 1
