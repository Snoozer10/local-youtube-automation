"""Unit tests for DialectTashkeelEngine and automate_all.apply_tashkeel_from_config."""

import json
from pathlib import Path

import pytest

import automate_all
from refine_script import DialectTashkeelEngine


def load_lexicon() -> dict:
    with open("daheeh_config.json", encoding="utf-8") as f:
        config = json.load(f)
    lexicon = config["al_daheeh_master_pipeline_config"]["dialect_profile"]["tashkeel_lexicon"]
    assert lexicon, "daheeh_config.json must define a non-empty tashkeel_lexicon"
    return lexicon


LEXICON = load_lexicon()


@pytest.fixture(autouse=True)
def reset_tashkeel_singleton():
    DialectTashkeelEngine._instance = None
    yield
    DialectTashkeelEngine._instance = None


@pytest.fixture
def engine_with_lexicon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _make(lexicon: dict) -> DialectTashkeelEngine:
        cfg = {
            "al_daheeh_master_pipeline_config": {"dialect_profile": {"tashkeel_lexicon": lexicon}}
        }
        (tmp_path / "daheeh_config.json").write_text(
            json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        return DialectTashkeelEngine.get_instance()

    return _make


class TestLexiconCoverage:
    @pytest.mark.parametrize("plain,vocalized", sorted(LEXICON.items()))
    def test_every_entry_transforms_bare_form_in_one_pass(self, plain, vocalized):
        engine = DialectTashkeelEngine.get_instance()
        result = engine.transform(f"start {plain} end")
        assert vocalized in result
        assert f" {plain} " not in result

    @pytest.mark.parametrize("plain", sorted(LEXICON))
    def test_bare_word_inside_longer_token_is_untouched(self, plain):
        engine = DialectTashkeelEngine.get_instance()
        glued = f"x{plain}y"
        assert engine.transform(glued) == glued

    def test_longer_key_is_not_consumed_by_shorter_overlapping_key(self, engine_with_lexicon):
        engine = engine_with_lexicon({"di": "<short-di>", "dish": "<long-dish>"})
        assert engine.transform("dish") == "<long-dish>"

    def test_sentence_receives_all_lexicon_entries(self):
        engine = DialectTashkeelEngine.get_instance()
        text = "keda dah di hoba qest"
        result = engine.transform(text)
        for vocalized in (
            LEXICON["keda"],
            LEXICON["dah"],
            LEXICON["di"],
            LEXICON["hoba"],
            LEXICON["qest"],
        ):
            assert vocalized in result


class TestPrefixAwareSubstitution:
    @pytest.mark.parametrize(
        "prefix",
        ["و", "ف", "ب", "ك", "ل", "وال", "بال", "لل"],
    )
    def test_arabic_prefix_preserved_before_vocalized_stem(self, prefix):
        engine = DialectTashkeelEngine.get_instance()
        result = engine.transform(f"{prefix}keda hoba")
        assert result.startswith(f"{prefix}{LEXICON['keda']} ")
        assert "hoba" not in result

    def test_prefixed_word_mid_sentence_still_vocalizes(self):
        engine = DialectTashkeelEngine.get_instance()
        result = engine.transform("قول لي بkeda تاني")
        assert f"ب{LEXICON['keda']}" in result

    def test_prefix_without_boundary_to_foreign_word_left_alone(self):
        engine = DialectTashkeelEngine.get_instance()
        assert engine.transform("وxyz") == "وxyz"


class TestSinglePassGuarantee:
    def test_applying_twice_equals_applying_once(self):
        engine = DialectTashkeelEngine.get_instance()
        text = "keda dah di hoba meallem baseeha dashmel khazooq sahla biyool"
        once = engine.transform(text)
        twice = engine.transform(once)
        assert twice == once

    def test_homograph_rules_are_idempotent(self):
        engine = DialectTashkeelEngine.get_instance()
        text = "مين اللي من غير كده"
        once = engine.transform(text)
        assert engine.transform(once) == once

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("مين اللي هنا؟", "مِين"),
            ("من غير كده", "مِن غِير"),
        ],
    )
    def test_contextual_homograph_disambiguation_applies(self, text, expected):
        engine = DialectTashkeelEngine.get_instance()
        assert expected in engine.transform(text)


class TestPassthroughAndDegradation:
    def test_text_without_lexicon_words_passes_through_unchanged(self):
        engine = DialectTashkeelEngine.get_instance()
        text = "Hello world 123 !@# untouched english sentence"
        assert engine.transform(text) == text

    def test_empty_string_returns_empty_string(self):
        engine = DialectTashkeelEngine.get_instance()
        assert engine.transform("") == ""

    def test_missing_config_file_disables_lexicon_but_keeps_engine_alive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        engine = DialectTashkeelEngine.get_instance()
        assert engine.transform("keda dah") == "keda dah"

    def test_corrupt_config_json_degrades_gracefully_without_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (tmp_path / "daheeh_config.json").write_text("{not valid json!!", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        engine = DialectTashkeelEngine.get_instance()
        assert engine.transform("keda") == "keda"

    def test_empty_lexicon_config_disables_substitution(self, engine_with_lexicon):
        engine = engine_with_lexicon({})
        assert engine.transform("keda dah") == "keda dah"


class TestAutomateAllApplyTashkeel:
    def test_real_config_vocalizes_lexicon_entries(self):
        for plain, vocalized in sorted(LEXICON.items()):
            result = automate_all.apply_tashkeel_from_config(f"say {plain} now")
            assert vocalized in result

    def test_idempotent_second_application(self):
        text = "keda dah di"
        once = automate_all.apply_tashkeel_from_config(text)
        assert automate_all.apply_tashkeel_from_config(once) == once

    def test_missing_config_returns_text_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        text = "untouched text keda"
        assert automate_all.apply_tashkeel_from_config(text) == text

    def test_corrupt_config_swallows_error_and_returns_input(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        (tmp_path / "daheeh_config.json").write_text("[[[", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        text = "still intact"
        assert automate_all.apply_tashkeel_from_config(text) == text
