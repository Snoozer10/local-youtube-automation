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


def test_adversarial_tampered_physical_evidence_blocks_derivation_and_activation(tmp_path: Path):
    """P1: Tampered physical evidence on disk must block derivation and activation."""
    sdir = tmp_path / "study_tamper"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_t", "ch_t", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"authentic bytes 1", evidence_id="ev_t1")
    st = col.add_evidence(st, "v2", "transcript", b"authentic bytes 2", evidence_id="ev_t2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(st, area, f"claim {area}", ["v1", "v2"], ["ev_t1", "ev_t2"], f"rationale {area}")

    # Derive profile while evidence is intact
    prof = derive_production_profile(st)

    # Tamper physical file on disk
    (col.evidence_dir / "ev_t1.bin").write_bytes(b"tampered bytes!")
    valid, mismatches = col.verify_evidence_integrity(st)
    assert not valid
    assert len(mismatches) > 0

    with pytest.raises(ValueError, match="Cannot derive production profile from non-CORE_READY study"):
        derive_production_profile(col.load_study())

    # Also test publish_and_activate directly refuses tampered profile
    mgr = ProfileActivationManager(tmp_path / "ch_t_dir")
    with pytest.raises(ValueError, match="Cannot activate profile.*tampered"):
        mgr.publish_and_activate(prof)


def test_adversarial_metadata_alone_cannot_establish_narrative_core(tmp_path: Path):
    """P1: Page metadata alone must not satisfy narrative core requirements."""
    sdir = tmp_path / "study_meta"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_m", "ch_m", _make_candidates())
    st = col.add_evidence(st, "v1", "metadata", b"meta 1", evidence_id="ev_m1")
    st = col.add_evidence(st, "v2", "metadata", b"meta 2", evidence_id="ev_m2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(st, area, f"claim {area}", ["v1", "v2"], ["ev_m1", "ev_m2"], f"rationale {area}")

    assert st.status == StudyStatus.PARTIAL
    assert any("metadata alone cannot establish narrative core" in g for g in st.actionable_gaps)
    with pytest.raises(ValueError, match="Cannot derive production profile from non-CORE_READY study"):
        derive_production_profile(st)


def test_adversarial_unresolved_contradictions_and_wrong_modality_reject_optional_guidance(tmp_path: Path):
    """P1: Optional traits with wrong modality or unresolved contradictions are not promoted to guidance."""
    sdir = tmp_path / "study_opt"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_o", "ch_o", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"t1", evidence_id="ev_t1")
    st = col.add_evidence(st, "v2", "transcript", b"t2", evidence_id="ev_t2")
    st = col.add_evidence(st, "v1", "metadata", b"meta_audio", evidence_id="ev_m_audio")
    st = col.add_evidence(st, "v2", "metadata", b"meta_audio_2", evidence_id="ev_m_audio_2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(st, area, f"claim {area}", ["v1", "v2"], ["ev_t1", "ev_t2"], f"rationale {area}")

    # Soundtrack backed by metadata and unresolved contradictions
    st = col.record_core_trait(
        st,
        "soundtrack",
        claim="Lo-fi beats",
        supporting_video_ids=["v1", "v2"],
        evidence_ids=["ev_m_audio", "ev_m_audio_2"],
        rationale="From video description",
        counterexamples=["Video 2 has rock music"],
        resolved_contradictions=False,
    )

    prof = derive_production_profile(st)
    assert prof.audio_guidance == {}


def test_adversarial_active_pointer_digest_mismatch_blocks_load(tmp_path: Path):
    """P1: load_active_profile must verify disk content against active pointer digest and reject tampering."""
    sdir = tmp_path / "study_ptr"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_p", "ch_p", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"t1", evidence_id="ev1")
    st = col.add_evidence(st, "v2", "transcript", b"t2", evidence_id="ev2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(st, area, f"claim {area}", ["v1", "v2"], ["ev1", "ev2"], f"rationale {area}")

    prof = derive_production_profile(st)
    mgr = ProfileActivationManager(tmp_path / "ch_ptr_dir")
    mgr.publish_and_activate(prof)

    # Directly tamper profile.json on disk
    prof_file = mgr.revisions_dir / prof.revision / "profile.json"
    data = json.loads(prof_file.read_text(encoding="utf-8"))
    data["tone_and_style"] = "tampered style"
    prof_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="Active profile digest mismatch"):
        mgr.load_active_profile()


def test_missing_evidence_directory_fails_closed_with_actionable_gaps(tmp_path: Path):
    """F5: Absent evidence directory fails closed with actionable gaps and blocks activation."""
    sdir = tmp_path / "study_missing_ev"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_m_ev", "ch_m_ev", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"v1 text", evidence_id="ev1")
    st = col.add_evidence(st, "v2", "transcript", b"v2 text", evidence_id="ev2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(st, area, f"claim {area}", ["v1", "v2"], ["ev1", "ev2"], f"rationale {area}")

    # Derive valid profile before storage is moved away
    prof = derive_production_profile(st)

    # Preserving evidence away simulates absent storage
    col.evidence_dir.rename(col.study_dir / "evidence-preserved-away")
    from youtube_automation.production.study import evaluate_study_readiness
    status, gaps = evaluate_study_readiness(st)

    assert status == StudyStatus.PARTIAL
    assert any("Physical evidence directory missing on disk" in g for g in gaps)

    # Derivation fails closed on missing storage
    with pytest.raises(ValueError, match="missing mandatory core evidence"):
        derive_production_profile(st)

    # Activation fails closed on missing storage
    mgr = ProfileActivationManager(tmp_path / "ch_missing_ev")
    with pytest.raises(ValueError, match="physical evidence directory missing"):
        mgr.publish_and_activate(prof)


def test_identical_evidence_input_does_not_double_count_spend(tmp_path: Path):
    """F7: Repeated identical evidence input must not double-count duration or bytes."""
    sdir = tmp_path / "study_dup"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_dup", "ch_dup", _make_candidates())

    st = col.add_evidence(st, "v1", "transcript", b"same content", duration_sec=20.0, evidence_id="ev_same")
    before_spend = st.spend.model_dump()

    st = col.add_evidence(st, "v1", "transcript", b"same content", duration_sec=20.0, evidence_id="ev_same")
    after_spend = st.spend.model_dump()

    assert len(st.evidence) == 1
    assert before_spend["total_duration_sec"] == 20.0
    assert after_spend["total_duration_sec"] == 20.0
    assert before_spend["total_bytes"] == len(b"same content")
    assert after_spend["total_bytes"] == len(b"same content")


def test_external_seconds_budget_exceeded_leaves_study_partial(tmp_path: Path):
    """F7: Exceeding max_external_seconds leaves study in PARTIAL state with actionable gap."""
    sdir = tmp_path / "study_budget"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_b", "ch_b", _make_candidates())
    st = col.add_evidence(st, "v1", "transcript", b"v1 text", evidence_id="ev1")
    st = col.add_evidence(st, "v2", "transcript", b"v2 text", evidence_id="ev2")

    for area in ["subject_promise", "viewer_need", "tone_register", "narrative_structure"]:
        st = col.record_core_trait(st, area, f"claim {area}", ["v1", "v2"], ["ev1", "ev2"], f"rationale {area}")

    from youtube_automation.production.study import evaluate_study_readiness
    base_status, base_gaps = evaluate_study_readiness(st)
    assert base_status == StudyStatus.CORE_READY

    over_spend = st.spend.model_copy(update={"external_seconds": st.policy.max_external_seconds + 1.0})
    st_over = st.model_copy(update={"spend": over_spend})
    over_status, over_gaps = evaluate_study_readiness(st_over)

    assert over_status == StudyStatus.PARTIAL
    assert any("Exceeded external time limit" in g for g in over_gaps)


def test_representative_appropriate_media_bundle_into_guidance(tmp_path: Path):
    """F8 / #46-#48: Bounded valid representative offline media bundle derives observable guidance."""
    import io, wave

    # Real 1x1 valid PNG image bytes
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00"
        b"\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xfe\xae"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    # Real RIFF WAV audio bytes generated via stdlib wave module
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 4410)  # 100ms of valid audio
    wav_bytes = wav_io.getvalue()

    # Valid MP4 container header
    mp4_bytes = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free\x00\x00\x00\x08mdat"

    sdir = tmp_path / "study_representative"
    col = StudyCollector(sdir)
    st = col.initialize_study("st_rep", "ch_rep", _make_candidates())

    # Transcripts
    st = col.add_evidence(st, "v1", "transcript", b"Documentary narrative transcript 1", evidence_id="ev_t1")
    st = col.add_evidence(st, "v2", "transcript", b"Documentary narrative transcript 2", evidence_id="ev_t2")

    # Visual frame and motion clip (#46)
    st = col.add_evidence(st, "v1", "frame", png_bytes, examined_range=(0.0, 5.0), evidence_id="ev_frame")
    st = col.add_evidence(st, "v2", "clip", mp4_bytes, examined_range=(10.0, 20.0), duration_sec=10.0, evidence_id="ev_clip")

    # Audio (#47)
    st = col.add_evidence(st, "v1", "audio", wav_bytes, examined_range=(0.0, 10.0), duration_sec=10.0, evidence_id="ev_audio1")
    st = col.add_evidence(st, "v2", "audio", wav_bytes, examined_range=(0.0, 10.0), duration_sec=10.0, evidence_id="ev_audio2")

    # Packaging thumbnail and title (#48)
    st = col.add_evidence(st, "v1", "thumbnail", png_bytes, evidence_id="ev_thumb1")
    st = col.add_evidence(st, "v2", "thumbnail", png_bytes, evidence_id="ev_thumb2")
    st = col.add_evidence(st, "v1", "title", b"Why Formations Evolved", evidence_id="ev_title1")
    st = col.add_evidence(st, "v2", "title", b"Tactics and Formations Part 2", evidence_id="ev_title2")

    # Core traits
    st = col.record_core_trait(st, "subject_promise", "Tactical evolution in warfare", ["v1", "v2"], ["ev_t1", "ev_t2"], "Historical evidence")
    st = col.record_core_trait(st, "viewer_need", "Military history audience", ["v1", "v2"], ["ev_t1", "ev_t2"], "Viewer retention pattern")
    st = col.record_core_trait(st, "tone_register", "Serious documentary Khaleeji", ["v1", "v2"], ["ev_t1", "ev_t2"], "Audio/narrative delivery")
    st = col.record_core_trait(st, "narrative_structure", "Hook, problem, mechanical analysis, outcome", ["v1", "v2"], ["ev_t1", "ev_t2"], "Story arc")

    # Multimodal guidance traits
    st = col.record_core_trait(st, "visual_motion", "Rule-of-thirds historical portrait framing", ["v1", "v2"], ["ev_frame", "ev_clip"], "Slow linear pans")
    st = col.record_core_trait(st, "soundtrack", "Acoustic oud ambient underbed", ["v1", "v2"], ["ev_audio1", "ev_audio2"], "Muted under voice")
    st = col.record_core_trait(st, "packaging", "Question hook title, high contrast figure", ["v1", "v2"], ["ev_thumb1", "ev_thumb2", "ev_title1", "ev_title2"], "Bold white typography")

    assert st.status == StudyStatus.CORE_READY
    prof = derive_production_profile(st)

    assert prof.visual_guidance["composition"] == "Rule-of-thirds historical portrait framing"
    assert prof.audio_guidance["treatment"] == "Acoustic oud ambient underbed"
    assert prof.packaging_guidance["packaging_rules"] == "Question hook title, high contrast figure"
    assert prof.provenance["visual_guidance"] == "evidence_derived"
    assert prof.provenance["audio_guidance"] == "evidence_derived"

    mgr = ProfileActivationManager(tmp_path / "ch_rep_active")
    res = mgr.publish_and_activate(prof)
    assert res["status"] == "ACTIVATED"
    channel = mgr.resolve_channel()
    assert channel.visual_guidance == prof.visual_guidance
    assert channel.audio_guidance == prof.audio_guidance


