import json
from copy import deepcopy

import pytest

from youtube_automation.core.utils import atomic_write_json
from youtube_automation.production.contracts import (
    Analysis,
    Brief,
    Channel,
    EpisodeVisualStrategy,
    fingerprint,
)
from youtube_automation.production.flow import prepare_flow
from youtube_automation.production.shots import (
    SCHULTE_6X6,
    SEMANTIC_PLANNER_VERSION,
    SHOT_COMPILER_VERSION,
    EditorialReview,
    NarrationUnit,
    SemanticIssue,
    SemanticPlanError,
    SemanticRepairBatch,
    SemanticReplacement,
    SemanticShotBatch,
    SemanticShotIntent,
    SemanticShotPatch,
    Shot,
    ShotBatch,
    _bind_repair_content,
    _compile_semantic_batch,
    _content_repair_patch_shape,
    _hook_repair_partition,
    _hook_repair_patch_shape,
    _load_semantic_partial_plan,
    _merge_semantic_patch,
    _narration_units,
    _plan_semantic_windows,
    _planning_windows,
    _save_semantic_partial_plan,
    _semantic_issues,
    _validate_hook_repair_partition,
    ensure_shot_plan,
    migrate_semantic_checkpoint,
)

HOOK_IDS = ("problem", "gap", "promise")


def test_later_window_context_does_not_reseed_opening_hook_goals():
    from youtube_automation.production.shots import _semantic_planning_prompt

    brief = _brief()
    units = [NarrationUnit(unit_id="u900_1050", start_frame=900, end_frame=1050,
                           text="Enjoyable exercises challenge your intelligence")]
    opening = _semantic_planning_prompt(brief, units, [], [], 0, "")
    later = _semantic_planning_prompt(brief, units, [], [], 1, "")
    assert "A concrete attention failure matters" in opening
    assert '"hook_microbeats"' in opening
    assert "A concrete attention failure matters" not in later
    assert '"hook_microbeats"' not in later
    assert "Do not recycle opening-hook goals" in later
    assert "Enjoyable exercises challenge your intelligence" in later


def _brief(*, version: int = 3, source: str = "semantic narration") -> Brief:
    channel = Channel(
        version=version,
        channel_id="professor",
        name="Professor",
        audience="Arabic-speaking adults",
        language="Arabic",
        dialect="MSA",
        voice="achird",
        tone="clear and evidence-conscious",
        style="warm editorial illustration",
        visual_directives=["Use narration-specific scenes and restrained local graphics"],
        forbidden_motifs=["generic office focus portrait"],
        allowed_treatments=["subject_scene", "detail", "comparison"],
        humor="none",
    )
    analysis = Analysis(
        topics=["attention"],
        claim_basis="factual",
        form="explanation",
        proposition="Attention changes can be made visible",
        narrative_strategy="Move from a concrete problem to a practical demonstration",
        treatments=["subject_scene", "detail", "comparison"],
        rationale="Each visual must prove its active narration beat",
    )
    source_sha256 = fingerprint(source)
    if version == 2:
        return Brief(
            version=2,
            source_sha256=source_sha256,
            profile_sha256=fingerprint(channel),
            channel=channel,
            analysis=analysis,
        )
    strategy = EpisodeVisualStrategy(
        source_sha256=source_sha256,
        topic="Attention challenge",
        viewer_question="Where does attention slip?",
        central_promise="See the gap and understand the challenge",
        evidence_mode="demonstrative",
        emotional_arc=["recognition", "curiosity", "agency"],
        hook_archetype="cold_open_challenge",
        hook_microbeats=[
            {
                "beat_id": "problem",
                "function": "problem",
                "duration_seconds": 3,
                "viewer_takeaway": "A concrete attention failure matters",
                "visual_mode": "human_context",
            },
            {
                "beat_id": "gap",
                "function": "curiosity",
                "duration_seconds": 3,
                "viewer_takeaway": "The hidden gap can be exposed",
                "visual_mode": "kinetic_type",
            },
            {
                "beat_id": "promise",
                "function": "promise",
                "duration_seconds": 3,
                "viewer_takeaway": "A designed challenge will reveal it",
                "visual_mode": "challenge_ui",
                "local_ui": ["timer"],
            },
        ],
        visual_modes=["human_context", "kinetic_type", "challenge_ui", "comparison"],
        local_ui_kit=["timer", "cards", "focus_sweep"],
        pacing="Three concise hook beats followed by evidence-led explanation",
        motion_grammar=["Animate only meaningful state changes"],
    )
    return Brief(
        version=3,
        source_sha256=source_sha256,
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
        visual_strategy=strategy,
    )


def _timeline(words: list[str], *, seconds_per_word: float = 3.0, fps: int = 10) -> dict:
    canonical_words = []
    spans = []
    for index, text in enumerate(words):
        start = index * seconds_per_word
        end = (index + 1) * seconds_per_word
        canonical_words.append({"id": index, "text": text, "start": start, "end": end})
        spans.append(
            {
                "index": index,
                "start_frame": round(start * fps),
                "end_frame": round(end * fps),
                "start_word_id": index,
                "end_word_id": index + 1,
                "text": text,
            }
        )
    return {
        "fps": fps,
        "total_frames": round(len(words) * seconds_per_word * fps),
        "spans": spans,
        "words": canonical_words,
    }


def _intent(
    beat_id: str,
    first_unit_id: str,
    last_unit_id: str | None = None,
    *,
    visual_mode: str = "human_context",
    framing: str = "wide",
    continuity: str = "new",
    reference_id: str | None = None,
    subject: str | None = None,
    visible_state: str | None = None,
    setting: str | None = None,
    composition: str | None = None,
    entity_ids: list[str] | None = None,
    beat_kind: str = "claim",
    graphic: dict | None = None,
) -> SemanticShotIntent:
    return SemanticShotIntent(
        beat_id=beat_id,
        first_unit_id=first_unit_id,
        last_unit_id=last_unit_id or first_unit_id,
        visual_mode=visual_mode,
        beat_kind=beat_kind,
        semantic_link="direct",
        viewer_takeaway=f"The viewer understands {beat_id}",
        subject=subject or f"A narration-specific subject for {beat_id}",
        visible_state=visible_state or f"A visible state unique to {beat_id}",
        setting=setting or f"A grounded setting for {beat_id}",
        framing=framing,
        composition=composition or f"A distinct composition for {beat_id}",
        entity_ids=entity_ids or [f"entity_{beat_id}"],
        continuity=continuity,
        reference_id=reference_id,
        graphic=graphic,
    )


def _batch_for_units(
    units: list[NarrationUnit], beat_ids: tuple[str, ...] = HOOK_IDS
) -> SemanticShotBatch:
    modes = ("human_context", "kinetic_type", "comparison")
    framings = ("wide", "close_up", "insert")
    beat_kinds = ("claim", "question", "reveal")
    return SemanticShotBatch(
        shots=[
            _intent(
                beat_id,
                unit.unit_id,
                visual_mode=modes[index % len(modes)],
                framing=framings[index % len(framings)],
                beat_kind=beat_kinds[index % len(beat_kinds)],
            )
            for index, (beat_id, unit) in enumerate(zip(beat_ids, units, strict=True))
        ]
    )


def _issue_matching(issues, phrase: str):
    return next(issue for issue in issues if phrase in issue.requirement)


def _write_run(root, brief: Brief, timeline: dict, raw: str) -> None:
    (root / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    atomic_write_json(str(root / "episode_brief.json"), brief.model_dump(mode="json"))
    atomic_write_json(str(root / "timeline.json"), timeline)


def _review_json(shot_ids: list[str]) -> str:
    review = EditorialReview(
        plan_sha256="0" * 64,
        approved=True,
        shots=[
            {
                "shot_id": shot_id,
                "semantic_match": 5,
                "takeaway_match": 5,
                "visual_specificity": 5,
                "verdict": "accept",
                "rationale": "The visible state directly proves the narration beat",
            }
            for shot_id in shot_ids
        ],
    )
    return review.model_dump_json()


class _SemanticAsk:
    def __init__(self, batches: list[SemanticShotBatch], shot_ids: list[str]):
        self.batches = list(batches)
        self.shot_ids = shot_ids
        self.planning_prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        if "independent YouTube storyboard critic" in prompt:
            return _review_json(self.shot_ids)
        self.planning_prompts.append(prompt)
        if not self.batches:
            raise AssertionError("Unexpected semantic planning request")
        return self.batches.pop(0).model_dump_json()


def test_initial_schema_binds_visual_modes_to_the_episode_palette(tmp_path, monkeypatch):
    from youtube_automation.production import shots as shots_module

    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = _batch_for_units(units, HOOK_IDS)

    def fake_request_json(prompt, ask, model, **kwargs):
        schema = model.model_json_schema()
        item_ref = schema["properties"]["shots"]["items"]["$ref"].split("/")[-1]
        allowed = schema["$defs"][item_ref]["properties"]["visual_mode"]["enum"]
        assert allowed == brief.visual_strategy.visual_modes
        assert schema == json.loads(
            prompt.split("SCHEMA:\n", 1)[1].split("\nCHANNEL POLICY:", 1)[0]
        )
        return model.model_validate(initial.model_dump())

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)
    planned, _ = _plan_semantic_windows(
        tmp_path, brief, timeline, [(0, timeline["total_frames"])], lambda _: "", ""
    )
    assert len(planned) == 3


@pytest.mark.parametrize("route", ["initial", "topology", "content"])
def test_episode_palette_rejects_global_only_modes_in_every_response_contract(route):
    from youtube_automation.production.shots import (
        _episode_semantic_models,
        _exact_semantic_repair_batch_model,
    )

    palette = tuple(_brief().visual_strategy.visual_modes)
    batch_model, patch_model, _ = _episode_semantic_models(palette)
    intent = _intent("purpose", "u0_30", visual_mode="editorial_metaphor").model_dump()
    if route == "initial":
        model = batch_model
        payload = {"shots": [intent]}
        record = payload["shots"][0]
    elif route == "topology":
        model = patch_model
        payload = {"replacements": [{"target_beat_id": "purpose", "shots": [intent]}]}
        record = payload["replacements"][0]["shots"][0]
    else:
        model = _exact_semantic_repair_batch_model(1, palette)
        payload = {
            "shots": [
                {
                    key: value
                    for key, value in intent.items()
                    if key not in {"beat_id", "first_unit_id", "last_unit_id"}
                }
            ]
        }
        record = payload["shots"][0]

    with pytest.raises(ValueError, match="episode palette"):
        model.model_validate(payload)
    record["visual_mode"] = "comparison"
    accepted = model.model_validate(payload)
    assert isinstance(accepted, (SemanticShotBatch, SemanticShotPatch, SemanticRepairBatch))
    mode_schemas = [
        item["properties"]["visual_mode"]
        for item in model.model_json_schema()["$defs"].values()
        if "visual_mode" in item.get("properties", {})
    ]
    assert mode_schemas and all(item["enum"] == list(palette) for item in mode_schemas)


def test_nested_schema_correction_retains_palette_and_compiler_owned_slots(tmp_path):
    brief = _brief(source="one two three four")
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = _batch_for_units(units[:3])
    initial.shots[-1].last_unit_id = units[3].unit_id
    records = [
        _intent(
            "promise",
            units[2].unit_id,
            visual_mode="challenge_ui",
            framing="insert",
            beat_kind="reveal",
        ),
        _intent(
            "continuation",
            units[3].unit_id,
            visual_mode="comparison",
            framing="medium",
            beat_kind="transition",
        ),
    ]
    corrected = {
        "shots": [
            record.model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"})
            for record in records
        ]
    }
    invalid = deepcopy(corrected)
    invalid["shots"][0]["visual_mode"] = "editorial_metaphor"

    class Ask:
        def __init__(self):
            self.repairs = []

        def __call__(self, prompt):
            return initial.model_dump_json()

        def repair_json(self, prompt, error, baseline, latest, schema, context):
            self.repairs.append((error, schema, context))
            return json.dumps(invalid if len(self.repairs) == 1 else corrected)

    ask = Ask()
    planned, _ = _plan_semantic_windows(
        tmp_path, brief, timeline, [(0, timeline["total_frames"])], ask, ""
    )
    assert len(ask.repairs) == 2
    assert "episode palette" in ask.repairs[-1][0]
    assert ask.repairs[0][1:] == ask.repairs[1][1:]
    assert (
        '"allowed_visual_modes": ["human_context", "kinetic_type", "challenge_ui", "comparison"]'
        in ask.repairs[-1][2]
    )
    assert "EPISODE VISUAL MODES:" in ask.repairs[-1][2]
    assert "COMPILER-OWNED REPAIR SLOTS:" in ask.repairs[-1][2]
    assert [shot.subject for shot in planned[:2]] == [shot.subject for shot in initial.shots[:2]]
    assert len(planned) == 4


def test_three_beat_hook_compiles_deterministically_to_nine_seconds():
    brief = _brief()
    timeline = _timeline(["problem words", "gap words", "promise words"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = _batch_for_units(units)

    first = _compile_semantic_batch(batch, units, brief, timeline, [], 0)
    second = _compile_semantic_batch(batch, units, brief, timeline, [], 0)

    assert [shot.model_dump(mode="json") for shot in first] == [
        shot.model_dump(mode="json") for shot in second
    ]
    assert [shot.hook_beat_id for shot in first] == list(HOOK_IDS)
    assert [shot.hook_function for shot in first] == ["problem", "curiosity", "promise"]
    assert first[-1].end_frame / timeline["fps"] == 9


def test_overlong_hook_repairs_only_the_last_hook_record_so_it_can_split():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, framing="wide", beat_kind="claim"),
            _intent(
                "gap",
                units[1].unit_id,
                visual_mode="kinetic_type",
                framing="close_up",
                beat_kind="question",
            ),
            _intent(
                "promise",
                units[2].unit_id,
                units[3].unit_id,
                visual_mode="challenge_ui",
                framing="insert",
                beat_kind="reveal",
            ),
        ]
    )

    with pytest.raises(SemanticPlanError) as caught:
        _compile_semantic_batch(batch, units, brief, timeline, [], 0)

    hook_issue = next(issue for issue in caught.value.issues if issue.code == "HOOK_DURATION")
    assert hook_issue.beat_ids == ["promise"]


def test_hook_duration_repair_expands_to_smallest_repartitionable_suffix():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, framing="wide", beat_kind="claim"),
            _intent(
                "gap",
                units[1].unit_id,
                units[2].unit_id,
                visual_mode="kinetic_type",
                framing="close_up",
                beat_kind="question",
            ),
            _intent(
                "promise",
                units[3].unit_id,
                visual_mode="challenge_ui",
                framing="insert",
                beat_kind="reveal",
            ),
        ]
    )

    with pytest.raises(SemanticPlanError) as caught:
        _compile_semantic_batch(batch, units, brief, timeline, [], 0)

    hook_issue = next(issue for issue in caught.value.issues if issue.code == "HOOK_DURATION")
    assert hook_issue.beat_ids == ["gap", "promise"]


def test_hook_repair_guidance_exposes_one_valid_partition_and_continuation():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent(
                "gap",
                units[1].unit_id,
                units[2].unit_id,
                visual_mode="kinetic_type",
            ),
            _intent("promise", units[3].unit_id, visual_mode="challenge_ui"),
        ]
    )

    partition = _hook_repair_partition(
        batch, {"gap", "promise"}, units, brief, timeline["fps"]
    )

    assert partition == [
        {"beat_id": "gap", "first_unit_id": units[1].unit_id, "last_unit_id": units[1].unit_id},
        {
            "beat_id": "promise",
            "first_unit_id": units[2].unit_id,
            "last_unit_id": units[2].unit_id,
        },
        {
            "beat_id": "promise__continuation",
            "first_unit_id": units[3].unit_id,
            "last_unit_id": units[3].unit_id,
        },
    ]


def test_hook_repair_patch_shape_nests_continuation_under_its_rejected_target():
    partition = [
        {
            "beat_id": "beat_2_curiosity",
            "first_unit_id": "u179_263",
            "last_unit_id": "u179_263",
        },
        {
            "beat_id": "beat_3_promise",
            "first_unit_id": "u263_355",
            "last_unit_id": "u355_444",
        },
        {
            "beat_id": "beat_3_promise__continuation",
            "first_unit_id": "u444_575",
            "last_unit_id": "u444_575",
        },
    ]

    shape = _hook_repair_patch_shape(
        partition, {"beat_2_curiosity", "beat_3_promise"}
    )

    assert shape == [
        {
            "target_beat_id": "beat_2_curiosity",
            "shots": [partition[0]],
        },
        {
            "target_beat_id": "beat_3_promise",
            "shots": partition[1:],
        },
    ]
    assert _hook_repair_patch_shape(partition, {"beat_3_promise"}) == [
        {
            "target_beat_id": "beat_3_promise",
            "shots": partition[1:],
        }
    ]


def test_hook_repair_patch_must_include_every_bound_partition_record():
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    partition = [
        {
            "beat_id": "promise",
            "first_unit_id": units[2].unit_id,
            "last_unit_id": units[2].unit_id,
        },
        {
            "beat_id": "promise__continuation",
            "first_unit_id": units[3].unit_id,
            "last_unit_id": units[3].unit_id,
        },
    ]
    truncated = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent("gap", units[1].unit_id, visual_mode="kinetic_type"),
            _intent("promise", units[2].unit_id, visual_mode="challenge_ui"),
        ]
    )

    with pytest.raises(ValueError, match="exact required hook partition"):
        _validate_hook_repair_partition(truncated, partition)


def test_hook_repair_binds_model_content_to_compiler_owned_slots(tmp_path, monkeypatch):
    from youtube_automation.production import shots as shots_module

    brief = _brief(source="one two three four")
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent(
                "gap",
                units[1].unit_id,
                visual_mode="kinetic_type",
                beat_kind="question",
                framing="close_up",
            ),
            _intent(
                "promise",
                units[2].unit_id,
                units[3].unit_id,
                visual_mode="challenge_ui",
                beat_kind="reveal",
                framing="insert",
            ),
        ]
    )
    semantic_records = [
        _intent(
            "model_cannot_choose_this_id",
            units[2].unit_id,
            visual_mode="challenge_ui",
            beat_kind="reveal",
            framing="insert",
        ).model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"}),
        _intent(
            "model_cannot_choose_continuation_id",
            units[3].unit_id,
            visual_mode="comparison",
            beat_kind="transition",
            framing="medium",
        ).model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"}),
    ]
    repair_prompts = []

    def fake_request_json(prompt, ask, model, **kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        assert model.__name__ == "SemanticRepairBatch"
        repair_prompts.append(prompt)
        return model.model_validate({"shots": semantic_records})

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    shots, _ = _plan_semantic_windows(
        tmp_path, brief, timeline, [(0, timeline["total_frames"])], lambda _: "", ""
    )

    assert len(repair_prompts) == 1
    assert "COMPILER-OWNED REPAIR SLOTS" in repair_prompts[0]
    assert [shot.hook_beat_id for shot in shots] == ["problem", "gap", "promise", None]
    assert [(shot.start_frame, shot.end_frame) for shot in shots[2:]] == [
        (units[2].start_frame, units[2].end_frame),
        (units[3].start_frame, units[3].end_frame),
    ]


def test_sparse_seventy_six_second_timeline_uses_contiguous_bounded_windows():
    timeline = {
        "fps": 10,
        "total_frames": 760,
        "spans": [{"index": 0, "start_frame": 0, "end_frame": 760, "text": "long speech"}],
        "words": [],
    }

    windows = _planning_windows(timeline)

    assert windows[0][0] == 0
    assert windows[-1][1] == 760
    assert all(
        left[1] == right[0]
        for left, right in zip(windows, windows[1:], strict=False)
    )
    assert all(end - start <= 200 for start, end in windows)


def test_narration_units_are_nonempty_and_cut_only_on_word_boundaries():
    timeline = {
        "fps": 10,
        "total_frames": 100,
        "words": [
            {"id": 0, "text": "first", "start": 0.0, "end": 1.0},
            {"id": 1, "text": "long", "start": 1.0, "end": 10.0},
        ],
        "spans": [
            {
                "index": 0,
                "start_frame": 0,
                "end_frame": 45,
                "start_word_id": 0,
                "end_word_id": 2,
                "text": "first long",
            },
            {
                "index": 1,
                "start_frame": 45,
                "end_frame": 100,
                "start_word_id": 1,
                "end_word_id": 2,
                "text": "long",
            },
        ],
    }

    units = _narration_units(timeline, 0, 100)
    word_boundaries = {10, 100}

    assert all(unit.text.strip() for unit in units)
    assert {unit.end_frame for unit in units} <= word_boundaries


def test_unknown_unit_rejects_only_the_record_that_names_it():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, "unknown_unit"),
            _intent("gap", units[0].unit_id, units[1].unit_id),
            _intent("promise", units[2].unit_id),
        ]
    )

    issue = _issue_matching(_semantic_issues(batch, units, brief, 10, {}), "ordered supplied")

    assert issue.beat_ids == ["problem"]


def test_gap_marks_the_smallest_boundary_record_for_repair():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, framing="wide"),
            _intent("gap", units[2].unit_id),
            _intent("promise", units[3].unit_id),
        ]
    )

    issue = _issue_matching(_semantic_issues(batch, units, brief, 10, {}), "next uncovered")

    assert issue.beat_ids == ["gap"]


def test_overlap_marks_the_smallest_boundary_record_for_repair():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, units[1].unit_id),
            _intent("gap", units[1].unit_id, units[2].unit_id),
            _intent("promise", units[3].unit_id),
        ]
    )

    issue = _issue_matching(_semantic_issues(batch, units, brief, 10, {}), "next uncovered")

    assert issue.beat_ids == ["gap"]


def test_duplicate_beat_id_is_a_record_level_semantic_issue():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent("problem", units[1].unit_id),
            _intent("promise", units[2].unit_id),
        ]
    )

    issue = _issue_matching(_semantic_issues(batch, units, brief, 10, {}), "unique")

    assert issue.beat_ids == ["problem"]


def test_visual_mode_outside_episode_allowlist_is_rejected():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = _batch_for_units(units)
    batch.shots[1].visual_mode = "environmental_detail"

    issue = _issue_matching(_semantic_issues(batch, units, brief, 10, {}), "allowlist")

    assert issue.beat_ids == ["gap"]


def test_framing_budget_marks_only_the_first_record_that_can_break_the_run():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, framing="wide"),
            _intent("gap", units[1].unit_id, framing="wide"),
            _intent("promise", units[2].unit_id, framing="wide"),
            _intent("after_hook", units[3].unit_id, framing="wide"),
        ]
    )

    issues = _semantic_issues(batch, units, brief, timeline["fps"], {})
    framing = [issue for issue in issues if "framing" in issue.requirement.casefold()]

    assert [issue.beat_ids for issue in framing] == [["promise"]]


def test_visual_mode_budget_marks_only_the_first_record_that_can_break_the_run():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, framing="wide"),
            _intent("gap", units[1].unit_id, framing="close_up"),
            _intent("promise", units[2].unit_id, framing="insert"),
            _intent("after_hook", units[3].unit_id, framing="medium"),
        ]
    )

    issues = _semantic_issues(batch, units, brief, timeline["fps"], {})
    mode_issues = [
        issue for issue in issues if "visual mode" in issue.requirement.casefold()
    ]

    assert [issue.beat_ids for issue in mode_issues] == [["promise"]]


def test_overlong_semantic_record_is_rejected_before_compilation():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, units[2].unit_id),
            _intent("gap", units[3].unit_id),
            _intent("promise", units[3].unit_id),
        ]
    )

    issue = _issue_matching(_semantic_issues(batch, units, brief, 10, {}), "maximum")

    assert issue.beat_ids == ["problem"]


def test_compiled_forbidden_visual_family_is_a_record_level_semantic_issue():
    brief = _brief()
    channel = brief.channel.model_copy(
        update={"forbidden_visual_families": ["generic_desk_task"]}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = _batch_for_units(units)
    batch.shots[0] = _intent(
        "problem",
        units[0].unit_id,
        framing="medium",
        subject=(
            "A person sitting at a desk with scattered notes, briefly pausing and "
            "rubbing temples in mid-afternoon fatigue"
        ),
        visible_state=(
            "Unstructured workspace with unorganized notes, slumped posture showing "
            "sudden mental friction"
        ),
        setting="Home office at midday",
    )

    with pytest.raises(SemanticPlanError) as exc_info:
        _compile_semantic_batch(batch, units, brief, timeline, [], 0)

    issue = _issue_matching(
        exc_info.value.issues,
        "forbidden visual family: generic_desk_task",
    )
    assert issue.code == "SEMANTIC_RECORD_INVALID"
    assert issue.beat_ids == ["problem"]


def test_ensure_repairs_only_the_record_with_an_invisible_declared_entity(
    tmp_path, monkeypatch
):
    from youtube_automation.production import shots as shots_module

    raw = "problem words gap words promise words"
    brief = _brief(source=raw)
    timeline = _timeline(["problem words", "gap words", "promise words"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = _batch_for_units(units)
    initial.shots[0] = _intent(
        "problem",
        units[0].unit_id,
        framing="medium",
        subject="A tutor stands beside an unlabeled wall",
        visible_state="The tutor points toward the empty teaching area",
        setting="A quiet classroom at midday",
        composition="The tutor occupies the left third with open negative space to the right",
        entity_ids=["office_backdrop"],
    )
    corrected_problem = _intent(
        "problem",
        units[0].unit_id,
        framing="medium",
        subject="A tutor stands beside an unlabeled wall",
        visible_state="The tutor points toward a blank canvas in the teaching area",
        setting="A quiet classroom at midday",
        composition="The tutor occupies the left third with open negative space to the right",
        entity_ids=["office_backdrop"],
    )
    repair = SemanticRepairBatch.model_validate(
        {
            "shots": [
                corrected_problem.model_dump(
                    exclude={"beat_id", "first_unit_id", "last_unit_id"}
                )
            ]
        }
    )
    shot_ids = ["p0_problem", "p0_gap", "p0_promise"]
    _write_run(tmp_path, brief, timeline, raw)
    ask = _SemanticAsk([], shot_ids)
    repair_calls = []

    def fake_request_json(prompt, ask_callback, model, **kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        if issubclass(model, SemanticRepairBatch):
            repair_calls.append((prompt, kwargs))
            return repair
        return model.model_validate_json(ask_callback(prompt))

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    plan = ensure_shot_plan(tmp_path, ask)

    assert len(repair_calls) == 1
    assert '"target_beat_id": "problem"' in repair_calls[0][0]
    assert "office_backdrop" in str(repair_calls[0][1]["repair_error"])
    assert "visible description" in str(repair_calls[0][1]["repair_error"])
    assert plan.shots[0].subject == corrected_problem.subject
    assert plan.shots[0].visible_state == corrected_problem.visible_state
    assert [shot.shot_id for shot in plan.shots[1:]] == ["p0_gap", "p0_promise"]


def test_forbidden_visual_family_repairs_only_its_semantic_record(
    tmp_path, monkeypatch
):
    from youtube_automation.production import shots as shots_module

    brief = _brief()
    channel = brief.channel.model_copy(
        update={"forbidden_visual_families": ["generic_desk_task"]}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = _batch_for_units(units)
    initial.shots[0] = _intent(
        "problem",
        units[0].unit_id,
        framing="medium",
        subject="A person sitting at a desk with scattered notes",
        visible_state="The person rubs their temples above unorganized notes",
        setting="Home office at midday",
    )
    corrected_problem = _intent(
        "problem",
        units[0].unit_id,
        framing="medium",
        subject="A commuter arriving at a closed metro platform gate",
        visible_state="The commuter stops as the gate indicator changes from green to red",
        setting="A quiet metro entrance at midday",
        composition="The blocked gate divides the commuter from the empty platform",
        entity_ids=["commuter", "gate"],
    )
    repair = SemanticRepairBatch.model_validate(
        {
            "shots": [
                corrected_problem.model_dump(
                    exclude={"beat_id", "first_unit_id", "last_unit_id"}
                )
            ]
        }
    )
    patch_calls = []

    def fake_request_json(prompt, ask, model, **kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        assert issubclass(model, SemanticRepairBatch)
        patch_calls.append((prompt, kwargs))
        return repair

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    shots, _ = _plan_semantic_windows(
        tmp_path,
        brief,
        timeline,
        [(0, timeline["total_frames"])],
        lambda _: "",
        "",
    )

    assert len(patch_calls) == 1
    assert '"target_beat_id": "problem"' in patch_calls[0][0]
    assert "forbidden visual family: generic_desk_task" in str(
        patch_calls[0][1]["repair_error"]
    )
    assert shots[0].subject == corrected_problem.subject
    assert [shot.shot_id for shot in shots[1:]] == ["p0_gap", "p0_promise"]


def test_recurring_entity_with_new_continuity_repairs_only_the_later_beat(
    tmp_path, monkeypatch
):
    from youtube_automation.production import shots as shots_module

    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    shared_entity = {
        "subject": "An office worker on a plain visual canvas",
        "setting": "A quiet home office",
        "composition": "The office worker fills the left side of the canvas",
        "entity_ids": ["office_worker_canvas_01"],
    }
    initial = SemanticShotBatch(
        shots=[
            _intent(
                "problem",
                units[0].unit_id,
                framing="wide",
                visible_state="The office worker watches a dim laptop screen",
                **shared_entity,
            ),
            _intent(
                "gap",
                units[1].unit_id,
                visual_mode="kinetic_type",
                beat_kind="question",
                framing="close_up",
                visible_state="The office worker looks away from the laptop screen",
                **shared_entity,
            ),
            _intent(
                "promise",
                units[2].unit_id,
                visual_mode="comparison",
                beat_kind="reveal",
                framing="insert",
                subject="A challenge canvas",
                visible_state="The challenge canvas opens to a clear starting state",
                setting="A neutral studio",
                composition="The challenge canvas fills the frame",
                entity_ids=["challenge_canvas"],
            ),
        ]
    )
    corrected_gap = initial.shots[1].model_copy(
        update={"continuity": "edit", "reference_id": "problem"}
    )
    repair = SemanticRepairBatch.model_validate(
        {
            "shots": [
                corrected_gap.model_dump(
                    exclude={"beat_id", "first_unit_id", "last_unit_id"}
                )
            ]
        }
    )
    patch_calls = []

    def fake_request_json(prompt, ask, model, **kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        assert issubclass(model, SemanticRepairBatch)
        repair_schema = model.model_json_schema()
        assert repair_schema["properties"]["shots"]["minItems"] == 1
        assert repair_schema["properties"]["shots"]["maxItems"] == 1
        repair_context = kwargs["repair_context"]
        assert "COMPILER-OWNED REPAIR SLOTS" in repair_context
        assert '"beat_id": "gap"' in repair_context
        assert '"current_entity_ids": ["office_worker_canvas_01"]' in repair_context
        assert '"earlier_entity_ids": ["office_worker_canvas_01"]' in repair_context
        patch_calls.append((prompt, kwargs))
        return repair

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    shots, _ = _plan_semantic_windows(
        tmp_path,
        brief,
        timeline,
        [(0, timeline["total_frames"])],
        lambda _: "",
        "",
    )

    assert len(patch_calls) == 1
    assert '"target_beat_id": "gap"' in patch_calls[0][0]
    assert "Recurring entity IDs cannot use new continuity" in str(
        patch_calls[0][1]["repair_error"]
    )
    assert shots[1].scene_id == shots[0].scene_id
    assert shots[1].reference_asset_id == shots[0].asset_id


def test_new_local_graphic_repair_gets_a_distinct_compiler_owned_canvas_id(
    tmp_path, monkeypatch
):
    from youtube_automation.production import shots as shots_module

    raw = "problem words gap words promise words"
    brief = _brief(source=raw)
    timeline = _timeline(["problem words", "gap words", "promise words"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = _batch_for_units(units)
    initial.shots[0] = _intent(
        "problem",
        units[0].unit_id,
        framing="medium",
        subject="A plain canvas",
        visible_state="The canvas holds one stable opening state",
        setting="A quiet studio backdrop",
        composition="The canvas fills the left half of frame",
        entity_ids=["canvas_shared"],
    )
    initial.shots[1] = _intent(
        "gap",
        units[1].unit_id,
        visual_mode="kinetic_type",
        framing="close_up",
        subject="Plain tactile visual canvas",
        visible_state="Quiet background reserved for deterministic local text",
        setting="Clean uncluttered studio backdrop",
        composition="Centered layout with negative space for typography",
        entity_ids=["canvas_shared"],
        beat_kind="question",
        graphic={"template": "kinetic_type", "primary_text": "Focus"},
    )
    repeated_content = initial.shots[1].model_dump(
        exclude={"beat_id", "first_unit_id", "last_unit_id"}
    )
    repair_calls = 0

    def fake_request_json(prompt, ask_callback, model, **kwargs):
        nonlocal repair_calls
        if issubclass(model, SemanticShotBatch):
            return initial
        if issubclass(model, SemanticRepairBatch):
            repair_calls += 1
            if repair_calls > 1:
                raise AssertionError(
                    "A repeated local-canvas ID must not consume another compiler repair"
                )
            return model.model_validate({"shots": [repeated_content]})
        return model.model_validate_json(ask_callback(prompt))

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)
    _write_run(tmp_path, brief, timeline, raw)
    plan = ensure_shot_plan(tmp_path, _SemanticAsk([], ["p0_problem", "p0_gap", "p0_promise"]))

    assert repair_calls == 1
    assert plan.shots[1].entity_ids == ["canvas_gap_1"]
    assert plan.shots[1].operation == "generate"


def test_same_batch_reuse_and_edit_resolve_the_earlier_beat():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    shared_scene = {
        "entity_ids": ["attention_card"],
        "subject": "A single attention card",
        "visible_state": "The attention card remains face down",
        "setting": "A quiet tabletop",
        "composition": "The attention card rests at frame left",
    }
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, beat_kind="claim", **shared_scene),
            _intent(
                "gap",
                units[1].unit_id,
                framing="close_up",
                continuity="reuse",
                reference_id="problem",
                beat_kind="question",
                **shared_scene,
            ),
            _intent(
                "promise",
                units[2].unit_id,
                visual_mode="comparison",
                framing="close_up",
                beat_kind="reveal",
                continuity="edit",
                reference_id="problem",
                entity_ids=["attention_card"],
                visible_state="The attention card is now face up",
            ),
        ]
    )

    compiled = _compile_semantic_batch(batch, units, brief, timeline, [], 0)

    assert compiled[1].operation == "reuse"
    assert compiled[1].asset_id == compiled[0].asset_id
    assert compiled[1].scene_id == compiled[0].scene_id
    assert compiled[2].operation == "replace"
    assert compiled[2].reference_asset_id == compiled[0].asset_id
    assert compiled[2].scene_id == compiled[0].scene_id


def test_prior_window_asset_can_be_reused_by_semantic_reference():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    prior = Shot(
        shot_id="prior_shot",
        scene_id="prior_scene",
        asset_id="prior_asset",
        entity_ids=["anchor"],
        span_ids=[0],
        start_frame=0,
        end_frame=10,
        purpose="Establish the anchor",
        treatment="subject_scene",
        subject="A concrete anchor object",
        visible_state="The anchor object is unchanged",
        setting="A grounded room",
        framing="wide",
        composition="Anchor object at frame left",
    )
    batch = _batch_for_units(units)
    batch.shots[0] = _intent(
        "problem",
        units[0].unit_id,
        framing="close_up",
        continuity="reuse",
        reference_id="prior_asset",
        entity_ids=["anchor"],
        subject="A concrete anchor object",
        visible_state="The anchor object is unchanged",
        setting="A grounded room",
        composition="Anchor object at frame left",
    )

    compiled = _compile_semantic_batch(batch, units, brief, timeline, [prior], 1)

    assert compiled[0].operation == "reuse"
    assert compiled[0].asset_id == "prior_asset"
    assert compiled[0].scene_id == "prior_scene"


def test_reuse_rejects_a_visible_state_change_that_requires_an_edit():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent(
                "problem",
                units[0].unit_id,
                entity_ids=["door"],
                visible_state="The door is closed",
            ),
            _intent(
                "gap",
                units[1].unit_id,
                continuity="reuse",
                reference_id="problem",
                entity_ids=["door"],
                visible_state="The door is open",
            ),
            _intent("promise", units[2].unit_id),
        ]
    )

    with pytest.raises(SemanticPlanError, match="(?i)reuse.*unchanged|unchanged.*reuse"):
        _compile_semantic_batch(batch, units, brief, timeline, [], 0)


def test_reused_pixels_require_meaningful_local_graphic_progression():
    brief = _brief()
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    base = _intent(
        "promise",
        units[2].unit_id,
        visual_mode="kinetic_type",
        subject="Plain tactile visual canvas",
        visible_state="Quiet background reserved for deterministic local graphics",
        setting="Clean uncluttered studio backdrop",
        entity_ids=["kinetic_canvas"],
        graphic={"template": "kinetic_type", "primary_text": "First", "timer_text": ""},
    )
    continuation = _intent(
        "after_hook",
        units[3].unit_id,
        visual_mode="kinetic_type",
        continuity="reuse",
        reference_id="promise",
        subject=base.subject,
        visible_state=base.visible_state,
        setting=base.setting,
        entity_ids=base.entity_ids,
        graphic={"template": "kinetic_type", "primary_text": "Second", "timer_text": ""},
    ).model_copy(update={"viewer_takeaway": base.viewer_takeaway, "beat_kind": base.beat_kind})
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent("gap", units[1].unit_id, visual_mode="comparison"),
            base,
            continuation,
        ]
    )

    with pytest.raises(SemanticPlanError, match="purposeful local progression"):
        _compile_semantic_batch(batch, units, brief, timeline, [], 0)


def test_patch_preserves_accepted_intents_and_splits_one_rejected_record():
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    original = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent("gap", units[1].unit_id, units[2].unit_id),
            _intent("promise", units[3].unit_id),
        ]
    )
    before_problem = original.shots[0].model_dump_json()
    before_promise = original.shots[2].model_dump_json()
    patch = SemanticShotPatch(
        replacements=[
            SemanticReplacement(
                target_beat_id="gap",
                shots=[
                    _intent("gap", units[1].unit_id),
                    _intent("gap_detail", units[2].unit_id),
                ],
            )
        ]
    )

    merged = _merge_semantic_patch(original, patch, {"gap"})

    assert [intent.beat_id for intent in merged.shots] == [
        "problem",
        "gap",
        "gap_detail",
        "promise",
    ]
    assert merged.shots[0].model_dump_json() == before_problem
    assert merged.shots[-1].model_dump_json() == before_promise


def test_split_patch_must_keep_the_target_id_as_its_first_replacement():
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    original = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent("gap", units[1].unit_id, units[2].unit_id),
            _intent("promise", units[3].unit_id),
        ]
    )
    patch = SemanticShotPatch(
        replacements=[
            SemanticReplacement(
                target_beat_id="gap",
                shots=[
                    _intent("gap_part_one", units[1].unit_id),
                    _intent("gap_part_two", units[2].unit_id),
                ],
            )
        ]
    )

    with pytest.raises(ValueError, match="first.*(?:target|rejected) beat ID"):
        _merge_semantic_patch(original, patch, {"gap"})


def test_content_only_follow_up_keeps_every_split_target_compiler_owned():
    timeline = _timeline(["one", "two", "three", "four"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("beat_1_problem", units[0].unit_id),
            _intent("beat_2_curiosity", units[1].unit_id),
            _intent("beat_3_promise", units[2].unit_id),
            _intent("beat_3_promise_b", units[3].unit_id),
        ]
    )
    issues = [
        SemanticIssue(
            beat_ids=["beat_1_problem"],
            code="SEMANTIC_RECORD_INVALID",
            requirement="Recurring entity IDs cannot use new continuity",
        ),
        *[
            SemanticIssue(
                beat_ids=[beat_id],
                code="SEMANTIC_RECORD_INVALID",
                requirement="Edit requires a changed entity set or visible state",
            )
            for beat_id in (
                "beat_2_curiosity",
                "beat_3_promise",
                "beat_3_promise_b",
            )
        ],
    ]
    rejected_ids = {beat_id for issue in issues for beat_id in issue.beat_ids}

    required_shape = _content_repair_patch_shape(batch, rejected_ids, issues)

    assert [item["target_beat_id"] for item in required_shape] == [
        "beat_1_problem",
        "beat_2_curiosity",
        "beat_3_promise",
        "beat_3_promise_b",
    ]
    assert [item["shots"][0]["beat_id"] for item in required_shape] == [
        intent.beat_id for intent in batch.shots
    ]
    repair = SemanticRepairBatch.model_validate(
        {
            "shots": [
                intent.model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"})
                for intent in batch.shots
            ]
        }
    )
    patch = _bind_repair_content(repair, required_shape)
    merged = _merge_semantic_patch(batch, patch, rejected_ids)
    assert [intent.beat_id for intent in merged.shots] == [
        intent.beat_id for intent in batch.shots
    ]


def test_content_repair_keeps_model_owned_topology_for_overlong_beat():
    timeline = _timeline(["one", "two"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[_intent("overlong", units[0].unit_id, units[1].unit_id)]
    )
    issues = [
        SemanticIssue(
            beat_ids=["overlong"],
            code="SEMANTIC_RECORD_INVALID",
            requirement="Beat exceeds the resolved maximum shot duration",
        )
    ]

    assert _content_repair_patch_shape(batch, {"overlong"}, issues) == []


def test_hook_repair_with_missing_semantic_slot_is_repaired_in_the_same_window(
    tmp_path, monkeypatch
):
    from youtube_automation.production import shots as shots_module

    brief = _brief(source="one two three four")
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id),
            _intent(
                "gap",
                units[1].unit_id,
                visual_mode="kinetic_type",
                beat_kind="question",
                framing="close_up",
            ),
            _intent(
                "promise",
                units[2].unit_id,
                units[3].unit_id,
                visual_mode="challenge_ui",
                beat_kind="reveal",
                framing="insert",
            ),
        ]
    )
    semantic_records = [
        _intent(
            "ignored_promise_id",
            units[2].unit_id,
            visual_mode="challenge_ui",
            beat_kind="reveal",
            framing="insert",
        ).model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"}),
        _intent(
            "ignored_continuation_id",
            units[3].unit_id,
            visual_mode="comparison",
            beat_kind="transition",
            framing="medium",
        ).model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"}),
    ]
    repair_payloads = [
        {"shots": semantic_records[:1]},
        {"shots": semantic_records},
    ]
    patch_calls = []
    patch_prompts = []

    def fake_request_json(prompt, ask, model, **kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        assert model.__name__ == "SemanticRepairBatch"
        patch_prompts.append(prompt)
        patch_calls.append(kwargs)
        repair_schema = model.model_json_schema()
        assert repair_schema["properties"]["shots"]["minItems"] == 2
        assert repair_schema["properties"]["shots"]["maxItems"] == 2
        with pytest.raises(ValueError, match="at least 2 items"):
            model.model_validate(repair_payloads.pop(0))
        return model.model_validate(repair_payloads.pop(0))

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    shots, _ = _plan_semantic_windows(
        tmp_path, brief, timeline, [(0, timeline["total_frames"])], lambda _: "", ""
    )

    assert len(patch_calls) == 1
    assert all("COMPILER-OWNED REPAIR SLOTS" in prompt for prompt in patch_prompts)
    assert patch_calls[-1]["repair_context"].startswith(
        "PATCH TASK: Return SemanticRepairBatch only"
    )
    assert repair_payloads == []
    assert [shot.hook_beat_id for shot in shots] == ["problem", "gap", "promise", None]


def test_progressing_semantic_defects_retain_a_final_content_correction(
    tmp_path, monkeypatch
):
    """Four distinct compiler findings must still leave one bounded repair turn."""
    from youtube_automation.production import shots as shots_module

    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = _batch_for_units(units)
    valid_compiled = _compile_semantic_batch(
        initial, units, brief, timeline, [], 0
    )
    repair = SemanticRepairBatch.model_validate(
        {
            "shots": [
                initial.shots[0].model_dump(
                    exclude={"beat_id", "first_unit_id", "last_unit_id"}
                )
            ]
        }
    )
    compile_calls = []
    repair_calls = []

    def staged_compile(*_args, **_kwargs):
        compile_calls.append(None)
        if len(compile_calls) <= 4:
            raise SemanticPlanError(
                [
                    SemanticIssue(
                        beat_ids=["problem"],
                        code="SEMANTIC_RECORD_INVALID",
                        requirement=f"Progressive compiler finding {len(compile_calls)}",
                    )
                ]
            )
        return valid_compiled

    def fake_request_json(_prompt, _ask, model, **_kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        assert issubclass(model, SemanticRepairBatch)
        repair_calls.append(None)
        return repair

    monkeypatch.setattr(shots_module, "_compile_semantic_batch", staged_compile)
    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    planned, _ = _plan_semantic_windows(
        tmp_path, brief, timeline, [(0, timeline["total_frames"])], lambda _: "", ""
    )

    assert len(compile_calls) == 5
    assert len(repair_calls) == 4
    assert [shot.shot_id for shot in planned] == ["p0_problem", "p0_gap", "p0_promise"]


def test_semantic_compiler_corrections_remain_bounded(tmp_path, monkeypatch):
    from youtube_automation.production import shots as shots_module

    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    initial = _batch_for_units(units)
    repair = SemanticRepairBatch.model_validate(
        {
            "shots": [
                initial.shots[0].model_dump(
                    exclude={"beat_id", "first_unit_id", "last_unit_id"}
                )
            ]
        }
    )
    compile_calls = []
    repair_calls = []

    def always_rejected(*_args, **_kwargs):
        compile_calls.append(None)
        raise SemanticPlanError(
            [
                SemanticIssue(
                    beat_ids=["problem"],
                    code="SEMANTIC_RECORD_INVALID",
                    requirement="Repeated uncorrected compiler finding",
                )
            ]
        )

    def fake_request_json(_prompt, _ask, model, **_kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        assert issubclass(model, SemanticRepairBatch)
        repair_calls.append(None)
        return repair

    monkeypatch.setattr(shots_module, "_compile_semantic_batch", always_rejected)
    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    with pytest.raises(SemanticPlanError, match="Repeated uncorrected"):
        _plan_semantic_windows(
            tmp_path,
            brief,
            timeline,
            [(0, timeline["total_frames"])],
            lambda _: "",
            "",
        )

    assert len(compile_calls) == shots_module.SEMANTIC_COMPILER_ATTEMPTS
    assert len(repair_calls) == shots_module.SEMANTIC_COMPILER_ATTEMPTS - 1


def test_narration_bound_event_is_split_and_repaired_in_the_same_plan_transaction(
    tmp_path,
):
    raw = "problem curiosity promise Schulte exercise"
    brief = _brief(source=raw)
    timeline = {
        "fps": 30,
        "total_frames": 360,
        "spans": [
            {"index": 0, "start_frame": 0, "end_frame": 90, "text": "problem"},
            {"index": 1, "start_frame": 90, "end_frame": 180, "text": "curiosity"},
            {"index": 2, "start_frame": 180, "end_frame": 270, "text": "promise"},
            {
                "index": 3,
                "start_frame": 270,
                "end_frame": 360,
                "text": "Schulte exercise",
            },
        ],
        "words": [],
    }
    _write_run(tmp_path, brief, timeline, raw)
    initial = SemanticShotBatch(
        shots=[
            _intent("problem", "u0_90", visual_mode="human_context", framing="medium"),
            _intent(
                "gap",
                "u90_180",
                visual_mode="comparison",
                framing="wide",
                beat_kind="question",
                entity_ids=["comparison_canvas"],
                subject="Plain comparison canvas",
                visible_state="Quiet canvas reserved for deterministic comparison cards",
                setting="Clean uncluttered studio backdrop",
                graphic={
                    "template": "comparison",
                    "primary_text": "Before",
                    "secondary_text": "After",
                },
            ),
            _intent(
                "promise",
                "u180_270",
                "u270_360",
                visual_mode="kinetic_type",
                framing="insert",
                beat_kind="reveal",
                entity_ids=["promise_canvas"],
                subject="Plain promise canvas",
                visible_state="Quiet canvas reserved for deterministic kinetic type",
                setting="Clean uncluttered studio backdrop",
                graphic={"template": "kinetic_type", "primary_text": "Challenge ahead"},
            ),
        ]
    )
    repaired = SemanticShotPatch(
        replacements=[
            SemanticReplacement(
                target_beat_id="promise",
                shots=[
                    _intent(
                        "promise",
                        "u180_270",
                        visual_mode="kinetic_type",
                        framing="insert",
                        beat_kind="reveal",
                        entity_ids=["promise_canvas"],
                        subject="Plain promise canvas",
                        visible_state="Quiet canvas reserved for deterministic kinetic type",
                        setting="Clean uncluttered studio backdrop",
                        graphic={"template": "kinetic_type", "primary_text": "Challenge ahead"},
                    ),
                    _intent(
                        "promise__schulte",
                        "u270_360",
                        visual_mode="challenge_ui",
                        framing="diagram",
                        beat_kind="instruction",
                        entity_ids=["schulte_canvas"],
                        subject="Plain Schulte canvas",
                        visible_state="Quiet canvas reserved for the deterministic Schulte grid",
                        setting="Clean uncluttered studio backdrop",
                        graphic={
                            "template": "schulte_challenge",
                            "primary_text": "Find the numbers in order",
                            "secondary_text": "Start",
                            "timer_text": "00:00",
                        },
                    ),
                ],
            )
        ]
    )
    planning_responses = [initial.model_dump_json(), repaired.model_dump_json()]

    def ask(prompt: str) -> str:
        if "independent YouTube storyboard critic" in prompt:
            return _review_json(
                ["p0_problem", "p0_gap", "p0_promise", "p0_promise__schulte"]
            )
        return planning_responses.pop(0)

    plan = ensure_shot_plan(tmp_path, ask)

    schulte = next(shot for shot in plan.shots if shot.local_composition == "schulte_challenge")
    assert schulte.start_frame == 270
    assert planning_responses == []


def test_hook_repair_exposes_slot_constraints_after_mechanical_content_failure(
    tmp_path, monkeypatch
):
    from youtube_automation.production import shots as shots_module

    brief = _brief(source="one two three four")
    timeline = _timeline(["one", "two", "three", "four"], seconds_per_word=4)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    gap = _intent(
        "gap",
        units[1].unit_id,
        visual_mode="comparison",
        beat_kind="question",
        framing="wide",
        subject="A closed metro gate",
        visible_state="The gate remains closed",
        setting="A quiet metro entrance",
        composition="The gate spans the center of the entrance",
        entity_ids=["gate"],
    )
    initial = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, framing="medium"),
            gap,
            _intent(
                "promise",
                units[2].unit_id,
                units[3].unit_id,
                visual_mode="comparison",
                beat_kind="reveal",
                framing="wide",
            ),
        ]
    )
    invalid_records = [
        _intent(
            "ignored_promise_id",
            units[2].unit_id,
            visual_mode="comparison",
            beat_kind="reveal",
            framing="wide",
            continuity="edit",
            reference_id="gap",
            subject=gap.subject,
            visible_state=gap.visible_state,
            setting=gap.setting,
            composition=gap.composition,
            entity_ids=gap.entity_ids,
        ).model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"}),
        _intent(
            "ignored_continuation_id",
            units[3].unit_id,
            beat_kind="transition",
            framing="wide",
            subject="A station clock",
            visible_state="The clock hand advances",
            setting="The metro platform",
            composition="The clock fills the upper half of the frame",
            entity_ids=gap.entity_ids,
        ).model_dump(exclude={"beat_id", "first_unit_id", "last_unit_id"}),
    ]
    corrected_records = deepcopy(invalid_records)
    corrected_records[0]["visible_state"] = "The gate indicator changes from green to red"
    corrected_records[1]["framing"] = "medium"
    corrected_records[1]["entity_ids"] = ["clock"]
    repair_payloads = [
        {"shots": invalid_records},
        {"shots": corrected_records},
    ]
    patch_prompts = []

    def fake_request_json(prompt, ask, model, **kwargs):
        if issubclass(model, SemanticShotBatch):
            return initial
        assert model.__name__ == "SemanticRepairBatch"
        patch_prompts.append(prompt)
        return model.model_validate(repair_payloads.pop(0))

    monkeypatch.setattr(shots_module, "request_json", fake_request_json)

    shots, _ = _plan_semantic_windows(
        tmp_path, brief, timeline, [(0, timeline["total_frames"])], lambda _: "", ""
    )

    follow_up_prompt = patch_prompts[-1]
    assert all(
        "COMPILER-DERIVED SLOT CONSTRAINTS" in prompt for prompt in patch_prompts
    )
    assert patch_prompts[0].count('"beat_id": "promise__continuation"') == 2
    assert "COMPILER-DERIVED SLOT CONSTRAINTS" in follow_up_prompt
    assert '"beat_id": "promise__continuation"' in follow_up_prompt
    assert '"disallowed_framings": ["wide"]' in follow_up_prompt
    assert '"available_reference_ids": ["gap", "problem", "promise"]' in follow_up_prompt
    assert '"current_continuity": "edit"' in follow_up_prompt
    assert '"current_entity_ids": ["gate"]' in follow_up_prompt
    assert '"earlier_entity_ids": ["entity_problem", "gate"]' in follow_up_prompt
    assert "new requires entity_ids distinct from every earlier_entity_id" in follow_up_prompt
    assert "edit requires at least one changed visible field" in follow_up_prompt
    assert [shot.hook_beat_id for shot in shots] == ["problem", "gap", "promise", None]


def test_progressive_schulte_states_do_not_escape_as_late_composition_repetition(
    tmp_path,
):
    timeline = _timeline(
        [
            "problem",
            "gap",
            "promise",
            "Schulte introduction",
            "Schulte benefit",
            "Schulte practice",
        ]
    )
    source = " ".join(word["text"] for word in timeline["words"])
    brief = _brief(source=source)
    _write_run(tmp_path, brief, timeline, source)
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = SemanticShotBatch(
        shots=[
            _intent("problem", units[0].unit_id, visual_mode="human_context"),
            _intent(
                "gap",
                units[1].unit_id,
                visual_mode="kinetic_type",
                framing="close_up",
                beat_kind="question",
            ),
            _intent(
                "promise",
                units[2].unit_id,
                visual_mode="comparison",
                framing="insert",
                beat_kind="reveal",
            ),
            _intent(
                "schulte_intro",
                units[3].unit_id,
                visual_mode="challenge_ui",
                framing="diagram",
                beat_kind="instruction",
                composition="The full grid establishes the challenge",
                entity_ids=["schulte_canvas_intro"],
                graphic={
                    "template": "schulte_challenge",
                    "primary_text": "Find 1 through 36",
                    "timer_text": "00:10",
                },
            ),
            _intent(
                "schulte_benefit",
                units[4].unit_id,
                visual_mode="comparison",
                framing="diagram",
                beat_kind="reveal",
                composition="The grid highlights the attention benefit",
                entity_ids=["schulte_canvas_benefit"],
                graphic={
                    "template": "schulte_challenge",
                    "primary_text": "Keep the center steady",
                    "timer_text": "00:07",
                },
            ),
            _intent(
                "schulte_practice",
                units[5].unit_id,
                visual_mode="challenge_ui",
                framing="diagram",
                beat_kind="instruction",
                composition="The grid advances into deliberate practice",
                entity_ids=["schulte_canvas_practice"],
                graphic={
                    "template": "schulte_challenge",
                    "primary_text": "Continue in order",
                    "timer_text": "00:04",
                },
            ),
        ]
    )
    shot_ids = [
        "p0_problem",
        "p0_gap",
        "p0_promise",
        "p0_schulte_intro",
        "p0_schulte_benefit",
        "p0_schulte_practice",
    ]

    plan = ensure_shot_plan(tmp_path, _SemanticAsk([batch], shot_ids))

    assert [shot.shot_id for shot in plan.shots] == shot_ids
    assert len([shot for shot in plan.shots if shot.local_composition == "schulte_challenge"]) == 3


def test_schulte_compiler_emits_immutable_grid_and_full_branded_layer_set():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = _batch_for_units(units)
    batch.shots[2] = _intent(
        "promise",
        units[2].unit_id,
        visual_mode="challenge_ui",
        framing="wide",
        entity_ids=["schulte_grid"],
        graphic={
            "template": "schulte_challenge",
            "primary_text": "Find the numbers in order",
            "secondary_text": "Start",
            "timer_text": "00:30",
        },
    )

    shot = _compile_semantic_batch(batch, units, brief, timeline, [], 0)[2]
    overlays = {overlay.kind: overlay for overlay in shot.overlays}

    assert shot.operation == "local_canvas"
    assert shot.framing == "diagram"
    assert shot.treatment == "detail"
    assert set(overlays) == {
        "data_grid",
        "timer",
        "challenge_frame",
        "rule_reveal",
        "fixation_cue",
        "target_indicator",
        "start_transition",
    }
    assert overlays["data_grid"].cells == SCHULTE_6X6
    assert overlays["data_grid"].rows == overlays["data_grid"].columns == 6
    assert all(
        overlay.start_frame == 0 and overlay.end_frame == shot.end_frame - shot.start_frame
        for overlay in shot.overlays
    )


def test_graphic_copy_and_geometry_never_leak_into_generated_scene_fields():
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = _batch_for_units(units)
    batch.shots[1] = _intent(
        "gap",
        units[1].unit_id,
        visual_mode="comparison",
        entity_ids=["plain_canvas"],
        graphic={
            "template": "comparison",
            "primary_text": "Before",
            "secondary_text": "After",
            "timer_text": "",
        },
    )

    shot = _compile_semantic_batch(batch, units, brief, timeline, [], 0)[1]
    generated_scene = " ".join(
        (shot.subject, shot.visible_state, shot.setting, shot.composition)
    ).casefold()

    assert "before" not in generated_scene
    assert "after" not in generated_scene
    assert not any(term in generated_scene for term in ("card", "panel", "slot", "grid", "timer"))
    assert shot.overlays[0].text == "Before"
    assert shot.overlays[0].secondary_text == "After"


def test_semantic_checkpoint_rejects_brief_timeline_window_and_compiler_drift(tmp_path):
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    windows = _planning_windows(timeline)
    units = _narration_units(timeline, *windows[0])
    batch = _batch_for_units(units)
    path = tmp_path / "shot_plan.semantic.partial.json"
    _save_semantic_partial_plan(path, brief, timeline, windows, [batch])
    baseline = json.loads(path.read_text(encoding="utf-8"))

    changed_brief = brief.model_copy(
        update={"analysis": brief.analysis.model_copy(update={"proposition": "Changed upstream"})}
    )
    with pytest.raises(ValueError, match="does not match current planning inputs"):
        _load_semantic_partial_plan(path, changed_brief, timeline, windows)

    changed_timeline = deepcopy(timeline)
    changed_timeline["words"][0]["text"] = "changed"
    with pytest.raises(ValueError, match="does not match current planning inputs"):
        _load_semantic_partial_plan(path, brief, changed_timeline, windows)

    with pytest.raises(ValueError, match="does not match current planning inputs"):
        _load_semantic_partial_plan(path, brief, timeline, [(0, timeline["total_frames"] - 1)])

    stale_compiler = baseline | {"compiler_version": SHOT_COMPILER_VERSION + 1}
    path.write_text(json.dumps(stale_compiler), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match current planning inputs"):
        _load_semantic_partial_plan(path, brief, timeline, windows)


@pytest.mark.parametrize("old_lineage", [(10, 2), (11, 3), (12, 4), (13, 5), (14, 6), (15, 6), (16, 7)])
def test_supported_checkpoint_rebuilds_before_the_first_narration_event(
    tmp_path, old_lineage
):
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    _write_run(tmp_path, brief, timeline, "semantic narration")
    windows = _planning_windows(timeline)
    units = _narration_units(timeline, *windows[0])
    batch = _batch_for_units(units)
    path = tmp_path / "shot_plan.semantic.partial.json"
    _save_semantic_partial_plan(path, brief, timeline, windows, [batch])
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    checkpoint.update(
        planner_version=old_lineage[0], compiler_version=old_lineage[1]
    )
    path.write_text(json.dumps(checkpoint), encoding="utf-8")

    assert migrate_semantic_checkpoint(tmp_path)
    next_window, batches, shots = _load_semantic_partial_plan(
        path, brief, timeline, windows
    )

    assert next_window == 1
    assert len(batches) == 1
    assert len(shots) == 3
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["planner_version"] == SEMANTIC_PLANNER_VERSION
    assert migrated["compiler_version"] == SHOT_COMPILER_VERSION


def test_current_checkpoint_revalidates_for_a_profile_recipe_change(tmp_path):
    brief = _brief()
    timeline = _timeline(["one", "two", "three"])
    _write_run(tmp_path, brief, timeline, "semantic narration")
    windows = _planning_windows(timeline)
    units = _narration_units(timeline, *windows[0])
    batch = _batch_for_units(units)
    path = tmp_path / "shot_plan.semantic.partial.json"
    _save_semantic_partial_plan(path, brief, timeline, windows, [batch])
    original = json.loads(path.read_text(encoding="utf-8"))

    assert migrate_semantic_checkpoint(tmp_path)

    revalidated = json.loads(path.read_text(encoding="utf-8"))
    assert revalidated == original


def test_lineage10_checkpoint_refuses_to_cross_a_narration_event_boundary(tmp_path):
    brief = _brief()
    timeline = _timeline(["one", "Schulte grid begins", "three"])
    _write_run(tmp_path, brief, timeline, "semantic narration")
    windows = _planning_windows(timeline)
    units = _narration_units(timeline, *windows[0])
    batch = _batch_for_units(units)
    path = tmp_path / "shot_plan.semantic.partial.json"
    _save_semantic_partial_plan(path, brief, timeline, windows, [batch])
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    checkpoint.update(planner_version=10, compiler_version=2)
    path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(ValueError, match="crosses a narration-event migration boundary"):
        migrate_semantic_checkpoint(tmp_path)

    unchanged = json.loads(path.read_text(encoding="utf-8"))
    assert unchanged["planner_version"] == 10
    assert unchanged["compiler_version"] == 2


def test_version_three_ensure_compiles_semantics_loads_without_regeneration_and_feeds_flow(
    tmp_path,
):
    raw = "problem words gap words promise words"
    brief = _brief(source=raw)
    timeline = _timeline(["problem words", "gap words", "promise words"])
    units = _narration_units(timeline, 0, timeline["total_frames"])
    batch = _batch_for_units(units)
    shot_ids = ["p0_problem", "p0_gap", "p0_promise"]
    _write_run(tmp_path, brief, timeline, raw)
    ask = _SemanticAsk([batch], shot_ids)

    plan = ensure_shot_plan(tmp_path, ask)

    assert plan.version == 3
    assert [shot.shot_id for shot in plan.shots] == shot_ids
    assert all(shot.narration_excerpt for shot in plan.shots)
    assert not (tmp_path / "shot_plan.semantic.partial.json").exists()
    loaded = ensure_shot_plan(
        tmp_path, lambda _: pytest.fail("Completed version-3 plan must load without regeneration")
    )
    assert loaded == plan

    prepared, _ = prepare_flow(
        tmp_path, lambda _: pytest.fail("Flow must consume the completed semantic plan")
    )
    payloads = json.loads((tmp_path / "flow_prompts.json").read_text(encoding="utf-8"))
    assert prepared == plan
    assert [payload["adaptive_shot"]["shot_id"] for payload in payloads] == shot_ids
    assert all("viewer_takeaway" in payload["adaptive_shot"] for payload in payloads)


def test_version_three_resume_uses_semantic_checkpoint_and_preserves_legacy_partial(tmp_path):
    raw = " ".join(f"word{i}" for i in range(6))
    brief = _brief(source=raw)
    timeline = _timeline([f"word{i}" for i in range(6)], seconds_per_word=4)
    windows = _planning_windows(timeline)
    assert windows == [(0, 120), (120, 240)]
    first_units = _narration_units(timeline, *windows[0])
    second_units = _narration_units(timeline, *windows[1])
    first_batch = _batch_for_units(first_units)
    second_ids = ("explain", "contrast", "handoff")
    second_batch = _batch_for_units(second_units, second_ids)
    shot_ids = [f"p0_{beat_id}" for beat_id in HOOK_IDS] + [
        f"p1_{beat_id}" for beat_id in second_ids
    ]
    _write_run(tmp_path, brief, timeline, raw)
    legacy_path = tmp_path / "shot_plan.partial.json"
    legacy_bytes = b'{"version":1,"legacy":"preserve this evidence"}'
    legacy_path.write_bytes(legacy_bytes)

    first_response_used = False

    def interrupted(prompt: str) -> str:
        nonlocal first_response_used
        if "independent YouTube storyboard critic" in prompt:
            raise AssertionError("Review cannot run before every window completes")
        if not first_response_used:
            first_response_used = True
            return first_batch.model_dump_json()
        raise RuntimeError("Gemini transport interrupted")

    with pytest.raises(RuntimeError, match="Browser transport failed"):
        ensure_shot_plan(tmp_path, interrupted)

    semantic_path = tmp_path / "shot_plan.semantic.partial.json"
    checkpoint = json.loads(semantic_path.read_text(encoding="utf-8"))
    assert checkpoint["version"] == 1
    assert checkpoint["planner_version"] == SEMANTIC_PLANNER_VERSION
    assert checkpoint["compiler_version"] == SHOT_COMPILER_VERSION
    assert checkpoint["next_window"] == 1
    assert len(checkpoint["batches"]) == 1
    assert legacy_path.read_bytes() == legacy_bytes

    resumed = _SemanticAsk([second_batch], shot_ids)
    plan = ensure_shot_plan(tmp_path, resumed)

    assert [shot.shot_id for shot in plan.shots] == shot_ids
    assert len(resumed.planning_prompts) == 1
    assert legacy_path.read_bytes() == legacy_bytes
    assert not semantic_path.exists()


def test_version_two_path_still_accepts_full_shot_batch_and_loads_completed_plan(tmp_path):
    raw = "legacy narration"
    brief = _brief(version=2, source=raw)
    timeline = _timeline([raw], seconds_per_word=6)
    _write_run(tmp_path, brief, timeline, raw)
    legacy_shot = Shot(
        shot_id="legacy_shot",
        scene_id="legacy_scene",
        asset_id="legacy_asset",
        entity_ids=["object"],
        span_ids=[0],
        start_frame=0,
        end_frame=60,
        purpose="Show the exact legacy narration beat",
        treatment="subject_scene",
        narrative_role="story_subject",
        subject="A concrete narration-specific object",
        visible_state="The object visibly demonstrates the narration point",
        setting="A grounded uncluttered room",
        framing="wide",
        composition="The object occupies the left third",
    )
    prompts = []

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return ShotBatch(shots=[legacy_shot]).model_dump_json()

    plan = ensure_shot_plan(tmp_path, ask)

    assert plan.version == 2
    assert plan.shots == [legacy_shot]
    assert "ShotBatch" in prompts[0] or '"shots"' in prompts[0]
    loaded = ensure_shot_plan(
        tmp_path, lambda _: pytest.fail("Completed version-2 plan must load without regeneration")
    )
    assert loaded == plan
