"""Validated data boundaries; model output never selects executable behavior."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=6000)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]
Treatment = Literal[
    "subject_scene", "detail", "mechanism", "comparison", "timeline_map", "metaphor", "host"
]
HookFunction = Literal["problem", "curiosity", "promise", "proof", "handoff"]
VisualMode = Literal[
    "human_context",
    "environmental_detail",
    "editorial_metaphor",
    "mechanism",
    "comparison",
    "timeline",
    "challenge_ui",
    "kinetic_type",
]
LocalUIPrimitive = Literal[
    "cards",
    "counter",
    "focus_sweep",
    "highlight",
    "progress_ring",
    "tile_reveal",
    "timer",
    "trace_path",
]
VisualFamily = Literal[
    "generic_desk_task",
    "generic_focus_portrait",
    "mechanical_cognition",
    "efficacy_transformation",
    "generated_exercise_surface",
    "wellness_strawman",
    "false_authority",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class Channel(Contract):
    version: Literal[1, 2, 3] = 1
    channel_id: Identifier
    name: Text
    audience: Text
    language: Text
    dialect: Text
    asr_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    voice: Text | None = None
    tone: Text
    style: Text
    visual_directives: list[Text] = Field(default_factory=list, max_length=30)
    forbidden_motifs: list[Text] = Field(default_factory=list, max_length=30)
    forbidden_visual_families: list[VisualFamily] = Field(default_factory=list, max_length=10)
    repetition_limited_visual_families: list[VisualFamily] = Field(
        default_factory=list, max_length=10
    )
    max_visual_family_repetitions: int = Field(default=3, ge=1, le=10)
    max_non_diagram_scene_appearances: int | None = Field(default=None, ge=1, le=10)
    host_mode: Literal["NONE", "CUSTOM_AVATAR"] = "NONE"
    host_description: str = ""
    allowed_treatments: list[Treatment] = Field(min_length=1)
    humor: Literal["none", "light", "central"] = "light"
    max_zoom: float = Field(default=1.06, ge=1, le=1.15)

    @model_validator(mode="after")
    def check_host(self) -> Channel:
        if self.host_mode == "CUSTOM_AVATAR" and not self.host_description.strip():
            raise ValueError("CUSTOM_AVATAR requires a stable host description")
        if self.host_mode == "NONE" and "host" in self.allowed_treatments:
            raise ValueError("Host treatment requires CUSTOM_AVATAR")
        if len(set(self.allowed_treatments)) != len(self.allowed_treatments):
            raise ValueError("Duplicate allowed treatments")
        if self.version >= 2 and (not self.visual_directives or not self.forbidden_motifs):
            raise ValueError("Version 2+ channels require visual directives and forbidden motifs")
        for label, values in (
            ("visual directives", self.visual_directives),
            ("forbidden motifs", self.forbidden_motifs),
            ("forbidden visual families", self.forbidden_visual_families),
            ("repetition-limited visual families", self.repetition_limited_visual_families),
        ):
            normalized = [value.casefold() for value in values]
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"Duplicate {label}")
        return self


class Analysis(Contract):
    topics: list[Text] = Field(min_length=1, max_length=20)
    claim_basis: Literal["factual", "fictional", "mixed"]
    form: Literal[
        "explanation",
        "argument",
        "chronology",
        "comparison",
        "narrative",
        "tutorial",
        "satire",
        "mixed",
    ]
    proposition: Text
    narrative_strategy: Text
    evidence_needs: list[Text] = Field(
        default_factory=list,
        max_length=30,
        description="External verification needed for real-world claims; never a requested image",
    )
    continuity_anchors: list[Text] = Field(
        default_factory=list,
        max_length=50,
        description="Source-stated identities, relationships, settings and visible states to preserve",
    )
    figurative_phrases: list[Text] = Field(default_factory=list, max_length=50)
    treatments: list[Treatment] = Field(min_length=1)
    rationale: Text

    @model_validator(mode="after")
    def separate_fact_checking_from_fiction(self) -> Analysis:
        if self.claim_basis == "fictional" and self.evidence_needs:
            raise ValueError(
                "Fictional narratives cannot request external factual evidence; use continuity_anchors"
            )
        return self


class HookMicrobeat(Contract):
    beat_id: Identifier
    function: HookFunction
    duration_seconds: float = Field(ge=1, le=6)
    viewer_takeaway: Text
    visual_mode: VisualMode
    local_ui: list[LocalUIPrimitive] = Field(default_factory=list, max_length=3)


class EpisodeVisualStrategy(Contract):
    """Topic-specific visual direction compiled for one immutable source."""

    version: Literal[1] = 1
    source_sha256: Digest
    topic: Text
    viewer_question: Text
    central_promise: Text
    evidence_mode: Literal["observational", "explanatory", "demonstrative", "narrative", "mixed"]
    emotional_arc: list[Text] = Field(min_length=2, max_length=8)
    hook_archetype: Literal[
        "cold_open_challenge",
        "counterintuitive_claim",
        "micro_story",
        "mystery_gap",
        "pattern_interrupt",
        "visual_comparison",
    ]
    hook_microbeats: list[HookMicrobeat] = Field(min_length=3, max_length=5)
    visual_modes: list[VisualMode] = Field(min_length=2, max_length=8)
    local_ui_kit: list[LocalUIPrimitive] = Field(default_factory=list, max_length=8)
    pacing: Text
    motion_grammar: list[Text] = Field(min_length=1, max_length=8)
    max_consecutive_visual_mode: int = Field(default=2, ge=1, le=4)
    max_repeated_composition: int = Field(default=2, ge=1, le=4)

    @model_validator(mode="after")
    def validate_hook(self) -> EpisodeVisualStrategy:
        duration = sum(beat.duration_seconds for beat in self.hook_microbeats)
        if not 8 <= duration <= 15:
            raise ValueError("Hook microbeats must total 8-15 seconds")
        functions = {beat.function for beat in self.hook_microbeats}
        if "problem" not in functions or "curiosity" not in functions or not functions & {
            "promise",
            "handoff",
        }:
            raise ValueError("Hook requires problem, curiosity and promise or handoff beats")
        ids = [beat.beat_id for beat in self.hook_microbeats]
        if len(ids) != len(set(ids)):
            raise ValueError("Hook beat IDs must be unique")
        if len(self.visual_modes) != len(set(self.visual_modes)):
            raise ValueError("Episode visual modes must be unique")
        if len(self.local_ui_kit) != len(set(self.local_ui_kit)):
            raise ValueError("Episode local UI primitives must be unique")
        return self


class Brief(Contract):
    version: Literal[2, 3] = 2
    source_sha256: Digest
    profile_sha256: Digest
    channel: Channel
    analysis: Analysis
    visual_strategy: EpisodeVisualStrategy | None = None

    @model_validator(mode="after")
    def check_policy(self) -> Brief:
        if fingerprint(self.channel) != self.profile_sha256:
            raise ValueError("Profile digest mismatch")
        if not set(self.analysis.treatments) <= set(self.channel.allowed_treatments):
            raise ValueError("Analysis selected a treatment outside channel policy")
        if self.version == 3:
            if self.channel.version < 3 or self.visual_strategy is None:
                raise ValueError("Version 3 briefs require a version 3 channel and visual strategy")
            if self.visual_strategy.source_sha256 != self.source_sha256:
                raise ValueError("Episode visual strategy source digest mismatch")
        elif self.visual_strategy is not None:
            raise ValueError("Version 2 briefs cannot carry a visual strategy")
        return self


def fingerprint(value: BaseModel | dict[str, Any] | str) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    value = _canonical_fingerprint_value(value)
    encoded = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def narration_fingerprint(brief: Brief) -> str:
    """Bind words and audio to channel identity without visual-only policy fields."""
    if brief.channel.version == 1:
        return fingerprint(brief)
    channel = brief.channel.model_dump(mode="json")
    channel["version"] = 1
    channel.pop("visual_directives", None)
    channel.pop("forbidden_motifs", None)
    channel.pop("forbidden_visual_families", None)
    channel.pop("repetition_limited_visual_families", None)
    channel.pop("max_visual_family_repetitions", None)
    channel.pop("max_non_diagram_scene_appearances", None)
    projected = brief.model_dump(mode="json")
    projected["version"] = 2
    projected.pop("visual_strategy", None)
    projected["channel"] = channel
    projected["profile_sha256"] = fingerprint(channel)
    return fingerprint(projected)


def _canonical_fingerprint_value(value: Any) -> Any:
    """Keep older channel fingerprints stable as visual-policy schemas evolve."""
    if isinstance(value, dict):
        normalized = {key: _canonical_fingerprint_value(item) for key, item in value.items()}
        if normalized.get("visual_strategy") is None:
            normalized.pop("visual_strategy", None)
        if "channel_id" in normalized and normalized.get("max_non_diagram_scene_appearances") is None:
            normalized.pop("max_non_diagram_scene_appearances", None)
        if normalized.get("version") == 1 and "channel_id" in normalized:
            normalized.pop("visual_directives", None)
            normalized.pop("forbidden_motifs", None)
            normalized.pop("forbidden_visual_families", None)
            normalized.pop("repetition_limited_visual_families", None)
            normalized.pop("max_visual_family_repetitions", None)
            normalized.pop("max_non_diagram_scene_appearances", None)
        elif normalized.get("version") == 2 and "channel_id" in normalized:
            normalized.pop("forbidden_visual_families", None)
            normalized.pop("repetition_limited_visual_families", None)
            normalized.pop("max_visual_family_repetitions", None)
            normalized.pop("max_non_diagram_scene_appearances", None)
        return normalized
    if isinstance(value, list):
        return [_canonical_fingerprint_value(item) for item in value]
    return value


def load_channel(path: str | Path) -> Channel:
    return Channel.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))


def load_brief(run_dir: str | Path) -> Brief:
    root = Path(run_dir)
    brief = Brief.model_validate_json((root / "episode_brief.json").read_text(encoding="utf-8"))
    raw = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig")
    if fingerprint(raw) != brief.source_sha256:
        raise ValueError("Raw script changed; rebuild the episode brief before downstream work")
    return brief
