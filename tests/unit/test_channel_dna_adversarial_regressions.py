"""Adversarial regression tests for Channel DNA findings from completion audit.

Ensures:
1. Rejection of nonexistent support, mismatched evidence, and uncorroborated claims.
2. Inability to derive profiles from non-CORE_READY studies.
3. Immutability of published profile revisions (refusal to overwrite with differing payload).
4. Safe preservation of prior active revision when recovering from corrupted switch targets.
5. Carrying derived visual/audio/packaging guidance into resolved Channel instances.
"""

import json
from pathlib import Path

import pytest

from youtube_automation.production.profile_activation import (
    ProfileActivationManager,
    derive_production_profile,
)
from youtube_automation.production.study import (
    CandidateVideo,
    StudyCollector,
    StudyStatus,
)


def _make_candidates():
    return [
        CandidateVideo(video_id="v1", title="T1", published_at="2026-10-01T00:00:00Z", duration_sec=100, view_count=100),
        CandidateVideo(video_id="v2", title="T2", published_at="2026-10-02T00:00:00Z", duration_sec=100, view_count=100),
        CandidateVideo(video_id="v3", title="T3", published_at="2026-10-03T00:00:00Z", duration_sec=100, view_count=100),
    ]


def test_adversarial_zero_evidence_and_foreign_ids_rejected(tmp_path: Path):
    sdir = tmp_path / "study_adv"
    col = StudyCollector(sdir)
    st = col.initialize_study("st1", "ch1", _make_candidates())

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(
            st,
            area,
            claim=f"claim {area}",
            supporting_video_ids=["nonexistent-a", "nonexistent-b"],
            evidence_ids=["missing-evidence"],
            rationale="",
        )

    assert st.status == StudyStatus.PARTIAL
    with pytest.raises(ValueError, match="Cannot derive production profile from non-CORE_READY study"):
        derive_production_profile(st)


def test_adversarial_profile_revision_immutable(tmp_path: Path):
    sdir = tmp_path / "study_valid"
    col = StudyCollector(sdir)
    st = col.initialize_study("st2", "ch2", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"v1 text", evidence_id="ev_v1")
    st = col.add_evidence(st, "v2", "transcript", b"v2 text", evidence_id="ev_v2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(
            st,
            area,
            claim=f"claim {area}",
            supporting_video_ids=["v1", "v2"],
            evidence_ids=["ev_v1", "ev_v2"],
            rationale=f"valid rationale for {area}",
        )

    assert st.status == StudyStatus.CORE_READY
    prof = derive_production_profile(st)

    mgr = ProfileActivationManager(tmp_path / "channel_dir")
    res = mgr.publish_and_activate(prof)
    assert res["status"] == "ACTIVATED"

    # Attempt overwrite of same revision with differing payload
    prof_tampered = prof.model_copy(update={"audience_intent": "completely different intent"})
    with pytest.raises(ValueError, match="is immutable and already published with differing content"):
        mgr.publish_and_activate(prof_tampered)


def test_adversarial_corrupted_recovery_preserves_active_pointer(tmp_path: Path):
    channel_dir = tmp_path / "channel_dir_rec"
    mgr = ProfileActivationManager(channel_dir)

    # Setup valid active profile
    sdir = tmp_path / "study_valid_2"
    col = StudyCollector(sdir)
    st = col.initialize_study("st3", "ch3", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"v1 text", evidence_id="ev_v1")
    st = col.add_evidence(st, "v2", "transcript", b"v2 text", evidence_id="ev_v2")
    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(
            st,
            area,
            claim=f"claim {area}",
            supporting_video_ids=["v1", "v2"],
            evidence_ids=["ev_v1", "ev_v2"],
            rationale=f"valid rationale for {area}",
        )

    prof = derive_production_profile(st)
    mgr.publish_and_activate(prof)
    active_rev = mgr.get_active_revision()

    # Corrupt switch target (empty JSON dictionary)
    target_rev = "rev_corrupted_target"
    (channel_dir / "profiles").mkdir(parents=True, exist_ok=True)
    (channel_dir / "profiles" / f"{target_rev}.json").write_text("{}", encoding="utf-8")
    (channel_dir / ".activation_journal.json").write_text(
        json.dumps({
            "channel_id": "ch3",
            "target_revision": target_rev,
            "profile_digest": "corrupt_digest",
            "status": "PENDING_SWITCH",
        }),
        encoding="utf-8",
    )

    rec = mgr.recover_interrupted_activation()
    assert rec["status"] == "RECOVERED_DISCARDED"
    assert mgr.get_active_revision() == active_rev


def test_guidance_carried_to_resolved_channel(tmp_path: Path):
    sdir = tmp_path / "study_guidance"
    col = StudyCollector(sdir)
    st = col.initialize_study("st4", "ch4", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"v1", evidence_id="ev1")
    st = col.add_evidence(st, "v2", "transcript", b"v2", evidence_id="ev2")
    st = col.add_evidence(st, "v1", "frame", b"f1", evidence_id="ev_f1")
    st = col.add_evidence(st, "v2", "frame", b"f2", evidence_id="ev_f2")
    st = col.add_evidence(st, "v1", "audio", b"a1", evidence_id="ev_a1")
    st = col.add_evidence(st, "v2", "audio", b"a2", evidence_id="ev_a2")
    st = col.add_evidence(st, "v1", "title", b"t1", evidence_id="ev_t1")
    st = col.add_evidence(st, "v2", "title", b"t2", evidence_id="ev_t2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(st, area, f"c_{area}", ["v1", "v2"], ["ev1", "ev2"], f"r_{area}")

    st = col.record_core_trait(st, "visual_motion", "Framing", ["v1", "v2"], ["ev_f1", "ev_f2"], "Pans")
    st = col.record_core_trait(st, "soundtrack", "Oud bed", ["v1", "v2"], ["ev_a1", "ev_a2"], "Quiet")
    st = col.record_core_trait(st, "packaging", "Question hook", ["v1", "v2"], ["ev_t1", "ev_t2"], "Bold font")

    prof = derive_production_profile(st)
    mgr = ProfileActivationManager(tmp_path / "ch4_dir")
    mgr.publish_and_activate(prof)

    ch = mgr.resolve_channel()
    assert ch.visual_guidance["composition"] == "Framing"
    assert ch.audio_guidance["treatment"] == "Oud bed"
    assert ch.packaging_guidance["packaging_rules"] == "Question hook"
