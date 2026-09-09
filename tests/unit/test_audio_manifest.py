"""Unit tests for audio manifest enrichment, physical WAV duration probe,
and monotonic timeline sequence alignment (Phase 3 Voice Generation).
"""

import json
import wave
from pathlib import Path

import pytest

from youtube_automation.audio.tts_generator import (
    AUDIO_MANIFEST_FILE_NAME,
    probe_audio_file,
    sync_audio_manifest,
)


def write_test_wav(path: Path, duration_sec: float = 1.0, rate: int = 24000, channels: int = 1) -> None:
    """Helper to write a valid PCM 16-bit WAV file with known duration."""
    nframes = int(duration_sec * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x01" * (nframes * channels))


def test_probe_audio_file_valid_wav(tmp_path: Path):
    wav_path = tmp_path / "test_clip.wav"
    write_test_wav(wav_path, duration_sec=2.5, rate=24000, channels=1)

    probe = probe_audio_file(str(wav_path))
    assert probe is not None
    assert probe["framerate"] == 24000
    assert probe["channels"] == 1
    assert probe["sampwidth"] == 2
    assert probe["duration"] == 2.5
    assert probe["nframes"] == 60000


def test_probe_audio_file_missing_or_corrupt(tmp_path: Path):
    assert probe_audio_file(str(tmp_path / "ghost.wav")) is None

    corrupt_file = tmp_path / "corrupt.wav"
    corrupt_file.write_bytes(b"NOT_A_WAV_HEADER_DATA")
    assert probe_audio_file(str(corrupt_file)) is None


def test_sync_audio_manifest_schema_and_monotonicity(tmp_path: Path):
    voice_dir = tmp_path / "voice_chapters"
    voice_dir.mkdir()

    # Create 3 chapters with distinct physical durations
    c1_path = voice_dir / "Chapter_1.wav"
    c2_path = voice_dir / "Chapter_2.wav"
    c3_path = voice_dir / "Chapter_3.wav"

    write_test_wav(c1_path, duration_sec=3.250, rate=24000)
    write_test_wav(c2_path, duration_sec=4.500, rate=24000)
    write_test_wav(c3_path, duration_sec=2.100, rate=24000)

    manifest = {
        "voice_config": {
            "model": "gemini-2.5-pro-preview-tts",
            "temperature": 0.8,
            "voice": "Achird",
        },
        "chapters": [
            {
                "chapter_num": 1,
                "text": "يا سيدي هذا المقطع الأول للتجربة ودا سر الطبخة",
                "audio_file": str(c1_path),
                "status": "COMPLETED",
                "md5": "abc111",
            },
            {
                "chapter_num": 2,
                "text": "ثانية واحدة يا أبو حميد دا المقطع التاني عظمة على عظمة",
                "audio_file": str(c2_path),
                "status": "COMPLETED",
                "md5": "abc222",
            },
            {
                "chapter_num": 3,
                "text": "المقطع الأخير يا فنان مسك الختام والهدوء النفسي",
                "audio_file": str(c3_path),
                "status": "COMPLETED",
                "md5": "abc333",
            },
        ],
    }

    result = sync_audio_manifest(str(tmp_path), manifest, silence_padding_sec=0.300)

    # 1. Verify top-level manifest structure
    assert result["schema_version"] == "1.0.0"
    assert result["voice_target"] == "Achird"
    assert result["silence_padding_sec"] == 0.300
    assert result["total_segments"] == 3
    assert result["completed_segments"] == 3
    assert result["format"]["sample_rate"] == 24000
    assert result["format"]["bit_depth"] == 16
    assert result["format"]["channels"] == 1

    segments = result["segments"]
    assert len(segments) == 3

    # 2. Verify Segment 1 (start = 0.0)
    s1 = segments[0]
    assert s1["id"] == "001"
    assert s1["index"] == 1
    assert s1["audio_file"] == "voice_chapters/Chapter_1.wav"
    assert s1["text_arabic"] == "يا سيدي هذا المقطع الأول للتجربة ودا سر الطبخة"
    assert s1["duration"] == 3.250
    assert s1["start_time"] == 0.0
    assert s1["end_time"] == 3.250
    assert s1["visual_keyframe_id"] == "scene_001"
    assert s1["words_count"] == 9
    assert s1["words_per_minute"] > 0

    # 3. Verify Segment 2 (monotonic start = s1.end + 0.300)
    s2 = segments[1]
    assert s2["id"] == "002"
    assert s2["index"] == 2
    assert s2["audio_file"] == "voice_chapters/Chapter_2.wav"
    assert s2["duration"] == 4.500
    assert s2["start_time"] == pytest.approx(3.550, abs=1e-3)
    assert s2["end_time"] == pytest.approx(8.050, abs=1e-3)
    assert s2["visual_keyframe_id"] == "scene_002"

    # 4. Verify Segment 3 (monotonic start = s2.end + 0.300)
    s3 = segments[2]
    assert s3["id"] == "003"
    assert s3["index"] == 3
    assert s3["duration"] == 2.100
    assert s3["start_time"] == pytest.approx(8.350, abs=1e-3)
    assert s3["end_time"] == pytest.approx(10.450, abs=1e-3)
    assert s3["visual_keyframe_id"] == "scene_003"

    # 5. Verify physical audio_manifest.json on disk
    manifest_disk_path = tmp_path / AUDIO_MANIFEST_FILE_NAME
    assert manifest_disk_path.exists()
    disk_data = json.loads(manifest_disk_path.read_text(encoding="utf-8"))
    assert disk_data["total_segments"] == 3
    assert disk_data["segments"][0]["id"] == "001"
    assert disk_data["segments"][1]["start_time"] == pytest.approx(3.550, abs=1e-3)

    # 6. Verify in-place enrichment of manifest["chapters"]
    c1 = manifest["chapters"][0]
    assert c1["id"] == "001"
    assert c1["duration"] == 3.250
    assert c1["visual_keyframe_id"] == "scene_001"
