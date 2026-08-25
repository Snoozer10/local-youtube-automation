"""Unit tests: zero-drift integer frame timeline allocation & acoustic snapping.

Covers compile_video.prepare_synchronized_timeline and AudioSyncAligner.
"""

import math
import wave

import pytest

import compile_video

FPS = 30


def _blocks(secs):
    return [{"name": f"{int(s):02d}_{int(round((s % 1) * 100)):02d}", "sec": s} for s in secs]


class TestZeroDriftTimeline:
    def test_contiguous_integer_frames_cover_audio_exactly(self):
        blocks = _blocks([0.0, 3.3, 7.7])
        tl = compile_video.prepare_synchronized_timeline(blocks, 10.0, FPS)
        assert len(tl) == 3
        total_frames = int(round(10.0 * FPS))
        assert tl[0]["start_frame"] == 0
        assert tl[-1]["end_frame"] == total_frames
        assert sum(b["frame_count"] for b in tl) == total_frames
        for prev, nxt in zip(tl, tl[1:], strict=False):
            assert nxt["start_frame"] == prev["end_frame"]
            assert all(isinstance(f, int) for f in (nxt["start_frame"], nxt["end_frame"]))
            assert nxt["start_frame"] > prev["start_frame"]

    def test_duration_matches_frame_count(self):
        blocks = _blocks([0.0, 2.5, 5.0, 8.0])
        tl = compile_video.prepare_synchronized_timeline(blocks, 9.0, FPS)
        for b in tl:
            assert b["duration"] == pytest.approx(b["frame_count"] / FPS)
            assert b["end_sec"] - b["sec"] == pytest.approx(b["duration"])

    def test_first_block_anchored_to_zero(self):
        blocks = _blocks([1.25, 4.0])
        tl = compile_video.prepare_synchronized_timeline(blocks, 6.0, FPS)
        assert tl[0]["start_frame"] == 0

    def test_grouped_simultaneous_blocks_split_with_weights(self):
        blocks = _blocks([0.0, 0.05, 5.0])
        tl = compile_video.prepare_synchronized_timeline(blocks, 10.0, FPS)
        assert len(tl) == 3
        first_pair = tl[:2]
        ratio = first_pair[0]["frame_count"] / (
            first_pair[0]["frame_count"] + first_pair[1]["frame_count"]
        )
        assert 0.60 <= ratio <= 0.80  # ~70/30 comedic weighting
        assert [b["occurrence"] for b in tl] == [1, 2, 1]

    def test_single_block_covers_all_frames(self):
        blocks = _blocks([0.0])
        tl = compile_video.prepare_synchronized_timeline(blocks, 4.0, FPS)
        assert len(tl) == 1
        assert tl[0]["frame_count"] == int(round(4.0 * FPS))

    def test_more_clips_than_frames_never_overflows_budget(self):
        """Repro: degenerate input (clips > frames) must not push end_frame past budget."""
        secs = [i * 0.001 for i in range(12)]
        blocks = _blocks(secs)
        tl = compile_video.prepare_synchronized_timeline(blocks, 0.03, FPS)  # 1 frame @30fps
        budget = int(round(0.03 * FPS))
        end_frames = [b["end_frame"] for b in tl]
        assert max(end_frames) <= budget, f"overflow: {max(end_frames)} > {budget}"
        starts = [b["start_frame"] for b in tl]
        assert starts == sorted(starts)


class TestAudioSyncAligner:
    @pytest.fixture
    def wav_with_pause(self, tmp_path):
        """1s leading silence, 0.5s tone, 0.4s silence dip at ~1.5s, tone to 2.5s."""
        path = str(tmp_path / "probe.wav")
        rate = 48000
        frames = []
        import struct

        def tone(n, amp=8000):
            return [
                int(amp * math.sin(2 * math.pi * 220 * (i / rate))) for i in range(n)
            ]

        silence = [0] * rate
        seg1 = tone(rate // 2)
        gap = [0] * int(0.4 * rate)
        seg2 = tone(int(0.6 * rate))
        frames = silence + seg1 + gap + seg2
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(struct.pack(f"<{len(frames)}h", *frames))
        return path

    def test_energy_profile_built_and_leading_silence_detected(self, wav_with_pause):
        aligner = compile_video.AudioSyncAligner(wav_with_pause)
        assert aligner.energy_profile
        # Fixture has exactly ~1.0s of leading silence before speech onset.
        assert aligner.leading_silence_sec == pytest.approx(1.0, abs=0.06)

    def test_snap_stays_within_search_radius(self, wav_with_pause):
        aligner = compile_video.AudioSyncAligner(wav_with_pause)
        snapped = aligner.snap_to_nearest_silence(1.55, search_radius_sec=0.20)
        assert abs(snapped - 1.55) <= 0.20

    def test_snap_without_profile_returns_target(self, tmp_path):
        empty = str(tmp_path / "none.wav")
        aligner = compile_video.AudioSyncAligner(empty)
        assert aligner.energy_profile == []
        assert aligner.snap_to_nearest_silence(2.0) == 2.0

    def test_non_wav_input_is_ignored(self, tmp_path):
        mp3 = tmp_path / "audio.mp3"
        mp3.write_bytes(b"ID3")
        aligner = compile_video.AudioSyncAligner(str(mp3))
        assert aligner.energy_profile == []

