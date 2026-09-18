"""Pydantic Scene-Graph Model and Bijective Timeline Synchronization.

Defines:
- SceneBeat: Atomic visual beat corresponding 1:1 to a timeline span.
- MacroScene: Cohesive thematic scene containing consecutive beats, sharing an archetype and anchor.
- SceneGraph: Complete hierarchical storyboard with bijective 1:1 assertion against timeline.json.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SceneBeat(BaseModel):
    """Atomic visual beat corresponding to exactly one timeline span."""

    beat_index: int
    timeline_span_index: int
    timestamp: str
    duration_seconds: float
    script_line: str
    visual_delta: str = ""
    spatial_direction: str = "centered"
    master_setup_prompt: str = ""  # Mode A prompt (80-100 words)
    surgical_delta_prompt: str = ""  # Mode B prompt (<25 words)
    arabic_overlay_text: str | None = None
    overlay_type: str | None = None  # TITLE_CARD | CALLOUT_BADGE | FOCUS_BRACKET | NONE
    sha256_hash: str | None = None
    render_status: str = "PENDING"  # PENDING | RENDERED | FAILED


class MacroScene(BaseModel):
    """Thematic scene grouping consecutive beats sharing an archetype, chromatic domain, and anchor."""

    scene_id: str
    domain_niche: str  # Dynamically inferred: Biology, Economics, History, Quantum Physics, etc.
    scene_archetype: Literal[
        "PROGRESSIVE_BUILD",
        "COMPARATIVE_SPLIT",
        "PUNCHLINE_STANDALONE",
        "EVIDENTIARY_ARCHIVAL",
    ]
    chromatic_domain: Literal[
        "ARCHIVAL_SEPIA",
        "TECHNICAL_SLATE",
        "NATURALIST_HERBARIUM",
    ] = "TECHNICAL_SLATE"
    start_timestamp: str
    end_timestamp: str
    continuity_anchor: str  # Concrete physical stage/object
    camera_rig: str = "orthographic flat 2D projection, fixed perspective"
    beats: list[SceneBeat] = Field(default_factory=list)


class SceneGraph(BaseModel):
    """Hierarchical Scene Graph strictly synchronized 1:1 with timeline spans."""

    video_title: str
    total_scenes: int
    total_spans: int  # Must equal total timeline spans (e.g. 293)
    scenes: list[MacroScene] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify_bijective_timeline_sync(self) -> SceneGraph:
        all_indices = [b.timeline_span_index for s in self.scenes for b in s.beats]
        expected = list(range(self.total_spans))
        if all_indices != expected:
            missing = sorted(set(expected) - set(all_indices))
            duplicates = sorted({x for x in all_indices if all_indices.count(x) > 1})
            raise ValueError(
                f"Bijective sync failure! Expected {self.total_spans} contiguous spans (0..{self.total_spans - 1}). "
                f"Missing: {missing}, Duplicates: {duplicates}"
            )
        return self

    def get_beat(self, span_index: int) -> SceneBeat | None:
        for scene in self.scenes:
            for beat in scene.beats:
                if beat.timeline_span_index == span_index:
                    return beat
        return None

    def get_scene(self, scene_id: str) -> MacroScene | None:
        for scene in self.scenes:
            if scene.scene_id == scene_id:
                return scene
        return None

    def get_scene_for_span(self, span_index: int) -> MacroScene | None:
        for scene in self.scenes:
            for beat in scene.beats:
                if beat.timeline_span_index == span_index:
                    return scene
        return None

    def to_json_file(self, path: str | Path) -> None:
        p = Path(path)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(p)

    @classmethod
    def from_json_file(cls, path: str | Path) -> SceneGraph:
        content = Path(path).read_text(encoding="utf-8")
        return cls.model_validate_json(content)
