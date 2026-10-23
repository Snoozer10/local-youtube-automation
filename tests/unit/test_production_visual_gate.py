import json
from types import SimpleNamespace

import pytest

from youtube_automation.production import visual_gate as gate


def plan(images=20, seconds=60, local=0):
    return SimpleNamespace(
        total_frames=seconds * 30,
        fps=30,
        shots=[SimpleNamespace(asset_id=f"asset_{i}", shot_id=f"shot_{i}",
            operation="local_canvas" if i < local else "generate", local_composition=None, visible_state="")
            for i in range(images)],
    )


@pytest.mark.parametrize("seconds,limit", [(30, 20), (600, 200), (1197, 399), (1200, 400), (3600, 400)])
def test_duration_never_allows_400_before_twenty_minutes(tmp_path, seconds, limit):
    assert gate.visual_budget(tmp_path, plan(seconds=seconds)).max_images == limit


def test_saved_pilot_cap_rejects_over_budget_before_generation(tmp_path):
    (tmp_path / "visual_budget.json").write_text(json.dumps({"version": 1, "max_images": 20}))
    with pytest.raises(gate.VisualBudgetExceeded, match="21 distinct images"):
        gate.enforce_visual_budget(tmp_path, plan(images=21, seconds=600))
    assert not (tmp_path / "visual_spending.json").exists()


def test_uncertain_sends_and_retries_consume_durable_budget(tmp_path):
    (tmp_path / "visual_budget.json").write_text(json.dumps({"max_images": 3}))
    candidate = plan(images=3, local=1)
    gate.reserve_flow_submission(tmp_path, candidate)
    gate.reserve_flow_submission(tmp_path, candidate)
    # A restarted worker has no in-memory allowance to reset.
    with pytest.raises(gate.VisualBudgetExceeded, match="2 Flow sends.*1 local"):
        gate.reserve_flow_submission(tmp_path, plan(images=3, local=1))
    assert json.loads((tmp_path / "visual_spending.json").read_text())["flow_submissions"] == 2


def test_changed_generation_archives_review_but_preserves_budget_and_spending(tmp_path):
    from youtube_automation.production.invalidation import invalidate_stage

    (tmp_path / "visual_audit.json").write_text('{"old":"audit"}')
    (tmp_path / "visual_budget.json").write_text('{"max_images":20}')
    (tmp_path / "visual_spending.json").write_text('{"flow_submissions":8}')
    proof = tmp_path / "visual_inspection" / "proof.png"
    proof.parent.mkdir()
    proof.write_bytes(b"prior inspected pixels")
    archived = invalidate_stage(tmp_path, "generate", "a"*64, "b"*64)
    assert len(archived) == 2
    assert not (tmp_path / "visual_audit.json").exists()
    assert not proof.exists()
    assert json.loads((tmp_path / "visual_spending.json").read_text())["flow_submissions"] == 8
    assert json.loads((tmp_path / "visual_budget.json").read_text())["max_images"] == 20


def test_complete_review_binds_every_shot_asset_proof_and_render_recipe(tmp_path, monkeypatch):
    from youtube_automation.production import render

    candidate = plan(images=2)
    candidate.shots[1].operation = "reuse"
    candidate.shots[1].asset_id = candidate.shots[0].asset_id
    (tmp_path / "visual_budget.json").write_text('{"max_images":20,"require_review":true}')
    original_fingerprint = gate.fingerprint
    monkeypatch.setattr(
        gate,
        "fingerprint",
        lambda value: "a" * 64 if value is candidate else original_fingerprint(value),
    )

    def accept(_root, shot, _brief):
        assert shot.operation != "reuse", "Validate the originating asset recipe"
        return tmp_path / "image.png"

    monkeypatch.setattr(gate, "accepted_asset", accept)
    monkeypatch.setattr(gate, "read_shot_receipt", lambda *_: {"sha256": "b" * 64})
    render_inputs = {
        "render_code_sha256": "c" * 64,
        "tool": "FFmpeg build 1",
        "config": {"OUTPUT_WIDTH": 1920, "OUTPUT_HEIGHT": 1080, "CPU_CRF": 23},
        "overlay_recipes": {"shot_0": "d" * 64},
    }
    monkeypatch.setattr(render, "current_render_inputs", lambda *_: dict(render_inputs))
    (tmp_path / "timeline.json").write_text(json.dumps({"audio_file": "audio.wav"}))
    candidate.timeline_sha256 = original_fingerprint({"audio_file": "audio.wav"})
    (tmp_path / "audio.wav").write_bytes(b"canonical narration bytes")
    config = {"OUTPUT_WIDTH": 1920, "OUTPUT_HEIGHT": 1080}
    proof = tmp_path / "proof.png"
    proof.write_bytes(b"inspected rendered pixels")
    late = tmp_path / "late.png"
    late.write_bytes(b"inspected late pixels")
    decisions = [
        {
            "shot_id": shot.shot_id,
            "proof_path": "proof.png",
            "proof_sha256": gate.file_digest(proof),
            "semantic_match": 4,
            "continuity": 4,
            "readability": 4,
            "attractiveness": 4,
            "notes": "Inspected narration, framing, graphic copy and progression",
            "additional_proofs": {"late.png": gate.file_digest(late)},
        }
        for shot in candidate.shots
    ]
    audit = {
        "version": 2,
        "plan_sha256": "a" * 64,
        "assets": {shot.asset_id: "b" * 64 for shot in candidate.shots},
        "render_inputs_sha256": original_fingerprint(render_inputs),
        "reviewer": "Visual inspector",
        "decisions": decisions,
    }
    path = tmp_path / "visual_audit.json"

    def require_current_audit():
        gate.require_visual_audit(tmp_path, candidate, None, render_config=config)

    with pytest.raises(ValueError, match="Every current shot"):
        require_current_audit()
    path.write_text(json.dumps(audit))
    require_current_audit()

    for key, changed in (
        ("render_code_sha256", "f" * 64),
        ("tool", "FFmpeg build 2"),
        ("config", {"OUTPUT_WIDTH": 1920, "OUTPUT_HEIGHT": 1080, "CPU_CRF": 28}),
        ("overlay_recipes", {"shot_0": "e" * 64}),
    ):
        original = render_inputs[key]
        render_inputs[key] = changed
        with pytest.raises(ValueError, match="render recipe is stale"):
            require_current_audit()
        audit["render_inputs_sha256"] = original_fingerprint(render_inputs)
        path.write_text(json.dumps(audit))
        require_current_audit()
        render_inputs[key] = original
        audit["render_inputs_sha256"] = original_fingerprint(render_inputs)
        path.write_text(json.dumps(audit))
        require_current_audit()

    audit["decisions"] = decisions[:1]
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="exact current plan"):
        require_current_audit()
    audit["decisions"] = decisions
    path.write_text(json.dumps(audit))
    late.write_bytes(b"late frame changed after review")
    with pytest.raises(ValueError, match="proof changed"):
        require_current_audit()
    late.write_bytes(b"inspected late pixels")
    proof.write_bytes(b"changed after review")
    with pytest.raises(ValueError, match="proof changed"):
        require_current_audit()


@pytest.mark.parametrize("asset_identity", ["storage", "shot"])
def test_visual_audit_explicit_encoder_recipe_must_match_inspected_inputs(tmp_path, monkeypatch, asset_identity):
    from youtube_automation.production import render

    candidate = plan(images=1)
    monkeypatch.setattr(gate, "enforce_visual_budget", lambda *_: SimpleNamespace(require_review=True))
    original_fingerprint = gate.fingerprint
    monkeypatch.setattr(gate, "fingerprint", lambda value: "a" * 64 if value is candidate else original_fingerprint(value))
    monkeypatch.setattr(gate, "accepted_asset", lambda *_: tmp_path / "asset.png")
    monkeypatch.setattr(gate, "read_shot_receipt", lambda *_: {"sha256": "b" * 64})
    (tmp_path / "timeline.json").write_text(json.dumps({"audio_file": "audio.wav"}))
    candidate.timeline_sha256 = original_fingerprint({"audio_file": "audio.wav"})
    (tmp_path / "audio.wav").write_bytes(b"canonical narration")
    proof = tmp_path / "proof.png"
    proof.write_bytes(b"inspected rendered pixels")
    config = {"OUTPUT_WIDTH": 1920, "OUTPUT_HEIGHT": 1080, "OUTPUT_FPS": 30}
    encoder = {"video_codec": "libx264", "encoder_args": ["-crf", "17"]}

    def recipe(_plan, _assets, _audio, supplied_config, *, encoder_config=None):
        return {"config": dict(supplied_config), "encoder_recipe": encoder_config, "assets": dict(_assets)}

    monkeypatch.setattr(render, "current_render_inputs", recipe)
    audit = gate.VisualAudit(
        version=2, plan_sha256="a" * 64, assets={"asset_0": "b" * 64},
        render_inputs_sha256=original_fingerprint(recipe(
            None, {"shot_0" if asset_identity == "shot" else "asset_0": "b" * 64},
            None, config, encoder_config=encoder,
        )),
        reviewer="Inspector",
        decisions=[gate.VisualDecision(
            shot_id="shot_0", proof_path="proof.png", proof_sha256=gate.file_digest(proof),
            semantic_match=4, continuity=4, readability=4, attractiveness=4,
            notes="Inspected current proof using its explicit execution recipe",
        )],
    )
    (tmp_path / "visual_audit.json").write_text(audit.model_dump_json())
    gate.require_visual_audit(
        tmp_path, candidate, None, render_config=config, encoder_config=encoder, asset_identity=asset_identity,
    )
    for changed_config, changed_encoder in (
        (dict(config, OUTPUT_WIDTH=1280), encoder),
        (config, dict(encoder, encoder_args=["-crf", "18"])),
        (config, None),
    ):
        with pytest.raises(ValueError, match="render recipe is stale"):
            gate.require_visual_audit(
                tmp_path, candidate, None, render_config=changed_config, encoder_config=changed_encoder,
                asset_identity=asset_identity,
            )


def test_visual_audit_rejects_unknown_asset_namespace_without_skipping(tmp_path):
    with pytest.raises(ValueError, match="Unknown render asset identity"):
        gate.require_visual_audit(tmp_path, plan(), None, asset_identity="unknown")


def test_legacy_audit_cannot_satisfy_required_review_but_no_review_skips_it(tmp_path):
    candidate = plan(images=1)
    path = tmp_path / "visual_audit.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "plan_sha256": "a" * 64,
                "assets": {},
                "reviewer": "Historical reviewer",
                "decisions": [],
            }
        )
    )
    budget = tmp_path / "visual_budget.json"
    budget.write_text('{"max_images":20,"require_review":true}')
    with pytest.raises(ValueError, match="Legacy visual audit"):
        gate.require_visual_audit(tmp_path, candidate, None)

    budget.write_text('{"max_images":20,"require_review":false}')
    gate.require_visual_audit(tmp_path, candidate, None)
