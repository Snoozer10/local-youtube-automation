"""Unit tests: Tashkeel lexicon engine, paragraph cleaner, cadence validators.

Exercises refine_script pure text pipeline against daheeh_config.json.
"""

import json
import os

import pytest

import refine_script


class TestSplitParagraphs:
    def test_crlf_normalization(self):
        assert refine_script.split_paragraphs("أول\r\n\r\nثاني") == ["أول", "ثاني"]

    def test_single_newline_fallback(self):
        assert refine_script.split_paragraphs("سطر أول\nسطر ثاني") == ["سطر أول", "سطر ثاني"]

    def test_blank_only_returns_empty(self):
        assert refine_script.split_paragraphs("   \n\n  ") == []


class TestSafePath:
    def test_traversal_collapsed_to_basename(self):
        resolved = refine_script._safe_path("../../etc", "refined_script.txt")
        parts = os.path.normpath(resolved).split(os.sep)
        assert "etc" in parts and ".." not in parts

    def test_absolute_path_collapsed(self):
        resolved = refine_script._safe_path("C:\\windows\\system32", "x.txt")
        assert "youtube_runs" in resolved and "system32" in resolved


class TestCheckpointRoundtrip:
    def _write_and_load(self, tmp_path, turns):
        folder = str(tmp_path)
        refine_script.save_checkpoint(folder, turns)
        return refine_script.load_checkpoint(folder)

    def test_roundtrip_preserves_turn_fields(self, tmp_path):
        turns = [
            refine_script.RefinedTurn(1, "orig", "مُنقّح", 1, 2.5, False),
            refine_script.RefinedTurn(2, "orig2", "تاني", 1, 0.0, True),
        ]
        loaded = self._write_and_load(tmp_path, turns)
        assert [t.refined_text for t in loaded] == ["مُنقّح", "تاني"]
        assert [t.is_outro for t in loaded] == [False, True]
        assert loaded[0].rhythm_variance == pytest.approx(2.5)

    def test_legacy_string_list_format_loads(self, tmp_path):
        folder = str(tmp_path)
        path = refine_script._safe_path(folder, "refine_checkpoint.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"refined_paragraphs": ["قديم أولاً", "قديم ثانياً"]}, f, ensure_ascii=False)
        loaded = refine_script.load_checkpoint(folder)
        assert [t.refined_text for t in loaded] == ["قديم أولاً", "قديم ثانياً"]

    def test_corrupt_json_returns_empty(self, tmp_path):
        folder = str(tmp_path)
        path = refine_script._safe_path(folder, "refine_checkpoint.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        path_enc = path if isinstance(path, str) else str(path)
        with open(path_enc, "w", encoding="utf-8") as f:
            f.write('{"refined_paragraphs": [TRUNCATED')
        assert refine_script.load_checkpoint(folder) == []

    def test_missing_file_returns_empty(self, tmp_path):
        assert refine_script.load_checkpoint(str(tmp_path)) == []

    def test_delete_removes_only_checkpoint(self, tmp_path):
        folder = str(tmp_path)
        refine_script.save_checkpoint(folder, [])
        refine_script.delete_checkpoint(folder)
        assert not os.path.exists(refine_script._safe_path(folder, "refine_checkpoint.json"))


class TestTashkeelEngine:
    def test_lexicon_word_vocalized(self, repo_cwd, fresh_tashkeel_engine):
        with open("daheeh_config.json", encoding="utf-8") as f:
            lex = (
                json.load(f)["al_daheeh_master_pipeline_config"]["dialect_profile"][
                    "tashkeel_lexicon"
                ]
            )
        assert lex, "daheeh_config.json must define a non-empty tashkeel_lexicon"
        word = sorted(lex.keys(), key=len)[-1]
        engine = fresh_tashkeel_engine()
        out = engine.transform(f"ده {word} مهم")
        assert lex[word] in out or word in lex.values()

    def test_prefixed_form_keeps_prefix(self, repo_cwd, fresh_tashkeel_engine):
        with open("daheeh_config.json", encoding="utf-8") as f:
            lex = json.load(f)["al_daheeh_master_pipeline_config"]["dialect_profile"][
                "tashkeel_lexicon"
            ]
        base = next((k for k in lex if not k.startswith(("و", "ف", "ب", "ك", "ل"))), None)
        if base is None:
            pytest.skip("no unprefixed lexicon key available")
        engine = fresh_tashkeel_engine()
        for prefix in ("و", "بال"):
            out = engine.transform(f"{prefix}{base} كمان")
            assert prefix in out
            assert lex[base] in out

    def test_homograph_meen_before_illi(self, fresh_tashkeel_engine):
        engine = fresh_tashkeel_engine()
        assert "مِين اللي" in engine.transform("مين اللي جاي")

    def test_homograph_min_ghayr(self, fresh_tashkeel_engine):
        engine = fresh_tashkeel_engine()
        out = engine.transform("من غير فلوس")
        assert "مِن غِير" in out

    def test_ya_ali_vocalized(self, fresh_tashkeel_engine):
        engine = fresh_tashkeel_engine()
        assert "يا عَلِي" in engine.transform("يا علي تعال")

    def test_empty_text_identity(self, fresh_tashkeel_engine):
        assert fresh_tashkeel_engine().transform("") == ""

    def test_longest_key_wins_over_substring(self, repo_cwd, fresh_tashkeel_engine):
        with open("daheeh_config.json", encoding="utf-8") as f:
            lex = json.load(f)["al_daheeh_master_pipeline_config"]["dialect_profile"][
                "tashkeel_lexicon"
            ]
        keys = sorted(lex.keys(), key=len, reverse=True)
        longest, shortest = keys[0], keys[-1]
        if len(longest) <= len(shortest) or shortest not in longest:
            pytest.skip("lexicon lacks substring nesting to prove precedence")
        engine = fresh_tashkeel_engine()
        out = engine.transform(longest)
        assert lex[longest] in out


class TestCleanRefinedParagraph:
    def test_final_script_tag_extraction(self, monkeypatch):
        monkeypatch.setattr(refine_script, "apply_tashkeel_from_config", lambda t: t)
        raw = "<thinking>خطة داخلية</thinking><final_script>النص النهائي الصافي</final_script>"
        assert refine_script.clean_refined_paragraph(raw) == "النص النهائي الصافي"

    def test_unclosed_thinking_block_is_purged(self, monkeypatch):
        """Repro: truncated model output leaves an orphan <thinking> open tag."""
        monkeypatch.setattr(refine_script, "apply_tashkeel_from_config", lambda t: t)
        raw = "<thinking>خطط طويلة انقطعت فجأة بدون قفلة\nالنص المطلوب يظهر هنا"
        cleaned = refine_script.clean_refined_paragraph(raw)
        assert "خطط طويلة" not in cleaned
        assert "النص المطلوب يظهر هنا" in cleaned

    def test_unclosed_slang_ledger_is_purged(self, monkeypatch):
        monkeypatch.setattr(refine_script, "apply_tashkeel_from_config", lambda t: t)
        raw = "<slang_ledger>\nكرافت\nالنص العربي الصافي"
        cleaned = refine_script.clean_refined_paragraph(raw)
        assert "SLANG" not in cleaned and "ledger" not in cleaned.lower()

    def test_latin_heavy_line_dropped(self, monkeypatch):
        monkeypatch.setattr(refine_script, "apply_tashkeel_from_config", lambda t: t)
        raw = "CADENCE_CHECK: beat one two three\nالنص العربي سليم تماماً"
        cleaned = refine_script.clean_refined_paragraph(raw)
        assert "CADENCE_CHECK" not in cleaned

    def test_loanword_transliteration(self, monkeypatch, repo_cwd, fresh_tashkeel_engine):
        raw = "<final_script>قيمة Pi مهمة جداً في الرياضيات الحقيقية هنا</final_script>"
        cleaned = refine_script.clean_refined_paragraph(raw)
        assert "Pi" not in cleaned
        assert "باي" in cleaned

    def test_duplicate_interjection_keeps_last(self, monkeypatch):
        monkeypatch.setattr(refine_script, "apply_tashkeel_from_config", lambda t: t)
        interjection = "ثانية واحدة يا أبو حميد!"
        raw = f"<final_script>{interjection} مقدمة، {interjection} الخاتمة بقى</final_script>"
        cleaned = refine_script.clean_refined_paragraph(raw)
        assert cleaned.count("ثانية واحدة يا أبو حميد") == 1


class TestTtsAcousticText:
    def test_ellipsis_becomes_arabic_pause(self):
        assert refine_script.prepare_tts_acoustic_text("انتظر... بعدين") == "انتظر ، بعدين"

    def test_stacked_punctuation_collapsed(self):
        out = refine_script.prepare_tts_acoustic_text("مستحيل!؟!")
        assert out.count("؟") == 1 and "!" not in out

    def test_em_dash_micro_pause(self):
        assert refine_script.prepare_tts_acoustic_text("واحد—اثنين") == "واحد ، اثنين"

    def test_spacing_normalized(self):
        out = refine_script.prepare_tts_acoustic_text("كلام , وفراغات :  زايدة")
        assert "  " not in out


class TestValidateRefinementQuality:
    def test_short_text_rejected(self):
        ok, _ = refine_script.validate_refinement_quality("قصير")
        assert ok is False

    def test_banned_fusha_connector_rejected(self):
        long_text = "كلام " * 20 + "علاوة على ذلك"
        ok, reason = refine_script.validate_refinement_quality(long_text)
        assert ok is False and "Fusha" in reason

    def test_raw_multi_digit_number_rejected(self):
        text = " ".join(["كلمة"] * 12) + " السنة 2024 كانت مليانة أحداث كتيرة ومتنوعة جداً"
        ok, reason = refine_script.validate_refinement_quality(text)
        assert ok is False and "digits" in reason

    def test_monolithic_structure_rejected(self):
        text = " ".join([f"كلمة{i}" for i in range(35)])
        ok, reason = refine_script.validate_refinement_quality(text)
        assert ok is False

    def test_outro_exempt_from_pause_marker_check(self):
        text = " ".join(["وداعاً يا أصدقاء"] * 12)
        ok, _ = refine_script.validate_refinement_quality(text, is_outro=True)
        assert ok is True


class TestRhythmVariance:
    def test_fewer_than_three_units_zero(self):
        assert refine_script.calculate_rhythm_variance("جملة واحدة قصيرة") == 0.0

    def test_flat_cadence_low_variance(self):
        flat = "، ".join([" ".join(["كلمة"] * 4)] * 4)
        assert refine_script.calculate_rhythm_variance(flat) < 1.0

    def test_varied_cadence_higher_variance(self):
        varied = ". ".join(
            ["كلمة", "جملة فيها تلات كلمات", "دلوقتي جملة أطول شوية فيها خمس كلمات تقريباً"]
        )
        assert refine_script.calculate_rhythm_variance(varied) > 0.0


class TestIsSafetyBlocked:
    @pytest.mark.parametrize(
        "kw",
        ["unable to assist", "safety guidelines", "as an ai language model"],
    )
    def test_refusal_keywords_detected(self, kw):
        assert refine_script.is_safety_blocked(f"I am sorry, {kw} for this request.")

    def test_short_response_treated_as_blocked(self):
        assert refine_script.is_safety_blocked("تمام")

    def test_clean_arabic_passes(self):
        text = "ده نص عربي سليم وطبيعي وطويل بما يكفي لعدم اعتباره رفض من النموذج"
        assert refine_script.is_safety_blocked(text) is False
