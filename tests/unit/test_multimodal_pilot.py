"""Integrated verification tests for Issues #46, #47, #48, #49, and #50.

Covers:
- #46: Visual and motion evidence bundle into new-episode guidance.
- #47: Actual-audio evidence bundle into new-episode guidance.
- #48: Title and thumbnail bundle into packaging guidance.
- #49: Explicit migration of existing episodes to selected revision.
- #50: Integrated resumable channel-study pilot with end-to-end recovery proof.
"""

import json
from pathlib import Path

import pytest

from youtube_automation.production.briefs import is_visual_policy_update, rebind_visual_policy
from youtube_automation.production.contracts import (
    Analysis,
    Brief,
    Channel,
    EpisodeVisualStrategy,
    HookMicrobeat,
    fingerprint,
    verify_profile_pin,
)
from youtube_automation.production.profile_activation import (
    ProfileActivationManager,
    derive_production_profile,
)
from youtube_automation.production.study import (
    CandidateVideo,
    StudyCollector,
    StudyStatus,
)


def sample_analysis() -> Analysis:
    return Analysis(
        treatments=["subject_scene", "detail"],
        topics=["military tactics", "history"],
        claim_basis="factual",
        form="explanation",
        proposition="Tactics evolve through conflict",
        narrative_strategy="Chronological documentary structure",
        rationale="Clear explanatory progression",
    )


def sample_strategy(source_sha256: str) -> EpisodeVisualStrategy:
    return EpisodeVisualStrategy(
        source_sha256=source_sha256,
        topic="Tactics evolution",
        viewer_question="How did defensive formations adapt?",
        central_promise="Understand tactical shifts",
        evidence_mode="observational",
        emotional_arc=["curiosity", "understanding"],
        hook_archetype="pattern_interrupt",
        hook_microbeats=[
            HookMicrobeat(
                beat_id="beat_1",
                function="problem",
                duration_seconds=3.0,
                viewer_takeaway="Ancient formations broke easily",
                visual_mode="human_context",
            ),
            HookMicrobeat(
                beat_id="beat_2",
                function="curiosity",
                duration_seconds=3.0,
                viewer_takeaway="New defensive line was devised",
                visual_mode="environmental_detail",
            ),
            HookMicrobeat(
                beat_id="beat_3",
                function="promise",
                duration_seconds=3.0,
                viewer_takeaway="How the shield wall functioned",
                visual_mode="mechanism",
            ),
        ],
        visual_modes=["human_context", "environmental_detail", "mechanism"],
        pacing="Deliberate explanatory cadence",
        motion_grammar=["Slow lateral panning on line formation"],
    )


@pytest.fixture
def multimodal_study(tmp_path: Path) -> tuple[StudyCollector, Path]:
    study_dir = tmp_path / "study_multimodal"
    collector = StudyCollector(study_dir)

    candidates = [
        CandidateVideo(video_id="v01", title="Ep 1", published_at="2026-10-01T10:00:00Z", duration_sec=500, view_count=1000),
        CandidateVideo(video_id="v02", title="Ep 2", published_at="2026-10-05T10:00:00Z", duration_sec=600, view_count=2000),
        CandidateVideo(video_id="v03", title="Ep 3", published_at="2026-10-10T10:00:00Z", duration_sec=700, view_count=3000),
    ]
    study = collector.initialize_study("study_multi", "pilot_channel", candidates)

    # 1. Transcripts for narrative/core
    study = collector.add_evidence(study, "v01", "transcript", b"Transcript 1 narrative bytes", evidence_id="ev_v01_t")
    study = collector.add_evidence(study, "v02", "transcript", b"Transcript 2 narrative bytes", evidence_id="ev_v02_t")

    # 2. Frames and clips for visual/motion (#46)
    study = collector.add_evidence(study, "v01", "frame", b"JPEG_FRAME_SAMPLE_1", examined_range=(10.0, 15.0), evidence_id="ev_frame")
    study = collector.add_evidence(study, "v02", "clip", b"MP4_CLIP_SAMPLE_2", examined_range=(30.0, 45.0), duration_sec=15.0, evidence_id="ev_clip")

    # 3. Audio for soundtrack treatment (#47)
    study = collector.add_evidence(study, "v01", "audio", b"RIFF_WAV_AUDIO_SAMPLE_1", examined_range=(0.0, 60.0), duration_sec=60.0, evidence_id="ev_audio1")
    study = collector.add_evidence(study, "v02", "audio", b"RIFF_WAV_AUDIO_SAMPLE_2", examined_range=(0.0, 60.0), duration_sec=60.0, evidence_id="ev_audio2")

    # 4. Title and thumbnail for packaging (#48)
    study = collector.add_evidence(study, "v01", "thumbnail", b"JPEG_THUMBNAIL_BYTES_1", evidence_id="ev_thumb1")
    study = collector.add_evidence(study, "v02", "thumbnail", b"JPEG_THUMBNAIL_BYTES_2", evidence_id="ev_thumb2")
    study = collector.add_evidence(study, "v01", "title", b"Why the Roman Shield Wall Never Failed", evidence_id="ev_title1")
    study = collector.add_evidence(study, "v02", "title", b"Why the Roman Shield Wall Never Failed Part 2", evidence_id="ev_title2")

    # Record 4 required core areas
    study = collector.record_core_trait(study, "subject_promise", "Ancient military formations", ["v01", "v02"], ["ev_v01_t", "ev_v02_t"], "Direct evidence")
    study = collector.record_core_trait(study, "viewer_need", "Military history fans", ["v01", "v02"], ["ev_v01_t", "ev_v02_t"], "Direct evidence")
    study = collector.record_core_trait(study, "tone_register", "Serious documentary Khaleeji", ["v01", "v02"], ["ev_v01_t", "ev_v02_t"], "Direct evidence")
    study = collector.record_core_trait(study, "narrative_structure", "Hook, explanation, resolution", ["v01", "v02"], ["ev_v01_t", "ev_v02_t"], "Direct evidence")

    # Record multimodal traits (#46, #47, #48)
    study = collector.record_core_trait(study, "visual_motion", "Rule-of-thirds historical portrait framing", ["v01", "v02"], ["ev_frame", "ev_clip"], "Slow linear pans")
    study = collector.record_core_trait(study, "soundtrack", "Acoustic oud ambient underbed, no heavy drums", ["v01", "v02"], ["ev_audio1", "ev_audio2"], "Muted during dialogue")
    study = collector.record_core_trait(study, "packaging", "Question hook title, high contrast central figure", ["v01", "v02"], ["ev_thumb1", "ev_thumb2", "ev_title1", "ev_title2"], "Bold white typography")

    return collector, study_dir


def test_issue_46_visual_and_motion_evidence_into_guidance(multimodal_study: tuple[StudyCollector, Path]):
    collector, _ = multimodal_study
    study = collector.load_study()
    assert study.status == StudyStatus.CORE_READY

    profile = derive_production_profile(study)
    assert "visual_guidance" in profile.model_dump()
    vg = profile.visual_guidance
    assert vg["composition"] == "Rule-of-thirds historical portrait framing"
    assert vg["motion_grammar"] == "Slow linear pans"
    assert profile.provenance["visual_guidance"] == "evidence_derived"


def test_issue_47_actual_audio_evidence_into_guidance(multimodal_study: tuple[StudyCollector, Path]):
    collector, _ = multimodal_study
    study = collector.load_study()

    owner_settings = {"voice": "Charon"}
    profile = derive_production_profile(study, owner_settings)

    ag = profile.audio_guidance
    assert ag["treatment"] == "Acoustic oud ambient underbed, no heavy drums"
    assert ag["sound_policy"] == "Muted during dialogue"
    assert profile.voice == "Charon"
    assert profile.provenance["voice"] == "owner_override"


def test_issue_48_title_and_thumbnail_into_packaging_guidance(multimodal_study: tuple[StudyCollector, Path]):
    collector, _ = multimodal_study
    study = collector.load_study()

    profile = derive_production_profile(study)
    pg = profile.packaging_guidance
    assert pg["packaging_rules"] == "Question hook title, high contrast central figure"
    assert pg["thumbnail_style"] == "Bold white typography"


def test_issue_49_explicit_migration_of_existing_episodes(tmp_path: Path):
    root = tmp_path / "run_migration"
    root.mkdir(parents=True, exist_ok=True)

    raw_narration = "Narration content that must be preserved."
    (root / "raw_transcript.txt").write_text(raw_narration, encoding="utf-8-sig")

    channel_v1 = Channel(
        channel_id="test_channel",
        name="test_channel",
        version=2,
        audience="History lovers",
        language="ar",
        dialect="khaleeji",
        tone="Documentary",
        style="Serious",
        voice="Achird",
        visual_directives=["Historical accuracy"],
        forbidden_motifs=["cartoon"],
        allowed_treatments=["subject_scene", "detail"],
        revision="rev_v1",
    )

    brief_v1 = Brief(
        version=2,
        source_sha256=fingerprint(raw_narration),
        profile_sha256=fingerprint(channel_v1),
        profile_revision=channel_v1.revision,
        channel=channel_v1,
        analysis=sample_analysis(),
    )
    (root / "episode_brief.json").write_text(brief_v1.model_dump_json(indent=2), encoding="utf-8")

    # Upgraded target channel (version 3)
    channel_v3 = Channel(
        channel_id="test_channel",
        name="test_channel",
        version=3,
        audience="History lovers",
        language="ar",
        dialect="khaleeji",
        tone="Documentary",
        style="Serious",
        voice="Achird",
        visual_directives=["Historical accuracy"],
        forbidden_motifs=["cartoon"],
        allowed_treatments=["subject_scene", "detail"],
        revision="rev_v3",
    )

    strategy = sample_strategy(fingerprint(raw_narration))
    def ask(_: str) -> str:
        return strategy.model_dump_json()

    assert is_visual_policy_update(root, channel_v3) is True
    rebound = rebind_visual_policy(root, channel_v3, ask=ask)

    # Narration and analysis preserved
    assert rebound.source_sha256 == fingerprint(raw_narration)
    assert rebound.analysis.proposition == brief_v1.analysis.proposition

    # Identity-changing migration (changing voice) fails closed
    changed_voice_channel = channel_v3.model_copy(update={"voice": "DifferentVoice"})
    assert is_visual_policy_update(root, changed_voice_channel) is False
    with pytest.raises(ValueError, match="Profile change is not limited to versioned visual policy"):
        rebind_visual_policy(root, changed_voice_channel, ask=ask)


def test_issue_50_integrated_resumable_channel_study_pilot(multimodal_study: tuple[StudyCollector, Path], tmp_path: Path):
    collector, study_dir = multimodal_study
    study = collector.load_study()
    assert study.status == StudyStatus.CORE_READY

    # 1. Derive Production Profile with multimodal guidance
    owner_settings = {
        "voice": "Achird",
        "target_language": "ar",
        "target_dialect": "khaleeji",
        "constraints": ["no_clickbait"],
    }
    profile = derive_production_profile(study, owner_settings)
    assert profile.revision.startswith("rev_")
    assert profile.voice == "Achird"
    assert profile.visual_guidance["composition"] != ""
    assert profile.audio_guidance["treatment"] != ""
    assert profile.packaging_guidance["packaging_rules"] != ""

    # 2. Publish and Atomically Activate Profile
    channel_dir = tmp_path / "pilot_channel_dna"
    mgr = ProfileActivationManager(channel_dir)
    res = mgr.publish_and_activate(profile)
    assert res["status"] == "ACTIVATED"
    assert mgr.get_active_revision() == profile.revision

    # 3. Bind New-Episode Brief
    active_channel = mgr.resolve_channel()
    assert active_channel.revision == profile.revision

    raw_text = "New episode narration on ancient defensive formations"
    new_brief = Brief(
        version=2,
        source_sha256=fingerprint(raw_text),
        profile_sha256=fingerprint(active_channel),
        profile_revision=active_channel.revision,
        channel=active_channel,
        analysis=sample_analysis(),
    )
    assert verify_profile_pin(new_brief, active_channel) is True

    # 4. End-to-End Interruption and Recovery Proof
    # Simulate an interrupted second profile publication
    journal_file = channel_dir / ".activation_journal.json"
    journal_file.write_text(
        json.dumps({
            "channel_id": active_channel.channel_id,
            "target_revision": "rev_interrupted",
            "profile_digest": "dummy_digest",
            "status": "PENDING_SWITCH",
        }),
        encoding="utf-8",
    )
    rec = mgr.recover_interrupted_activation()
    # Missing revision payload causes clean discard; prior active revision remains active
    assert rec["status"] == "RECOVERED_DISCARDED"
    assert mgr.get_active_revision() == profile.revision
    assert verify_profile_pin(new_brief, mgr.resolve_channel()) is True
