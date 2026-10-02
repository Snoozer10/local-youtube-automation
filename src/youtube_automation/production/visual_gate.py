"""Bound image spending and require review of the actual current visuals."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal

from pydantic import Field

from youtube_automation.core.utils import atomic_write_json

from .assets import accepted_asset, asset_storage_id, file_digest, read_shot_receipt
from .contracts import Brief, Contract, Digest, Text, fingerprint
from .ledger import publication_guard
from .shots import Shot, ShotPlan, uses_local_canvas


class VisualBudgetExceeded(RuntimeError):
    """A hard spending stop, never a transport-retry condition."""


class VisualBudget(Contract):
    version: Literal[1] = 1
    max_images: int = Field(ge=1, le=400)
    require_review: bool = True


def visual_budget(root: Path, plan: ShotPlan) -> VisualBudget:
    # Twenty stills per minute, minimum twenty; 400 requires at least twenty minutes.
    minutes = plan.total_frames / plan.fps / 60
    duration_limit = min(400, max(20, math.floor(minutes * 20)))
    path = root / "visual_budget.json"
    configured = (
        VisualBudget.model_validate_json(path.read_text(encoding="utf-8-sig"))
        if path.is_file()
        else VisualBudget(max_images=duration_limit, require_review=False)
    )
    return configured.model_copy(update={"max_images": min(configured.max_images, duration_limit)})


def enforce_visual_budget(root: Path, plan: ShotPlan) -> VisualBudget:
    budget = visual_budget(root, plan)
    images = len({asset_storage_id(shot) for shot in plan.shots})
    if images > budget.max_images:
        raise VisualBudgetExceeded(
            f"Plan needs {images} distinct images; limit is {budget.max_images}. "
            "Replan with meaningful reuse before generating; never truncate narration."
        )
    return budget


def reserve_flow_submission(root: Path, plan: ShotPlan) -> None:
    """Journal before every send/retrigger; uncertain sends still consume the cap."""
    budget = enforce_visual_budget(root, plan)
    local = len({asset_storage_id(shot) for shot in plan.shots if uses_local_canvas(shot)})
    path = root / "visual_spending.json"
    with publication_guard():
        state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
            "version": 1, "flow_submissions": 0
        }
        used = state["flow_submissions"]
        if type(used) is not int or used < 0:
            raise ValueError("Invalid visual spending journal")
        if used + local >= budget.max_images:
            raise VisualBudgetExceeded(
                f"Image budget exhausted: {used} Flow sends + {local} local images; "
                f"limit {budget.max_images}. Preserve receipts and stop."
            )
        state["flow_submissions"] = used + 1
        atomic_write_json(str(path), state)


class VisualDecision(Contract):
    shot_id: Text
    proof_path: Text
    proof_sha256: Digest
    additional_proofs: dict[str, Digest] = Field(default_factory=dict)
    semantic_match: int = Field(ge=4, le=5)
    continuity: int = Field(ge=4, le=5)
    readability: int = Field(ge=4, le=5)
    attractiveness: int = Field(ge=4, le=5)
    notes: Text


class VisualAudit(Contract):
    version: Literal[1] = 1
    plan_sha256: Digest
    assets: dict[str, Digest]
    reviewer: Text
    decisions: list[VisualDecision]


def require_visual_audit(root: Path, plan: ShotPlan, brief: Brief) -> None:
    budget = enforce_visual_budget(root, plan)
    if not budget.require_review:
        return
    path = root / "visual_audit.json"
    if not path.is_file():
        raise ValueError("Every current shot must pass visual inspection before advancing")
    audit = VisualAudit.model_validate_json(path.read_text(encoding="utf-8-sig"))
    if audit.plan_sha256 != fingerprint(plan) or [d.shot_id for d in audit.decisions] != [
        shot.shot_id for shot in plan.shots
    ]:
        raise ValueError("Visual audit does not cover the exact current plan in order")
    expected = {}
    origins: dict[str, Shot] = {}
    for shot in plan.shots:
        key = asset_storage_id(shot)
        origins.setdefault(key, shot)
        if accepted_asset(root, origins[key], brief) is None:
            raise ValueError(f"Visual audit asset is invalid: {shot.asset_id}")
        expected[key] = read_shot_receipt(root, shot)["sha256"]
    if audit.assets != expected:
        raise ValueError("Visual audit image bytes changed")
    for decision in audit.decisions:
        proofs = {**decision.additional_proofs, decision.proof_path: decision.proof_sha256}
        for name, digest in proofs.items():
            proof = (root / name).resolve()
            if not proof.is_relative_to(root.resolve()) or not proof.is_file() or file_digest(proof) != digest:
                raise ValueError(f"Visual audit proof changed: {decision.shot_id}")
