"""Unit tests for the paged roadmap orchestrator."""

import json
from pathlib import Path
from typing import Any

import pytest

import roadmap_orchestrator as ro
from pipeline_manifest import PipelineManifest


def _sentence(index: int) -> str:
    return f"جملة رقم {index} عن موضوع الحلقة."


def _make_sentences(count: int) -> list[str]:
    return [_sentence(i) for i in range(1, count + 1)]


def _row(index: int) -> ro.RoadmapRow:
    return ro.RoadmapRow(
        index=index,
        timestamp=f"00:{index:02d}",
        script_line=_sentence(index),
        sequence_type="STANDALONE",
        layout_classification="AHWA_STUDIO",
        camera_specification="static",
        visual_concept=f"Wide host desk concept {index}",
        color_and_arabic_text="NONE",
    )


def _md_row(index: int) -> str:
    row = _row(index)
    return (
        f"| {row.index} | {row.timestamp} | {row.script_line} | {row.sequence_type} "
        f"| {row.layout_classification} | {row.camera_specification} "
        f"| {row.visual_concept} | {row.color_and_arabic_text} |"
    )


def _md_page(start: int, end: int) -> str:
    return "\n".join(_md_row(i) for i in range(start, end + 1))


@pytest.fixture
def manifest(tmp_path: Path) -> PipelineManifest:
    return PipelineManifest.load_or_create(tmp_path, "test-script-hash")


@pytest.fixture
def fake_controller(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"responses": [], "injections": [], "sessions": 0}

    def fake_open(page: Any, target_model: str) -> bool:
        state["sessions"] += 1
        return True

    def fake_inject(page: Any, text: str, fill_limit: int = 500) -> bool:
        state["injections"].append(text)
        return True

    def fake_wait(page: Any, **kwargs: Any) -> str:
        if not state["responses"]:
            raise AssertionError("no queued responses left")
        return str(state["responses"].pop(0))

    monkeypatch.setattr(ro, "open_ephemeral_session", fake_open)
    monkeypatch.setattr(ro, "inject_prompt_via_cdp", fake_inject)
    monkeypatch.setattr(ro, "wait_for_gemini_turn_completion", fake_wait)
    monkeypatch.setattr(ro, "jitter_delay", lambda *a, **k: 0.0)
    return state


class TestWindowing:
    def test_even_split(self) -> None:
        windows = ro.split_transcript_into_windows(_make_sentences(100))
        assert [len(w) for w in windows] == [25, 25, 25, 25]

    def test_uneven_last_window(self) -> None:
        windows = ro.split_transcript_into_windows(_make_sentences(103))
        assert [len(w) for w in windows] == [25, 25, 25, 25, 3]

    def test_single_short_window(self) -> None:
        assert ro.split_transcript_into_windows(_make_sentences(24)) == [_make_sentences(24)]

    def test_empty_input(self) -> None:
        assert ro.split_transcript_into_windows([]) == []

    def test_window_content_slices(self) -> None:
        sentences = _make_sentences(30)
        windows = ro.split_transcript_into_windows(sentences, window_size=10)
        assert windows[0][0] == sentences[0]
        assert windows[-1][-1] == sentences[-1]

    def test_small_tail_stays_own_page(self) -> None:
        sentences = _make_sentences(23)
        windows = ro.split_transcript_into_windows(sentences, window_size=10)
        assert [len(w) for w in windows] == [10, 10, 3]
        assert windows[-1][-1] == sentences[-1]


class TestParseMarkdownTableLine:
    def test_leading_and_trailing_pipes(self) -> None:
        assert ro.parse_markdown_table_line("| a | b |") == ["a", "b"]

    def test_missing_outer_pipe_is_skipped(self) -> None:
        assert ro.parse_markdown_table_line("a | b | c") == []

    def test_separator_row_skipped(self) -> None:
        assert ro.parse_markdown_table_line("| --- | --- | --- |") == []

    def test_prose_skipped(self) -> None:
        assert ro.parse_markdown_table_line("plain prose without pipes") == []

    def test_inner_empty_cells_preserved(self) -> None:
        assert ro.parse_markdown_table_line("| a |  | b |") == ["a", "", "b"]

    def test_whitespace_stripped(self) -> None:
        assert ro.parse_markdown_table_line("  |  x  |  y  |  ") == ["x", "y"]

    def test_tab_separated_rendered_html_row(self) -> None:
        assert ro.parse_markdown_table_line("1\t00:01\tArabic text\tSTANDALONE") == [
            "1",
            "00:01",
            "Arabic text",
            "STANDALONE",
        ]


class TestParseRoadmapRows:
    REALISTIC_TABLE = "\n".join(
        [
            "| Index | Timestamp | Script Line | Sequence Type | Layout Classification "
            "| Camera Specification | Visual Concept & Composition "
            "| Color & Selective Arabic Text |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
            "| 1 | 00:00 | سطر أول | STANDALONE | AHWA_STUDIO | zoom_in "
            "| Wide host desk establishing shot | دا قِسط |",
            "| 2 | 00:05 | سطر ثانٍ | HISTORICAL_PARODY | HISTORICAL_MUSEUM | pan_left "
            "| Dolly past marble busts of scholars | NONE |",
            "| 3 | 00:10 | سطر ثالث | SCIENTIFIC_BLUEPRINT | RETRO_BLUEPRINT | tilt_down "
            "| Blueprint overhead reveal of the machine | NONE |",
        ]
    )

    def test_realistic_table_builds_typed_rows(self) -> None:
        rows = ro.parse_roadmap_rows(self.REALISTIC_TABLE)
        assert [r.index for r in rows] == [1, 2, 3]
        assert rows[0].sequence_type == "STANDALONE"
        assert rows[0].color_and_arabic_text == "دا قِسط"
        assert rows[1].layout_classification == "HISTORICAL_MUSEUM"

    def test_tab_separated_rendered_html_table(self) -> None:
        html_table_text = "\n".join(
            [
                "Index\tTimestamp\tScript Line\tSequence Type\tLayout Classification\tCamera Specification\tVisual Concept & Composition\tColor & Selective Arabic Text",
                "1\t00:00\tسطر أول\tSTANDALONE\tHOST_STUDIO_DESK\tzoom_in\tWide host desk establishing shot\tNONE",
                "2\t00:05\tسطر ثانٍ\tPROGRESSIVE_BUILD_SET\tEXPLAINER_DECK\tpan_right\tSplit screen profile view\tNONE",
            ]
        )
        rows = ro.parse_roadmap_rows(html_table_text)
        assert len(rows) == 2
        assert rows[0].index == 1
        assert rows[0].layout_classification == "HOST_STUDIO_DESK"
        assert rows[1].index == 2
        assert rows[1].sequence_type == "PROGRESSIVE_BUILD_SET"
        assert rows[1].camera_specification == "pan_right"
        assert rows[1].visual_concept == "Split screen profile view"
        assert rows[0].script_line == "سطر أول"

    def test_short_rows_skipped_without_crash(self) -> None:
        text = self.REALISTIC_TABLE + "\n| 7 | only-two-cells |\nprose line\n"
        rows = ro.parse_roadmap_rows(text)
        assert [r.index for r in rows] == [1, 2, 3]

    def test_unreadable_index_skipped(self) -> None:
        text = (
            self.REALISTIC_TABLE
            + "\n| abc | 00:99 | bad | STANDALONE | AHWA_STUDIO | static | x | y |"
        )
        rows = ro.parse_roadmap_rows(text)
        assert [r.index for r in rows] == [1, 2, 3]

    def test_duplicate_index_keeps_latest(self) -> None:
        text = self.REALISTIC_TABLE + "\n" + _md_row(3).replace("| static |", "| zoom_out |")
        rows = ro.parse_roadmap_rows(text)
        assert len(rows) == 3
        assert rows[2].camera_specification == "zoom_out"


class TestBuildPagePrompt:
    def test_first_page_envelope(self) -> None:
        prompt = ro.build_page_prompt(_make_sentences(3), 1, 3, None)
        assert "[SYSTEM DIRECTIVE: VISUAL ROADMAP ARCHITECT]" in prompt
        assert "Script Indices 1 through 3." in prompt
        assert "CONTINUITY ANCHOR" not in prompt
        assert "with this exact header:" in prompt
        assert ", do not repeat headers" not in prompt
        assert "Index 1: جملة رقم 1 عن موضوع الحلقة." in prompt
        assert "Index 3: جملة رقم 3 عن موضوع الحلقة." in prompt
        assert "STANDALONE | PROGRESSIVE_BUILD_SET" in prompt
        assert "zoom_in | zoom_out" in prompt

    def test_continuation_page_anchor_and_header_rule(self) -> None:
        anchor = _row(25)
        prompt = ro.build_page_prompt(_make_sentences(30)[25:], 26, 30, anchor)
        assert 'CONTINUITY ANCHOR (Index 25): "Wide host desk concept 25"' in prompt
        assert "Script Indices 26 through 30." in prompt
        assert ", do not repeat headers:" in prompt
        assert "with this exact header" not in prompt
        assert "Index 26: جملة رقم 26 عن موضوع الحلقة." in prompt


class TestRowsToMarkdown:
    def test_header_once_plus_rows(self) -> None:
        md = ro.rows_to_markdown([_row(2), _row(1)])
        lines = md.splitlines()
        assert sum(1 for line in lines if line.startswith("| Index")) == 1
        assert len(lines) == 3
        assert "1" in lines[1] and "2" in lines[2]

    def test_multiline_cells_sanitized(self) -> None:
        row = ro.RoadmapRow(
            index=1,
            timestamp="t",
            script_line="s",
            sequence_type="st",
            layout_classification="lay",
            camera_specification="cam",
            visual_concept="line one\nline two",
            color_and_arabic_text="NONE",
        )
        md = ro.rows_to_markdown([row])
        assert len(md.splitlines()) == 2


class TestLoadOrMigrateRoadmap:
    def _write_jsonl(self, folder: Path, indices: list[int]) -> None:
        rows = [_row(i) for i in indices]
        payload = "".join(json.dumps(r.to_dict(), ensure_ascii=False) + "\n" for r in rows)
        (folder / ro.ROADMAP_JSONL_FILENAME).write_text(payload, encoding="utf-8")

    def test_jsonl_hit_returns_rows_and_completes_manifest(
        self, tmp_path: Path, manifest: PipelineManifest
    ) -> None:
        sentences = _make_sentences(3)
        self._write_jsonl(tmp_path, [1, 2, 3])
        result = ro.load_or_migrate_roadmap(tmp_path, sentences, manifest)
        assert result is not None
        assert [r.index for r in result] == [1, 2, 3]
        assert result[0].visual_concept == "Wide host desk concept 1"
        data = manifest.to_dict()["roadmap_phase"]
        assert data["status"] == "COMPLETED"
        assert data["total_lines"] == 3

    def test_invalid_jsonl_falls_through_to_none(
        self, tmp_path: Path, manifest: PipelineManifest
    ) -> None:
        sentences = _make_sentences(3)
        self._write_jsonl(tmp_path, [1, 2])
        assert ro.load_or_migrate_roadmap(tmp_path, sentences, manifest) is None

    def test_legacy_txt_migrates_to_jsonl(self, tmp_path: Path, manifest: PipelineManifest) -> None:
        sentences = _make_sentences(3)
        (tmp_path / ro.LEGACY_ROADMAP_FILENAME).write_text(
            ro.rows_to_markdown([_row(1), _row(2), _row(3)]), encoding="utf-8"
        )
        result = ro.load_or_migrate_roadmap(tmp_path, sentences, manifest)
        assert result is not None
        assert [r.index for r in result] == [1, 2, 3]
        assert (tmp_path / ro.ROADMAP_JSONL_FILENAME).exists()
        data = manifest.to_dict()["roadmap_phase"]
        assert data["status"] == "COMPLETED"

    def test_corrupt_legacy_garbage_returns_none(
        self, tmp_path: Path, manifest: PipelineManifest
    ) -> None:
        sentences = _make_sentences(3)
        (tmp_path / ro.LEGACY_ROADMAP_FILENAME).write_text("عشوائي " * 40, encoding="utf-8")
        assert ro.load_or_migrate_roadmap(tmp_path, sentences, manifest) is None

    def test_stuck_placeholder_legacy_returns_none(
        self, tmp_path: Path, manifest: PipelineManifest
    ) -> None:
        (tmp_path / ro.LEGACY_ROADMAP_FILENAME).write_text("analyzing", encoding="utf-8")
        assert ro.load_or_migrate_roadmap(tmp_path, _make_sentences(3), manifest) is None

    def test_no_files_returns_none(self, tmp_path: Path, manifest: PipelineManifest) -> None:
        assert ro.load_or_migrate_roadmap(tmp_path, _make_sentences(3), manifest) is None


class TestGenerateMasterRoadmap:
    def test_happy_path_two_pages(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        fake_controller["responses"] = [_md_page(1, 25), _md_page(26, 50)]
        rows = ro.generate_master_roadmap(object(), _make_sentences(50), tmp_path, manifest)

        assert [r.index for r in rows] == list(range(1, 51))
        assert fake_controller["sessions"] in [0, 1]
        assert len(fake_controller["injections"]) == 2

        jsonl_lines = (
            (tmp_path / ro.ROADMAP_JSONL_FILENAME).read_text(encoding="utf-8").splitlines()
        )
        assert len(jsonl_lines) == 50
        first = json.loads(jsonl_lines[0])
        assert first["index"] == 1
        txt = (tmp_path / ro.LEGACY_ROADMAP_FILENAME).read_text(encoding="utf-8")
        assert txt.count("| Index |") == 1
        assert len(txt.strip().splitlines()) == 51

        data = manifest.to_dict()["roadmap_phase"]
        assert data["status"] == "COMPLETED"
        assert data["completed_pages"] == [1, 2]
        assert data["last_processed_index"] == 50
        assert data["total_lines"] == 50

    def test_self_heal_repairs_missing_index(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        page1_broken = "\n".join(_md_row(i) for i in range(1, 26) if i != 3)
        fake_controller["responses"] = [page1_broken, _md_row(3), _md_page(26, 50)]

        rows = ro.generate_master_roadmap(object(), _make_sentences(50), tmp_path, manifest)

        assert [r.index for r in rows] == list(range(1, 51))
        assert fake_controller["sessions"] in [0, 1]
        assert len(fake_controller["injections"]) == 3
        repair_payload = fake_controller["injections"][1]
        assert "missing indices: [3]" in repair_payload
        data = manifest.to_dict()["roadmap_phase"]
        assert data["completed_pages"] == [1, 2]

    def test_exhausted_page_raises_runtime_error(
        self,
        tmp_path: Path,
        manifest: PipelineManifest,
        fake_controller: dict[str, Any],
    ) -> None:
        garbage = "Unfortunately I cannot produce a table right now."
        fake_controller["responses"] = [garbage, garbage, garbage]

        with pytest.raises(RuntimeError, match="unresolved indices"):
            ro.generate_master_roadmap(object(), _make_sentences(25), tmp_path, manifest)

        data = manifest.to_dict()["roadmap_phase"]
        assert data["status"] == "IN_PROGRESS"

    def test_empty_transcript_raises(self, tmp_path: Path, manifest: PipelineManifest) -> None:
        with pytest.raises(RuntimeError, match="empty transcript"):
            ro.generate_master_roadmap(object(), [], tmp_path, manifest)

    def test_resumes_from_existing_complete_jsonl(
        self, tmp_path: Path, manifest: PipelineManifest
    ) -> None:
        rows = [_row(i) for i in range(1, 4)]
        payload = "".join(json.dumps(r.to_dict(), ensure_ascii=False) + "\n" for r in rows)
        (tmp_path / ro.ROADMAP_JSONL_FILENAME).write_text(payload, encoding="utf-8")
        result = ro.load_or_migrate_roadmap(tmp_path, _make_sentences(3), manifest)
        assert result is not None and len(result) == 3
