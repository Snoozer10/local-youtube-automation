import json
import shutil
from pathlib import Path

import pytest

from youtube_automation.production import shots
from youtube_automation.production.contracts import fingerprint
from youtube_automation.production.failure_replay import (
    build_failure_intelligence_report,
    load_semantic_failure_case,
    replay_semantic_failure_case,
)

CORPUS = Path(__file__).parents[1] / "fixtures" / "semantic_failures"


def countdown_case():
    return load_semantic_failure_case(CORPUS / "professor_lineage16_countdown_coverage.json")


def test_fixed_tail_reserves_diversity_in_editable_window():
    case = load_semantic_failure_case(CORPUS / "professor_lineage17_fixed_tail_framing.json")
    result = replay_semantic_failure_case(case)
    assert result.observed_boundary == "semantic_compiler"
    assert result.issues[0].beat_ids == ["beat_1_problem"]
    assert result.corrected_boundary == "accepted"


def test_repair_excludes_exhausted_prefix_scenes_and_accepts_fresh_scene():
    case = load_semantic_failure_case(CORPUS / "professor_lineage17_fixed_tail_framing.json")
    prefix = []
    for index, batch in enumerate(case.checkpoint.batches):
        prefix.extend(shots._compile_semantic_batch(batch.to_semantic_batch(),
            case.checkpoint.units_by_window[index], case.brief, case.timeline, prefix, index))
    batch = case.corrected_candidate.to_semantic_batch()
    intent = batch.shots[0]
    shape = [{"target_beat_id": intent.beat_id, "shots": [{
        "beat_id": intent.beat_id, "first_unit_id": intent.first_unit_id,
        "last_unit_id": intent.last_unit_id}]}]
    brief = case.brief.model_copy(update={"channel": case.brief.channel.model_copy(
        update={"max_non_diagram_scene_appearances": 2})})
    constraints = shots._repair_slot_constraints(batch, shape, brief, prefix, case.timeline, case.failed_units)
    exhausted = constraints[0]["exhausted_non_grid_reference_ids"]
    assert exhausted
    assert not set(exhausted).intersection(constraints[0]["available_reference_ids"])
    content = shots.SemanticRepairContent.model_validate(intent.model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"}))
    invalid = content.model_copy(update={"continuity": "edit", "reference_id": exhausted[0]})
    with pytest.raises(ValueError, match="exhausted scene reference"):
        shots._bind_repair_content(shots.SemanticRepairBatch(shots=[invalid]), shape, constraints)
    fresh = content.model_copy(update={"continuity": "new", "reference_id": None,
        "entity_ids": ["fresh_subject_01"], "subject": "A fresh subject",
        "visible_state": "The fresh subject waits", "setting": "A grounded room"})
    patch = shots._bind_repair_content(shots.SemanticRepairBatch(shots=[fresh]), shape, constraints)
    assert patch.replacements[0].shots[0].reference_id is None
    corrected = batch.model_copy(update={"shots": patch.replacements[0].shots + batch.shots[1:]})
    assert shots._compile_semantic_batch(corrected, case.failed_units, brief, case.timeline, prefix, 2)


def test_fixed_tail_migration_archives_and_reopens_only_affected_suffix(tmp_path):
    case = load_semantic_failure_case(CORPUS / "professor_lineage17_fixed_tail_framing.json")
    path = tmp_path / "shot_plan.semantic.partial.json"
    batches = [b.to_semantic_batch() for b in case.checkpoint.batches]
    batches.append(case.failed_candidate.to_semantic_batch())
    windows = [tuple(window) for window in case.checkpoint.windows]
    shots._save_semantic_partial_plan(path, case.brief, case.timeline, windows, batches)
    old = json.loads(path.read_text(encoding="utf-8"))
    old.update(planner_version=17, compiler_version=8)
    path.write_text(json.dumps(old), encoding="utf-8")
    index, accepted, compiled = shots._load_semantic_partial_plan(path, case.brief, case.timeline, windows)
    assert index == len(accepted) == 2
    assert len(compiled) == 7
    archived = list((tmp_path / "planner_rejections").glob("*.json"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text(encoding="utf-8")) == old
    assert json.loads(path.read_text(encoding="utf-8"))["next_window"] == 2


def compile_corrected(case):
    return shots._compile_semantic_batch(
        case.corrected_candidate.to_semantic_batch(),
        case.failed_units,
        case.brief,
        case.timeline,
        [],
        0,
    )


def test_mandatory_grid_compiles_truthful_mode_without_fake_variety():
    case = countdown_case()
    batch = case.corrected_candidate.to_semantic_batch()
    batch = batch.model_copy(update={"shots": [intent.model_copy(update={
        "visual_mode": "kinetic_type", "beat_kind": "instruction"}) for intent in batch.shots]})
    compiled = shots._compile_semantic_batch(batch, case.failed_units, case.brief, case.timeline, [], 0)
    assert [shot.visual_mode for shot in compiled] == ["challenge_ui"] * 3
    shots.validate_plan(full_plan(case, compiled), case.timeline, case.brief)


def test_mandatory_grid_does_not_consume_next_window_mode_budget():
    case = countdown_case()
    prefix = compile_corrected(case)
    timeline = {**case.timeline, "total_frames": 600, "spans": case.timeline["spans"] + [
        {"index": 3, "start_frame": 450, "end_frame": 600, "text": "Next attention task"}]}
    unit = shots.NarrationUnit(unit_id="u450_600", start_frame=450, end_frame=600, text="Next attention task")
    intent = shots.SemanticShotIntent(beat_id="next_task", first_unit_id=unit.unit_id, last_unit_id=unit.unit_id,
        visual_mode="challenge_ui", beat_kind="instruction", semantic_link="instruction",
        viewer_takeaway="Focus on a single point", subject="A plain local canvas",
        visible_state="A fixation point appears", setting="A clean studio backdrop",
        framing="diagram", composition="A single fixation point", entity_ids=["canvas_99"],
        continuity="new", reference_id=None, graphic=shots.SemanticGraphic(template="focus_sweep", primary_text="Focus"))
    compiled = shots._compile_semantic_batch(shots.SemanticShotBatch(shots=[intent]), [unit], case.brief, timeline, prefix, 1)
    assert compiled[0].start_frame == 450


def full_plan(case, compiled):
    return shots.ShotPlan(
        version=3,
        shots=compiled,
        brief_sha256=fingerprint(case.brief),
        timeline_sha256=fingerprint(case.timeline),
        fps=30,
        total_frames=450,
        editorial_policy=shots.resolve_editorial_policy(case.brief),
    )


def test_countdown_cutaway_is_addressed_before_prefix_validation():
    result = replay_semantic_failure_case(countdown_case())
    assert result.observed_boundary == "semantic_compiler"
    assert result.issues[0].beat_ids == ["beat_2_curiosity"]
    assert result.issues[0].code == "NARRATION_EVENT_COUNTDOWN_COVERAGE"
    assert result.corrected_boundary == "accepted"
    assert result.late_validator_escape is None


def test_countdown_repair_slot_binds_required_graphic():
    case = countdown_case()
    batch = case.failed_candidate.to_semantic_batch()
    intent = batch.shots[1]
    shape = [
        {
            "target_beat_id": intent.beat_id,
            "shots": [
                {
                    "beat_id": intent.beat_id,
                    "first_unit_id": intent.first_unit_id,
                    "last_unit_id": intent.last_unit_id,
                }
            ],
        }
    ]
    constraints = shots._repair_slot_constraints(
        batch,
        shape,
        case.brief,
        [],
        case.timeline,
        case.failed_units,
    )
    assert constraints[0]["required_graphic_template"] == "schulte_challenge"
    content = shots.SemanticRepairContent.model_validate(
        intent.model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"})
    )
    with pytest.raises(ValueError, match="requires graphic.template=schulte_challenge"):
        shots._bind_repair_content(shots.SemanticRepairBatch(shots=[content]), shape, constraints)


@pytest.mark.parametrize("transport_abort", [False, True])
def test_critic_rejection_reopens_completed_checkpoint(tmp_path, monkeypatch, transport_abort):
    case = countdown_case()
    batch = case.corrected_candidate.to_semantic_batch()
    plan = full_plan(case, compile_corrected(case))
    shots._save_semantic_partial_plan(
        tmp_path / "shot_plan.semantic.partial.json",
        case.brief,
        case.timeline,
        [(0, 450)],
        [batch],
    )
    decisions = [
        shots.EditorialShotDecision(
            shot_id=shot.shot_id,
            semantic_match=2 if i == 1 else 4,
            takeaway_match=4,
            visual_specificity=4,
            verdict="reject" if i == 1 else "accept",
            rationale="Make the local rule more specific",
        )
        for i, shot in enumerate(plan.shots)
    ]
    review = shots.EditorialReview(plan_sha256=fingerprint(plan), approved=False, shots=decisions)
    (tmp_path / "editorial_review.json").write_text(review.model_dump_json(), encoding="utf-8")
    changed = batch.model_copy(deep=True)
    changed.shots[1].viewer_takeaway = "Revised narration-specific explanation"
    changed.shots[1].graphic.primary_text = "Revised local instruction"
    calls = []

    def request(prompt, ask, model, **kwargs):
        calls.append(prompt)
        if transport_abort:
            raise RuntimeError("Interrupted transport")
        return model.model_validate(changed.model_dump())

    monkeypatch.setattr(shots, "request_json", request)
    if transport_abort:
        with pytest.raises(RuntimeError, match="Interrupted transport"):
            shots._plan_semantic_windows(
                tmp_path,
                case.brief,
                case.timeline,
                [(0, 450)],
                lambda _: "",
                "Prior critic rejection",
            )
        assert not (tmp_path / "shot_plan.semantic.partial.json").exists()
        assert list((tmp_path / "editorial_rejections").glob("semantic-*.json"))
        return
    planned, _ = shots._plan_semantic_windows(
        tmp_path,
        case.brief,
        case.timeline,
        [(0, 450)],
        lambda _: "",
        "Prior critic rejection",
    )
    assert len(calls) == 1
    assert "Prior critic rejection" in calls[0]
    assert fingerprint(full_plan(case, planned)) != fingerprint(plan)
    assert list((tmp_path / "editorial_rejections").glob("semantic-*.json"))


def test_incomplete_critic_coverage_is_repaired_before_publication(tmp_path, monkeypatch):
    case = countdown_case()
    plan = full_plan(case, compile_corrected(case))
    decisions = [
        shots.EditorialShotDecision(
            shot_id=shot.shot_id,
            semantic_match=4,
            takeaway_match=4,
            visual_specificity=4,
            verdict="accept",
            rationale="Narration-specific local instruction",
        )
        for shot in plan.shots
    ]
    incomplete = shots.EditorialReview(
        plan_sha256=fingerprint(plan), approved=True, shots=decisions[:1]
    )
    complete = incomplete.model_copy(update={"shots": decisions})
    calls = []

    def request(prompt, ask, model, **kwargs):
        calls.append(kwargs)
        return incomplete if len(calls) == 1 else complete

    monkeypatch.setattr(shots, "request_json", request)
    review = shots.ensure_editorial_review(tmp_path, plan, case.timeline, case.brief, lambda _: "")
    review.assert_approved(plan)
    assert len(calls) == 2
    assert "every shot" in calls[1]["repair_error"]
    assert (
        shots.EditorialReview.model_validate_json(
            (tmp_path / "editorial_review.json").read_text()
        ).shots
        == decisions
    )


def test_edit_cannot_import_an_entity_owned_by_another_scene():
    case = load_semantic_failure_case(CORPUS / "professor_lineage9_recurring_entity.json")
    batch = case.corrected_candidate.to_semantic_batch()
    batch.shots[0] = batch.shots[0].model_copy(
        update={
            "entity_ids": ["alice"],
            "subject": "Alice observes a task",
            "visible_state": "Alice notices a difficulty",
            "setting": "A grounded room",
        }
    )
    batch.shots[1] = batch.shots[1].model_copy(
        update={
            "entity_ids": ["bob"],
            "subject": "Bob compares two options",
            "visible_state": "Bob considers the difference",
            "setting": "A separate room",
        }
    )
    batch.shots[2] = batch.shots[2].model_copy(
        update={
            "entity_ids": ["alice", "bob"],
            "subject": "Alice and Bob",
            "visible_state": "Alice and Bob compare the outcome",
            "setting": "A separate room",
            "continuity": "edit",
            "reference_id": batch.shots[1].beat_id,
        }
    )
    with pytest.raises(shots.SemanticPlanError) as caught:
        shots._compile_semantic_batch(batch, case.failed_units, case.brief, case.timeline, [], 0)
    assert any(
        issue.code == "SEMANTIC_ENTITY_SCENE_MIGRATION"
        and issue.beat_ids == [batch.shots[2].beat_id]
        for issue in caught.value.issues
    )


def test_graphic_composition_cannot_request_generated_typography():
    case = load_semantic_failure_case(CORPUS / "professor_lineage9_recurring_entity.json")
    batch = case.corrected_candidate.to_semantic_batch()
    intent = batch.shots[1]
    batch.shots[1] = intent.model_copy(
        update={
            "graphic": shots.SemanticGraphic(template="kinetic_type", primary_text="Local copy"),
            "composition": "Readable text printed beside the plain canvas",
        }
    )
    with pytest.raises(shots.SemanticPlanError) as caught:
        shots._compile_semantic_batch(batch, case.failed_units, case.brief, case.timeline, [], 0)
    assert any(
        issue.beat_ids == [intent.beat_id] and "typography" in issue.requirement.lower()
        for issue in caught.value.issues
    )


def test_unreplayed_recorded_escape_blocks_live_readiness(tmp_path):
    corpus = tmp_path / "corpus"
    shutil.copytree(CORPUS, corpus)
    (corpus / "professor_lineage16_countdown_coverage.json").unlink()
    report = build_failure_intelligence_report(
        corpus, corpus / "evidence/professor_lineages_8_19.json"
    )
    assert report.replay_corpus_ready
    assert report.late_validator_escapes == ["professor_lineage16_countdown_escape"]
    assert report.bounded_live_requests_allowed == 0
    assert not report.ready_for_one_bounded_live_request
