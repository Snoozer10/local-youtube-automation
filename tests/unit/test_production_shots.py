import pytest

from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint
from youtube_automation.production.shots import (
    Shot,
    ShotPlan,
    _validate_editorial_quality,
    generation_prompt,
    resolve_editorial_policy,
    validate_plan,
)


def shot(**updates):
    data = {
        "shot_id": "s1",
        "scene_id": "animal",
        "asset_id": "a1",
        "entity_ids": ["cat"],
        "span_ids": [0, 1],
        "start_frame": 0,
        "end_frame": 60,
        "purpose": "Show what the animal is watching",
        "treatment": "subject_scene",
        "subject": "Cat watching a hand",
        "visible_state": "Eyes directed at the hand",
        "setting": "Garden",
        "framing": "medium",
        "composition": "Eye-level close-up",
    }
    return Shot(**(data | updates))


def episode_brief():
    channel = Channel(
        channel_id="cat",
        name="Cat",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="naturalistic illustration",
        allowed_treatments=["subject_scene"],
    )
    analysis = Analysis(
        topics=["animals"],
        claim_basis="factual",
        form="explanation",
        proposition="Perception",
        narrative_strategy="Observe",
        treatments=["subject_scene"],
        rationale="Concrete",
    )
    return Brief(
        source_sha256="a" * 64,
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
    )


def version_two_brief():
    channel = Channel(
        version=2,
        channel_id="psychology",
        name="Psychology",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="evidence-conscious",
        style="editorial illustration",
        visual_directives=["Use specific human contexts and clean local diagrams"],
        forbidden_motifs=["mechanical puzzle", "glowing brain"],
        allowed_treatments=["subject_scene", "detail", "mechanism"],
    )
    analysis = Analysis(
        topics=["attention"],
        claim_basis="factual",
        form="explanation",
        proposition="Attention can be trained with a visual search task",
        narrative_strategy="Move from context to an interactive exercise",
        treatments=["subject_scene", "detail", "mechanism"],
        rationale="Concrete demonstration",
    )
    return Brief(
        source_sha256="a" * 64,
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
    )


def editorial_policy():
    return resolve_editorial_policy(episode_brief())


def test_many_spans_one_shot_and_explicit_reuse():
    plan = ShotPlan(
        shots=[
            shot(),
            shot(shot_id="s2", operation="reuse", span_ids=[2], start_frame=60, end_frame=90),
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=90,
        editorial_policy=editorial_policy(),
    )
    assert len(plan.shots) == 2
    assert plan.shots[0].span_ids == [0, 1]


@pytest.mark.parametrize(
    "update",
    [
        {"start_frame": 1},
        {"end_frame": 59},
        {"operation": "reuse"},
        {"operation": "reframe", "reference_asset_id": "missing"},
    ],
)
def test_invalid_coverage_and_references_rejected(update):
    with pytest.raises(ValueError):
        ShotPlan(
            shots=[shot(**update)],
            brief_sha256="a" * 64,
            timeline_sha256="b" * 64,
            fps=30,
            total_frames=60,
            editorial_policy=editorial_policy(),
        )


def test_policy_and_narration_checks():
    channel = Channel(
        channel_id="cat",
        name="Cat",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="naturalistic illustration",
        allowed_treatments=["subject_scene"],
    )
    analysis = Analysis(
        topics=["animals"],
        claim_basis="factual",
        form="explanation",
        proposition="Perception",
        narrative_strategy="Observe",
        treatments=["subject_scene"],
        rationale="Concrete",
    )
    brief = Brief(
        source_sha256="a" * 64,
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
    )
    timeline = {
        "fps": 30,
        "total_frames": 60,
        "spans": [
            {"index": 0, "start_frame": 0, "end_frame": 30},
            {"index": 1, "start_frame": 30, "end_frame": 60},
        ],
    }
    plan = ShotPlan(
        shots=[shot()],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    validate_plan(plan, timeline, brief)
    prompt = generation_prompt(plan.shots[0], brief)
    assert "naturalistic illustration" in prompt
    assert "Eye-level close-up" in prompt
    plan.shots[0].span_ids = [0]
    with pytest.raises(ValueError, match="Narration"):
        validate_plan(plan, timeline, brief)


def test_paged_plan_validates_real_canonical_spans_and_flow_roundtrip(tmp_path):
    import json

    from youtube_automation.core.utils import atomic_write_json
    from youtube_automation.production.flow import prepare_flow
    from youtube_automation.production.shots import ensure_shot_plan
    from youtube_automation.timeline.engine import build_timeline
    from youtube_automation.visuals.flow_generator import parse_json_prompts

    raw = "A cat observes its surroundings."
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    channel = Channel(
        channel_id="cat",
        name="Cat",
        audience="adults",
        language="Arabic",
        dialect="MSA",
        voice="voice",
        tone="calm",
        style="naturalistic illustration",
        allowed_treatments=["subject_scene"],
    )
    analysis = Analysis(
        topics=["animals"],
        claim_basis="factual",
        form="explanation",
        proposition="Perception",
        narrative_strategy="Observe",
        treatments=["subject_scene"],
        rationale="Concrete",
    )
    brief = Brief(
        source_sha256=fingerprint(raw),
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=analysis,
    )
    atomic_write_json(str(tmp_path / "episode_brief.json"), brief.model_dump())
    # Use the actual timeline builder, then enough valid spans to exercise pagination.
    timeline = build_timeline([], audio_duration=26, audio_file="audacity_voice/voice.wav", fps=30)
    timeline["spans"] = [
        {"index": i, "start_frame": i * 30, "end_frame": (i + 1) * 30, "text": raw}
        for i in range(26)
    ]
    atomic_write_json(str(tmp_path / "timeline.json"), timeline)
    calls = []

    def ask(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            scenes = [
                shot(end_frame=180, span_ids=list(range(6)), framing="establishing"),
                shot(
                    shot_id="s2",
                    asset_id="a2",
                    operation="reframe",
                    reference_asset_id="a1",
                    start_frame=180,
                    end_frame=390,
                    span_ids=list(range(6, 13)),
                    framing="wide",
                ),
            ]
        else:
            scenes = [
                shot(
                    shot_id="s3",
                    asset_id="a3",
                    operation="reframe",
                    reference_asset_id="a2",
                    start_frame=390,
                    end_frame=570,
                    span_ids=list(range(13, 19)),
                    framing="close_up",
                ),
                shot(
                    shot_id="s4",
                    asset_id="a4",
                    operation="reframe",
                    reference_asset_id="a3",
                    start_frame=570,
                    end_frame=780,
                    span_ids=list(range(19, 26)),
                    framing="insert",
                ),
            ]
        return json.dumps({"shots": [s.model_dump() for s in scenes]})

    def interrupted_after_first_window(prompt):
        if calls:
            raise RuntimeError("Gemini transport interrupted")
        return ask(prompt)

    with pytest.raises(RuntimeError, match="Gemini transport interrupted"):
        ensure_shot_plan(tmp_path, interrupted_after_first_window)
    partial_path = tmp_path / "shot_plan.partial.json"
    checkpoint = json.loads(partial_path.read_text(encoding="utf-8"))
    assert checkpoint["next_window"] == 1
    checkpoint["timeline_sha256"] = "0" * 64
    partial_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match current planning inputs"):
        ensure_shot_plan(tmp_path, ask)
    checkpoint["timeline_sha256"] = fingerprint(timeline)
    partial_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    plan = ensure_shot_plan(tmp_path, ask)
    assert len(calls) == 2
    assert not (tmp_path / "shot_plan.partial.json").exists()
    assert "INTERVAL [0, 390)" in calls[0]
    assert "INTERVAL [390, 780)" in calls[1]
    assert '"asset_id": "a1"' in calls[1]
    assert plan.total_frames == 780
    prepare_flow(tmp_path, lambda _: pytest.fail("Validated plan should resume"))
    parsed = parse_json_prompts(str(tmp_path / "flow_prompts.json"))
    assert len(parsed) == 4  # Deliberate local reuse never requests new diffusion output.
    assert parsed[0].raw_payload["adaptive_shot"]["asset_id"] == "a1"
    assert parsed[0].raw_payload["adaptive_shot"]["subject"] == "Cat watching a hand"


def test_sparse_long_spans_are_split_into_short_word_sliced_requests():
    from youtube_automation.production.shots import _planning_windows, _window_spans

    timeline = {
        "fps": 30,
        "total_frames": 2296,
        "spans": [
            {"index": 0, "start_frame": 0, "end_frame": 308, "start_word_id": 0, "end_word_id": 1},
            {"index": 1, "start_frame": 308, "end_frame": 1219, "start_word_id": 1, "end_word_id": 3},
            {"index": 2, "start_frame": 1219, "end_frame": 1659, "start_word_id": 3, "end_word_id": 4},
            {"index": 3, "start_frame": 1659, "end_frame": 2296, "start_word_id": 4, "end_word_id": 5},
        ],
        "words": [
            {"id": 0, "text": "first", "start": 0.0, "end": 10.0},
            {"id": 1, "text": "second", "start": 10.3, "end": 20.0},
            {"id": 2, "text": "third", "start": 20.1, "end": 40.0},
            {"id": 3, "text": "fourth", "start": 40.6, "end": 55.0},
            {"id": 4, "text": "fifth", "start": 55.3, "end": 76.5},
        ],
    }
    windows = _planning_windows(timeline)
    assert len(windows) == 4
    assert windows[0][0] == 0 and windows[-1][1] == 2296
    assert all(end - start <= 20 * 30 for start, end in windows)
    assert all(left[1] == right[0] for left, right in zip(windows, windows[1:], strict=False))
    first = _window_spans(timeline, *windows[0])
    last = _window_spans(timeline, *windows[-1])
    assert first[0]["index"] == 0
    assert last[-1]["index"] == 3
    assert "first" in first[0]["text"]
    assert "fifth" not in first[-1]["text"]


def test_multiple_shots_can_share_one_narration_span():
    plan = ShotPlan(
        shots=[
            shot(end_frame=15, span_ids=[0]),
            shot(shot_id="s2", start_frame=15, end_frame=30, span_ids=[0], operation="reuse"),
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=30,
        editorial_policy=editorial_policy(),
    )
    assert [s.span_ids for s in plan.shots] == [[0], [0]]


def test_harmless_overlay_overrun_and_generic_human_entity_are_normalized():
    normalized = shot(
        entity_ids=["e_person"],
        subject="A young adult studying a visual challenge",
        end_frame=60,
        overlays=[
            {
                "kind": "timer",
                "start_frame": 20,
                "end_frame": 90,
                "text": "00:40",
            }
        ],
    )
    assert normalized.overlays[0].end_frame == 60
    plan = ShotPlan(
        shots=[normalized],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=editorial_policy(),
    )
    # The generic entity token is semantically visible as a young adult.
    from youtube_automation.production.shots import _validate_editorial_quality

    _validate_editorial_quality(plan, episode_brief(), complete=False)


@pytest.mark.parametrize(
    "update", [{"scene_id": "unrelated"}, {"entity_ids": ["different-animal"]}]
)
def test_reuse_cannot_relabel_the_same_bitmap_as_unrelated_scene(update):
    with pytest.raises(ValueError, match="Reuse cannot change"):
        ShotPlan(
            shots=[
                shot(),
                shot(
                    shot_id="s2",
                    operation="reuse",
                    start_frame=60,
                    end_frame=90,
                    span_ids=[2],
                    **update,
                ),
            ],
            brief_sha256="a" * 64,
            timeline_sha256="b" * 64,
            fps=30,
            total_frames=90,
            editorial_policy=editorial_policy(),
        )


def test_editorial_quality_rejects_overlong_shot():
    brief = episode_brief()
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [{"index": 0, "start_frame": 0, "end_frame": 300}],
    }
    plan = ShotPlan(
        shots=[shot(end_frame=300, span_ids=[0])],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=300,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="cadence ceiling"):
        validate_plan(plan, timeline, brief)


def test_editorial_quality_requires_recurring_entity_reference():
    brief = episode_brief()
    timeline = {
        "fps": 30,
        "total_frames": 120,
        "spans": [
            {"index": 0, "start_frame": 0, "end_frame": 60},
            {"index": 1, "start_frame": 60, "end_frame": 120},
        ],
    }
    plan = ShotPlan(
        shots=[
            shot(end_frame=60, span_ids=[0], entity_ids=["cat"]),
            shot(
                shot_id="s2",
                asset_id="a2",
                start_frame=60,
                end_frame=120,
                span_ids=[1],
                entity_ids=["cat"],
                framing="close_up",
            ),
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=120,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="must reuse or reference"):
        validate_plan(plan, timeline, brief)


def test_editorial_quality_rejects_invisible_entity_and_literalized_idiom():
    brief = episode_brief()
    timeline = {
        "fps": 30,
        "total_frames": 60,
        "spans": [{"index": 0, "start_frame": 0, "end_frame": 60}],
    }
    invisible = ShotPlan(
        shots=[shot(entity_ids=["cat", "dog"], span_ids=[0])],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="without a visible description"):
        validate_plan(invisible, timeline, brief)

    literal = ShotPlan(
        shots=[
            shot(
                visible_state="Cat literally transformed into a block of ice",
                span_ids=[0],
            )
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="literalize figurative language"):
        validate_plan(literal, timeline, brief)


def test_version_two_channel_requires_roles_and_rejects_forbidden_motifs():
    brief = version_two_brief()
    missing_role = ShotPlan(
        shots=[shot()],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="requires narrative_role"):
        _validate_editorial_quality(missing_role, brief, complete=False)

    forbidden = ShotPlan(
        shots=[shot(narrative_role="story_subject", subject="Adult solving a mechanical puzzle")],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="channel-forbidden motif: mechanical puzzle"):
        _validate_editorial_quality(forbidden, brief, complete=False)


def test_host_free_channel_rejects_presenter_role():
    brief = version_two_brief()
    plan = ShotPlan(
        shots=[shot(narrative_role="presenter")],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="Host-free channel cannot use a presenter"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_schulte_grid_requires_clean_near_full_frame_diagram():
    brief = version_two_brief()
    grid = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 60,
        "x": 0.1,
        "y": 0.15,
        "width": 0.8,
        "height": 0.7,
        "preset": "schulte_6x6",
    }
    bad = ShotPlan(
        shots=[
            shot(
                narrative_role="participant",
                subject="A man holds a board toward the viewer",
                overlays=[grid],
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="clean, human-free, near-full-frame diagram"):
        _validate_editorial_quality(bad, brief, complete=False)

    accepted = ShotPlan(
        shots=[
            shot(
                narrative_role="diagram",
                treatment="mechanism",
                entity_ids=["schulte_grid"],
                subject="Schulte grid",
                visible_state="Grid fills the frame",
                setting="Clean dark graphic field",
                framing="diagram",
                composition="High-contrast grid centered for visual search",
                overlays=[grid],
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    _validate_editorial_quality(accepted, brief, complete=False)


def test_version_one_channel_fingerprint_remains_backward_compatible():
    channel = episode_brief().channel
    legacy = channel.model_dump(mode="json")
    legacy.pop("visual_directives")
    legacy.pop("forbidden_motifs")
    assert fingerprint(channel) == fingerprint(legacy)


def test_version_two_channel_fingerprint_includes_visual_policy():
    channel = version_two_brief().channel
    changed = channel.model_copy(update={"forbidden_motifs": ["floating icon"]})
    assert fingerprint(channel) != fingerprint(changed)


def test_generation_prompt_carries_channel_visual_policy():
    brief = version_two_brief()
    prompt = generation_prompt(shot(narrative_role="story_subject"), brief)
    assert "Use specific human contexts and clean local diagrams" in prompt
    assert "mechanical puzzle; glowing brain" in prompt


def test_reframe_may_focus_on_subset_of_reference_entities():
    ShotPlan(
        shots=[
            shot(entity_ids=["cat", "hand"]),
            shot(
                shot_id="s2",
                asset_id="a2",
                reference_asset_id="a1",
                entity_ids=["cat"],
                operation="reframe",
                start_frame=60,
                end_frame=90,
                span_ids=[2],
                framing="close_up",
            ),
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=90,
        editorial_policy=editorial_policy(),
    )


def test_referenced_generate_is_normalized_using_reference_entities():
    plan = ShotPlan(
        shots=[
            shot(asset_id="a0", entity_ids=["cat", "hand"]),
            shot(
                shot_id="s2",
                asset_id="a1",
                reference_asset_id="a0",
                entity_ids=["cat"],
                start_frame=60,
                end_frame=90,
                span_ids=[2],
                framing="close_up",
            ),
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=90,
        editorial_policy=editorial_policy(),
    )
    assert plan.shots[1].operation == "reframe"
