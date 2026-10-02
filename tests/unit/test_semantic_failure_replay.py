from pathlib import Path

from youtube_automation.production.failure_replay import (
    SanitizedSemanticIntent,
    build_failure_intelligence_report,
    load_semantic_failure_case,
    replay_semantic_failure_case,
    replay_semantic_failure_corpus,
    semantic_validator_audit,
)
from youtube_automation.production.shots import (
    NarrationUnit,
    SemanticIssue,
    narration_bound_visual_events,
)

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "semantic_failures"
    / "professor_lineage10_schulte_intro.json"
)
CORPUS = FIXTURE.parent
LIVE_EVIDENCE = CORPUS / "evidence" / "professor_lineages_8_16.json"


def test_lineage10_schulte_failure_replays_at_the_addressable_compiler_boundary():
    result = replay_semantic_failure_case(FIXTURE)

    assert result.case_id == "professor_lineage10_schulte_intro"
    assert result.checkpoint_batches == 2
    assert result.checkpoint_shots == 7
    assert result.observed_boundary == "semantic_compiler"
    assert [issue.code for issue in result.issues] == ["NARRATION_EVENT_TOPOLOGY"]
    assert result.issues[0].beat_ids == ["beat_1_problem"]


def test_schulte_obligation_activates_from_explicit_narration_only():
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [
            {
                "index": 0,
                "start_frame": 0,
                "end_frame": 300,
                "text": "A general attention exercise without a named grid",
            }
        ],
    }

    assert narration_bound_visual_events(timeline) == []

    timeline["spans"][0]["text"] = "The Schulte exercise begins now"
    event = narration_bound_visual_events(timeline)[0]
    assert event.preset == "schulte_6x6"
    assert event.graphic_template == "schulte_challenge"
    assert event.earliest_start_frame == 0
    assert event.latest_start_frame == 30


def test_professor_failure_corpus_replays_every_distinct_boundary_offline():
    report = replay_semantic_failure_corpus(CORPUS)

    assert report.case_ids == [
        "professor_lineage10_schulte_intro",
        "professor_lineage14_episode_visual_mode",
        "professor_lineage15_visible_mechanical_family",
        "professor_lineage16_countdown_coverage",
        "professor_lineage8_entity_visibility",
        "professor_lineage9_exact_repair_cardinality",
        "professor_lineage9_recurring_entity",
    ]
    assert report.observed_boundaries == {
        "professor_lineage10_schulte_intro": "semantic_compiler",
        "professor_lineage14_episode_visual_mode": "request_contract",
        "professor_lineage15_visible_mechanical_family": "semantic_compiler",
        "professor_lineage16_countdown_coverage": "semantic_compiler",
        "professor_lineage8_entity_visibility": "semantic_compiler",
        "professor_lineage9_exact_repair_cardinality": "request_contract",
        "professor_lineage9_recurring_entity": "semantic_compiler",
    }
    assert report.accepted_checkpoint_batches == 2
    assert report.late_validator_escapes == []
    assert report.ready


def test_lineage14_global_only_visual_mode_replays_at_the_request_contract():
    result = replay_semantic_failure_case(
        CORPUS / "professor_lineage14_episode_visual_mode.json"
    )

    assert result.observed_boundary == "request_contract"
    assert result.issues[0].code == "SCHEMA_EPISODE_VISUAL_MODE"
    assert result.issues[0].beat_ids == ["beat_schulte_purpose"]
    assert result.corrected_boundary == "accepted"
    assert result.late_validator_escape is None


def test_lineage15_local_canvas_accepts_editorial_mechanism_label():
    result = replay_semantic_failure_case(
        CORPUS / "professor_lineage15_visible_mechanical_family.json"
    )
    assert result.observed_boundary == "semantic_compiler"
    assert result.issues[0].code == "SEMANTIC_RECORD_INVALID"
    assert "mechanical_cognition" in result.issues[0].requirement
    assert result.corrected_boundary == "accepted"
    assert result.late_validator_escape is None


def test_literalized_visual_is_addressable_before_final_validation():
    case = load_semantic_failure_case(
        CORPUS / "professor_lineage8_entity_visibility.json"
    )
    assert case.corrected_candidate is not None
    candidate = case.corrected_candidate.model_copy(deep=True)
    candidate.shots[0] = candidate.shots[0].model_copy(
        update={
            "entity_ids": ["professional"],
            "subject": "A visible professional literally transformed into a block of ice",
            "visible_state": "The professional is frozen in place",
        }
    )
    probe = case.model_copy(
        update={
            "failed_candidate": candidate,
            "corrected_candidate": None,
            "expected_issue": SemanticIssue(
                beat_ids=["beat_1_problem"],
                code="SEMANTIC_RECORD_INVALID",
                requirement="Literalized figurative transformations are forbidden",
            ),
        }
    )

    result = replay_semantic_failure_case(probe)

    assert result.observed_boundary == "semantic_compiler"
    assert result.late_validator_escape is None
    assert "literalize" in result.issues[0].requirement.lower()


def test_generated_typography_is_addressable_before_final_validation():
    case = load_semantic_failure_case(
        CORPUS / "professor_lineage8_entity_visibility.json"
    )
    assert case.corrected_candidate is not None
    candidate = case.corrected_candidate.model_copy(deep=True)
    candidate.shots[0] = candidate.shots[0].model_copy(
        update={
            "entity_ids": ["poster"],
            "subject": "A visible poster with readable text",
            "visible_state": "Written words fill the poster",
        }
    )
    probe = case.model_copy(
        update={
            "failed_candidate": candidate,
            "corrected_candidate": None,
            "expected_issue": SemanticIssue(
                beat_ids=["beat_1_problem"],
                code="SEMANTIC_RECORD_INVALID",
                requirement="Generated typography must become a deterministic local graphic",
            ),
        }
    )

    result = replay_semantic_failure_case(probe)

    assert result.observed_boundary == "semantic_compiler"
    assert result.late_validator_escape is None
    assert "typography" in result.issues[0].requirement.lower()


def test_channel_forbidden_motif_is_addressable_before_final_validation():
    case = load_semantic_failure_case(
        CORPUS / "professor_lineage8_entity_visibility.json"
    )
    assert case.corrected_candidate is not None
    channel = case.brief.channel.model_copy(
        update={"forbidden_motifs": ["red hourglass"]}
    )
    brief = case.brief.model_copy(update={"channel": channel})
    candidate = case.corrected_candidate.model_copy(deep=True)
    candidate.shots[0] = candidate.shots[0].model_copy(
        update={
            "entity_ids": ["red_hourglass"],
            "subject": "A visible red hourglass",
            "visible_state": "The red hourglass stands motionless",
        }
    )
    probe = case.model_copy(
        update={
            "brief": brief,
            "failed_candidate": candidate,
            "corrected_candidate": None,
            "expected_issue": SemanticIssue(
                beat_ids=["beat_1_problem"],
                code="SEMANTIC_RECORD_INVALID",
                requirement="Channel-forbidden motifs must be repaired before final validation",
            ),
        }
    )

    result = replay_semantic_failure_case(probe)

    assert result.observed_boundary == "semantic_compiler"
    assert result.late_validator_escape is None
    assert "forbidden motif" in result.issues[0].requirement.lower()


def test_adjacent_reuse_repetition_is_addressable_before_final_validation():
    case = load_semantic_failure_case(
        CORPUS / "professor_lineage8_entity_visibility.json"
    )
    assert case.corrected_candidate is not None
    candidate = case.corrected_candidate.model_copy(deep=True)
    first = candidate.shots[0].model_copy(
        update={
            "entity_ids": ["worker"],
            "subject": "A visible worker",
            "visible_state": "The worker studies one task",
            "setting": "A grounded room",
            "framing": "wide",
        }
    )
    candidate.shots[0] = first
    candidate.shots[1] = candidate.shots[1].model_copy(
        update={
            "entity_ids": first.entity_ids,
            "subject": first.subject,
            "visible_state": first.visible_state,
            "setting": first.setting,
            "framing": first.framing,
            "continuity": "reuse",
            "reference_id": first.beat_id,
        }
    )
    probe = case.model_copy(
        update={
            "failed_candidate": candidate,
            "corrected_candidate": None,
            "expected_issue": SemanticIssue(
                beat_ids=["beat_2_curiosity"],
                code="SEMANTIC_PREFIX_REPETITION",
                requirement="Adjacent reuse must change framing or local meaning",
            ),
        }
    )

    result = replay_semantic_failure_case(probe)

    assert result.observed_boundary == "semantic_compiler"
    assert result.late_validator_escape is None
    assert result.issues[0].code == "SEMANTIC_PREFIX_REPETITION"
    assert result.issues[0].beat_ids == ["beat_2_curiosity"]


def test_scene_repetition_limit_is_addressable_before_final_validation():
    case = load_semantic_failure_case(
        CORPUS / "professor_lineage8_entity_visibility.json"
    )
    assert case.corrected_candidate is not None
    channel = case.brief.channel.model_copy(
        update={"max_non_diagram_scene_appearances": 1}
    )
    brief = case.brief.model_copy(update={"channel": channel})
    candidate = case.corrected_candidate.model_copy(deep=True)
    first = candidate.shots[0].model_copy(
        update={
            "entity_ids": ["worker"],
            "subject": "A visible worker",
            "visible_state": "The worker studies one task",
            "setting": "A grounded room",
            "framing": "wide",
        }
    )
    candidate.shots[0] = first
    candidate.shots[1] = candidate.shots[1].model_copy(
        update={
            "entity_ids": first.entity_ids,
            "subject": first.subject,
            "visible_state": first.visible_state,
            "setting": first.setting,
            "framing": "close_up",
            "continuity": "reuse",
            "reference_id": first.beat_id,
        }
    )
    probe = case.model_copy(
        update={
            "brief": brief,
            "failed_candidate": candidate,
            "corrected_candidate": None,
            "expected_issue": SemanticIssue(
                beat_ids=["beat_2_curiosity"],
                code="SEMANTIC_SCENE_REPETITION",
                requirement="Scene appearances must remain within the channel limit",
            ),
        }
    )

    result = replay_semantic_failure_case(probe)

    assert result.observed_boundary == "semantic_compiler"
    assert result.late_validator_escape is None
    assert result.issues[0].code == "SEMANTIC_SCENE_REPETITION"


def test_visual_family_repetition_is_addressable_before_final_validation():
    case = load_semantic_failure_case(
        CORPUS / "professor_lineage8_entity_visibility.json"
    )
    assert case.corrected_candidate is not None
    channel = case.brief.channel.model_copy(
        update={
            "forbidden_visual_families": [],
            "repetition_limited_visual_families": ["generic_desk_task"],
            "max_visual_family_repetitions": 1,
        }
    )
    brief = case.brief.model_copy(update={"channel": channel})
    candidate = case.corrected_candidate.model_copy(deep=True)
    candidate.shots[0] = candidate.shots[0].model_copy(
        update={
            "entity_ids": ["worker_one"],
            "subject": "A visible worker at a desk with scattered notes",
            "visible_state": "The worker rubs their temples",
            "setting": "A home office",
        }
    )
    candidate.shots[1] = candidate.shots[1].model_copy(
        update={
            "entity_ids": ["worker_two"],
            "subject": "A second visible worker at a desk with scattered notes",
            "visible_state": "The worker looks down at paperwork",
            "setting": "Another home office",
        }
    )
    probe = case.model_copy(
        update={
            "brief": brief,
            "failed_candidate": candidate,
            "corrected_candidate": None,
            "expected_issue": SemanticIssue(
                beat_ids=["beat_2_curiosity"],
                code="SEMANTIC_VISUAL_FAMILY_REPETITION",
                requirement="Visual family repetition must remain within the channel limit",
            ),
        }
    )

    result = replay_semantic_failure_case(probe)

    assert result.observed_boundary == "semantic_compiler"
    assert result.late_validator_escape is None
    assert result.issues[0].code == "SEMANTIC_VISUAL_FAMILY_REPETITION"


def test_final_framing_diversity_is_addressable_in_the_last_window():
    case = load_semantic_failure_case(
        CORPUS / "professor_lineage8_entity_visibility.json"
    )
    assert case.corrected_candidate is not None
    ranges = [(0, 90), (90, 180), (180, 270), (270, 480), (480, 690), (690, 900)]
    units = [
        NarrationUnit(
            unit_id=f"u{start}_{end}",
            start_frame=start,
            end_frame=end,
            text=f"Sanitized narration {index}",
        )
        for index, (start, end) in enumerate(ranges)
    ]
    timeline = {
        "fps": 30,
        "total_frames": 900,
        "spans": [
            {
                "index": index,
                "start_frame": start,
                "end_frame": end,
                "text": f"Sanitized narration {index}",
            }
            for index, (start, end) in enumerate(ranges)
        ],
    }
    candidate = case.corrected_candidate.model_copy(deep=True)
    candidate.shots.extend(
        [
            SanitizedSemanticIntent(
                beat_id=f"beat_{index}",
                first_unit_id=unit.unit_id,
                visual_mode="human_context" if index % 2 else "comparison",
                beat_kind="example" if index % 2 else "contrast",
                framing="wide" if index % 2 else "close_up",
                entity_ids=[f"object_{index}"],
                subject=f"A visible object {index}",
                visible_state=f"The object {index} shows a distinct state",
                setting="A grounded room",
                composition=f"Distinct composition {index}",
            )
            for index, unit in enumerate(units[3:], start=4)
        ]
    )
    candidate.shots[0] = candidate.shots[0].model_copy(update={"framing": "wide"})
    candidate.shots[1] = candidate.shots[1].model_copy(update={"framing": "close_up"})
    candidate.shots[2] = candidate.shots[2].model_copy(update={"framing": "wide"})
    checkpoint = case.checkpoint.model_copy(
        update={"windows": [(0, 900)], "next_window": 0}
    )
    probe = case.model_copy(
        update={
            "timeline": timeline,
            "checkpoint": checkpoint,
            "failed_units": units,
            "failed_candidate": candidate,
            "corrected_candidate": None,
            "expected_issue": SemanticIssue(
                beat_ids=["beat_4", "beat_5", "beat_6"],
                code="SEMANTIC_FRAMING_DIVERSITY",
                requirement="The complete plan requires at least three distinct framings",
            ),
        }
    )

    result = replay_semantic_failure_case(probe)

    assert result.observed_boundary == "semantic_compiler"
    assert result.late_validator_escape is None
    assert result.issues[0].code == "SEMANTIC_FRAMING_DIVERSITY"


def test_validator_audit_assigns_every_final_rule_to_an_earlier_owner():
    audit = semantic_validator_audit()

    assert {entry.rule_group for entry in audit.entries} == {
        "input_lineage_and_timing",
        "compiled_shot_schema",
        "semantic_record_rules",
        "prefix_and_episode_budgets",
        "narration_bound_events",
        "aesthetic_judgment",
    }
    assert audit.late_validator_rule_groups == []
    assert audit.ready


def test_failure_intelligence_report_is_green_before_one_bounded_live_request():
    report = build_failure_intelligence_report(CORPUS, LIVE_EVIDENCE)

    assert report.live_runs == 8
    assert report.live_attempts == 8
    assert report.accepted_windows == 2
    assert report.live_attempts_per_accepted_window == 4
    assert report.repair_count == 42
    assert report.provider_refusals == 3
    assert report.quota_switches == 0
    assert report.checkpoint_progress == "2/4 windows, 7 shots"
    assert report.repeated_failure_codes == {"SEMANTIC_RECORD_INVALID": 3}
    assert report.late_validator_escapes == []
    assert report.validator_audit_ready
    assert report.replay_corpus_ready
    assert report.next_planner_version == 17
    assert report.next_compiler_version == 8
    assert report.ready_for_one_bounded_live_request
