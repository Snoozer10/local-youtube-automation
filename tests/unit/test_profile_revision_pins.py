from pathlib import Path

import pytest

from youtube_automation.production.briefs import (
    analyze_script,
    ensure_brief,
    rebind_visual_policy,
)
from youtube_automation.production.contracts import (
    Analysis,
    Brief,
    Channel,
    EpisodeVisualStrategy,
    fingerprint,
    load_brief,
    profile_revision_identity,
    verify_profile_pin,
)


def sample_channel(version: int = 3, revision: str | None = None) -> Channel:
    return Channel(
        version=version,
        revision=revision,
        channel_id="snoozer-anime",
        name="Test Channel",
        audience="Anime enthusiasts",
        language="Arabic",
        dialect="Egyptian",
        asr_language="ar",
        tone="Humorous and energetic",
        style="Dynamic anime recap with expressive framing",
        host_mode="NONE",
        allowed_treatments=["metaphor", "subject_scene"],
        humor="light",
        max_zoom=1.06,
        visual_directives=["Use scene-specific narrative framing"] if version >= 2 else [],
        forbidden_motifs=["generic B-roll"] if version >= 2 else [],
    )


def sample_analysis() -> Analysis:
    return Analysis(
        treatments=["metaphor", "subject_scene"],
        topics=["perception", "focus"],
        claim_basis="factual",
        form="explanation",
        proposition="Perception varies across observers",
        narrative_strategy="Compare observational contrasts",
        rationale="Highlights perceptual differences",
    )


def sample_strategy(source_sha256: str) -> EpisodeVisualStrategy:
    return EpisodeVisualStrategy(
        source_sha256=source_sha256,
        topic="Animal perception",
        viewer_question="What does an animal notice?",
        central_promise="Experience another point of view",
        evidence_mode="observational",
        emotional_arc=["curiosity", "understanding"],
        hook_archetype="mystery_gap",
        hook_microbeats=[
            {
                "beat_id": "p",
                "function": "problem",
                "duration_seconds": 3,
                "viewer_takeaway": "We miss unnoticed signals",
                "visual_mode": "human_context",
            },
            {
                "beat_id": "c",
                "function": "curiosity",
                "duration_seconds": 3,
                "viewer_takeaway": "Animals detect different signals",
                "visual_mode": "environmental_detail",
            },
            {
                "beat_id": "h",
                "function": "handoff",
                "duration_seconds": 3,
                "viewer_takeaway": "Compare them side by side",
                "visual_mode": "comparison",
            },
        ],
        visual_modes=["human_context", "environmental_detail", "comparison"],
        pacing="Rapid question followed by clear examples",
        motion_grammar=["Move only on meaningful transitions"],
    )


def test_new_brief_records_profile_revision_and_digest():
    raw = "Observation and perception across species."
    channel = sample_channel(version=3, revision="rev_20261026_01")
    strategy = sample_strategy(fingerprint(raw))

    def ask(prompt: str) -> str:
        if "visual strategy" in prompt.lower():
            return strategy.model_dump_json()
        return sample_analysis().model_dump_json()

    brief = analyze_script(raw, channel, ask)
    assert brief.profile_revision == "rev_20261026_01"
    assert brief.profile_sha256 == fingerprint(channel)
    assert verify_profile_pin(brief, channel) is True
    assert verify_profile_pin(brief) is True


def test_profile_content_revisions_remain_distinct_sharing_format_version():
    channel_rev_a = sample_channel(version=3, revision="profile-rev-a")
    channel_rev_b = sample_channel(version=3, revision="profile-rev-b")

    assert channel_rev_a.version == channel_rev_b.version == 3
    assert profile_revision_identity(channel_rev_a) == "profile-rev-a"
    assert profile_revision_identity(channel_rev_b) == "profile-rev-b"
    assert fingerprint(channel_rev_a) != fingerprint(channel_rev_b)

    raw = "Sensory inputs in varied contexts."
    strat_a = sample_strategy(fingerprint(raw))
    strat_b = sample_strategy(fingerprint(raw))

    def ask_a(prompt: str) -> str:
        if "visual strategy" in prompt.lower():
            return strat_a.model_dump_json()
        return sample_analysis().model_dump_json()

    def ask_b(prompt: str) -> str:
        if "visual strategy" in prompt.lower():
            return strat_b.model_dump_json()
        return sample_analysis().model_dump_json()

    brief_a = analyze_script(raw, channel_rev_a, ask_a)
    brief_b = analyze_script(raw, channel_rev_b, ask_b)

    assert brief_a.profile_revision == "profile-rev-a"
    assert brief_b.profile_revision == "profile-rev-b"
    assert brief_a.profile_sha256 != brief_b.profile_sha256
    assert verify_profile_pin(brief_a, channel_rev_a) is True
    assert verify_profile_pin(brief_b, channel_rev_b) is True
    assert verify_profile_pin(brief_a, channel_rev_b) is False
    assert verify_profile_pin(brief_b, channel_rev_a) is False


def test_legacy_brief_without_profile_revision_retains_compatibility(tmp_path: Path):
    raw = "Legacy brief compatibility test transcript."
    legacy_channel = sample_channel(version=2, revision=None)
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")

    legacy_brief = Brief(
        version=2,
        source_sha256=fingerprint(raw),
        profile_sha256=fingerprint(legacy_channel),
        profile_revision=None,
        channel=legacy_channel,
        analysis=sample_analysis(),
        visual_strategy=None,
    )
    brief_path = tmp_path / "episode_brief.json"
    brief_path.write_text(legacy_brief.model_dump_json(), encoding="utf-8")

    loaded = load_brief(tmp_path)
    assert loaded.profile_revision is None
    assert loaded.profile_sha256 == fingerprint(legacy_channel)
    assert verify_profile_pin(loaded, legacy_channel) is True


def test_mismatched_profile_revision_or_digest_fails_safely():
    raw = "Verification safety tests."
    channel_valid = sample_channel(version=3, revision="rev-valid")
    channel_mismatched = sample_channel(version=3, revision="rev-changed")
    strategy = sample_strategy(fingerprint(raw))

    brief = Brief(
        version=3,
        source_sha256=fingerprint(raw),
        profile_sha256=fingerprint(channel_valid),
        profile_revision="rev-valid",
        channel=channel_valid,
        analysis=sample_analysis(),
        visual_strategy=strategy,
    )

    # Valid pin verifies successfully
    assert verify_profile_pin(brief, channel_valid) is True

    # Mismatched revision fails
    assert verify_profile_pin(brief, channel_mismatched) is False

    # Corrupted revision identity in Brief raises validation error
    with pytest.raises(ValueError, match="Profile revision identity mismatch"):
        Brief(
            version=3,
            source_sha256=fingerprint(raw),
            profile_sha256=fingerprint(channel_valid),
            profile_revision="unrelated-revision-pin",
            channel=channel_valid,
            analysis=sample_analysis(),
            visual_strategy=strategy,
        )

    # Corrupted profile digest raises validation error
    with pytest.raises(ValueError, match="Profile digest mismatch"):
        Brief(
            version=3,
            source_sha256=fingerprint(raw),
            profile_sha256="0" * 64,
            profile_revision="rev-valid",
            channel=channel_valid,
            analysis=sample_analysis(),
            visual_strategy=strategy,
        )


def test_running_episode_with_downstream_artifacts_refuses_silent_revision_rebind(tmp_path: Path):
    raw = "Downstream protection test script."
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    channel_v1 = sample_channel(version=3, revision="rev-initial")
    strat = sample_strategy(fingerprint(raw))

    def ask(prompt: str) -> str:
        if "visual strategy" in prompt.lower():
            return strat.model_dump_json()
        return sample_analysis().model_dump_json()

    brief = ensure_brief(tmp_path, channel_v1, ask)
    assert brief.profile_revision == "rev-initial"

    # Simulate downstream progress
    (tmp_path / "final_output.txt").write_text("Rendered output", encoding="utf-8")

    # Attempt to run ensure_brief with a changed profile revision
    channel_v2 = sample_channel(version=3, revision="rev-modified")
    with pytest.raises(ValueError, match="Changed brief inputs with downstream artifacts"):
        ensure_brief(tmp_path, channel_v2, ask)


def test_visual_policy_rebind_preserves_bound_profile_revision(tmp_path: Path):
    raw = "Visual policy preservation test."
    (tmp_path / "raw_transcript.txt").write_text(raw, encoding="utf-8")
    initial_channel = sample_channel(version=2, revision="rev-locked-2026")

    brief = analyze_script(raw, initial_channel, lambda _: sample_analysis().model_dump_json())
    (tmp_path / "episode_brief.json").write_text(brief.model_dump_json(), encoding="utf-8")

    upgraded_channel = initial_channel.model_copy(
        update={
            "visual_directives": ["New visual directive added"],
            "forbidden_motifs": ["New forbidden motif added"],
        }
    )

    rebound = rebind_visual_policy(tmp_path, upgraded_channel)
    assert rebound.profile_revision == "rev-locked-2026"
    assert rebound.channel == upgraded_channel
    assert verify_profile_pin(rebound) is True
