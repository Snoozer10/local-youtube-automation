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


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)


class Channel(Contract):
    version: Literal[1, 2] = 1
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
        if self.version == 2 and (not self.visual_directives or not self.forbidden_motifs):
            raise ValueError("Version 2 channels require visual directives and forbidden motifs")
        for label, values in (
            ("visual directives", self.visual_directives),
            ("forbidden motifs", self.forbidden_motifs),
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


class Brief(Contract):
    version: Literal[2] = 2
    source_sha256: Digest
    profile_sha256: Digest
    channel: Channel
    analysis: Analysis

    @model_validator(mode="after")
    def check_policy(self) -> Brief:
        if fingerprint(self.channel) != self.profile_sha256:
            raise ValueError("Profile digest mismatch")
        if not set(self.analysis.treatments) <= set(self.channel.allowed_treatments):
            raise ValueError("Analysis selected a treatment outside channel policy")
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
    projected = brief.model_dump(mode="json")
    projected["channel"] = channel
    projected["profile_sha256"] = fingerprint(channel)
    return fingerprint(projected)


def _canonical_fingerprint_value(value: Any) -> Any:
    """Keep version-1 channel fingerprints stable while version 2 adds policy fields."""
    if isinstance(value, dict):
        normalized = {key: _canonical_fingerprint_value(item) for key, item in value.items()}
        if normalized.get("version") == 1 and "channel_id" in normalized:
            normalized.pop("visual_directives", None)
            normalized.pop("forbidden_motifs", None)
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
