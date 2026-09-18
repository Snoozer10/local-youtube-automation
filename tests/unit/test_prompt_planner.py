"""Unit tests for the stateless Phase-2 prompt planner."""

import json
from pathlib import Path
from typing import Any

import pytest

import prompt_planner as pp
from pipeline_manifest import ChunkStatus, PipelineManifest
from roadmap_orchestrator import RoadmapRow


def _sentence(index: int) -> str:
    return f"جملة رقم {index} عن موضوع الحلقة."


def _make_sentences(count: int) -> list[str]:
    return [_sentence(i) for i in range(1, count + 1)]


def _timestamp(index: int) -> str:
    return f"{(index - 1) // 60:02d}:{(index - 1) % 60:02d}"


def _make_timestamps(count: int) -> list[str]:
    return [_timestamp(i) for i in range(1, count + 1)]


def _row(index: int) -> RoadmapRow:
    return RoadmapRow(
        index=index,
        timestamp=_timestamp(index),
        script_line=_sentence(index),
        sequence_type="STANDALONE",
        layout_classification="AHWA_STUDIO",
        camera_specification="static",
        visual_concept=f"Wide host desk concept {index}",
        color_and_arabic_text="NONE",
    )


def _rows(count: int) -> list[RoadmapRow]:
    return [_row(i) for i in range(1, count + 1)]


STYLE_ANCHOR = (
    "2D graphic vector animation explainer style, crisp 3px black vector outlines, "
    "flat 2-step cel-shading, 16:9 widescreen"
)


def _frame(index: int) -> dict[str, Any]:
    return {
        "index": index,
        "timestamp": f"[{_timestamp(index)}]",
        "sequence_type": "STANDALONE",
        "layout_classification": "AHWA_STUDIO",
        "sequence_metadata": {"set_id": "SET_01", "frame_index": 1, "total_frames_in_set": 1},
        "visual_density": "MEDIUM_ACTION",
        "visual_prompt": {
            "subject_details": "HOST",
            "subject_action_increment": f"gesture {index}",
            "environment_coordinates": "AHWA_STUDIO",
            "composition_layout": "centered subject in golden center",
            "camera_specifications": "static",
            "text_overlay_arabic": "NONE",
            "accent_color_hook": "Warm Amber (#E09F3E)",
            "style_anchor": STYLE_ANCHOR,
        },
    }


def _array(start: int, end: int) -> str:
    return json.dumps([_frame(i) for i in range(start, end + 1)], ensure_ascii=False)


def _preset_fixtures() -> dict[str, Any]:
    return {
        "CHARACTERS": {
            "HOST": {
                "name": "CHARACTER_HOST_MAIN",
                "info": (
                    "Character Visual DNA: Ahmed El-Ghandour.\n"
                    "Anatomy: curly afro hair, wire glasses."
                ),
                "portrait_prompt": "bust portrait",
                "body_prompt": "turnaround sheet",
            },
            "GOVERNMENT_CLERK": {
                "name": "CHARACTER_CLERK_BUREAUCRAT",
                "info": (
                    "Character Visual DNA: Science Bureaucrat.\n"
                    "Anatomy: beige suit, laminated ID badge."
                ),
                "portrait_prompt": "bust portrait",
                "body_prompt": "turnaround sheet",
            },
            "SKEPTIC": {
                "name": "CHARACTER_SKEPTIC_ABO_HMEED",
                "info": "Character Visual DNA: Abo Hmeed.\nAnatomy: questioning eyebrows.",
                "portrait_prompt": "bust portrait",
                "body_prompt": "turnaround sheet",
            },
        },
        "SCENES": {
            "AHWA_STUDIO": {
                "name": "SCENE_AHWA_STUDIO_ENV",
                "scene_prompt": "Cozy Cairo studio.\nWooden desk, CRT monitor, mint tea.",
            },
            "ARCHIVAL_DOSSIER": {
                "name": "SCENE_ARCHIVAL_DOSSIER_ENV",
                "scene_prompt": "Warm parchment dossier flat-lay.",
            },
            "COMPARATIVE_DIAGRAM_DESK": {
                "name": "SCENE_COMPARATIVE_DIAGRAM_ENV",
                "scene_prompt": "Cream clipboard comparison chart.",
            },
            "RETRO_BLUEPRINT": {
                "name": "SCENE_RETRO_BLUEPRINT_ENV",
                "scene_prompt": "Navy canvas with cyan schematics.",
            },
            "HISTORICAL_MUSEUM": {
                "name": "SCENE_HISTORICAL_MUSEUM_ENV",
                "scene_prompt": "Baroque gallery with damask wallpaper.",
            },
            "ISOLATED_WHITE": {
                "name": "SCENE_ISOLATED_WHITE_ENV",
                "scene_prompt": "Solid white cyclorama plate.",
            },
        },
    }


@pytest.fixture
def manifest(tmp_path: Path) -> PipelineManifest:
    return PipelineManifest.load_or_create(tmp_path, "planner-test-hash")


@pytest.fixture
def fake_controller(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"responses": [], "injections": [], "sessions": 0, "models": [], "last_idx": None}

    def fake_persistent(page: Any, current_start_idx: int, planner_model: str) -> bool:
        if state["last_idx"] is None or current_start_idx - state["last_idx"] >= 100:
            state["sessions"] += 1
            state["last_idx"] = current_start_idx
            state["models"].append(planner_model)
        return True

    def fake_inject(page: Any, text: str, fill_limit: int = 500) -> bool:
        state["injections"].append(text)
        return True

    def fake_wait(page: Any, **kwargs: Any) -> str:
        if not state["responses"]:
            raise AssertionError("no queued responses left")
        return str(state["responses"].pop(0))

    monkeypatch.setattr(pp, "ensure_persistent_gemini_session", fake_persistent)
    monkeypatch.setattr(pp, "inject_prompt_via_cdp", fake_inject)
    monkeypatch.setattr(pp, "wait_for_gemini_turn_completion", fake_wait)
    monkeypatch.setattr(pp, "jitter_delay", lambda *a, **k: 0.0)
    return state


class TestExtractRoadmapSlice:
    def test_default_buffer_includes_neighbors(self) -> None:
        sliced = pp.extract_roadmap_slice(_rows(40), 16, 30)
        assert [row.index for row in sliced] == list(range(15, 32))

    def test_zero_buffer_exact_span(self) -> None:
        sliced = pp.extract_roadmap_slice(_rows(40), 16, 30, buffer=0)
        assert [row.index for row in sliced] == list(range(16, 31))

    def test_empty_input_safe(self) -> None:
        assert pp.extract_roadmap_slice([], 1, 15) == []

    def test_unsorted_input_sorted_ascending(self) -> None:
        sliced = pp.extract_roadmap_slice(list(reversed(_rows(40))), 16, 30)
        assert [row.index for row in sliced] == list(range(15, 32))


class TestBuildCompactPreamble:
    def test_always_present_sections(self) -> None:
        preamble = pp.build_compact_preamble(None)
        assert pp.STYLE_DNA_TEXT in preamble
        for term in ("subtitles", "margin", "watermark", "Latin text", "photorealism", "gradients"):
            assert term in preamble
        assert "Kufic" in preamble
        assert '"NONE"' in preamble
        assert "OUTPUT: ONE raw JSON array" in preamble

    def test_no_presets_renders_no_asset_tokens(self) -> None:
        preamble = pp.build_compact_preamble(None)
        assert "HOST:" not in preamble
        assert "SKEPTIC:" not in preamble
        assert "GOVERNMENT_CLERK:" not in preamble
        assert "ISOLATED_WHITE:" not in preamble

    def test_character_and_scene_tokens_rendered_verbatim(self) -> None:
        preamble = pp.build_compact_preamble(_preset_fixtures())
        assert 'HOST: "CHARACTER_HOST_MAIN.' in preamble
        assert 'GOVERNMENT_CLERK: "CHARACTER_CLERK_BUREAUCRAT.' in preamble
        assert 'SKEPTIC: "CHARACTER_SKEPTIC_ABO_HMEED.' in preamble
        assert 'AHWA_STUDIO: "SCENE_AHWA_STUDIO_ENV.' in preamble
        assert 'ARCHIVAL_DOSSIER: "SCENE_ARCHIVAL_DOSSIER_ENV.' in preamble
        assert 'COMPARATIVE_DIAGRAM_DESK: "SCENE_COMPARATIVE_DIAGRAM_ENV.' in preamble
        assert 'RETRO_BLUEPRINT: "SCENE_RETRO_BLUEPRINT_ENV.' in preamble
        assert 'HISTORICAL_MUSEUM: "SCENE_HISTORICAL_MUSEUM_ENV.' in preamble
        assert 'ISOLATED_WHITE: "SCENE_ISOLATED_WHITE_ENV.' in preamble

    def test_multiline_descriptions_condensed_to_one_line(self) -> None:
        preamble = pp.build_compact_preamble(_preset_fixtures())
        host_line = next(
            line for line in preamble.splitlines() if line.lstrip().startswith("HOST:")
        )
        assert "Ahmed El-Ghandour." in host_line
        assert "wire glasses." in host_line
        scene_line = next(
            line for line in preamble.splitlines() if line.lstrip().startswith("AHWA_STUDIO:")
        )
        assert "Cozy Cairo studio." in scene_line
        assert "mint tea." in scene_line

    def test_dynamic_profile_overrides_host_preset(self) -> None:
        from youtube_automation.prompts.niche_engine import ChannelProfile
        profile = ChannelProfile(
            channel_name="Science Explained",
            niche="SCIENCE_TECH",
            host_mode="CUSTOM_AVATAR",
            host_avatar_description="female astrophysicist in lab coat with wire glasses",
        )
        preamble = pp.build_compact_preamble(_preset_fixtures(), profile=profile)
        assert "female astrophysicist in lab coat" in preamble
        assert "Ahmed El-Ghandour" not in preamble

    def test_host_mode_none_omits_host_character(self) -> None:
        from youtube_automation.prompts.niche_engine import ChannelProfile
        profile = ChannelProfile(
            channel_name="Documentary Studio",
            niche="SCIENCE_TECH",
            host_mode="NONE",
        )
        preamble = pp.build_compact_preamble(_preset_fixtures(), profile=profile)
        assert "HOST:" not in preamble
        assert "GOVERNMENT_CLERK:" in preamble



class TestBuildChunkPayload:
    def _payload(self) -> str:
        preamble = pp.build_compact_preamble(None)
        slice_rows = pp.extract_roadmap_slice(_rows(40), 16, 30)
        script_lines = [(i, _timestamp(i), _sentence(i)) for i in range(16, 31)]
        return pp.build_chunk_payload(preamble, slice_rows, script_lines)

    def test_contains_preamble_and_section_headers(self) -> None:
        payload = self._payload()
        assert pp.build_compact_preamble(None) in payload
        assert "ROADMAP CONTEXT (target span +/- buffer):" in payload
        assert "SCRIPT LINES TO CONVERT:" in payload

    def test_table_rows_include_buffer_row(self) -> None:
        payload = self._payload()
        assert "| 15 |" in payload
        assert "| 30 |" in payload

    def test_script_lines_use_index_timestamp_format(self) -> None:
        payload = self._payload()
        assert f"Index 16 [{_timestamp(16)}] {_sentence(16)}" in payload
        assert f"Index 30 [{_timestamp(30)}] {_sentence(30)}" in payload

    def test_exact_span_directive(self) -> None:
        assert "Emit the JSON array for Indices 16..30 now." in self._payload()


class TestPlanAllChunksHappyPath:
    def test_two_chunks_planned_and_persisted(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        fake_controller["responses"] = [_array(1, 15), _array(16, 30)]
        result = pp.plan_all_chunks(
            object(),
            _make_sentences(30),
            _make_timestamps(30),
            _rows(30),
            tmp_path,
            manifest,
        )

        assert [frame["index"] for frame in result] == list(range(1, 31))
        saved = json.loads((tmp_path / "flow_prompts.json").read_text(encoding="utf-8"))
        assert [frame["index"] for frame in saved] == list(range(1, 31))

        chunks = manifest.to_dict()["planning_phase"]["chunks"]
        assert chunks["chunk_1"]["status"] == "VERIFIED"
        assert chunks["chunk_2"]["status"] == "VERIFIED"
        assert chunks["chunk_1"]["attempts"] >= 1
        assert chunks["chunk_2"]["attempts"] >= 1
        assert fake_controller["sessions"] in [0, 1]
        assert fake_controller["models"] in [[], ["Flash-Lite"], ["Flash-Lite", "Flash-Lite"]]


class TestPlanAllChunksRepairPath:
    def test_missing_index_self_heals_same_session(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        broken = json.dumps([_frame(i) for i in range(1, 21) if i != 17], ensure_ascii=False)
        fake_controller["responses"] = [broken, json.dumps([_frame(17)]), _array(21, 30)]

        result = pp.plan_all_chunks(
            object(),
            _make_sentences(30),
            _make_timestamps(30),
            _rows(30),
            tmp_path,
            manifest,
            chunk_size=20,
        )

        assert [frame["index"] for frame in result] == list(range(1, 31))
        chunks = manifest.to_dict()["planning_phase"]["chunks"]
        assert chunks["chunk_1"]["status"] == "REPAIRED"
        assert chunks["chunk_1"]["attempts"] == 2
        assert chunks["chunk_2"]["status"] == "VERIFIED"
        repair_payload = fake_controller["injections"][1]
        assert "[17]" in repair_payload
        assert f"Index 17 [{_timestamp(17)}]" in repair_payload

    def test_invalid_schema_item_triggers_repair(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        invalid_frame = _frame(1)
        del invalid_frame["visual_prompt"]["style_anchor"]
        fake_controller["responses"] = [
            json.dumps([invalid_frame]),
            json.dumps([_frame(1)], ensure_ascii=False),
        ]

        result = pp.plan_all_chunks(
            object(), ["جملة واحدة."], ["00:00"], _rows(1), tmp_path, manifest
        )

        assert len(result) == 1 and result[0]["index"] == 1
        chunks = manifest.to_dict()["planning_phase"]["chunks"]
        assert chunks["chunk_1"]["status"] == "REPAIRED"
        assert "Rejected because:" in fake_controller["injections"][1]


class TestPlanAllChunksExhaustion:
    def test_exhaustion_raises_with_debug_dump(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        broken = json.dumps([_frame(i) for i in range(1, 21) if i != 17], ensure_ascii=False)
        fake_controller["responses"] = [broken, broken, broken]

        with pytest.raises(pp.ChunkPlanningError) as exc_info:
            pp.plan_all_chunks(
                object(),
                _make_sentences(30),
                _make_timestamps(30),
                _rows(30),
                tmp_path,
                manifest,
                chunk_size=20,
            )

        error = exc_info.value
        assert error.chunk_id == "chunk_1"
        assert error.missing_indices == [17]
        assert error.debug_dump_path != ""

        dump_file = Path(error.debug_dump_path)
        assert dump_file == tmp_path / "debug" / "malformed_chunk_1.json"
        dumped = json.loads(dump_file.read_text(encoding="utf-8"))
        assert dumped["missing_indices"] == [17]
        assert dumped["raw_response"] == broken

        chunks = manifest.to_dict()["planning_phase"]["chunks"]
        assert chunks["chunk_1"]["status"] == "FAILED"
        assert chunks["chunk_1"]["attempts"] == 3


class TestResumeAndMerge:
    def test_complete_run_skips_all_gemini_calls(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        (tmp_path / "flow_prompts.json").write_text(
            json.dumps([_frame(i) for i in range(1, 31)], ensure_ascii=False), encoding="utf-8"
        )
        manifest.init_planning(15, 2)
        manifest.set_chunk_status("chunk_1", list(range(1, 16)), ChunkStatus.VERIFIED, 1)
        manifest.set_chunk_status("chunk_2", list(range(16, 31)), ChunkStatus.VERIFIED, 1)

        result = pp.plan_all_chunks(
            object(),
            _make_sentences(30),
            _make_timestamps(30),
            _rows(30),
            tmp_path,
            manifest,
        )

        assert [frame["index"] for frame in result] == list(range(1, 31))
        assert fake_controller["sessions"] == 0
        assert fake_controller["injections"] == []

    def test_baseline_chunk_merged_only_chunk_two_planned(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        (tmp_path / "flow_prompts.json").write_text(
            json.dumps([_frame(i) for i in range(1, 16)], ensure_ascii=False), encoding="utf-8"
        )
        manifest.init_planning(15, 2)
        manifest.set_chunk_status("chunk_1", list(range(1, 16)), ChunkStatus.VERIFIED, 1)
        fake_controller["responses"] = [_array(16, 30)]

        result = pp.plan_all_chunks(
            object(),
            _make_sentences(30),
            _make_timestamps(30),
            _rows(30),
            tmp_path,
            manifest,
        )

        assert fake_controller["sessions"] in [0, 1]
        assert [frame["index"] for frame in result] == list(range(1, 31))
        saved = json.loads((tmp_path / "flow_prompts.json").read_text(encoding="utf-8"))
        assert [frame["index"] for frame in saved] == list(range(1, 31))
        chunks = manifest.to_dict()["planning_phase"]["chunks"]
        assert chunks["chunk_1"]["status"] == "VERIFIED"
        assert chunks["chunk_1"]["attempts"] == 1
        assert chunks["chunk_2"]["status"] == "VERIFIED"

    def test_corrupt_baseline_warns_and_replans_everything(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        (tmp_path / "flow_prompts.json").write_text("{not valid json", encoding="utf-8")
        fake_controller["responses"] = [_array(1, 15), _array(16, 30)]

        result = pp.plan_all_chunks(
            object(),
            _make_sentences(30),
            _make_timestamps(30),
            _rows(30),
            tmp_path,
            manifest,
        )

        assert fake_controller["sessions"] in [0, 1]
        assert len(result) == 30
        saved = json.loads((tmp_path / "flow_prompts.json").read_text(encoding="utf-8"))
        assert [frame["index"] for frame in saved] == list(range(1, 31))


class Test3SpanWindowContext:
    def test_build_3span_window_context_middle_span(self):
        spans = [
            {"index": 1, "start": 0.0, "end": 3.0, "text": "Sentence one", "pause_before": 0.0, "pause_after": 0.4},
            {"index": 2, "start": 3.4, "end": 6.8, "text": "Sentence two", "pause_before": 0.4, "pause_after": 0.5},
            {"index": 3, "start": 7.3, "end": 10.5, "text": "Sentence three", "pause_before": 0.5, "pause_after": 0.0},
        ]
        ctx = pp.build_3span_window_context(spans, target_index=2)
        assert ctx["current_span"]["index"] == 2
        assert ctx["prev_span"]["index"] == 1
        assert ctx["next_span"]["index"] == 3
        assert ctx["pause_before"] == 0.4
        assert ctx["pause_after"] == 0.5

    def test_build_3span_window_context_boundary_spans(self):
        spans = [
            {"index": 1, "start": 0.0, "end": 3.0, "text": "First sentence", "pause_before": 0.0, "pause_after": 0.4},
            {"index": 2, "start": 3.4, "end": 6.8, "text": "Second sentence", "pause_before": 0.4, "pause_after": 0.0},
        ]
        # First span has no prev_span
        ctx_first = pp.build_3span_window_context(spans, target_index=1)
        assert ctx_first["prev_span"] is None
        assert ctx_first["next_span"]["index"] == 2

        # Last span has no next_span
        ctx_last = pp.build_3span_window_context(spans, target_index=2)
        assert ctx_last["prev_span"]["index"] == 1
        assert ctx_last["next_span"] is None


class TestSubjectContinuityTracker:
    def test_register_and_match_similar_subject(self):
        tracker = pp.SubjectContinuityTracker(similarity_threshold=0.78)
        # Register host
        c_id = tracker.register_subject("CHARACTER_HOST_MAIN", "Ahmed El-Ghandour with afro hair and wire glasses")
        assert c_id == "SUBJ_01"

        # Query coreferenced / similar subject
        match_id, sim, is_match = tracker.resolve_subject("Ahmed El-Ghandour host at desk")
        assert is_match is True
        assert match_id == "SUBJ_01"
        assert sim >= 0.78

    def test_unrelated_subject_creates_new_continuity_id(self):
        tracker = pp.SubjectContinuityTracker(similarity_threshold=0.78)
        tracker.register_subject("CHARACTER_HOST_MAIN", "Host with glasses")

        match_id, sim, is_match = tracker.resolve_subject("A mechanical clockwork gears diagram")
        assert is_match is False
        assert sim < 0.78
        # Registering new subject gives new id
        new_id = tracker.register_subject("CLOCKWORK_DIAGRAM", "A mechanical clockwork gears diagram")
        assert new_id == "SUBJ_02"
