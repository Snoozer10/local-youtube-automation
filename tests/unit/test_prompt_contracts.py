from youtube_automation.prompts import loader


def test_meta_blocks_stripped_across_all_prompts():
    for name in ("phase1", "phase3", "refine", "tts"):
        rendered = loader.render(name)
        assert "<<<PROMPT_META" not in rendered
        assert "PROMPT_META_END" not in rendered


def test_phase1_contract():
    body = loader.render("phase1")
    assert "SOLO NARRATOR" in body
    assert "Paragraph 1 (The Hook)" in body


def test_phase3_contract():
    body = loader.render("phase3")
    assert "30% Academic Fusha : 70% Cairene Amiya" in body
    for token in ("كِدَه", "بِيُقول", "هُوبَّا", "قِسط"):
        assert token in body


def test_refine_cadence_and_slang_contract():
    pr = loader.load("refine")
    assert "مستعد" in pr.ack_tokens
    assert set(pr.xml_tags) == {"final_script", "thinking", "slang_ledger"}
    body = loader.render("refine")
    assert "Beat 1 (Short Hit: 2 to 5 words)" in body
    assert "Beat 3 (Dense Explainer: 15 to 22 words)" in body
    assert "Category A" in body
    assert "Category D" in body


def test_multi_channel_dynamic_override():
    sci_channel = {
        "name": "Nova Science",
        "dialect_profile": {
            "fusha_academic_ratio": 0.9,
            "cairo_amiya_ratio": 0.1,
            "tashkeel_lexicon": {"gravity": "جَاذِبِيَّة"},
        },
    }
    body = loader.render("phase3", channel=sci_channel)
    assert "90% Academic Fusha : 10% Cairene Amiya" in body
    assert "جَاذِبِيَّة" in body


def test_tts_single_calibration_contract():
    body = loader.render("tts")
    assert body.count("Rules Confirmation: Awaiting the transcript.") == 1
    assert "Ready for the script. Please provide your video transcript script" not in body
    assert "Breakdown Structure & Voice Recommendations" in body


def test_slang_catalog_purity():
    terms = loader.slang_terms()
    assert "يا دكتور" in terms
    assert "야 닥터" not in terms
    assert "The Pacing Boosters" not in terms
    assert all(not t.startswith(" ") for t in terms)


def test_legacy_aliases_resolve():
    assert loader.render("prompt") == loader.render("phase1")
    assert loader.render("prompt_phase3") == loader.render("phase3")
    assert loader.render("refine_prompt") == loader.render("refine")
    assert loader.render("TTS_PROMPT") == loader.render("tts")


def test_turn_templates_render_cleanly():
    lean_res = loader.turn(
        "refine",
        "lean",
        index=1,
        total=5,
        persona="Al-Daheeh",
        context_bridge="Bridge",
        tone_block="Tone",
        slang_restriction="Slang",
        source_paragraph="Source Text",
    )
    assert "<<<PROMPT_META" not in lean_res
    assert "Refine Paragraph 1/5:" in lean_res
    assert "Source Text" in lean_res

    p3_res = loader.turn("phase3", "turn", index=1, total=5, paragraph="Paragraph text")
    assert "<<<PROMPT_META" not in p3_res
    assert "Paragraph 1 of 5" in p3_res
    assert "Paragraph text" in p3_res
