"""Regression tests for stitch_chapters.scan_sequential_chapters (defect ERR-03)."""

import wave
from pathlib import Path

import pytest

import stitch_chapters


def write_wav(path: Path, frames: int = 64, rate: int = 44100) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x01" * frames)


@pytest.fixture
def chapters_dir(tmp_path: Path) -> Path:
    d = tmp_path / "voice_chapters"
    d.mkdir()
    return d


def make_chapters(d: Path, *indices: int) -> list[str]:
    for i in indices:
        write_wav(d / f"Chapter_{i}.wav")
    return [str(d / f"Chapter_{i}.wav") for i in indices]


class TestSequentialScan:
    def test_complete_sequence_finds_all_and_reports_no_missing(self, chapters_dir):
        expected = make_chapters(chapters_dir, 1, 2, 3, 4)
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir))
        assert found == expected
        assert missing == []

    def test_no_chapter_files_returns_empty_pair(self, chapters_dir):
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir))
        assert found == []
        assert missing == []

    def test_missing_directory_returns_empty_pair(self, tmp_path):
        found, missing = stitch_chapters.scan_sequential_chapters(str(tmp_path / "ghost"))
        assert found == []
        assert missing == []

    def test_non_chapter_files_are_ignored(self, chapters_dir):
        expected = make_chapters(chapters_dir, 1, 2)
        (chapters_dir / "notes.txt").write_text("scratch", encoding="utf-8")
        (chapters_dir / "cover.png").write_bytes(b"\x89PNG")
        (chapters_dir / "Chapter_2.wav.bak").write_text("stale", encoding="utf-8")
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir))
        assert found == expected
        assert missing == []

    def test_start_index_limits_scan_window(self, chapters_dir):
        make_chapters(chapters_dir, 1, 2, 3, 4)
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir), start_index=3)
        assert found == [
            str(chapters_dir / "Chapter_3.wav"),
            str(chapters_dir / "Chapter_4.wav"),
        ]
        assert missing == []

    def test_start_index_beyond_max_scans_nothing(self, chapters_dir):
        make_chapters(chapters_dir, 1, 2)
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir), start_index=5)
        assert found == []
        assert missing == []

    def test_gap_truncates_found_to_contiguous_prefix(self, chapters_dir):
        make_chapters(chapters_dir, 1, 2, 4)
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir))
        assert missing == ["Chapter_3.wav"]
        assert found == [
            str(chapters_dir / "Chapter_1.wav"),
            str(chapters_dir / "Chapter_2.wav"),
        ]

    def test_post_gap_orphans_warned_and_excluded(self, chapters_dir, capsys):
        make_chapters(chapters_dir, 1, 2, 4, 5, 7)
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir))
        assert missing == ["Chapter_3.wav", "Chapter_6.wav"]
        assert found == [
            str(chapters_dir / "Chapter_1.wav"),
            str(chapters_dir / "Chapter_2.wav"),
        ]
        out = capsys.readouterr().out
        assert (
            "[WARN] 3 orphan chapter(s) beyond gap ignored: Chapter_4.wav, Chapter_5.wav, Chapter_7.wav"
            in out
        )

    def test_gap_at_start_reports_missing_first_and_orphans(self, chapters_dir, capsys):
        make_chapters(chapters_dir, 2, 3)
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir))
        assert found == []
        assert missing == ["Chapter_1.wav"]
        out = capsys.readouterr().out
        assert "[WARN] 2 orphan chapter(s) beyond gap ignored: Chapter_2.wav, Chapter_3.wav" in out
