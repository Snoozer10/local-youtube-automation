"""Unit tests: lossless WAV chapter stitching invariants."""

import struct
import wave

import pytest

import stitch_chapters


def _make_wav(path, seconds=0.5, rate=48000, channels=1, sampwidth=2, fill=1200):
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{n}h", *([fill] * n)))
    return str(path)


@pytest.fixture
def chapters_dir(tmp_path):
    d = tmp_path / "voice_chapters"
    d.mkdir()
    return d


class TestFrameExactStitching:
    def test_total_frames_equal_sum_of_chapters(self, chapters_dir):
        specs = [(0.5, 48000), (0.25, 48000), (1.0, 48000)]
        for i, secs in enumerate(specs, 1):
            _make_wav(chapters_dir / f"Chapter_{i}.wav", seconds=secs[0])
        out = _make_wav(chapters_dir / "out.wav", seconds=0.1)

        total_frames = sum(int(s * 48000) for s, *_ in specs)
        stitch_chapters.stitch_files(
            [str(chapters_dir / f"Chapter_{i}.wav") for i in (1, 2, 3)], out
        )
        with wave.open(out, "rb") as wf:
            assert wf.getnframes() == total_frames
            assert wf.getframerate() == 48000 and wf.getsampwidth() == 2

    def test_params_preserved_from_first_chapter(self, chapters_dir):
        _make_wav(chapters_dir / "Chapter_1.wav", rate=44100, channels=2)
        _make_wav(chapters_dir / "Chapter_2.wav", rate=44100, channels=2)
        out = _make_wav(chapters_dir / "out.wav")
        stitch_chapters.stitch_files(
            [str(chapters_dir / "Chapter_1.wav"), str(chapters_dir / "Chapter_2.wav")], out
        )
        with wave.open(out, "rb") as wf:
            assert wf.getframerate() == 44100
            assert wf.getnchannels() == 2

    def test_sample_rate_mismatch_is_rejected(self, chapters_dir):
        """Repro: blind frame concat of mixed rates produced chipmunk audio."""
        _make_wav(chapters_dir / "Chapter_1.wav", rate=48000)
        _make_wav(chapters_dir / "Chapter_2.wav", rate=44100)
        out = _make_wav(chapters_dir / "out.wav")
        with pytest.raises(ValueError):
            stitch_chapters.stitch_files(
                [str(chapters_dir / "Chapter_1.wav"), str(chapters_dir / "Chapter_2.wav")], out
            )

    def test_channel_mismatch_is_rejected(self, chapters_dir):
        _make_wav(chapters_dir / "Chapter_1.wav", channels=1)
        _make_wav(chapters_dir / "Chapter_2.wav", channels=2)
        out = _make_wav(chapters_dir / "out.wav")
        with pytest.raises(ValueError):
            stitch_chapters.stitch_files(
                [str(chapters_dir / "Chapter_1.wav"), str(chapters_dir / "Chapter_2.wav")], out
            )

    def test_sample_width_mismatch_is_rejected(self, chapters_dir):
        _make_wav(chapters_dir / "Chapter_1.wav", sampwidth=2)
        _make_wav(chapters_dir / "Chapter_2.wav", sampwidth=1)
        out = _make_wav(chapters_dir / "out.wav")
        with pytest.raises(ValueError):
            stitch_chapters.stitch_files(
                [str(chapters_dir / "Chapter_1.wav"), str(chapters_dir / "Chapter_2.wav")], out
            )


class TestSequentialDetection:
    def test_gap_in_sequence_reported_not_silent(self, chapters_dir):
        """Repro: Chapter_3 missing silently dropped chapter 4 content."""
        _make_wav(chapters_dir / "Chapter_1.wav")
        _make_wav(chapters_dir / "Chapter_2.wav")
        _make_wav(chapters_dir / "Chapter_4.wav")
        found, missing = stitch_chapters.scan_sequential_chapters(str(chapters_dir))
        assert found == [
            str(chapters_dir / "Chapter_1.wav"),
            str(chapters_dir / "Chapter_2.wav"),
        ]
        assert missing == ["Chapter_3.wav"]

