"""Wayfinder Reference Channel Study contract and collector (Issue #43)."""

from __future__ import annotations

import enum
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StudyStatus(str, enum.Enum):
    PARTIAL = "PARTIAL"
    CORE_READY = "CORE_READY"


REQUIRED_CORE_AREAS = [
    "subject_promise",
    "viewer_need",
    "tone_register",
    "narrative_structure",
]

ALLOWED_AREAS = REQUIRED_CORE_AREAS + [
    "visual_motion",
    "soundtrack",
    "packaging",
]


class SamplingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_pool_limit: int = Field(default=30, ge=1, le=100)
    target_sample_size: int = Field(default=6, ge=1, le=20)
    min_distinct_videos_for_core: int = Field(default=3, ge=1)
    max_video_duration_sec: float = Field(default=3600.0, gt=0.0)  # 60 min
    max_total_duration_sec: float = Field(default=10800.0, gt=0.0)  # 180 min
    max_evidence_bytes: int = Field(default=2 * 1024 * 1024 * 1024)  # 2 GiB
    max_external_attempts: int = Field(default=10, ge=1)
    max_attempts_per_source: int = Field(default=2, ge=1)
    max_external_seconds: float = Field(default=1200.0, gt=0.0)  # 20 min


class CandidateVideo(BaseModel):
    model_config = ConfigDict(frozen=True)

    video_id: str
    title: str
    published_at: str  # ISO-8601 string
    duration_sec: float
    view_count: int | None = None
    selection_group: str | None = None  # "recent", "highest_viewed", "middle_ranked"
    excluded_reason: str | None = None


class AttributableEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    video_id: str
    modality: str  # "transcript", "audio", "frame", "clip", "metadata"
    examined_range: tuple[float, float] | None = None
    sha256: str
    byte_count: int
    is_owner_supplied: bool = False
    notes: str = ""


class InferredTrait(BaseModel):
    model_config = ConfigDict(frozen=True)

    area: str
    claim: str
    supporting_video_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str
    uncertainty: str = "low"
    counterexamples: list[str] = Field(default_factory=list)
    resolved_contradictions: bool = True


class CumulativeSpend(BaseModel):
    total_duration_sec: float = 0.0
    total_bytes: int = 0
    external_attempts: int = 0
    external_seconds: float = 0.0

    def add_source(self, duration_sec: float, byte_count: int) -> None:
        self.total_duration_sec += duration_sec
        self.total_bytes += byte_count

    def add_attempt(self, seconds: float = 0.0) -> None:
        self.external_attempts += 1
        self.external_seconds += seconds


class ReferenceStudy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_id: str
    channel_id: str
    declared_scope: dict[str, Any] = Field(
        default_factory=lambda: {"format": "long-form", "language": "ar", "period_months": 12}
    )
    policy: SamplingPolicy = Field(default_factory=SamplingPolicy)
    status: StudyStatus = StudyStatus.PARTIAL
    candidates: list[CandidateVideo] = Field(default_factory=list)
    selected_sample: list[CandidateVideo] = Field(default_factory=list)
    evidence: list[AttributableEvidence] = Field(default_factory=list)
    core_traits: dict[str, InferredTrait] = Field(default_factory=dict)
    optional_traits: dict[str, str] = Field(
        default_factory=lambda: {
            "visual_style": "unknown",
            "motion": "unknown",
            "sound_design": "unknown",
            "packaging": "unknown",
        }
    )
    actionable_gaps: list[str] = Field(default_factory=list)
    spend: CumulativeSpend = Field(default_factory=CumulativeSpend)


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def select_sample(
    candidates: list[CandidateVideo], policy: SamplingPolicy
) -> tuple[list[CandidateVideo], list[str]]:
    """Select up to 6 distinct videos according to the 3-2-1 group policy, preserving shortfalls."""
    eligible = [c for c in candidates if not c.excluded_reason]
    # Pool cap of 30 candidates
    pool = eligible[: policy.candidate_pool_limit]

    selected: list[CandidateVideo] = []
    selected_ids: set[str] = set()
    gaps: list[str] = []

    # Sort helpers
    by_recency = sorted(pool, key=lambda x: (x.published_at, x.video_id), reverse=True)

    # 1. Group: 3 most recent
    recent_group: list[CandidateVideo] = []
    for c in by_recency:
        if c.video_id not in selected_ids and len(recent_group) < 3:
            v = c.model_copy(update={"selection_group": "recent"})
            recent_group.append(v)
            selected.append(v)
            selected_ids.add(c.video_id)
    if len(recent_group) < 3:
        gaps.append(f"Shortfall in recent group: selected {len(recent_group)} of 3")

    # 2. Group: 2 highest-viewed remaining
    remaining = [c for c in pool if c.video_id not in selected_ids]
    with_views = [c for c in remaining if c.view_count is not None]
    by_views = sorted(with_views, key=lambda x: (x.view_count or 0, x.published_at, x.video_id), reverse=True)

    high_view_group: list[CandidateVideo] = []
    for c in by_views:
        if c.video_id not in selected_ids and len(high_view_group) < 2:
            v = c.model_copy(update={"selection_group": "highest_viewed"})
            high_view_group.append(v)
            selected.append(v)
            selected_ids.add(c.video_id)
    if len(high_view_group) < 2:
        gaps.append(f"Shortfall in highest_viewed group: selected {len(high_view_group)} of 2")

    # 3. Group: 1 middle-ranked remaining
    remaining_middle = [c for c in pool if c.video_id not in selected_ids and c.view_count is not None]
    middle_sorted = sorted(remaining_middle, key=lambda x: (x.view_count or 0, x.published_at, x.video_id), reverse=True)

    if middle_sorted:
        mid_idx = len(middle_sorted) // 2
        mid_cand = middle_sorted[mid_idx].model_copy(update={"selection_group": "middle_ranked"})
        selected.append(mid_cand)
        selected_ids.add(mid_cand.video_id)
    else:
        gaps.append("Shortfall in middle_ranked group: 0 of 1 available")

    if len(selected_ids) < policy.min_distinct_videos_for_core:
        gaps.append(
            f"Insufficient sample: {len(selected_ids)} distinct videos; minimum {policy.min_distinct_videos_for_core} required for core inference"
        )

    return selected, gaps


def evaluate_study_readiness(study: ReferenceStudy) -> tuple[StudyStatus, list[str]]:
    """Evaluate core readiness vs partial state per settled Issue #35 criteria."""
    gaps: list[str] = []

    # 1. Distinct video sample check
    distinct_videos = {v.video_id for v in study.selected_sample}
    if len(distinct_videos) < study.policy.min_distinct_videos_for_core:
        gaps.append(
            f"Sample has {len(distinct_videos)} distinct videos; minimum {study.policy.min_distinct_videos_for_core} required"
        )

    # 2. Cumulative cap checks
    if study.spend.total_duration_sec > study.policy.max_total_duration_sec:
        gaps.append(
            f"Exceeded total duration limit: {study.spend.total_duration_sec}s > {study.policy.max_total_duration_sec}s"
        )
    if study.spend.total_bytes > study.policy.max_evidence_bytes:
        gaps.append(
            f"Exceeded evidence size limit: {study.spend.total_bytes} bytes > {study.policy.max_evidence_bytes} bytes"
        )
    if study.spend.external_attempts > study.policy.max_external_attempts:
        gaps.append(
            f"Exceeded external attempt cap: {study.spend.external_attempts} > {study.policy.max_external_attempts}"
        )

    # 3. Required core areas check
    for area in REQUIRED_CORE_AREAS:
        trait = study.core_traits.get(area)
        if trait is None:
            gaps.append(f"Missing required core area: '{area}'")
            continue

        distinct_supporting = set(trait.supporting_video_ids)
        if len(distinct_supporting) < 2:
            gaps.append(
                f"Core area '{area}' supported by {len(distinct_supporting)} video(s); minimum 2 required"
            )

        if not trait.resolved_contradictions:
            gaps.append(f"Core area '{area}' has unresolved contradictions or counterexamples")

    status = StudyStatus.CORE_READY if not gaps else StudyStatus.PARTIAL
    return status, gaps


class StudyCollector:
    """Manages collection, persistence, and interruption recovery of reference studies."""

    def __init__(self, study_dir: Path) -> None:
        self.study_dir = study_dir.resolve()
        self.study_file = self.study_dir / "study.json"
        self.evidence_dir = self.study_dir / "evidence"

    def initialize_study(
        self,
        study_id: str,
        channel_id: str,
        candidates: list[CandidateVideo],
        policy: SamplingPolicy | None = None,
    ) -> ReferenceStudy:
        """Create a new reference study and select the initial candidate sample."""
        self.study_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        eff_policy = policy or SamplingPolicy()
        selected, initial_gaps = select_sample(candidates, eff_policy)

        study = ReferenceStudy(
            study_id=study_id,
            channel_id=channel_id,
            policy=eff_policy,
            candidates=candidates,
            selected_sample=selected,
            actionable_gaps=initial_gaps,
        )
        return self.save_study(study)

    def save_study(self, study: ReferenceStudy) -> ReferenceStudy:
        """Persist study state atomically."""
        status, gaps = evaluate_study_readiness(study)
        sample_gaps = [g for g in study.actionable_gaps if "group" in g or "Insufficient sample" in g]
        all_gaps = sorted(set(sample_gaps + gaps))
        updated = study.model_copy(update={"status": status, "actionable_gaps": all_gaps})
        temp_file = self.study_file.with_suffix(".tmp")
        temp_file.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
        temp_file.replace(self.study_file)
        return updated

    def load_study(self) -> ReferenceStudy:
        """Load persisted study state."""
        if not self.study_file.is_file():
            raise FileNotFoundError(f"Study file missing: {self.study_file}")
        data = json.loads(self.study_file.read_text(encoding="utf-8"))
        return ReferenceStudy.model_validate(data)

    def add_evidence(
        self,
        study: ReferenceStudy,
        video_id: str,
        modality: str,
        data: bytes,
        examined_range: tuple[float, float] | None = None,
        duration_sec: float = 0.0,
        is_owner_supplied: bool = False,
        notes: str = "",
    ) -> ReferenceStudy:
        """Add attributable evidence, updating cumulative spend and persisting the raw item."""
        # 1. Enforce per-video duration limit
        if duration_sec > study.policy.max_video_duration_sec:
            raise ValueError(
                f"Video {video_id} duration {duration_sec}s exceeds limit {study.policy.max_video_duration_sec}s"
            )

        sha = compute_sha256(data)
        evidence_id = f"ev_{video_id}_{modality}_{sha[:8]}"

        # Write evidence bytes
        ev_file = self.evidence_dir / f"{evidence_id}.bin"
        ev_file.write_bytes(data)

        # Update spend
        spend = study.spend.model_copy()
        spend.add_source(duration_sec, len(data))

        new_evidence = AttributableEvidence(
            evidence_id=evidence_id,
            video_id=video_id,
            modality=modality,
            examined_range=examined_range,
            sha256=sha,
            byte_count=len(data),
            is_owner_supplied=is_owner_supplied,
            notes=notes,
        )

        existing_evidence = [e for e in study.evidence if e.evidence_id != evidence_id]
        existing_evidence.append(new_evidence)

        updated_study = study.model_copy(
            update={"evidence": existing_evidence, "spend": spend}
        )
        self.save_study(updated_study)
        return updated_study

    def record_core_trait(
        self,
        study: ReferenceStudy,
        area: str,
        claim: str,
        supporting_video_ids: list[str],
        evidence_ids: list[str],
        rationale: str,
        counterexamples: list[str] | None = None,
        resolved_contradictions: bool = True,
    ) -> ReferenceStudy:
        """Record an inferred core trait with attributable evidence and rationale."""
        if area not in ALLOWED_AREAS:
            raise ValueError(f"Area '{area}' is not a permitted study area ({ALLOWED_AREAS})")

        trait = InferredTrait(
            area=area,
            claim=claim,
            supporting_video_ids=sorted(set(supporting_video_ids)),
            evidence_ids=sorted(set(evidence_ids)),
            rationale=rationale,
            counterexamples=counterexamples or [],
            resolved_contradictions=resolved_contradictions,
        )

        traits = dict(study.core_traits)
        traits[area] = trait

        updated_study = study.model_copy(update={"core_traits": traits})
        self.save_study(updated_study)
        return updated_study

    def verify_evidence_integrity(self, study: ReferenceStudy) -> tuple[bool, list[str]]:
        """Verify that all recorded evidence files exist on disk and match their stored SHA-256."""
        mismatches: list[str] = []
        for ev in study.evidence:
            ev_file = self.evidence_dir / f"{ev.evidence_id}.bin"
            if not ev_file.is_file():
                mismatches.append(f"Missing evidence file for {ev.evidence_id}")
                continue
            actual_sha = compute_sha256(ev_file.read_bytes())
            if actual_sha != ev.sha256:
                mismatches.append(
                    f"Digest mismatch for {ev.evidence_id}: expected {ev.sha256}, got {actual_sha}"
                )
        return len(mismatches) == 0, mismatches
