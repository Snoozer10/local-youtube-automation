import pytest

from youtube_automation.production.contracts import Analysis, Brief, Channel, fingerprint
from youtube_automation.production.shots import Shot, ShotPlan, generation_prompt, validate_plan


def shot(**updates):
    data = {
        "shot_id": "s1",
        "scene_id": "animal",
        "asset_id": "a1",
        "span_ids": [0, 1],
        "start_frame": 0,
        "end_frame": 60,
        "purpose": "Show what the animal is watching",
        "treatment": "subject_scene",
        "subject": "Cat watching a hand",
        "visible_state": "Eyes directed at the hand",
        "setting": "Garden",
        "composition": "Eye-level close-up",
    }
    return Shot(**(data | updates))


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
            scenes = [shot(end_frame=750, span_ids=list(range(25)))]
        else:
            scenes = [
                shot(shot_id="s2", start_frame=750, end_frame=780, span_ids=[25], operation="reuse")
            ]
        return json.dumps({"shots": [s.model_dump() for s in scenes]})

    plan = ensure_shot_plan(tmp_path, ask)
    assert len(calls) == 2
    assert '"asset_id": "a1"' in calls[1]
    assert plan.total_frames == 780
    prepare_flow(tmp_path, lambda _: pytest.fail("Validated plan should resume"))
    parsed = parse_json_prompts(str(tmp_path / "flow_prompts.json"))
    assert len(parsed) == 1  # Deliberate local reuse never requests new diffusion output.
    assert parsed[0].raw_payload["adaptive_shot"]["asset_id"] == "a1"
    assert parsed[0].raw_payload["adaptive_shot"]["subject"] == "Cat watching a hand"


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
    )
    assert [s.span_ids for s in plan.shots] == [[0], [0]]


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
        )
