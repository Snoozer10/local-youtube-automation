
import pytest

from youtube_automation.prompts import loader


@pytest.fixture
def sample_env(tmp_path, monkeypatch):
    p_dir = tmp_path / "prompts"
    f_dir = p_dir / "fragments"
    t_dir = p_dir / "turns"
    p_dir.mkdir()
    f_dir.mkdir()
    t_dir.mkdir()

    cfg_file = tmp_path / "daheeh_config.json"
    cfg_file.write_text('{"al_daheeh_master_pipeline_config": {"dialect_profile": {"fusha_academic_ratio": 0.3, "cairo_amiya_ratio": 0.7, "tashkeel_lexicon": {"k": "كِدَه"}}}}', encoding="utf-8")

    (p_dir / "demo.txt").write_text(
        "<<<PROMPT_META_START>>>\n"
        "name: demo\nversion: 2.0.0\nrole: test\n"
        "ack_tokens: مستعد|جاهز\nxml_tags: final_script\n"
        "calibration: Reply مستعد\noutput_schema: test_schema\n"
        "<<<PROMPT_META_END>>>\n"
        "Channel: {persona} | Dialect: {config:ratios} | Frag: {fragment:f1} | Var: {user_val}",
        encoding="utf-8"
    )
    (f_dir / "f1.txt").write_text("Hello Fragment", encoding="utf-8")
    (f_dir / "slang_categories.txt").write_text(
        "- Category A (The Pacing Boosters): (هوبا، قوم إيه).\n"
        "- Category B (The Parasocial Address): (يا سيدي، يا دكتور).",
        encoding="utf-8"
    )
    (t_dir / "demo_turn.txt").write_text("Turn {index}: {content}", encoding="utf-8")

    monkeypatch.setattr(loader, "PROMPTS_DIR", p_dir)
    monkeypatch.setattr(loader, "FRAGMENTS_DIR", f_dir)
    monkeypatch.setattr(loader, "TURNS_DIR", t_dir)
    monkeypatch.setattr(loader, "CONFIG_PATH", cfg_file)
    return tmp_path


def test_load_parses_and_strips_meta(sample_env):
    pr = loader.load("demo")
    assert pr.name == "demo"
    assert pr.version == "2.0.0"
    assert pr.ack_tokens == ["مستعد", "جاهز"]
    assert "PROMPT_META" not in pr.body


def test_render_with_default_legacy_config(sample_env):
    rendered = loader.render("demo", user_val="Value123", persona="Default Host")
    assert "30% Academic Fusha : 70% Cairene Amiya" in rendered
    assert "Hello Fragment" in rendered
    assert "Value123" in rendered


def test_render_with_dynamic_channel_override(sample_env):
    channel_override = {
        "name": "Science Channel",
        "dialect_profile": {
            "fusha_academic_ratio": 0.8,
            "cairo_amiya_ratio": 0.2,
            "tashkeel_lexicon": {"gravity": "جَاذِبِيَّة"}
        }
    }
    rendered = loader.render("demo", channel=channel_override, user_val="Sci", persona="Dr. Tech")
    assert "80% Academic Fusha : 20% Cairene Amiya" in rendered
    assert "Dr. Tech" in rendered


def test_slang_terms_excludes_titles_and_strips_whitespace(sample_env):
    terms = loader.slang_terms()
    assert "The Pacing Boosters" not in terms
    assert "The Parasocial Address" not in terms
    assert "قوم إيه" in terms
    assert " يا دكتور" not in terms
    assert "يا دكتور" in terms


def test_injection_safety_with_literal_braces(sample_env):
    rendered = loader.render("demo", user_val="Code {braces} and {config:ratios} literal", persona="Test")
    assert "Code {braces} and {config:ratios} literal" in rendered
