"""Derivation and safe activation of production channel profiles (Issue #44)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .contracts import Channel
from .study import ReferenceStudy, StudyStatus


class DerivedProductionProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: str
    revision: str
    study_id: str
    study_digest: str
    target_language: str = "ar"
    target_dialect: str = "khaleeji"
    audience_intent: str
    tone_and_style: str
    voice: str | None = None  # None is a valid explicit null-voice (blocks TTS)
    allowed_visual_treatments: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    visual_guidance: dict[str, Any] = Field(default_factory=dict)
    audio_guidance: dict[str, Any] = Field(default_factory=dict)
    packaging_guidance: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, str] = Field(default_factory=dict)  # field -> source
    study_dir: str | None = None
    evidence_hashes: dict[str, str] = Field(default_factory=dict)
    created_at: str


def compute_profile_digest(profile_dict: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 digest of canonical profile JSON."""
    raw = json.dumps(profile_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def derive_production_profile(
    study: ReferenceStudy,
    owner_settings: dict[str, Any] | None = None,
) -> DerivedProductionProfile:
    """Derive an immutable production profile from a CORE_READY study and owner settings."""
    from .study import evaluate_study_readiness
    status, gaps = evaluate_study_readiness(study)
    if status != StudyStatus.CORE_READY or study.status != StudyStatus.CORE_READY:
        raise ValueError(
            f"Cannot derive production profile from non-CORE_READY study; missing mandatory core evidence: {gaps}"
        )

    settings = owner_settings or {}
    provenance: dict[str, str] = {}

    # 1. Language & Dialect
    lang = settings.get("target_language") or settings.get("language")
    if lang:
        target_language = str(lang)
        provenance["target_language"] = "owner_override"
    else:
        target_language = "ar"
        provenance["target_language"] = "inherited_default"

    dialect = settings.get("target_dialect") or settings.get("dialect")
    if dialect:
        target_dialect = str(dialect)
        provenance["target_dialect"] = "owner_override"
    else:
        target_dialect = "khaleeji"
        provenance["target_dialect"] = "inherited_default"

    # 2. Audience Intent & Tone (Evidence-derived unless owner overrides)
    if "audience_intent" in settings:
        audience_intent = str(settings["audience_intent"])
        provenance["audience_intent"] = "owner_override"
    else:
        audience_intent = study.core_traits["viewer_need"].claim
        provenance["audience_intent"] = "evidence_derived"

    if "tone_and_style" in settings:
        tone_and_style = str(settings["tone_and_style"])
        provenance["tone_and_style"] = "owner_override"
    else:
        tone_and_style = study.core_traits["tone_register"].claim
        provenance["tone_and_style"] = "evidence_derived"

    # 3. Voice (Preserve owner voice, including explicit None null-voice)
    if "voice" in settings:
        voice = settings["voice"]
        provenance["voice"] = "owner_override"
    else:
        voice = None
        provenance["voice"] = "inherited_default"

    # 4. Constraints & Visual treatments
    constraints = list(settings.get("constraints", []))
    provenance["constraints"] = "owner_override" if "constraints" in settings else "inherited_default"

    visual_treatments = list(settings.get("allowed_visual_treatments", []))
    provenance["allowed_visual_treatments"] = (
        "owner_override" if "allowed_visual_treatments" in settings else "inherited_default"
    )

    # 5. Multimodal Guidance Bundles (#46, #47, #48)
    # Require genuine corroboration (>= 2 distinct supporting videos with linked evidence) for reusable guidance
    evidence_by_id = {e.evidence_id: e for e in study.evidence}
    sample_vids = {v.video_id for v in study.selected_sample}

    visual_guidance = dict(settings.get("visual_guidance", {}))
    if not visual_guidance and "visual_motion" in study.core_traits:
        vt = study.core_traits["visual_motion"]
        ev_vids = {
            evidence_by_id[eid].video_id
            for eid in vt.evidence_ids
            if eid in evidence_by_id and evidence_by_id[eid].modality in ("video", "frame", "clip", "visual")
        }
        if (
            vt.resolved_contradictions
            and not vt.counterexamples
            and len(set(vt.supporting_video_ids).intersection(sample_vids)) >= 2
            and len(ev_vids) >= 2
            and vt.claim.strip()
        ):
            visual_guidance = {
                "composition": vt.claim,
                "motion_grammar": vt.rationale,
                "evidence_ids": vt.evidence_ids,
                "supporting_video_ids": vt.supporting_video_ids,
            }
    provenance["visual_guidance"] = (
        "owner_override" if "visual_guidance" in settings else ("evidence_derived" if visual_guidance else "inherited_default")
    )

    audio_guidance = dict(settings.get("audio_guidance", {}))
    if not audio_guidance and "soundtrack" in study.core_traits:
        st = study.core_traits["soundtrack"]
        ev_vids = {
            evidence_by_id[eid].video_id
            for eid in st.evidence_ids
            if eid in evidence_by_id and evidence_by_id[eid].modality in ("audio", "soundtrack")
        }
        if (
            st.resolved_contradictions
            and not st.counterexamples
            and len(set(st.supporting_video_ids).intersection(sample_vids)) >= 2
            and len(ev_vids) >= 2
            and st.claim.strip()
        ):
            audio_guidance = {
                "treatment": st.claim,
                "sound_policy": st.rationale,
                "evidence_ids": st.evidence_ids,
                "supporting_video_ids": st.supporting_video_ids,
            }
    provenance["audio_guidance"] = (
        "owner_override" if "audio_guidance" in settings else ("evidence_derived" if audio_guidance else "inherited_default")
    )

    packaging_guidance = dict(settings.get("packaging_guidance", {}))
    if not packaging_guidance and "packaging" in study.core_traits:
        pt = study.core_traits["packaging"]
        ev_vids = {
            evidence_by_id[eid].video_id
            for eid in pt.evidence_ids
            if eid in evidence_by_id and evidence_by_id[eid].modality in ("thumbnail", "packaging", "metadata", "title")
        }
        if (
            pt.resolved_contradictions
            and not pt.counterexamples
            and len(set(pt.supporting_video_ids).intersection(sample_vids)) >= 2
            and len(ev_vids) >= 2
            and pt.claim.strip()
        ):
            packaging_guidance = {
                "packaging_rules": pt.claim,
                "thumbnail_style": pt.rationale,
                "evidence_ids": pt.evidence_ids,
                "supporting_video_ids": pt.supporting_video_ids,
            }
    provenance["packaging_guidance"] = (
        "owner_override" if "packaging_guidance" in settings else ("evidence_derived" if packaging_guidance else "inherited_default")
    )

    study_raw = study.model_dump_json()
    study_sha = hashlib.sha256(study_raw.encode("utf-8")).hexdigest()

    # Pre-calculate deterministic revision ID
    base_dict = {
        "channel_id": study.channel_id,
        "study_id": study.study_id,
        "study_digest": study_sha,
        "target_language": target_language,
        "target_dialect": target_dialect,
        "audience_intent": audience_intent,
        "tone_and_style": tone_and_style,
        "voice": voice,
        "allowed_visual_treatments": visual_treatments,
        "constraints": constraints,
        "visual_guidance": visual_guidance,
        "audio_guidance": audio_guidance,
        "packaging_guidance": packaging_guidance,
    }
    revision_id = f"rev_{compute_profile_digest(base_dict)[:16]}"

    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    evidence_hashes = {e.evidence_id: e.sha256 for e in study.evidence}

    return DerivedProductionProfile(
        channel_id=study.channel_id,
        revision=revision_id,
        study_id=study.study_id,
        study_digest=study_sha,
        study_dir=study.study_dir,
        evidence_hashes=evidence_hashes,
        target_language=target_language,
        target_dialect=target_dialect,
        audience_intent=audience_intent,
        tone_and_style=tone_and_style,
        voice=voice,
        allowed_visual_treatments=visual_treatments,
        constraints=constraints,
        visual_guidance=visual_guidance,
        audio_guidance=audio_guidance,
        packaging_guidance=packaging_guidance,
        provenance=provenance,
        created_at=created_at,
    )


class ProfileActivationManager:
    """Manages publishing immutable revisions and atomic activation with journal recovery."""

    def __init__(self, channel_dir: Path) -> None:
        self.channel_dir = channel_dir.resolve()
        self.revisions_dir = self.channel_dir / "revisions"
        self.active_pointer_file = self.channel_dir / "active_revision.json"
        self.journal_file = self.channel_dir / ".activation_journal.json"

    def publish_and_activate(self, profile: DerivedProductionProfile) -> dict[str, Any]:
        """Publish immutable revision and atomically switch active pointer."""
        # Mandatory physical evidence validation before publishing or activating
        if not profile.study_dir:
            raise ValueError("Cannot activate profile: missing study directory storage")
        ev_dir = Path(profile.study_dir) / "evidence"
        if not ev_dir.is_dir():
            raise ValueError(f"Cannot activate profile: physical evidence directory missing: {ev_dir}")
        if not profile.evidence_hashes:
            raise ValueError("Cannot activate profile: profile contains zero evidence hashes")
        for ev_id, expected_sha in profile.evidence_hashes.items():
            ev_file = ev_dir / f"{ev_id}.bin"
            if not ev_file.is_file():
                raise ValueError(f"Cannot activate profile: missing evidence file for {ev_id}")
            actual_sha = hashlib.sha256(ev_file.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError(
                    f"Cannot activate profile: physical evidence file {ev_id} tampered (hash mismatch)"
                )

        self.revisions_dir.mkdir(parents=True, exist_ok=True)
        rev_dir = self.revisions_dir / profile.revision
        rev_dir.mkdir(parents=True, exist_ok=True)
        profile_file = rev_dir / "profile.json"

        profile_dict = profile.model_dump()
        profile_digest = compute_profile_digest(profile_dict)

        # 1. Verify revision immutability: refuse to overwrite existing revision with differing content
        if profile_file.is_file():
            existing_dict = json.loads(profile_file.read_bytes().decode("utf-8"))
            existing_digest = compute_profile_digest(existing_dict)
            if existing_digest != profile_digest:
                raise ValueError(
                    f"Revision '{profile.revision}' is immutable and already published with differing content (existing digest {existing_digest} != {profile_digest})"
                )
        else:
            temp_profile = profile_file.with_suffix(".tmp")
            temp_profile.write_bytes(profile.model_dump_json(indent=2).encode("utf-8"))
            temp_profile.replace(profile_file)

        # 2. Record journal entry for atomic pointer switch
        journal_data = {
            "channel_id": profile.channel_id,
            "target_revision": profile.revision,
            "profile_digest": profile_digest,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "PENDING_SWITCH",
        }
        self.journal_file.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")

        # 3. Atomically update active pointer
        pointer_data = {
            "channel_id": profile.channel_id,
            "active_revision": profile.revision,
            "digest": profile_digest,
            "profile_digest": profile_digest,
            "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        temp_pointer = self.active_pointer_file.with_suffix(".tmp")
        temp_pointer.write_text(json.dumps(pointer_data, indent=2), encoding="utf-8")
        temp_pointer.replace(self.active_pointer_file)

        # 4. Remove journal after successful switch
        if self.journal_file.exists():
            self.journal_file.unlink()

        return {
            "status": "ACTIVATED",
            "channel_id": profile.channel_id,
            "active_revision": profile.revision,
            "digest": profile_digest,
        }

    def recover_interrupted_activation(self) -> dict[str, Any]:
        """Check for and recover from an interrupted activation journal."""
        if not self.journal_file.is_file():
            return {"status": "CLEAN", "active_revision": self.get_active_revision()}

        journal = json.loads(self.journal_file.read_text(encoding="utf-8"))
        target_rev = journal["target_revision"]
        rev_file = self.revisions_dir / target_rev / "profile.json"

        # Validate target revision: existence, schema, digest, identity, and physical evidence
        is_valid_target = False
        loaded = None
        if rev_file.is_file():
            try:
                target_json = rev_file.read_text(encoding="utf-8")
                target_dict = json.loads(target_json)
                actual_digest = hashlib.sha256(target_json.encode("utf-8")).hexdigest()
                canonical_digest = compute_profile_digest(target_dict)
                exp = journal.get("profile_digest")
                if actual_digest == exp or canonical_digest == exp:
                    loaded = DerivedProductionProfile.model_validate(target_dict)
                    if loaded.revision == target_rev and loaded.channel_id == journal.get("channel_id"):
                        is_valid_target = True
            except Exception:
                is_valid_target = False

        if is_valid_target and loaded is not None:
            # Revalidate target profile's physical evidence before finalizing recovery pointer
            try:
                if not loaded.study_dir:
                    is_valid_target = False
                else:
                    ev_dir = Path(loaded.study_dir) / "evidence"
                    if not ev_dir.is_dir() or not loaded.evidence_hashes:
                        is_valid_target = False
                    else:
                        for ev_id, expected_sha in loaded.evidence_hashes.items():
                            ev_file = ev_dir / f"{ev_id}.bin"
                            if not ev_file.is_file() or hashlib.sha256(ev_file.read_bytes()).hexdigest() != expected_sha:
                                is_valid_target = False
                                break
            except Exception:
                is_valid_target = False

        if is_valid_target:
            pointer_data = {
                "channel_id": journal["channel_id"],
                "active_revision": target_rev,
                "digest": journal["profile_digest"],
                "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            temp_pointer = self.active_pointer_file.with_suffix(".tmp")
            temp_pointer.write_text(json.dumps(pointer_data, indent=2), encoding="utf-8")
            temp_pointer.replace(self.active_pointer_file)
            self.journal_file.unlink()
            return {"status": "RECOVERED_FINALIZED", "active_revision": target_rev}
        else:
            self.journal_file.unlink()
            return {"status": "RECOVERED_DISCARDED", "active_revision": self.get_active_revision()}

    def get_active_revision(self) -> str | None:
        """Return the active revision ID or None if no active profile exists."""
        if not self.active_pointer_file.is_file():
            return None
        data = json.loads(self.active_pointer_file.read_text(encoding="utf-8"))
        return str(data.get("active_revision"))

    def load_active_profile(self) -> DerivedProductionProfile:
        """Load the currently active production profile."""
        rev = self.get_active_revision()
        if not rev:
            raise FileNotFoundError(f"No active profile revision in {self.channel_dir}")
        profile_file = self.revisions_dir / rev / "profile.json"
        if not profile_file.is_file():
            raise FileNotFoundError(f"Active profile file missing: {profile_file}")

        # Enforce active pointer digest validation against profile content on disk
        if self.active_pointer_file.is_file():
            ptr_data = json.loads(self.active_pointer_file.read_text(encoding="utf-8"))
            expected_digest = ptr_data.get("profile_digest") or ptr_data.get("digest")
            raw_bytes = profile_file.read_bytes()
            actual_digest = hashlib.sha256(raw_bytes).hexdigest()
            try:
                prof_dict = json.loads(raw_bytes.decode("utf-8"))
                canonical_digest = compute_profile_digest(prof_dict)
            except Exception:
                canonical_digest = None

            if expected_digest:
                if actual_digest != expected_digest and canonical_digest != expected_digest:
                    raise ValueError(
                        f"Active profile digest mismatch: pointer expects {expected_digest}, but file on disk has {actual_digest}"
                    )
            return DerivedProductionProfile.model_validate(prof_dict)

        return DerivedProductionProfile.model_validate_json(profile_file.read_text(encoding="utf-8"))

    def resolve_channel(self) -> Channel:
        """Construct a Channel contract instance reflecting the active profile and pinned revision."""
        profile = self.load_active_profile()
        valid_treatments = [
            t for t in profile.allowed_visual_treatments
            if t in ("subject_scene", "detail", "mechanism", "comparison", "timeline_map", "metaphor", "host")
        ]
        if not valid_treatments:
            valid_treatments = ["subject_scene", "detail"]

        return Channel(
            channel_id=profile.channel_id,
            name=profile.channel_id,
            revision=profile.revision,
            audience=profile.audience_intent,
            language=profile.target_language,
            dialect=profile.target_dialect,
            tone=profile.tone_and_style,
            style=profile.tone_and_style,
            voice=profile.voice,
            allowed_treatments=valid_treatments,  # type: ignore[arg-type]
            visual_guidance=profile.visual_guidance,
            audio_guidance=profile.audio_guidance,
            packaging_guidance=profile.packaging_guidance,
        )
