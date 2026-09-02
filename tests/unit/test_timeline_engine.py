"""Unit tests for timeline_engine: canonical timeline.json, span derivation, shims, sidecars, and deprecation."""

import hashlib
import json
import os
import shutil
import tempfile
import warnings

import pytest

from timeline_engine import (
    TIMELINE_FILENAME,
    build_timeline,
    build_words_from_whisper,
    derive_spans_from_words,
    load_timeline_or_shim,
    resolve_vad_snap_threshold,
    save_timeline_and_shims,
    verify_shim,
)


@pytest.fixture
def sample_whisper_words():
    """Sample word list representing speech with pauses."""
    return [
        {"word": "يا", "start": 0.05, "end": 0.30},
        {"word": "عم،", "start": 0.30, "end": 0.60},
        {"word": "بتهلوس؟", "start": 0.65, "end": 1.20},
        # Pause: 1.20 -> 1.70 (0.50s >= 0.35s VAD threshold)
        {"word": "الجاس", "start": 1.70, "end": 2.10},
        {"word": "لايتنج", "start": 2.10, "end": 2.60},
        {"word": "ده", "start": 2.60, "end": 2.80},
        {"word": "بجد،", "start": 2.80, "end": 3.40},
        # Pause: 3.40 -> 3.90 (0.50s >= 0.35s)
        {"word": "والمريونيط", "start": 3.90, "end": 4.60},
        {"word": "بيتحرك،", "start": 4.60, "end": 5.20},
        # Pause: 5.20 -> 5.60 (0.40s >= 0.35s)
        {"word": "والرموت", "start": 5.60, "end": 6.10},
        {"word": "كونترول", "start": 6.10, "end": 6.70},
        {"word": "تاه.", "start": 6.70, "end": 7.30},
        # Pause: 7.30 -> 7.80 (0.50s >= 0.35s)
        {"word": "سدقني،", "start": 7.80, "end": 8.40},
        {"word": "بلاش", "start": 8.40, "end": 8.80},
        {"word": "تلعب", "start": 8.80, "end": 9.20},
        {"word": "بالنار.", "start": 9.20, "end": 10.00},
    ]


class TestWordIngestion:
    def test_words_are_monotonic_and_indexed(self, sample_whisper_words):
        words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
        assert len(words) == len(sample_whisper_words)
        for idx, w in enumerate(words):
            assert w["id"] == idx
            assert w["start"] < w["end"]
            if idx > 0:
                assert w["start"] >= words[idx - 1]["end"] - 1e-4

    def test_pause_after_calculated_accurately(self, sample_whisper_words):
        words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
        assert words[2]["pause_after"] == pytest.approx(0.50, abs=0.01)
        assert words[6]["pause_after"] == pytest.approx(0.50, abs=0.01)
        assert words[-1]["pause_after"] == 0.0


class TestSpanDerivation:
    def test_span_invariants(self, sample_whisper_words):
        words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
        spans = derive_spans_from_words(words, audio_duration=10.0, fps=30)

        assert len(spans) > 0
        total_budget = round(10.0 * 30)

        # Invariant 1: First span start_frame == 0
        assert spans[0]["start_frame"] == 0

        # Invariant 2: Contiguous frames with no gaps
        for i in range(1, len(spans)):
            assert spans[i]["start_frame"] == spans[i - 1]["end_frame"]
            assert spans[i]["frame_count"] == spans[i]["end_frame"] - spans[i]["start_frame"]
            assert spans[i]["frame_count"] >= 1

        # Invariant 3: Total frame count equals audio duration * fps
        assert sum(s["frame_count"] for s in spans) == total_budget
        assert spans[-1]["end_frame"] == total_budget

        # Invariant 4: spans[i].start == words[start_word_id].start
        for s in spans:
            w_start = words[s["start_word_id"]]
            assert s["start"] == w_start["start"]
            w_end = words[s["end_word_id"]]
            assert s["end"] == w_end["end"]

    def test_span_durations_bounded_within_target_range(self, sample_whisper_words):
        words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
        spans = derive_spans_from_words(
            words, audio_duration=10.0, fps=30, min_span_sec=2.5, max_span_sec=4.5
        )

        for s in spans:
            # All spans respect hard cap <= 4.5s
            assert s["duration"] <= 4.55
            # Spans are >= 2.5s except possibly boundary/tail cases that cannot be merged
            if s["duration"] < 2.5:
                # If duration < 2.5s, it must be guarded by a breath (pause >= 0.35s) or be a single remaining chunk
                assert s["pause_after"] >= 0.35 or s == spans[-1]

    def test_nearest_snap_prefers_closest_pause(self):
        # Construct words where candidate cut at 3.0s has pauses at 2.8s (0.2s away) and 3.5s (0.5s away)
        words_data = [
            {"word": "واحد", "start": 0.0, "end": 1.0},
            {"word": "اثنين", "start": 1.0, "end": 2.4},
            # Pause at 2.4 -> 2.8 (0.4s >= 0.35s)
            {"word": "ثلاثة", "start": 2.8, "end": 3.4},
            {"word": "اربعة", "start": 3.4, "end": 4.0},
            # Pause at 4.0 -> 4.5 (0.5s >= 0.35s)
            {"word": "خمسة", "start": 4.5, "end": 6.0},
        ]
        words = build_words_from_whisper(words_data, audio_duration=6.0)
        spans = derive_spans_from_words(words, audio_duration=6.0, fps=30)
        assert len(spans) >= 2
        # Nearest snap snaps to 2.4 (end of word 'اثنين')
        assert spans[0]["end_word_id"] == 1
        assert spans[0]["end"] == 2.4

    def test_long_sentence_split_at_cadence(self):
        # 6-second sentence with internal comma cadence
        words_data = [
            {"word": f"كلمة_{i}،" if i == 6 else f"كلمة_{i}", "start": i * 0.5, "end": (i + 1) * 0.5}
            for i in range(12)
        ]
        words = build_words_from_whisper(words_data, audio_duration=6.0)
        spans = derive_spans_from_words(words, audio_duration=6.0, fps=30, max_span_sec=4.5)
        # Should be split because 6.0s > 4.5s
        assert len(spans) >= 2
        for s in spans:
            assert s["duration"] <= 4.55


class TestTimelineSchemaAndChecksums:
    def test_timeline_structure_and_checksums(self, sample_whisper_words):
        words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
        timeline = build_timeline(words, audio_duration=10.0, audio_file="test_voice.wav", fps=30)

        assert timeline["version"] == "1.0.0"
        assert timeline["audio_file"] == "test_voice.wav"
        assert timeline["audio_duration"] == 10.0
        assert timeline["fps"] == 30
        assert timeline["total_frames"] == 300
        assert "words" in timeline
        assert "spans" in timeline
        assert "checksums" in timeline
        assert "words_sha256" in timeline["checksums"]
        assert "spans_sha256" in timeline["checksums"]
        assert len(timeline["checksums"]["words_sha256"]) == 64


class TestShimsAndSidecars:
    def test_atomic_save_and_sidecars(self, sample_whisper_words):
        d = tempfile.mkdtemp()
        try:
            words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
            timeline = build_timeline(words, audio_duration=10.0, audio_file="voice.wav", fps=30)

            t_path, shims = save_timeline_and_shims(timeline, d, export_srt=True)
            assert os.path.exists(t_path)
            assert os.path.exists(os.path.join(d, "image_timestamps.txt"))
            assert os.path.exists(os.path.join(d, "image_timestamps.txt.sha256"))
            assert os.path.exists(os.path.join(d, "timestamped_transcript.txt"))
            assert os.path.exists(os.path.join(d, "timestamped_transcript.txt.sha256"))

            # Check image_timestamps.txt [MM:SS] format
            with open(os.path.join(d, "image_timestamps.txt"), encoding="utf-8") as f:
                content = f.read()
                assert "[00:00]" in content

            # Verify sidecar hash matches timeline.json
            with open(t_path, "rb") as f:
                t_sha = hashlib.sha256(f.read()).hexdigest()

            with open(os.path.join(d, "image_timestamps.txt.sha256"), encoding="utf-8") as f:
                sidecar_sha = f.read().strip()
                assert sidecar_sha == t_sha

            # verify_shim returns True on valid match
            assert verify_shim(os.path.join(d, "image_timestamps.txt"), t_path) is True
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_stale_shim_rejected(self, sample_whisper_words):
        d = tempfile.mkdtemp()
        try:
            words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
            timeline = build_timeline(words, audio_duration=10.0, audio_file="voice.wav", fps=30)
            t_path, _ = save_timeline_and_shims(timeline, d)

            # Mutate timeline.json to make shim stale
            with open(t_path, "w", encoding="utf-8") as f:
                f.write(json.dumps({"mutated": True}))

            # verify_shim should detect hash mismatch and return False
            assert verify_shim(os.path.join(d, "image_timestamps.txt"), t_path) is False
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_load_timeline_or_shim(self, sample_whisper_words):
        d = tempfile.mkdtemp()
        try:
            words = build_words_from_whisper(sample_whisper_words, audio_duration=10.0)
            timeline = build_timeline(words, audio_duration=10.0, audio_file="voice.wav", fps=30)
            save_timeline_and_shims(timeline, d)

            # 1. Load from timeline.json
            blocks = load_timeline_or_shim(d)
            assert len(blocks) == len(timeline["spans"])
            assert blocks[0]["sec"] == 0.0
            assert "name" in blocks[0]

            # 2. If timeline.json deleted, fallback to valid shim
            os.unlink(os.path.join(d, TIMELINE_FILENAME))
            blocks_shim = load_timeline_or_shim(d)
            assert len(blocks_shim) > 0
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestDeprecatedKeyMigration:
    def test_deprecated_alias_triggers_warning_and_sets_threshold(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            val = resolve_vad_snap_threshold({"IMAGE_PAUSE_SPLIT": 0.42})
            assert val == 0.42
            assert any(issubclass(item.category, DeprecationWarning) for item in w)

    def test_canonical_key_takes_precedence_over_deprecated(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            val = resolve_vad_snap_threshold(
                {"VAD_SNAP_THRESHOLD": 0.38, "SILENCE_SPLIT_GAP": 0.50}
            )
            assert val == 0.38
            # Warning still fires for deprecated presence
            assert any(issubclass(item.category, DeprecationWarning) for item in w)

    def test_default_threshold_when_no_keys_present(self):
        val = resolve_vad_snap_threshold({})
        assert val == 0.35
