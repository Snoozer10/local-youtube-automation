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
    version: Literal[1] = 1
    channel_id: Identifier
    name: Text
    audience: Text
    language: Text
    dialect: Text
    asr_language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    voice: Text
    tone: Text
    style: Text
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
        return self


class Analysis(Contract):
    topics: list[Text] = Field(min_length=1, max_length=20)
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
    evidence_needs: list[Text] = Field(default_factory=list, max_length=30)
    figurative_phrases: list[Text] = Field(default_factory=list, max_length=50)
    treatments: list[Treatment] = Field(min_length=1)
    rationale: Text


class Brief(Contract):
    version: Literal[1] = 1
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
    encoded = (
        value
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_channel(path: str | Path) -> Channel:
    return Channel.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))


def load_brief(run_dir: str | Path) -> Brief:
    root = Path(run_dir)
    brief = Brief.model_validate_json((root / "episode_brief.json").read_text(encoding="utf-8"))
    raw = (root / "raw_transcript.txt").read_text(encoding="utf-8-sig")
    if fingerprint(raw) != brief.source_sha256:
        raise ValueError("Raw script changed; rebuild the episode brief before downstream work")
    return brief
