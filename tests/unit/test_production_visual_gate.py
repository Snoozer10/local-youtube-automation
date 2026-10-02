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


def test_complete_review_binds_every_shot_asset_and_proof(tmp_path, monkeypatch):
    candidate = plan(images=2)
    candidate.shots[1].operation = "reuse"
    candidate.shots[1].asset_id = candidate.shots[0].asset_id
    (tmp_path / "visual_budget.json").write_text('{"max_images":20,"require_review":true}')
    monkeypatch.setattr(gate, "fingerprint", lambda _: "a" * 64)
    def accept(_root, shot, _brief):
        assert shot.operation != "reuse", "Validate the originating asset recipe"
        return tmp_path / "image.png"
    monkeypatch.setattr(gate, "accepted_asset", accept)
    monkeypatch.setattr(gate, "read_shot_receipt", lambda *_: {"sha256": "b" * 64})
    proof = tmp_path / "proof.png"
    proof.write_bytes(b"inspected rendered pixels")
    late = tmp_path / "late.png"
    late.write_bytes(b"inspected late pixels")
    decisions = [{"shot_id": s.shot_id, "proof_path": "proof.png", "proof_sha256": gate.file_digest(proof),
        "semantic_match":4,"continuity":4,"readability":4,"attractiveness":4,
        "notes":"Inspected narration, framing, graphic copy and progression",
        "additional_proofs":{"late.png":gate.file_digest(late)}} for s in candidate.shots]
    audit = {"plan_sha256":"a"*64, "assets":{s.asset_id:"b"*64 for s in candidate.shots},
        "reviewer":"Visual inspector", "decisions":decisions}
    path = tmp_path / "visual_audit.json"
    with pytest.raises(ValueError, match="Every current shot"):
        gate.require_visual_audit(tmp_path, candidate, None)
    path.write_text(json.dumps(audit))
    gate.require_visual_audit(tmp_path, candidate, None)
    audit["decisions"] = decisions[:1]
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="exact current plan"):
        gate.require_visual_audit(tmp_path, candidate, None)
    audit["decisions"] = decisions
    path.write_text(json.dumps(audit))
    late.write_bytes(b"late frame changed after review")
    with pytest.raises(ValueError, match="proof changed"):
        gate.require_visual_audit(tmp_path, candidate, None)
    late.write_bytes(b"inspected late pixels")
    proof.write_bytes(b"changed after review")
    with pytest.raises(ValueError, match="proof changed"):
        gate.require_visual_audit(tmp_path, candidate, None)
