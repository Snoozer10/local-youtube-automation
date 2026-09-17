"""Unit tests for SceneGraph Pydantic models and bijective timeline synchronization.

Validates:
1. Valid SceneGraph with contiguous 1:1 timeline span indices passes validation.
2. Missing timeline span index triggers ValueError.
3. Duplicate timeline span index triggers ValueError.
4. JSON serialization and deserialization roundtrip.
5. Archetype and Chromatic domain Literal validation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from youtube_automation.timeline.scene_graph import (
    MacroScene,
    SceneBeat,
    SceneGraph,
)


def _make_beat(beat_idx: int, span_idx: int, ts: str = "00:00") -> SceneBeat:
    return SceneBeat(
        beat_index=beat_idx,
        timeline_span_index=span_idx,
        timestamp=ts,
        duration_seconds=4.0,
        script_line=f"Sentence for span {span_idx}",
        visual_delta=f"Delta for beat {beat_idx}",
        spatial_direction="centered",
        master_setup_prompt="Mode A master setup prompt with 24mm lens and chiaroscuro.",
        surgical_delta_prompt="In the attached scene, add element.",
    )


def test_valid_scenegraph_passes_bijective_sync():
    # 2 scenes, 5 total spans (0, 1, 2 in scene 1; 3, 4 in scene 2)
    scene1 = MacroScene(
        scene_id="SCENE_01",
        domain_niche="Physics",
        scene_archetype="PROGRESSIVE_BUILD",
        chromatic_domain="TECHNICAL_SLATE",
        start_timestamp="00:00",
        end_timestamp="00:12",
        continuity_anchor="Brass balance scale on walnut drafting table",
        beats=[_make_beat(1, 0), _make_beat(2, 1), _make_beat(3, 2)],
    )
    scene2 = MacroScene(
        scene_id="SCENE_02",
        domain_niche="Philosophy",
        scene_archetype="COMPARATIVE_SPLIT",
        chromatic_domain="ARCHIVAL_SEPIA",
        start_timestamp="00:12",
        end_timestamp="00:20",
        continuity_anchor="Dual parchment scrolls with Greek inscription",
        beats=[_make_beat(1, 3), _make_beat(2, 4)],
    )

    sg = SceneGraph(
        video_title="Test Video",
        total_scenes=2,
        total_spans=5,
        scenes=[scene1, scene2],
    )

    assert sg.total_spans == 5
    assert len(sg.scenes) == 2
    assert sg.get_beat(3).script_line == "Sentence for span 3"
    assert sg.get_scene_for_span(1).scene_id == "SCENE_01"


def test_scenegraph_rejects_missing_span():
    # Spans: 0, 1, 3 (span 2 missing!)
    scene = MacroScene(
        scene_id="SCENE_01",
        domain_niche="Economics",
        scene_archetype="PROGRESSIVE_BUILD",
        start_timestamp="00:00",
        end_timestamp="00:15",
        continuity_anchor="Merchant counter with scale",
        beats=[_make_beat(1, 0), _make_beat(2, 1), _make_beat(3, 3)],
    )

    with pytest.raises(ValidationError) as excinfo:
        SceneGraph(
            video_title="Missing Span Video",
            total_scenes=1,
            total_spans=4,
            scenes=[scene],
        )

    assert "Bijective sync failure" in str(excinfo.value)
    assert "Missing: [2]" in str(excinfo.value)


def test_scenegraph_rejects_duplicate_span():
    # Spans: 0, 1, 1 (span 1 duplicated!)
    scene = MacroScene(
        scene_id="SCENE_01",
        domain_niche="History",
        scene_archetype="PUNCHLINE_STANDALONE",
        start_timestamp="00:00",
        end_timestamp="00:10",
        continuity_anchor="Ancient roman forum map",
        beats=[_make_beat(1, 0), _make_beat(2, 1), _make_beat(3, 1)],
    )

    with pytest.raises(ValidationError) as excinfo:
        SceneGraph(
            video_title="Duplicate Span Video",
            total_scenes=1,
            total_spans=3,
            scenes=[scene],
        )

    assert "Bijective sync failure" in str(excinfo.value)
    assert "Duplicates: [1]" in str(excinfo.value)


def test_scenegraph_json_file_roundtrip(tmp_path):
    scene = MacroScene(
        scene_id="SCENE_01",
        domain_niche="Biology",
        scene_archetype="EVIDENTIARY_ARCHIVAL",
        chromatic_domain="NATURALIST_HERBARIUM",
        start_timestamp="00:00",
        end_timestamp="00:08",
        continuity_anchor="Petri dish microscopic slide",
        beats=[_make_beat(1, 0), _make_beat(2, 1)],
    )
    sg = SceneGraph(
        video_title="Roundtrip Test",
        total_scenes=1,
        total_spans=2,
        scenes=[scene],
    )

    json_file = tmp_path / "scene_graph.json"
    sg.to_json_file(json_file)
    assert json_file.exists()

    loaded = SceneGraph.from_json_file(json_file)
    assert loaded.video_title == "Roundtrip Test"
    assert loaded.total_spans == 2
    assert loaded.scenes[0].domain_niche == "Biology"
    assert loaded.scenes[0].chromatic_domain == "NATURALIST_HERBARIUM"


def test_archetype_literal_validation():
    with pytest.raises(ValidationError):
        MacroScene(
            scene_id="SCENE_BAD",
            domain_niche="Invalid",
            scene_archetype="INVALID_ARCHETYPE",  # not one of 4 allowed
            start_timestamp="00:00",
            end_timestamp="00:05",
            continuity_anchor="anchor",
            beats=[_make_beat(1, 0)],
        )


def test_build_scene_graph_from_roadmap():
    from roadmap_orchestrator import RoadmapRow, build_scene_graph_from_roadmap

    rows = [
        RoadmapRow(
            index=1,
            timestamp="00:00",
            script_line="Sentence 1",
            sequence_type="PROGRESSIVE_BUILD",
            layout_classification="AHWA_STUDIO",
            camera_specification="static",
            visual_concept="Anchor concept 1",
            color_and_arabic_text="NONE",
        ),
        RoadmapRow(
            index=2,
            timestamp="00:04",
            script_line="Sentence 2",
            sequence_type="PROGRESSIVE_BUILD",
            layout_classification="AHWA_STUDIO",
            camera_specification="pan_left",
            visual_concept="Delta concept 2",
            color_and_arabic_text="نص توضيحي",
        ),
        RoadmapRow(
            index=3,
            timestamp="00:08",
            script_line="Sentence 3",
            sequence_type="PUNCHLINE_STANDALONE",
            layout_classification="KEYNOTE_SLATE",
            camera_specification="zoom_in",
            visual_concept="Punchline concept 3",
            color_and_arabic_text="NONE",
        ),
    ]

    timeline_data = {
        "spans": [
            {"index": 0, "start": 0.0, "duration": 4.0, "text": "Sentence 1"},
            {"index": 1, "start": 4.0, "duration": 4.0, "text": "Sentence 2"},
            {"index": 2, "start": 8.0, "duration": 3.0, "text": "Sentence 3"},
        ]
    }

    sg = build_scene_graph_from_roadmap(rows, timeline_data, "Test Build")
    assert sg.total_spans == 3
    assert len(sg.scenes) >= 1
    assert sg.get_beat(0).beat_index == 1
    assert sg.get_beat(1).arabic_overlay_text == "نص توضيحي"
    assert sg.get_beat(1).overlay_type == "TITLE_CARD"
    assert sg.get_beat(2).timeline_span_index == 2
