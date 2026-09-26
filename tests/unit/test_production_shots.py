import pytest

from youtube_automation.production.contracts import (
    Analysis,
    Brief,
    Channel,
    EpisodeVisualStrategy,
    fingerprint,
)
from youtube_automation.production.shots import (
    EditorialReview,
    Overlay,
    Shot,
    ShotPlan,
    _validate_editorial_quality,
    _validate_interactive_graphics,
    ensure_editorial_review,
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


def version_three_brief():
    base = version_two_brief()
    channel = base.channel.model_copy(update={"version": 3})
    strategy = EpisodeVisualStrategy(
        source_sha256="a" * 64,
        topic="Attention challenge",
        viewer_question="Can you spot your attention gap?",
        central_promise="Recognize the gap and test it",
        evidence_mode="demonstrative",
        emotional_arc=["recognition", "curiosity", "agency"],
        hook_archetype="cold_open_challenge",
        hook_microbeats=[
            {
                "beat_id": "problem",
                "function": "problem",
                "duration_seconds": 3,
                "viewer_takeaway": "Attention slips",
                "visual_mode": "human_context",
            },
            {
                "beat_id": "gap",
                "function": "curiosity",
                "duration_seconds": 3,
                "viewer_takeaway": "The gap can be exposed",
                "visual_mode": "kinetic_type",
            },
            {
                "beat_id": "promise",
                "function": "promise",
                "duration_seconds": 3,
                "viewer_takeaway": "A challenge is coming",
                "visual_mode": "challenge_ui",
                "local_ui": ["timer"],
            },
        ],
        visual_modes=["human_context", "kinetic_type", "challenge_ui"],
        local_ui_kit=["timer"],
        pacing="Three quick hook beats followed by a calm challenge",
        motion_grammar=["Animate only focus and state changes"],
    )
    return Brief(
        version=3,
        source_sha256="a" * 64,
        profile_sha256=fingerprint(channel),
        channel=channel,
        analysis=base.analysis,
        visual_strategy=strategy,
    )


def semantic_hook_plan(brief):
    timeline = {
        "fps": 30,
        "total_frames": 270,
        "spans": [
            {"index": i, "start_frame": i * 90, "end_frame": (i + 1) * 90, "text": text}
            for i, text in enumerate(("Attention slips", "Can you see why", "Try this challenge"))
        ],
        "words": [
            {"id": i, "text": text, "start": i * 3.0, "end": (i + 1) * 3.0}
            for i, text in enumerate(("Attention slips", "Can you see why", "Try this challenge"))
        ],
    }
    functions = (("problem", "problem"), ("gap", "curiosity"), ("promise", "promise"))
    shots = []
    for i, ((beat_id, function), text) in enumerate(
        zip(functions, ("Attention slips", "Can you see why", "Try this challenge"), strict=True)
    ):
        shots.append(
            shot(
                shot_id=f"s{i}",
                scene_id=f"scene{i}",
                asset_id=f"asset{i}",
                entity_ids=[f"subject{i}"],
                span_ids=[i],
                start_frame=i * 90,
                end_frame=(i + 1) * 90,
                subject=f"Subject{i} visible in an episode-specific composition",
                visible_state=f"Subject{i} demonstrates only this narration beat",
                composition=f"Distinct episode composition {i}",
                framing=("wide", "close_up", "diagram")[i],
                narrative_role="diagram" if i == 2 else "story_subject",
                visual_mode=("human_context", "kinetic_type", "challenge_ui")[i],
                beat_kind=("claim", "question", "instruction")[i],
                narration_excerpt=text,
                viewer_takeaway=("Attention fails", "There is a reason", "I can try it")[i],
                semantic_link=("example", "direct", "instruction")[i],
                hook_beat_id=beat_id,
                hook_function=function,
            )
        )
    return timeline, ShotPlan(
        version=3,
        shots=shots,
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=270,
        editorial_policy=resolve_editorial_policy(brief),
    )


def test_version_three_plan_requires_exact_narration_and_structural_hook():
    brief = version_three_brief()
    timeline, plan = semantic_hook_plan(brief)
    validate_plan(plan, timeline, brief)
    plan.shots[1].narration_excerpt = "Broad topic paraphrase"
    with pytest.raises(ValueError, match="not exact canonical speech"):
        validate_plan(plan, timeline, brief)


def test_version_three_plan_enforces_episode_visual_mode_budget():
    brief = version_three_brief()
    timeline, plan = semantic_hook_plan(brief)
    plan.shots[1].visual_mode = "human_context"
    plan.shots[2].visual_mode = "human_context"
    with pytest.raises(ValueError, match="repeats beyond the episode budget"):
        validate_plan(plan, timeline, brief)


def test_editorial_critic_persists_rejection_before_flow(tmp_path):
    brief = version_three_brief()
    timeline, plan = semantic_hook_plan(brief)
    review = EditorialReview(
        plan_sha256=fingerprint(plan),
        approved=False,
        shots=[
            {
                "shot_id": shot_item.shot_id,
                "semantic_match": 3 if index == 1 else 5,
                "takeaway_match": 3 if index == 1 else 5,
                "visual_specificity": 2 if index == 1 else 5,
                "verdict": "reject" if index == 1 else "accept",
                "rationale": "Generic topical image" if index == 1 else "Exact visual beat",
            }
            for index, shot_item in enumerate(plan.shots)
        ],
    )
    with pytest.raises(ValueError, match="rejected shot plan"):
        ensure_editorial_review(tmp_path, plan, timeline, brief, lambda _: review.model_dump_json())
    persisted = EditorialReview.model_validate_json(
        (tmp_path / "editorial_review.json").read_text(encoding="utf-8")
    )
    assert persisted.shots[1].verdict == "reject"
    assert len(list((tmp_path / "editorial_rejections").glob("*.json"))) == 1


def test_editorial_critic_archives_stale_rejection_and_reviews_changed_plan(tmp_path):
    brief = version_three_brief()
    timeline, plan = semantic_hook_plan(brief)
    stale = EditorialReview(
        plan_sha256="f" * 64,
        approved=False,
        shots=[
            {
                "shot_id": item.shot_id,
                "semantic_match": 2,
                "takeaway_match": 2,
                "visual_specificity": 2,
                "verdict": "reject",
                "rationale": "Previous plan was generic",
            }
            for item in plan.shots
        ],
    )
    (tmp_path / "editorial_review.json").write_text(
        stale.model_dump_json(), encoding="utf-8"
    )
    accepted = stale.model_copy(
        update={
            "approved": True,
            "shots": [
                decision.model_copy(
                    update={
                        "semantic_match": 5,
                        "takeaway_match": 5,
                        "visual_specificity": 5,
                        "verdict": "accept",
                        "rationale": "Exact repaired beat",
                    }
                )
                for decision in stale.shots
            ],
        }
    )

    review = ensure_editorial_review(
        tmp_path, plan, timeline, brief, lambda _: accepted.model_dump_json()
    )

    assert review.approved
    assert review.plan_sha256 == fingerprint(plan)
    assert len(list((tmp_path / "editorial_rejections").glob("*.json"))) == 1


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
    assert "CONTINUITY-LOCKED ESTABLISHED ASSETS" in calls[1]
    assert "operation=generate is forbidden" in calls[1]
    assert "new pose, action, expression or visible state" in calls[1]
    assert "NON-DIAGRAM SCENE BUDGETS" in calls[1]
    assert '"remaining": 2' in calls[1]
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


def test_version_two_channel_rejects_semantic_visual_family_paraphrase():
    brief = version_two_brief()
    channel = brief.channel.model_copy(
        update={"forbidden_visual_families": ["mechanical_cognition"]}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    plan = ShotPlan(
        shots=[
            shot(
                narrative_role="diagram",
                treatment="mechanism",
                framing="diagram",
                entity_ids=["wooden_tiles", "alignment_track"],
                subject="Wooden tiles moving along an alignment track",
                visible_state="Tiles snap into orderly rows",
                purpose="Visualize a mechanism for faster cognitive attention",
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="forbidden visual family: mechanical_cognition"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_close_up_thoughtful_focus_portrait_is_classified_semantically():
    brief = version_two_brief()
    channel = brief.channel.model_copy(
        update={"forbidden_visual_families": ["generic_focus_portrait"]}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    plan = ShotPlan(
        shots=[
            shot(
                narrative_role="participant",
                framing="close_up",
                entity_ids=["adult_commuter"],
                subject="Adult commuter in close portrait",
                visible_state="Calm attentive expression and thoughtful gaze suggest mental sharpness",
                setting="Urban platform",
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="forbidden visual family: generic_focus_portrait"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_generated_scene_rejects_requested_typography_inside_pixels():
    brief = version_two_brief()
    plan = ShotPlan(
        shots=[
            shot(
                narrative_role="background",
                treatment="detail",
                entity_ids=["open_book"],
                subject="Open book on a library table",
                visible_state="Printed text is clearly visible across both pages",
                setting="Quiet library",
                framing="close_up",
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="requests typography inside generated pixels"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_semantic_visual_family_matching_does_not_split_words():
    brief = version_two_brief()
    channel = brief.channel.model_copy(
        update={"forbidden_visual_families": ["mechanical_cognition"]}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    plan = ShotPlan(
        shots=[
            shot(
                narrative_role="story_subject",
                entity_ids=["adult_person"],
                subject="An adult searches a cluttered bowl of keys",
                visible_state="Mildly frustrated by mental fog",
                setting="Tactile paper textures in a residential entryway",
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    _validate_editorial_quality(plan, brief, complete=False)


def test_semantic_visual_family_rejects_wellness_strawman_paraphrase():
    brief = version_two_brief()
    channel = brief.channel.model_copy(
        update={"forbidden_visual_families": ["wellness_strawman"]}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    plan = ShotPlan(
        shots=[
            shot(
                narrative_role="background",
                entity_ids=["incense_burner"],
                subject="An unlit incense burner on a shelf",
                visible_state="Cold and ignored",
                purpose="Represent the boring meditation solution that the narration dismisses",
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="forbidden visual family: wellness_strawman"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_version_two_channel_limits_repeated_generic_visual_family():
    brief = version_two_brief()
    channel = brief.channel.model_copy(
        update={
            "repetition_limited_visual_families": ["generic_desk_task"],
            "max_visual_family_repetitions": 2,
        }
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    shots = []
    for index, framing in enumerate(("medium", "close_up", "overhead")):
        shots.append(
            shot(
                shot_id=f"s{index}",
                scene_id=f"desk_{index}",
                asset_id=f"a{index}",
                entity_ids=[f"worker_{index}", f"paper_{index}"],
                start_frame=index * 60,
                end_frame=(index + 1) * 60,
                span_ids=[index],
                narrative_role="participant",
                treatment="detail",
                subject=f"Worker {index} writing on paper at a desk",
                visible_state="Hand holds a pen over the paper",
                setting="Wooden desk",
                framing=framing,
            )
        )
    plan = ShotPlan(
        shots=shots,
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=180,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="generic_desk_task exceeds.*limit of 2"):
        _validate_editorial_quality(plan, brief, complete=False)


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


def test_channel_limits_repeated_non_diagram_scene_appearances():
    brief = version_two_brief()
    channel = brief.channel.model_copy(
        update={"version": 3, "max_non_diagram_scene_appearances": 2}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    shots = [
        shot(
            shot_id=f"s{index}",
            scene_id="same_room",
            asset_id=f"asset_{index}",
            entity_ids=[f"object_{index}"],
            subject=f"Object {index} in a room",
            start_frame=index * 60,
            end_frame=(index + 1) * 60,
            span_ids=[index],
            narrative_role="story_subject",
            framing=("wide", "medium", "close_up")[index],
        )
        for index in range(3)
    ]
    plan = ShotPlan(
        shots=shots,
        brief_sha256=fingerprint(brief),
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=180,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="same_room exceeds.*limit of 2"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_adjacent_non_diagram_shots_cannot_hide_one_long_identical_hold():
    brief = version_two_brief()
    plan = ShotPlan(
        shots=[
            shot(narrative_role="story_subject"),
            shot(
                shot_id="s2",
                operation="reuse",
                start_frame=60,
                end_frame=120,
                span_ids=[1],
                narrative_role="story_subject",
            ),
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=120,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="same asset, framing and motion"):
        _validate_editorial_quality(plan, brief, complete=False)


def test_entity_identity_cannot_migrate_between_scenes():
    brief = version_two_brief()
    plan = ShotPlan(
        shots=[
            shot(narrative_role="story_subject"),
            shot(
                shot_id="s2",
                scene_id="different_scene",
                asset_id="a2",
                start_frame=60,
                end_frame=120,
                span_ids=[1],
                framing="wide",
                narrative_role="story_subject",
            ),
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=120,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="cannot migrate"):
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

    exclusion_wording = accepted.model_copy(deep=True)
    exclusion_wording.shots[0].visible_state = (
        "Clean graphic canvas without generated text and clear of human figures"
    )
    _validate_editorial_quality(exclusion_wording, brief, complete=False)


def test_schulte_grid_begins_at_introduction_and_uses_readable_timer():
    brief = version_two_brief()
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [
            {"index": 0, "start_frame": 0, "end_frame": 150, "text": "جدول شولتي"},
            {"index": 1, "start_frame": 150, "end_frame": 300, "text": "جاهز ابدا"},
        ],
    }
    grid = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 180,
        "x": 0.1,
        "y": 0.15,
        "width": 0.8,
        "height": 0.7,
        "preset": "schulte_6x6",
    }
    late = ShotPlan(
        shots=[
            shot(end_frame=120, span_ids=[0], narrative_role="participant"),
            shot(
                shot_id="s2",
                scene_id="grid",
                asset_id="grid_asset",
                entity_ids=["schulte_grid"],
                start_frame=120,
                end_frame=300,
                span_ids=[0, 1],
                narrative_role="diagram",
                treatment="mechanism",
                subject="Schulte grid",
                visible_state="Grid fills the frame",
                setting="Clean graphic field",
                framing="diagram",
                composition="High-contrast local grid",
                overlays=[grid],
            ),
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=300,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="must begin when the exercise is introduced"):
        validate_plan(late, timeline, brief)

    unreadable_timer = ShotPlan(
        shots=[
            shot(
                scene_id="grid",
                asset_id="grid_asset",
                entity_ids=["schulte_grid"],
                end_frame=300,
                span_ids=[0, 1],
                narrative_role="diagram",
                treatment="mechanism",
                subject="Schulte grid",
                visible_state="Grid fills the frame",
                setting="Clean graphic field",
                framing="diagram",
                composition="High-contrast local grid",
                overlays=[
                    grid | {"end_frame": 300},
                    {
                        "kind": "timer",
                        "start_frame": 0,
                        "end_frame": 300,
                        "text": "40",
                    },
                ],
            )
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=300,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="MM:SS"):
        validate_plan(unreadable_timer, timeline, brief)


def test_schulte_center_instruction_and_countdown_require_local_animation():
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [
            {
                "index": 0,
                "start_frame": 0,
                "end_frame": 150,
                "text": "جدول شولتي ثبت نظرك على المركز",
            },
            {
                "index": 1,
                "start_frame": 150,
                "end_frame": 300,
                "text": "جاهز واحد اثنان ثلاثة ابدأ",
            },
        ],
    }
    base_grid = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 300,
        "preset": "schulte_6x6",
    }

    def exercise_plan(overlays):
        return ShotPlan(
            shots=[
                shot(
                    scene_id="grid",
                    asset_id="grid_asset",
                    entity_ids=["schulte_grid"],
                    end_frame=300,
                    span_ids=[0, 1],
                    narrative_role="diagram",
                    treatment="mechanism",
                    subject="Schulte grid",
                    visible_state="Grid fills the frame",
                    setting="Clean graphic field",
                    framing="diagram",
                    composition="High-contrast local grid",
                    operation="local_canvas",
                    overlays=overlays,
                )
            ],
            brief_sha256="a" * 64,
            timeline_sha256=fingerprint(timeline),
            fps=30,
            total_frames=300,
            editorial_policy=resolve_editorial_policy(version_two_brief()),
        )

    with pytest.raises(ValueError, match="center-fixation instruction requires a local highlight"):
        _validate_interactive_graphics(exercise_plan([base_grid]), timeline, complete=True)

    highlight = {
        "kind": "highlight",
        "start_frame": 0,
        "end_frame": 150,
        "x": 0.44,
        "y": 0.44,
        "width": 0.12,
        "height": 0.12,
    }
    with pytest.raises(ValueError, match="spoken countdown requires a local countdown label"):
        _validate_interactive_graphics(
            exercise_plan([base_grid, highlight]), timeline, complete=True
        )

    countdown = {
        "kind": "label",
        "start_frame": 150,
        "end_frame": 300,
        "text": "جاهز 1 2 3",
    }
    _validate_interactive_graphics(
        exercise_plan([base_grid, highlight, countdown]), timeline, complete=True
    )


def test_schulte_partial_plan_does_not_require_future_countdown_label():
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [
            {
                "index": 0,
                "start_frame": 0,
                "end_frame": 150,
                "text": "جدول شولتي ثبت نظرك على المركز",
            },
            {
                "index": 1,
                "start_frame": 150,
                "end_frame": 300,
                "text": "جاهز واحد اثنان ثلاثة ابدأ",
            },
        ],
    }
    partial = ShotPlan(
        shots=[
            shot(
                scene_id="grid",
                asset_id="grid_asset",
                entity_ids=["schulte_grid"],
                end_frame=150,
                span_ids=[0],
                narrative_role="diagram",
                treatment="mechanism",
                subject="Schulte grid",
                visible_state="Grid fills the frame",
                setting="Clean graphic field",
                framing="diagram",
                composition="High-contrast local grid",
                operation="local_canvas",
                overlays=[
                    {
                        "kind": "data_grid",
                        "start_frame": 0,
                        "end_frame": 150,
                        "preset": "schulte_6x6",
                    },
                    {
                        "kind": "highlight",
                        "start_frame": 0,
                        "end_frame": 150,
                        "x": 0.44,
                        "y": 0.44,
                        "width": 0.12,
                        "height": 0.12,
                    },
                ],
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=150,
        editorial_policy=resolve_editorial_policy(version_two_brief()),
    )
    _validate_interactive_graphics(partial, timeline, complete=False)


def test_schulte_grid_continuity_is_enforced_in_partial_plans():
    brief = version_two_brief()
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [
            {"index": 0, "start_frame": 0, "end_frame": 150, "text": "جدول شولتي"},
            {"index": 1, "start_frame": 150, "end_frame": 300, "text": "جاهز ابدأ"},
        ],
    }
    grid = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 90,
        "preset": "schulte_6x6",
    }
    partial = ShotPlan(
        shots=[
            shot(
                scene_id="grid",
                asset_id="grid_asset",
                entity_ids=["schulte_grid"],
                end_frame=90,
                span_ids=[0],
                narrative_role="diagram",
                treatment="mechanism",
                subject="Schulte grid",
                visible_state="Grid fills the frame",
                setting="Clean graphic field",
                framing="diagram",
                composition="High-contrast local grid",
                overlays=[grid],
            ),
            shot(
                shot_id="cutaway",
                scene_id="kitchen",
                asset_id="kitchen_asset",
                entity_ids=["person"],
                start_frame=90,
                end_frame=150,
                span_ids=[0],
                narrative_role="story_subject",
                subject="Person in kitchen",
                visible_state="Person looks toward a counter",
                setting="Kitchen",
                framing="medium",
                composition="Person beside counter",
            ),
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=150,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="dominant canvas"):
        _validate_interactive_graphics(partial, timeline, complete=False)


def test_schulte_grid_cannot_be_revealed_too_early():
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [
            {"index": 0, "start_frame": 0, "end_frame": 120, "text": "مقدمة"},
            {"index": 1, "start_frame": 120, "end_frame": 300, "text": "جدول شولتي جاهز ابدأ"},
        ],
    }
    grid = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 300,
        "preset": "schulte_6x6",
    }
    early = ShotPlan(
        shots=[
            shot(
                scene_id="grid",
                asset_id="grid_asset",
                entity_ids=["schulte_grid"],
                end_frame=300,
                span_ids=[0, 1],
                narrative_role="diagram",
                treatment="mechanism",
                subject="Schulte grid",
                visible_state="Grid fills the frame",
                setting="Clean graphic field",
                framing="diagram",
                composition="High-contrast local grid",
                overlays=[grid],
            )
        ],
        brief_sha256="a" * 64,
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=300,
        editorial_policy=resolve_editorial_policy(version_two_brief()),
    )
    with pytest.raises(ValueError, match="more than one second before"):
        _validate_interactive_graphics(early, timeline, complete=False)


def test_schulte_preset_overwrites_untrusted_model_geometry_and_values():
    overlay = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 60,
        "preset": "schulte_6x6",
        "rows": 1,
        "columns": 2,
        "cells": ["wrong", "values"],
    }
    normalized = shot(
        narrative_role="diagram",
        treatment="mechanism",
        framing="diagram",
        operation="local_canvas",
        overlays=[overlay],
    ).overlays[0]
    assert normalized.rows == 6
    assert normalized.columns == 6
    assert (normalized.x, normalized.y, normalized.width, normalized.height) == (
        0.15,
        0.15,
        0.7,
        0.7,
    )
    assert normalized.cells == [
        "17", "3", "29", "12", "35", "8",
        "24", "31", "6", "19", "1", "27",
        "10", "22", "34", "15", "26", "5",
        "33", "14", "21", "7", "30", "18",
        "4", "28", "11", "36", "16", "23",
        "25", "9", "32", "2", "20", "13",
    ]


def test_version_one_channel_fingerprint_remains_backward_compatible():
    channel = episode_brief().channel
    legacy = channel.model_dump(mode="json")
    legacy.pop("visual_directives")
    legacy.pop("forbidden_motifs")
    legacy.pop("forbidden_visual_families")
    legacy.pop("repetition_limited_visual_families")
    legacy.pop("max_visual_family_repetitions")
    legacy.pop("max_non_diagram_scene_appearances")
    assert fingerprint(channel) == fingerprint(legacy)


def test_version_two_channel_fingerprint_includes_visual_policy():
    channel = version_two_brief().channel
    changed = channel.model_copy(update={"forbidden_motifs": ["floating icon"]})
    assert fingerprint(channel) != fingerprint(changed)


def test_version_two_channel_fingerprint_ignores_version_three_policy_defaults():
    channel = version_two_brief().channel
    legacy = channel.model_dump(mode="json")
    legacy.pop("forbidden_visual_families")
    legacy.pop("repetition_limited_visual_families")
    legacy.pop("max_visual_family_repetitions")
    legacy.pop("max_non_diagram_scene_appearances")
    assert fingerprint(channel) == fingerprint(legacy)


def test_version_three_channel_fingerprint_includes_semantic_policy():
    channel = version_two_brief().channel.model_copy(
        update={
            "version": 3,
            "forbidden_visual_families": ["mechanical_cognition"],
        }
    )
    changed = channel.model_copy(
        update={"forbidden_visual_families": ["efficacy_transformation"]}
    )
    assert fingerprint(channel) != fingerprint(changed)


def test_generation_prompt_carries_channel_visual_policy():
    brief = version_two_brief()
    channel = brief.channel.model_copy(
        update={"forbidden_visual_families": ["mechanical_cognition"]}
    )
    brief = brief.model_copy(
        update={"channel": channel, "profile_sha256": fingerprint(channel)}
    )
    prompt = generation_prompt(shot(narrative_role="story_subject"), brief)
    assert "Use specific human contexts and clean local diagrams" in prompt
    assert "mechanical puzzle; glowing brain" in prompt
    assert "tracks, tiles, mechanisms, puzzles" in prompt


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


def test_incompatible_explicit_reference_operation_is_normalized_from_entities():
    plan = ShotPlan(
        shots=[
            shot(asset_id="a0", entity_ids=["cat"]),
            shot(
                shot_id="s2",
                asset_id="a1",
                reference_asset_id="a0",
                entity_ids=["cat", "ball"],
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
    assert plan.shots[1].operation == "add"


def test_same_asset_reframe_normalizes_to_local_subset_reuse():
    first = shot(
        asset_id="kitchen",
        scene_id="kitchen_scene",
        entity_ids=["adult", "keys", "counter"],
    )
    detail = shot(
        shot_id="s2",
        asset_id="kitchen",
        reference_asset_id="kitchen",
        scene_id="kitchen_scene",
        entity_ids=["keys", "counter"],
        span_ids=[1],
        start_frame=60,
        end_frame=120,
        framing="close_up",
        operation="reframe",
    )
    plan = ShotPlan(
        shots=[first, detail],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=120,
        editorial_policy=editorial_policy(),
    )
    assert plan.shots[1].operation == "reuse"
    assert plan.shots[1].reference_asset_id is None


def test_file_grounding_citations_are_removed_from_shot_text():
    grounded = shot(
        subject="An adult pauses in a kitchen[cite: 4].",
        visible_state="Looking past visible keys [cite: 3, 7]",
    )
    assert grounded.subject == "An adult pauses in a kitchen."
    assert grounded.visible_state == "Looking past visible keys"


def test_generic_desk_task_rejects_real_staged_drafting_and_card_concepts():
    from youtube_automation.production.shots import _shot_visual_families

    rejected_concepts = [
        shot(
            subject="A hand holding a pen, actively drawing a sharp, continuous line connecting a series of cobalt ink dots on a vertical paper board.",
            visible_state="executing a confident, bold path with a pen",
            setting="Extreme close-up on a textured tactile paper surface",
            entity_ids=["hand_pen", "paper_board"],
        ),
        shot(
            subject="A person's hands confidently using a brass drafting compass to draw precise shapes on a piece of tactile paper.",
            visible_state="steady and precise, deliberately manipulating the drafting tool over the paper",
            setting="A clean wooden drafting table",
            entity_ids=["hands", "compass"],
        ),
        shot(
            subject="A young adult standing in front of a massive wall covered in scattered, overlapping paper notes, rubbing their forehead in frustration.",
            visible_state="looking overwhelmed and exhausted by the chaotic environment",
            setting="A dimly lit room with wall papers",
            entity_ids=["adult"],
        ),
        shot(
            subject="A young adult standing by a wooden bookshelf, eagerly pulling out a thick, tactile paper sketchpad.",
            visible_state="actively removing the sketchpad from the shelf with anticipation",
            setting="A studio room with a large wooden bookshelf",
            entity_ids=["adult_hobbyist", "sketchpad"],
        ),
        shot(
            subject="A young adult leaning forward, actively tracing a path on a large structural sketch pinned to a studio wall.",
            visible_state="evaluating the sketch with focused intent",
            setting="A studio with a structural sketch",
            entity_ids=["adult"],
        ),
        shot(
            subject="A person eagerly arranging a chaotic spread of bold, tactile index cards on a wide wooden table.",
            visible_state="hands actively moving the cards across the surface with focused intent",
            setting="Minimalist studio with wooden table",
            entity_ids=["person", "tactile_cards"],
        ),
    ]
    for s in rejected_concepts:
        families = _shot_visual_families(s)
        assert "generic_desk_task" in families, f"Expected generic_desk_task for: {s.subject}"


def test_generic_desk_task_permits_relatable_daily_attention_lapses():
    from youtube_automation.production.shots import _shot_visual_families

    valid_attention_lapses = [
        shot(
            subject="An adult searching for car keys across a cluttered kitchen table, looking right past the keys sitting beside a mug.",
            visible_state="furrowed brow and distracted expression, unaware the keys are in plain sight",
            setting="Warm residential kitchen table in morning light",
            entity_ids=["adult", "keys"],
        ),
        shot(
            subject="An adult seated at a dining table holding a cup of tea, gazing out the window lost in thought while an open book sits ignored on the table.",
            visible_state="gaze unfocused, completely drifted away from reading",
            setting="Quiet dining room table with rain streaking the window",
            entity_ids=["adult", "tea_cup"],
        ),
        shot(
            subject="A person standing in an office doorway holding an empty mug, looking around trying to remember what they came to fetch.",
            visible_state="hesitating mid-step with a puzzled, blank expression",
            setting="Residential hallway doorway connecting to an office",
            entity_ids=["person"],
        ),
        shot(
            subject="An adult at a kitchen counter glancing at a smartphone that just lit up with a notification, attention pulled away from an open cookbook.",
            visible_state="head turned toward the illuminated screen, interrupted mid-recipe",
            setting="Home kitchen counter with ingredients and an open recipe book",
            entity_ids=["adult", "phone"],
        ),
    ]
    for s in valid_attention_lapses:
        families = _shot_visual_families(s)
        assert "generic_desk_task" not in families, f"Did not expect generic_desk_task for: {s.subject}"


def test_efficacy_transformation_rejects_boost_and_renewed_clarity_paraphrases():
    from youtube_automation.production.shots import _shot_visual_families

    boost_shot = shot(
        subject="A person demonstrating a dramatic boost in focus following the exercise",
        visible_state="radiating mental energy with heightened clarity",
        entity_ids=["person"],
        purpose="Show the transformed cognitive state",
    )
    assert "efficacy_transformation" in _shot_visual_families(boost_shot)

    clarity_shot = shot(
        subject="An adult showing renewed clarity and transformed mental sharpness after the cognitive test",
        visible_state="eyes bright with elevated focus and active cognitive sharpness",
        entity_ids=["adult"],
        purpose="Illustrate the desired mental outcome",
    )
    assert "efficacy_transformation" in _shot_visual_families(clarity_shot)


def test_generic_focus_portrait_classification_and_lapse_counterexamples():
    from youtube_automation.production.shots import _shot_visual_families

    staged_portrait = shot(
        subject="A student sitting at a clean desk, looking focused",
        visible_state="Staring forward with a steady gaze and confident expression",
        framing="medium",
        entity_ids=["student"],
        purpose="Show dedication to studying",
    )
    assert "generic_focus_portrait" in _shot_visual_families(staged_portrait)

    alert_portrait = shot(
        subject="Portrait of a worker with alert eyes",
        visible_state="Focused expression looking ahead",
        framing="close_up",
        entity_ids=["worker"],
        purpose="Demonstrate mental clarity",
    )
    assert "generic_focus_portrait" in _shot_visual_families(alert_portrait)

    cosmetic_face_detail = shot(
        treatment="detail",
        subject="Close up of the woman's face and hands as she finishes tying her hair",
        visible_state="Alert expression, hands adjusting her hair",
        framing="close_up",
        entity_ids=["woman"],
        purpose="Convey sharpness and active engagement",
    )
    assert "generic_focus_portrait" in _shot_visual_families(cosmetic_face_detail)

    attention_lapse = shot(
        subject="A man in a jacket standing by his front door, holding his house keys in his left hand while frantically searching his own jacket pockets with his right hand",
        visible_state="Frantically searching pockets, looking confused, completely unaware he is already holding the keys",
        framing="medium",
        entity_ids=["man", "keys"],
        purpose="Establish the relatable feeling of foggy thinking and lost focus using a common daily attention lapse",
    )
    assert "generic_focus_portrait" not in _shot_visual_families(attention_lapse)

    hand_detail = shot(
        treatment="detail",
        subject="Close up of the man's hand firmly holding the house keys",
        visible_state="Hand holding the keys motionless",
        framing="close_up",
        entity_ids=["man", "keys"],
        purpose="Highlight the object of attention failure to emphasize the cognitive lapse",
    )
    assert "generic_focus_portrait" not in _shot_visual_families(hand_detail)

    physical_action = shot(
        subject="A woman standing at a bathroom sink, splashing cold water on her face",
        visible_state="Splashing water on her face, eyes closed but expression awake and refreshed",
        framing="medium",
        entity_ids=["woman", "sink"],
        purpose="Ground waking up the mind in a physical routine",
    )
    assert "generic_focus_portrait" not in _shot_visual_families(physical_action)


def test_perfect_mental_clarity_portrait_is_an_efficacy_transformation():
    from youtube_automation.production.shots import _shot_visual_families

    portrait = shot(
        subject="Close-up view of a man's face",
        visible_state="A self-assured smile radiating a sense of perfect mental clarity",
        framing="close_up",
        entity_ids=["man"],
        purpose="Highlight total mental confidence",
    )
    assert "efficacy_transformation" in _shot_visual_families(portrait)


def test_unestablished_clinical_diagnostic_language_is_false_authority():
    from youtube_automation.production.shots import _shot_visual_families

    clinical = shot(
        narrative_role="diagram",
        treatment="mechanism",
        framing="diagram",
        subject="Schulte 6x6 interactive matrix",
        visible_state="Clinical diagnostic metric callout",
        entity_ids=["schulte_grid"],
        purpose="Present a diagnostic test of processing speed",
    )
    assert "false_authority" in _shot_visual_families(clinical)


def test_diagram_role_cannot_disguise_an_ordinary_object_detail():
    brief = version_two_brief()
    mislabeled = ShotPlan(
        shots=[shot(narrative_role="diagram", framing="close_up")],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=60,
        editorial_policy=resolve_editorial_policy(brief),
    )
    with pytest.raises(ValueError, match="require diagram framing"):
        _validate_editorial_quality(mislabeled, brief, complete=False)


def test_local_canvas_is_reserved_for_local_full_frame_data_diagrams():
    overlay = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 60,
        "preset": "schulte_6x6",
    }
    accepted = shot(
        narrative_role="diagram",
        treatment="mechanism",
        framing="diagram",
        operation="local_canvas",
        overlays=[overlay],
    )
    assert accepted.operation == "local_canvas"
    with pytest.raises(ValueError, match="reserved for full-frame diagrams"):
        shot(operation="local_canvas", overlays=[overlay])


def test_branded_schulte_composition_requires_all_playability_layers():
    base = {
        "narrative_role": "diagram",
        "treatment": "mechanism",
        "framing": "diagram",
        "operation": "local_canvas",
        "local_composition": "schulte_challenge",
    }
    incomplete = [
        {
            "kind": "data_grid",
            "preset": "schulte_6x6",
            "start_frame": 0,
            "end_frame": 60,
        }
    ]
    with pytest.raises(ValueError, match="branded challenge layers"):
        shot(**base, overlays=incomplete)

    complete = incomplete + [
        {"kind": "challenge_frame", "start_frame": 0, "end_frame": 60, "text": "Focus"},
        {"kind": "rule_reveal", "start_frame": 0, "end_frame": 30, "text": "Find 1 to 36"},
        {"kind": "fixation_cue", "start_frame": 0, "end_frame": 30},
        {"kind": "target_indicator", "start_frame": 15, "end_frame": 45, "target_cell": 10},
        {"kind": "start_transition", "start_frame": 30, "end_frame": 45, "text": "Start"},
    ]
    branded = shot(**base, overlays=complete)
    assert branded.local_composition == "schulte_challenge"
    with pytest.raises(ValueError, match="less than or equal to 35"):
        Overlay(
            kind="target_indicator",
            start_frame=0,
            end_frame=30,
            target_cell=36,
        )
    with pytest.raises(ValueError, match="data-grid overlay"):
        shot(
            narrative_role="diagram",
            treatment="mechanism",
            framing="diagram",
            operation="local_canvas",
        overlays=[],
    )


def test_branded_schulte_layers_satisfy_center_and_start_narration():
    brief = version_three_brief()
    timeline = {
        "fps": 30,
        "total_frames": 300,
        "spans": [
            {
                "index": 0,
                "start_frame": 0,
                "end_frame": 150,
                "text": "جدول شولتي ثبت نظرك على المركز",
            },
            {
                "index": 1,
                "start_frame": 150,
                "end_frame": 300,
                "text": "جاهز واحد اثنان ثلاثة ابدأ",
            },
        ],
    }
    overlays = [
        {"kind": "data_grid", "preset": "schulte_6x6", "start_frame": 0, "end_frame": 300},
        {"kind": "challenge_frame", "start_frame": 0, "end_frame": 300, "text": "Focus"},
        {"kind": "rule_reveal", "start_frame": 0, "end_frame": 90, "text": "Find 1 to 36"},
        {"kind": "fixation_cue", "start_frame": 0, "end_frame": 150},
        {"kind": "target_indicator", "start_frame": 90, "end_frame": 210, "target_cell": 10},
        {"kind": "start_transition", "start_frame": 150, "end_frame": 180, "text": "Start"},
    ]
    plan = ShotPlan(
        version=3,
        shots=[
            shot(
                scene_id="grid",
                asset_id="grid_asset",
                entity_ids=["schulte_grid"],
                end_frame=300,
                span_ids=[0, 1],
                narrative_role="diagram",
                treatment="mechanism",
                subject="Schulte grid",
                visible_state="Grid fills frame",
                setting="Clean graphic field",
                framing="diagram",
                composition="Branded high-contrast local challenge",
                operation="local_canvas",
                local_composition="schulte_challenge",
                overlays=overlays,
            )
        ],
        brief_sha256=fingerprint(brief),
        timeline_sha256=fingerprint(timeline),
        fps=30,
        total_frames=300,
        editorial_policy=resolve_editorial_policy(brief),
    )

    _validate_interactive_graphics(plan, timeline, complete=True)


def test_repeated_identical_local_canvas_declaration_normalizes_to_reuse():
    overlay = {
        "kind": "data_grid",
        "start_frame": 0,
        "end_frame": 60,
        "preset": "schulte_6x6",
    }
    first = shot(
        shot_id="grid_1",
        scene_id="exercise",
        asset_id="canvas",
        entity_ids=["schulte_grid"],
        narrative_role="diagram",
        treatment="mechanism",
        framing="diagram",
        operation="local_canvas",
        overlays=[overlay],
    )
    second = shot(
        shot_id="grid_2",
        scene_id="exercise",
        asset_id="canvas",
        entity_ids=["schulte_grid"],
        span_ids=[1],
        start_frame=60,
        end_frame=120,
        narrative_role="diagram",
        treatment="mechanism",
        framing="diagram",
        operation="local_canvas",
        overlays=[overlay],
    )
    plan = ShotPlan(
        shots=[first, second],
        brief_sha256="a" * 64,
        timeline_sha256="b" * 64,
        fps=30,
        total_frames=120,
        editorial_policy=editorial_policy(),
    )
    assert plan.shots[1].operation == "reuse"


def test_wellness_strawman_requires_visible_prop():
    from youtube_automation.production.shots import _shot_visual_families

    visible_incense = shot(
        subject="An unlit incense burner on a shelf",
        visible_state="Cold, dusty and ignored",
        entity_ids=["incense_burner"],
        purpose="Represent the boring meditation alternative that narration dismisses",
    )
    assert "wellness_strawman" in _shot_visual_families(visible_incense)

    contrastive_fingers = shot(
        treatment="detail",
        subject="Close up of the woman's fingers drumming impatiently on the edge of the wooden bathroom counter",
        visible_state="Fingers tapping rapidly in a rhythmic, impatient motion",
        framing="insert",
        entity_ids=["woman", "counter"],
        purpose="Convey impatience and rejection of slow, boring solutions (like meditation) through restless body language, avoiding any forbidden wellness tropes or props",
    )
    assert "wellness_strawman" not in _shot_visual_families(contrastive_fingers)
