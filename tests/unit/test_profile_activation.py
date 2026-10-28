"""Tests for Issue #44: Derivation and safe activation of production channel profiles."""

from pathlib import Path

import pytest

from youtube_automation.production.contracts import (
    Analysis,
    Brief,
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


@pytest.fixture
def core_ready_study(tmp_path: Path) -> Path:
    study_dir = tmp_path / "study_core_ready"
    collector = StudyCollector(study_dir)
    candidates = [
        CandidateVideo(video_id="v01", title="Ep 1", published_at="2026-10-01T10:00:00Z", duration_sec=500, view_count=1000),
        CandidateVideo(video_id="v02", title="Ep 2", published_at="2026-10-05T10:00:00Z", duration_sec=600, view_count=2000),
        CandidateVideo(video_id="v03", title="Ep 3", published_at="2026-10-10T10:00:00Z", duration_sec=700, view_count=3000),
    ]
    study = collector.initialize_study("study_ready", "test_channel", candidates)
    study = collector.add_evidence(study, "v01", "transcript", b"evidence v01", evidence_id="ev_01")
    study = collector.add_evidence(study, "v02", "transcript", b"evidence v02", evidence_id="ev_02")

    # Record 4 core areas with 2 supporting videos each
    study = collector.record_core_trait(study, "subject_promise", "Military tactics history", ["v01", "v02"], ["ev_01", "ev_02"], "Consistent")
    study = collector.record_core_trait(study, "viewer_need", "Military strategy analysis", ["v01", "v02"], ["ev_01", "ev_02"], "Consistent")
    study = collector.record_core_trait(study, "tone_register", "Serious documentary Khaleeji", ["v01", "v02"], ["ev_01", "ev_02"], "Consistent")
    study = collector.record_core_trait(study, "narrative_structure", "Hook, conflict, resolution", ["v01", "v02"], ["ev_01", "ev_02"], "Consistent")

    return study_dir


def test_derive_production_profile_from_core_ready_study(core_ready_study: Path):
    collector = StudyCollector(core_ready_study)
    study = collector.load_study()
    assert study.status == StudyStatus.CORE_READY

    profile = derive_production_profile(study)
    assert profile.channel_id == "test_channel"
    assert profile.audience_intent == "Military strategy analysis"
    assert profile.tone_and_style == "Serious documentary Khaleeji"
    assert profile.target_language == "ar"
    assert profile.target_dialect == "khaleeji"
    assert profile.provenance["audience_intent"] == "evidence_derived"
    assert profile.provenance["target_language"] == "inherited_default"
    assert profile.revision.startswith("rev_")


def test_derive_profile_refuses_partial_study(tmp_path: Path):
    study_dir = tmp_path / "study_partial"
    collector = StudyCollector(study_dir)
    candidates = [
        CandidateVideo(video_id="v01", title="Ep 1", published_at="2026-10-01T10:00:00Z", duration_sec=500, view_count=1000),
    ]
    study = collector.initialize_study("study_part", "test_channel", candidates)
    assert study.status == StudyStatus.PARTIAL

    with pytest.raises(ValueError, match="missing mandatory core evidence"):
        derive_production_profile(study)


def test_owner_overrides_take_precedence_without_rewriting_study(core_ready_study: Path):
    collector = StudyCollector(core_ready_study)
    study = collector.load_study()

    owner_settings = {
        "target_language": "ar-SA",
        "voice": "Achird",
        "constraints": ["no_informal_slang", "max_60_sec_intro"],
        "audience_intent": "Advanced defense analysts",
    }

    profile = derive_production_profile(study, owner_settings)

    # Overrides applied in derived profile
    assert profile.target_language == "ar-SA"
    assert profile.voice == "Achird"
    assert profile.audience_intent == "Advanced defense analysts"
    assert "no_informal_slang" in profile.constraints
    assert profile.provenance["target_language"] == "owner_override"
    assert profile.provenance["voice"] == "owner_override"
    assert profile.provenance["audience_intent"] == "owner_override"

    # Study core traits remain untouched
    reloaded_study = collector.load_study()
    assert reloaded_study.core_traits["viewer_need"].claim == "Military strategy analysis"


def test_explicit_null_voice_preserved_and_activatable(core_ready_study: Path):
    collector = StudyCollector(core_ready_study)
    study = collector.load_study()

    profile = derive_production_profile(study, {"voice": None})
    assert profile.voice is None

    mgr = ProfileActivationManager(core_ready_study.parent / "channel_out")
    mgr.publish_and_activate(profile)

    channel = mgr.resolve_channel()
    assert channel.voice is None
    assert channel.revision == profile.revision


def test_atomic_publish_and_activation_and_idempotent_recovery(core_ready_study: Path, tmp_path: Path):
    collector = StudyCollector(core_ready_study)
    study = collector.load_study()
    profile = derive_production_profile(study, {"voice": "Charon"})

    channel_dir = tmp_path / "channel_dna"
    mgr = ProfileActivationManager(channel_dir)

    res = mgr.publish_and_activate(profile)
    assert res["status"] == "ACTIVATED"
    assert mgr.get_active_revision() == profile.revision

    # Verify channel contract construction
    channel = mgr.resolve_channel()
    assert channel.channel_id == "test_channel"
    assert channel.revision == profile.revision
    assert channel.voice == "Charon"

    # Simulate an interrupted second activation
    journal_file = channel_dir / ".activation_journal.json"
    journal_file.write_text('{"channel_id": "test_channel", "target_revision": "rev_unwritten", "profile_digest": "none"}', encoding="utf-8")

    rec = mgr.recover_interrupted_activation()
    assert rec["status"] == "RECOVERED_DISCARDED"
    # Prior active revision preserved
    assert mgr.get_active_revision() == profile.revision


def test_brief_binding_pins_active_revision_and_preserves_existing_episodes(core_ready_study: Path, tmp_path: Path):
    collector = StudyCollector(core_ready_study)
    study = collector.load_study()
    profile1 = derive_production_profile(study, {"voice": "Achird"})

    channel_dir = tmp_path / "channel_dna_briefs"
    mgr = ProfileActivationManager(channel_dir)
    mgr.publish_and_activate(profile1)

    channel_v1 = mgr.resolve_channel()
    assert channel_v1.revision == profile1.revision

    # Create new episode brief bound to revision 1
    raw_source = "Historical episode source narration"
    analysis = Analysis(
        treatments=["subject_scene"],
        topics=["military tactics", "history"],
        claim_basis="factual",
        form="explanation",
        proposition="Tactics evolve through conflict",
        narrative_strategy="Chronological documentary structure",
        rationale="Clear explanatory progression",
    )
    brief_v1 = Brief(
        source_sha256=fingerprint(raw_source),
        profile_sha256=fingerprint(channel_v1),
        profile_revision=channel_v1.revision,
        channel=channel_v1,
        analysis=analysis,
    )
    assert brief_v1.profile_revision == profile1.revision
    assert verify_profile_pin(brief_v1, channel_v1) is True

    # Advance channel to revision 2
    profile2 = derive_production_profile(study, {"voice": "Achird", "target_dialect": "modern_standard"})
    mgr.publish_and_activate(profile2)
    channel_v2 = mgr.resolve_channel()
    assert channel_v2.revision == profile2.revision

    # Prior episode brief retains its original pin
    assert brief_v1.profile_revision == profile1.revision
    assert brief_v1.profile_revision != channel_v2.revision
