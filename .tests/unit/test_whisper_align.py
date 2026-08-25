"""Unit tests: Whisper timestamp formatting & script-to-audio alignment engine."""

import pytest

from faster_whisper_transcribe_audio import (
    align_script_words_with_audio,
    format_srt_timestamp,
    format_timestamp,
    normalize_arabic_token,
)


class TestTimestampFormatting:
    def test_under_hour_mmss(self):
        assert format_timestamp(75) == "[01:15]"

    def test_over_hour_hhmmss(self):
        assert format_timestamp(3675) == "[01:01:15]"

    def test_zero(self):
        assert format_timestamp(0) == "[00:00]"

    def test_srt_millisecond_precision(self):
        assert format_srt_timestamp(1.9996) == "00:00:02,000"
        assert format_srt_timestamp(0) == "00:00:00,000"

    def test_srt_negative_clamped_to_zero(self):
        assert format_srt_timestamp(-3.2) == "00:00:00,000"


class TestNormalizeArabicToken:
    def test_diacritics_stripped(self):
        assert normalize_arabic_token("مُنَحَّر") == normalize_arabic_token("منحر")

    def test_alef_variants_folded(self):
        assert normalize_arabic_token("أحمد") == normalize_arabic_token("احمد")
        assert normalize_arabic_token("إلى") == normalize_arabic_token("الي")

    def test_taa_marbuta_folds_to_ha(self):
        assert normalize_arabic_token("مدرسة") == normalize_arabic_token("مدرسه")

    def test_punctuation_removed(self):
        assert normalize_arabic_token("«تمام،»") == "تمام"


class TestAlignScriptWordsWithAudio:
    def _whisper(self, *words):
        t = 0.5
        out = []
        for w in words:
            out.append({"word": w, "start": t, "end": t + 0.4})
            t += 0.45
        return out

    def test_empty_script_returns_empty(self):
        assert align_script_words_with_audio("", self._whisper("كلمة")) == []

    def test_no_whisper_words_zero_times(self):
        aligned = align_script_words_with_audio("كلمتين هنا", [])
        assert [a["start"] for a in aligned] == [0.0, 0.0]

    def test_exact_anchor_timings_applied(self):
        whisper = self._whisper("الأرض", "كوكب", "جميل")
        script = "والأرض كوكب جميل حقاً"
        aligned = align_script_words_with_audio(script, whisper)
        by_text = {a["text"]: a for a in aligned}
        # "الأرض" appears inside script token "والأرض" — no direct match; core
        # anchors are the exact tokens كوكب/جميل
        assert by_text["كوكب"]["start"] == whisper[1]["start"]
        assert by_text["جميل"]["end"] == whisper[2]["end"]

    def test_strict_monotonicity(self):
        whisper = self._whisper("واحد", "اثنين", "تلاتة", "أربعة", "خمسة")
        script = "واحد كلمة دخيلة اثنين تلاتة أربعة خمسة زيادة"
        aligned = align_script_words_with_audio(script, whisper)
        for prev, cur in zip(aligned, aligned[1:], strict=False):
            assert cur["start"] >= prev["start"]
            assert cur["end"] > cur["start"]

    def test_interpolated_gaps_stay_within_audio_bounds(self):
        whisper = self._whisper("البداية", "النهاية")
        script = "البداية و الكلام المُدرج بينهما كثير جداً النهاية"
        aligned = align_script_words_with_audio(script, whisper)
        audio_max = whisper[-1]["end"]
        trailing = [a for a in aligned if a["text"] != "النهاية"]
        assert max(a["end"] for a in trailing) <= audio_max + 1.05

    def test_leading_unaligned_words_before_first_anchor(self):
        # Anchor block must be >=2 tokens (production rule filters size<2 blocks).
        whisper = self._whisper("مقدمة", "ثانية")
        script = "كلمة تمهيدية مقدمة ثانية"
        aligned = align_script_words_with_audio(script, whisper)
        by_text = {a["text"]: a for a in aligned}
        assert by_text["مقدمة"]["start"] == pytest.approx(whisper[0]["start"])
        assert by_text["ثانية"]["start"] == pytest.approx(whisper[1]["start"])
        leading = [a for a in aligned if a["text"] == "كلمة" or a["text"] == "تمهيدية"]
        assert all(a["end"] <= whisper[0]["start"] + 1e-6 for a in leading)
