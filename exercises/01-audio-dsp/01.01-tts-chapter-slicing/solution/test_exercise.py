"""Unit & Diagnostic Drill Tests for 01.01 TTS Chapter Slicing."""

import tempfile
from pathlib import Path

import pytest

from .exercise import (
    extract_tts_blocks,
    sanitize_tts_script,
    scan_directory_for_chapters,
    verify_chapter_sequence,
)


@pytest.mark.drill
def test_speech_tag_armor_enforces_lowercase() -> None:
    raw_script = (
        "مرحبا بكم [Tone: Energetic] في هذا المقطع.\n"
        "اليوم سنشرح [PACE: Slow] الفكرة بالتفصيل [Pause: 1.5s]."
    )
    cleaned = sanitize_tts_script(raw_script)

    assert "[tone: energetic]" in cleaned
    assert "[pace: slow]" in cleaned
    assert "[pause: 1.5s]" in cleaned
    assert "[Tone:" not in cleaned
    assert "[PACE:" not in cleaned


@pytest.mark.drill
def test_markdown_code_fences_and_controls_stripped() -> None:
    raw_script = """```text
مرحبا بالجميع
PROCEED
نواصل الحديث في النقطة التالية.
COMPLETE
```"""
    cleaned = sanitize_tts_script(raw_script)

    assert "```" not in cleaned
    assert "PROCEED" not in cleaned
    assert "COMPLETE" not in cleaned
    assert "مرحبا بالجميع" in cleaned
    assert "نواصل الحديث" in cleaned


@pytest.mark.drill
def test_extract_tts_blocks_sequential_indexing() -> None:
    script = """
    TTS BLOCK 1 of 3
    الفقرة الأولى تتحدث عن البداية.

    TTS BLOCK 2 of 3
    الفقرة الثانية تتعمق في الشرح.

    TTS BLOCK 3 of 3
    الفقرة الثالثة تختتم الموضوع.
    """
    blocks = extract_tts_blocks(script)
    assert len(blocks) == 3

    for idx, block in enumerate(blocks, start=1):
        assert block["chapter_num"] == idx
        assert block["audio_file"] == f"Chapter_{idx}.wav"
        assert block["status"] == "PENDING"
        assert len(block["text"]) > 0


@pytest.mark.drill
def test_verify_chapter_sequence_complete() -> None:
    files = ["Chapter_1.wav", "Chapter_2.wav", "Chapter_3.wav"]
    prefix, missing, orphans = verify_chapter_sequence(files)

    assert prefix == ["Chapter_1.wav", "Chapter_2.wav", "Chapter_3.wav"]
    assert missing == []
    assert orphans == []


@pytest.mark.drill
def test_verify_chapter_sequence_with_gap_and_orphans() -> None:
    files = ["Chapter_1.wav", "Chapter_3.wav", "Chapter_4.wav"]
    prefix, missing, orphans = verify_chapter_sequence(files)

    assert prefix == ["Chapter_1.wav"]
    assert missing == ["Chapter_2.wav"]
    assert orphans == ["Chapter_3.wav", "Chapter_4.wav"]


@pytest.mark.drill
def test_production_scan_sequential_chapters_integration() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "Chapter_1.wav").write_bytes(b"dummy1")
        (tmp_path / "Chapter_2.wav").write_bytes(b"dummy2")
        (tmp_path / "Chapter_4.wav").write_bytes(b"dummy4")

        found, missing = scan_directory_for_chapters(tmp_path)
        assert len(found) == 2
        assert "Chapter_3.wav" in missing
