"""Tests for Issue #43: Wayfinder Reference Channel Study contract, sampling, and collector."""

from pathlib import Path

import pytest

from youtube_automation.production.study import (
    CandidateVideo,
    SamplingPolicy,
    StudyCollector,
    StudyStatus,
    select_sample,
)


@pytest.fixture
def candidate_pool() -> list[CandidateVideo]:
    return [
        CandidateVideo(video_id="v01", title="Ep 1", published_at="2026-10-01T10:00:00Z", duration_sec=600, view_count=1000),
        CandidateVideo(video_id="v02", title="Ep 2", published_at="2026-10-05T10:00:00Z", duration_sec=700, view_count=5000),
        CandidateVideo(video_id="v03", title="Ep 3", published_at="2026-10-10T10:00:00Z", duration_sec=800, view_count=2000),
        CandidateVideo(video_id="v04", title="Ep 4", published_at="2026-10-15T10:00:00Z", duration_sec=900, view_count=10000),
        CandidateVideo(video_id="v05", title="Ep 5", published_at="2026-10-20T10:00:00Z", duration_sec=500, view_count=8000),
        CandidateVideo(video_id="v06", title="Ep 6", published_at="2026-10-22T10:00:00Z", duration_sec=650, view_count=3000),
        CandidateVideo(video_id="v07", title="Ep 7", published_at="2026-10-25T10:00:00Z", duration_sec=750, view_count=15000),
    ]


def test_sampling_policy_selects_3_2_1_group_ordering(candidate_pool: list[CandidateVideo]):
    policy = SamplingPolicy()
    selected, gaps = select_sample(candidate_pool, policy)

    assert len(selected) == 6
    assert len(gaps) == 0

    # 1. Recent 3: v07, v06, v05
    recent_group = [s for s in selected if s.selection_group == "recent"]
    assert len(recent_group) == 3
    assert {s.video_id for s in recent_group} == {"v07", "v06", "v05"}

    # 2. Highest viewed remaining: out of {v04 (10k), v02 (5k), v06 (used), v07 (used), v05 (used), v03 (2k), v01 (1k)}
    # remaining with views: v04 (10k), v02 (5k), v03 (2k), v01 (1k) -> highest 2 are v04, v02
    high_group = [s for s in selected if s.selection_group == "highest_viewed"]
    assert len(high_group) == 2
    assert {s.video_id for s in high_group} == {"v04", "v02"}

    # 3. Middle ranked remaining: out of remaining {v03 (2k), v01 (1k)}
    mid_group = [s for s in selected if s.selection_group == "middle_ranked"]
    assert len(mid_group) == 1
    assert mid_group[0].video_id in {"v03", "v01"}


def test_shortfall_preserved_without_silent_cross_fill():
    # Only 2 videos available
    limited_pool = [
        CandidateVideo(video_id="v1", title="Ep 1", published_at="2026-10-01T10:00:00Z", duration_sec=600, view_count=1000),
        CandidateVideo(video_id="v2", title="Ep 2", published_at="2026-10-05T10:00:00Z", duration_sec=700, view_count=2000),
    ]
    policy = SamplingPolicy()
    selected, gaps = select_sample(limited_pool, policy)

    assert len(selected) == 2
    assert any("Shortfall in recent group: selected 2 of 3" in g for g in gaps)
    assert any("Shortfall in highest_viewed group: selected 0 of 2" in g for g in gaps)
    assert any("Shortfall in middle_ranked group" in g for g in gaps)
    assert any("Insufficient sample: 2 distinct videos" in g for g in gaps)


def test_collector_enforces_duration_limits_and_spend_accumulation(tmp_path: Path, candidate_pool: list[CandidateVideo]):
    collector = StudyCollector(tmp_path / "study_run")
    study = collector.initialize_study("study_test", "channel_123", candidate_pool)

    # Adding valid evidence
    ev_data = b"Transcript data for video 07 narration"
    study = collector.add_evidence(study, "v07", "transcript", ev_data, duration_sec=1200.0)

    assert study.spend.total_duration_sec == 1200.0
    assert study.spend.total_bytes == len(ev_data)
    assert len(study.evidence) == 1

    # Oversized video duration (> 3600s) raises ValueError
    with pytest.raises(ValueError, match="exceeds limit"):
        collector.add_evidence(study, "v07", "transcript", b"extra", duration_sec=4000.0)


def test_core_readiness_requires_four_areas_with_two_videos_each(tmp_path: Path, candidate_pool: list[CandidateVideo]):
    collector = StudyCollector(tmp_path / "study_run")
    study = collector.initialize_study("study_test", "channel_123", candidate_pool)

    # Initial study is PARTIAL (missing core traits)
    assert study.status == StudyStatus.PARTIAL
    assert any("Missing required core area" in g for g in study.actionable_gaps)

    # Add evidence for 3 videos
    study = collector.add_evidence(study, "v07", "transcript", b"v07 data", duration_sec=300, evidence_id="ev_v07")
    study = collector.add_evidence(study, "v06", "transcript", b"v06 data", duration_sec=300, evidence_id="ev_v06")
    study = collector.add_evidence(study, "v05", "transcript", b"v05 data", duration_sec=300, evidence_id="ev_v05")

    # Record 3 core areas
    study = collector.record_core_trait(
        study, "subject_promise", "Historical military narratives", ["v07", "v06"], ["ev_v07", "ev_v06"], "Consistent theme"
    )
    study = collector.record_core_trait(
        study, "viewer_need", "Military history enthusiasts", ["v07", "v06"], ["ev_v07", "ev_v06"], "Audience assumptions"
    )
    study = collector.record_core_trait(
        study, "tone_register", "Serious documentary Khaleeji register", ["v07", "v05"], ["ev_v07", "ev_v05"], "Consistent dialect"
    )

    # Still PARTIAL because narrative_structure is missing
    reloaded = collector.load_study()
    assert reloaded.status == StudyStatus.PARTIAL
    assert any("Missing required core area: 'narrative_structure'" in g for g in reloaded.actionable_gaps)

    # Add narrative_structure with only 1 supporting video
    study = collector.record_core_trait(
        study, "narrative_structure", "Three-beat hook structure", ["v07"], ["ev_v07"], "Only one video observed"
    )
    reloaded = collector.load_study()
    assert reloaded.status == StudyStatus.PARTIAL
    assert any("supported by 1 video(s); minimum 2 required" in g for g in reloaded.actionable_gaps)

    # Add second supporting video for narrative_structure
    study = collector.record_core_trait(
        study, "narrative_structure", "Three-beat hook structure", ["v07", "v05"], ["ev_v07", "ev_v05"], "Corroborated across two videos"
    )
    reloaded = collector.load_study()
    # Now all 4 areas are supported by >= 2 distinct videos -> CORE_READY!
    assert reloaded.status == StudyStatus.CORE_READY
    assert len(reloaded.actionable_gaps) == 0

    # Optional traits remain unknown without blocking readiness
    assert reloaded.optional_traits["visual_style"] == "unknown"


def test_evidence_integrity_and_recovery_verification(tmp_path: Path, candidate_pool: list[CandidateVideo]):
    study_dir = tmp_path / "study_recovery"
    collector = StudyCollector(study_dir)
    study = collector.initialize_study("study_rec", "channel_abc", candidate_pool)

    data1 = b"Sample video 1 transcript"
    data2 = b"Sample video 2 transcript"
    study = collector.add_evidence(study, "v07", "transcript", data1, duration_sec=400)
    study = collector.add_evidence(study, "v06", "transcript", data2, duration_sec=500)

    # Fresh collector loading from disk
    new_collector = StudyCollector(study_dir)
    reloaded = new_collector.load_study()

    ok, errors = new_collector.verify_evidence_integrity(reloaded)
    assert ok is True
    assert len(errors) == 0

    # Tamper with an evidence file to verify detection
    ev_file = study_dir / "evidence" / f"{reloaded.evidence[0].evidence_id}.bin"
    ev_file.write_bytes(b"tampered data bytes")

    ok_tampered, errors_tampered = new_collector.verify_evidence_integrity(reloaded)
    assert ok_tampered is False
    assert len(errors_tampered) == 1
    assert "Digest mismatch" in errors_tampered[0]
