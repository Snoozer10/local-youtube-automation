"""Unit tests for transcript spelling corrector."""

import json
from pathlib import Path

import pytest

from youtube_automation.speech.spelling_corrector import (
    align_and_correct_file,
    correct_transcript,
)


def test_align_and_correct_txt_preserves_timestamps(tmp_path: Path):
    txt_file = tmp_path / "image_timestamps.txt"
    # Transcript has ASR misspelled words "بيقول" instead of "بِيُقول" and "كده" instead of "كِدَه"
    txt_file.write_text("[00:00] يا سيدي بيقول كده\n[00:05] ده سر الطبخة\n", encoding="utf-8")

    ref_words = ["يا", "سيدي", "بِيُقول", "كِدَه", "ده", "سر", "الطبخة"]
    align_and_correct_file(str(txt_file), ref_words, "txt")

    content = txt_file.read_text(encoding="utf-8")
    assert "[00:00]" in content
    assert "[00:05]" in content
    assert "بِيُقول كِدَه" in content
    assert "ده سر الطبخة" in content


def test_align_and_correct_srt_preserves_structure(tmp_path: Path):
    srt_file = tmp_path / "timestamped_transcript.srt"
    srt_content = (
        "1\n"
        "00:00:00,000 --> 00:00:03,160\n"
        "يا سيدي بيقول كده\n\n"
        "2\n"
        "00:00:03,440 --> 00:00:06,490\n"
        "ده سر الطبخة\n\n"
    )
    srt_file.write_text(srt_content, encoding="utf-8-sig")

    ref_words = ["يا", "سيدي", "بِيُقول", "كِدَه", "ده", "سر", "الطبخة"]
    align_and_correct_file(str(srt_file), ref_words, "srt")

    corrected = srt_file.read_text(encoding="utf-8-sig")
    assert "1\n00:00:00,000 --> 00:00:03,160\n" in corrected
    assert "2\n00:00:03,440 --> 00:00:06,490\n" in corrected
    assert "بِيُقول كِدَه" in corrected


def test_correct_transcript_prioritizes_audio_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    runs_dir = tmp_path / "youtube_runs" / "test_run"
    runs_dir.mkdir(parents=True)

    # Audio manifest has 4 spoken words
    manifest = {
        "segments": [
            {"id": "001", "text_arabic": "يا سيدي بِيُقول كِدَه"}
        ]
    }
    (runs_dir / "audio_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    # Refined script has 100 words (unspoken draft)
    long_script = "يا سيدي بِيُقول كِدَه " + ("كلمة " * 100)
    (runs_dir / "refined_script.txt").write_text(long_script, encoding="utf-8")

    # SRT with 4 words
    srt_file = runs_dir / "timestamped_transcript.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:03,000\nيا سيدي بيقول كده\n\n", encoding="utf-8-sig")

    # Call correct_transcript pointing to test_run
    monkeypatch.setattr("sys.argv", ["correct_transcript_spelling.py", str(runs_dir)])
    correct_transcript()

    # Verify that the 100 extra unspoken words from refined_script were NOT injected
    corrected_srt = srt_file.read_text(encoding="utf-8-sig")
    assert "كلمة" not in corrected_srt
    assert "بِيُقول كِدَه" in corrected_srt
