import json
from types import SimpleNamespace

import pytest

from youtube_automation.production import review


def rejected_preview(tmp_path, monkeypatch):
    artifact = tmp_path / "preview.mp4"
    artifact.write_bytes(b"rejected preview bytes")
    plan = SimpleNamespace(shots=[])
    monkeypatch.setattr(review, "fingerprint", lambda _value: "a" * 64)
    monkeypatch.setattr(review, "review_context", lambda _root: (SimpleNamespace(version=3), plan))
    monkeypatch.setattr(review, "verify_generated_assets", lambda *_args: None)
    monkeypatch.setattr(review, "load_brief", lambda _root: SimpleNamespace(source_sha256="d" * 64))
    preview = {
        "path": artifact.name,
        "sha256": review.file_digest(artifact),
        "inputs": {"plan": "a" * 64},
    }
    (tmp_path / "adaptive_preview.json").write_text(json.dumps(preview), encoding="utf-8")
    rejection = review.HumanPreviewRejection(
        reviewer="owner",
        overall_rating=1.5,
        plan_sha256="a" * 64,
        preview_sha256=preview["sha256"],
        reasons=["The returning participant changes appearance; the progression is boring."],
        required_next="Revise and obtain a new human review.",
        source="Direct owner feedback.",
    )
    (tmp_path / "human_review_rejection.json").write_text(rejection.model_dump_json(), encoding="utf-8")
    return plan, preview


def test_owner_rejection_blocks_all_four_scorecard_and_approval(tmp_path, monkeypatch):
    rejected_preview(tmp_path, monkeypatch)
    scores = dict.fromkeys((
        "semantic_match", "hook_strength", "attractiveness", "progression",
        "continuity", "readability", "motion",
    ), 4)
    scores["notes"] = "Prior assistant assessment cannot supersede explicit human rejection."
    with pytest.raises(ValueError, match="Human rejected this preview"):
        review.record_preview_scorecard(tmp_path, "owner", scores)
    with pytest.raises(ValueError, match="Human rejected this preview"):
        review.approve_review(tmp_path, "owner")
    assert not (tmp_path / "editorial_approval.json").exists()
    assert not (tmp_path / "preview_scorecard.json").exists()


def test_rejection_preserves_overall_rating_without_fabricating_dimensions(tmp_path, monkeypatch):
    plan, preview = rejected_preview(tmp_path, monkeypatch)
    rejection = review.HumanPreviewRejection.model_validate_json(
        (tmp_path / "human_review_rejection.json").read_text(encoding="utf-8")
    )
    assert rejection.overall_rating == 1.5
    with pytest.raises(ValueError, match="Human rejected"):
        review.require_no_human_rejection(tmp_path, "a" * 64, preview["sha256"])
    review.require_no_human_rejection(tmp_path, "a" * 64, "b" * 64)


def test_malformed_rejection_cannot_silently_authorize_publication(tmp_path, monkeypatch):
    plan, preview = rejected_preview(tmp_path, monkeypatch)
    (tmp_path / "human_review_rejection.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        review.require_no_human_rejection(tmp_path, "a" * 64, preview["sha256"])


def test_recording_rejection_archives_exact_old_evidence_and_revokes_audit(tmp_path, monkeypatch):
    plan, preview = rejected_preview(tmp_path, monkeypatch)
    (tmp_path / "shot_plan.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(review.ShotPlan, "model_validate_json", lambda _text: plan)
    prior = b'{"statement":"I approve."}\r\n'
    audit = b'{"reviewer":"assistant","rating":4}\r\n'
    (tmp_path / "human_review_intent.json").write_bytes(prior)
    (tmp_path / "visual_audit.json").write_bytes(audit)
    rejection = review.record_preview_rejection(
        tmp_path, "owner", ["Characters change appearance and the video is boring."], overall_rating=1.5
    )
    assert rejection.preview_sha256 == preview["sha256"]
    assert rejection.overall_rating == 1.5
    assert not (tmp_path / "visual_audit.json").exists()
    assert (tmp_path / "human_review_intent.json").read_bytes() == prior
    archived = list((tmp_path / "editorial_rejections" / "human").rglob("*.json"))
    assert any(p.read_bytes() == audit for p in archived)
    assert any(p.read_bytes() == prior for p in archived)
    with pytest.raises(ValueError, match="Human rejected"):
        review.require_no_human_rejection(tmp_path, "a" * 64, preview["sha256"])


def test_cached_approval_cannot_skip_a_new_human_rejection(tmp_path, monkeypatch):
    from youtube_automation.production import cli

    plan, _preview = rejected_preview(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_render_output_complete", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cli, "_validated_plan", lambda _root: (SimpleNamespace(version=3), plan, {}))
    assert not cli._stage_complete(tmp_path, SimpleNamespace(stage="approve", reviewer="owner"))


def _compile_receipted_fixture_video(tmp_path, output):
    from PIL import Image

    from youtube_automation.video.engine import compile_video
    from youtube_automation.video.runner import FakeMediaRunner
    from youtube_automation.video.schema import (
        CompilationRequest,
        CompilationSpan,
        CompilationTarget,
    )

    audio = tmp_path / "canonical-fixture.wav"
    audio.write_bytes(b"canonical fixture audio")
    image = tmp_path / "canonical-fixture.png"
    Image.new("RGB", (640, 360), "#304560").save(image)
    runner = FakeMediaRunner(
        default_total_frames=30,
        default_duration=1.0,
        default_width=640,
        default_height=360,
        default_fps=30.0,
        default_pix_fmt="yuv420p",
    )
    result = compile_video(
        CompilationRequest(
            spans=(CompilationSpan(0, "synthetic", 0, 30, "subject"),),
            audio_path=audio,
            asset_paths={"subject": image},
            output_path=output,
            target=CompilationTarget(width=640, height=360, fps=30),
            encoder_override="libx264",
        ),
        runner=runner,
        base_config={
            "OUTPUT_WIDTH": 640,
            "OUTPUT_HEIGHT": 360,
            "OUTPUT_FPS": 30,
            "ENCODER_FORCE": "libx264",
        },
    )
    return result


def test_orphan_master_cannot_activate_from_rejected_approval(tmp_path, monkeypatch):
    from contextlib import nullcontext

    from youtube_automation.production import render

    _plan, rejected = rejected_preview(tmp_path, monkeypatch)
    _plan.fps = 30
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"canonical fixture audio")
    original_fingerprint = render.fingerprint
    monkeypatch.setattr(render, "fingerprint", lambda value: "a" * 64 if value is _plan else original_fingerprint(value))
    monkeypatch.setattr(render, "render_tool_version", lambda: "FFmpeg fixture build")
    monkeypatch.setattr(render, "detect_hardware_encoder", lambda _config: {
        "video_codec": "libx264", "encoder_name": "libx264", "hwaccel": "none", "encoder_args": ["-crf", "17"],
    })
    inputs = render.current_render_inputs(_plan, {}, audio, {"OUTPUT_WIDTH": 640, "OUTPUT_HEIGHT": 360})
    encoder_execution = {
        "version": 1, "clips": [], "assembly": inputs["encoder_policy"]["assembly"],
    }
    generation = render.fingerprint(inputs)
    current_artifact = tmp_path / "current_preview.mp4"
    current_result = _compile_receipted_fixture_video(tmp_path, current_artifact)
    current = {
        "path": current_artifact.name, "sha256": current_result.sha256,
        "inputs": inputs, "generation": generation, "frames": 30, "editorial_status": "pending",
        "encoder_execution": encoder_execution,
    }
    (tmp_path / "adaptive_preview.json").write_text(json.dumps(current), encoding="utf-8")
    (tmp_path / "editorial_approval.json").write_text(
        json.dumps({"preview_sha256": rejected["sha256"]}), encoding="utf-8"
    )
    work = tmp_path / "adaptive_renders" / generation
    work.mkdir(parents=True)
    pending = work / "orphan.pending.mp4"
    orphan_result = _compile_receipted_fixture_video(tmp_path, pending)
    orphan_bytes = pending.read_bytes()
    destination = work / f"master-{orphan_result.sha256}.mp4"
    pending.rename(destination)
    from youtube_automation.video.receipt import verify_compilation_receipt

    assert verify_compilation_receipt(destination)["sha256"] == orphan_result.sha256
    pointer = {
        "generation": generation, "inputs": inputs, "frames": 30,
        "editorial_status": "approved", "sha256": orphan_result.sha256,
        "path": str(destination.relative_to(tmp_path)),
        "encoder_execution": encoder_execution,
    }
    journal = render._render_journal_path(tmp_path, generation, False)
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"version": 1, "kind": "master", "pointer": pointer}), encoding="utf-8")
    monkeypatch.setattr(render, "probe_video", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(render, "publication_guard", nullcontext)
    with pytest.raises(ValueError, match="Human rejected"):
        render._recover_render_publication(tmp_path, generation, inputs, 30, 30, preview=False)
    assert not (tmp_path / "active_master.json").exists()
    assert journal.exists()
    assert destination.read_bytes() == orphan_bytes

def test_human_feedback_forces_fresh_complete_critic_and_binds_cache(tmp_path, monkeypatch):
    from youtube_automation.production import render, shots

    brief = SimpleNamespace(version=3, source_sha256="d" * 64, visual_strategy=None)
    plan = SimpleNamespace(
        shots=[SimpleNamespace(shot_id="s1")], fps=30,
        model_dump_json=lambda: '{"shots":[{"shot_id":"s1"}]}',
    )
    # Use actual string fingerprints; the plan object has a fixed fixture identity.
    original = review.fingerprint
    monkeypatch.setattr(shots, "fingerprint", lambda value: "a" * 64 if value is plan else original(value))
    monkeypatch.setattr(render, "overlay_review_evidence", lambda *_: {})
    decision = {"shot_id": "s1", "verdict": "accept", "semantic_match": 4,
                "takeaway_match": 4, "visual_specificity": 4, "rationale": "Concrete visible action"}
    old = shots.EditorialReview(plan_sha256="a" * 64, approved=True, shots=[decision])
    (tmp_path / "editorial_review.json").write_text(old.model_dump_json())
    rejection = review.HumanPreviewRejection(reviewer="owner", overall_rating=1.5,
        plan_sha256="a" * 64, preview_sha256="b" * 64, source_sha256=brief.source_sha256,
        reasons=["Character identity changes"], required_next="Revise and review all shots", source="owner")
    feedback_path = tmp_path / "human_review_rejection.json"
    feedback_path.write_text(rejection.model_dump_json())
    with pytest.raises(ValueError, match="predates current human feedback"):
        shots.require_editorial_review(tmp_path, plan, brief)
    calls = []

    def ask(prompt):
        calls.append(prompt)
        return old.model_dump_json()

    fresh = shots.ensure_editorial_review(tmp_path, plan, {"total_frames": 30}, brief, ask)
    assert len(calls) == 1 and "Character identity changes" in calls[0]
    assert fresh.human_feedback_sha256 is not None
    assert shots.require_editorial_review(tmp_path, plan, brief) == fresh
    shots.ensure_editorial_review(tmp_path, plan, {"total_frames": 30}, brief, ask)
    assert len(calls) == 1
    feedback_path.write_text(rejection.model_copy(update={"reasons": ["The revised progression still repeats"]}).model_dump_json())
    with pytest.raises(ValueError, match="predates current human feedback"):
        shots.require_editorial_review(tmp_path, plan, brief)


def test_feedback_is_typed_and_does_not_cross_source_lineage(tmp_path):
    from youtube_automation.production.shots import _human_quality_feedback

    rejection = review.HumanPreviewRejection(reviewer="owner", plan_sha256="a" * 64,
        preview_sha256="b" * 64, source_sha256="d" * 64, reasons=["Repair character"],
        required_next="Fresh review", source="owner")
    path = tmp_path / "human_review_rejection.json"
    path.write_text(rejection.model_dump_json())
    assert _human_quality_feedback(tmp_path, SimpleNamespace(source_sha256="e" * 64)) == ""
    path.write_text("{}")
    with pytest.raises(ValueError):
        _human_quality_feedback(tmp_path, SimpleNamespace(source_sha256="d" * 64))


@pytest.mark.parametrize("rejection_location", ["active", "archive"])
@pytest.mark.parametrize("changed_plan", [False, True])
def test_rejected_preview_bytes_stay_blocked_across_plan_changes(
    tmp_path, monkeypatch, rejection_location, changed_plan
):
    _plan, preview = rejected_preview(tmp_path, monkeypatch)
    active = tmp_path / "human_review_rejection.json"
    if rejection_location == "archive":
        archive = tmp_path / "editorial_rejections" / "human" / "prior"
        archive.mkdir(parents=True)
        (archive / "rejection.json").write_bytes(active.read_bytes())
        active.unlink()

    plan_hash = "b" * 64 if changed_plan else "a" * 64
    with pytest.raises(ValueError, match="Human rejected this preview"):
        review.require_no_human_rejection(tmp_path, plan_hash, preview["sha256"])


def test_revised_preview_bytes_clear_rejection_gate(tmp_path, monkeypatch):
    _plan, _preview = rejected_preview(tmp_path, monkeypatch)

    review.require_no_human_rejection(tmp_path, "a" * 64, "f" * 64)
