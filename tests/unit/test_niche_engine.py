"""Unit tests for Dynamic Niche Engine and Inverted Pyramid Prompt Grammar."""

from __future__ import annotations

import json
import os
import tempfile

from youtube_automation.prompts.niche_engine import (
    get_niche_preset,
    load_channel_profile,
)
from youtube_automation.prompts.prompt_enhancer import build_mode_a_prompt


def test_niche_preset_resolutions():
    for key in ["SCIENCE_TECH", "FINANCE_ECONOMICS", "HISTORY_GEOPOLITICS", "PHILOSOPHY_ESSAY", "GENERAL_EXPLAINER", "CULTURE_COMEDY"]:
        preset = get_niche_preset(key)
        assert preset.niche_code == key
        assert len(preset.accents) >= 2
        assert preset.substrate_desc
        assert preset.palette_desc

    # Fallback to general explainer
    fallback = get_niche_preset("UNKNOWN_CUSTOM_NICHE")
    assert fallback.niche_code == "GENERAL_EXPLAINER"


def test_inverted_pyramid_subject_at_start():
    subj = "particle accelerator magnetic chamber"
    prompt = build_mode_a_prompt(subj, niche="SCIENCE_TECH")
    # Subject must lead at the beginning of the prompt (Zone 1)
    assert prompt.startswith(subj)
    # Niche-specific telemetry and palette
    assert "displaying" not in prompt
    assert "Requested diagram:" not in prompt
    assert "#00E5FF" in prompt
    word_count = len(prompt.split())
    assert word_count > 0


def test_load_channel_profile_custom_json():
    with tempfile.TemporaryDirectory() as tmp_dir:
        profile_path = os.path.join(tmp_dir, "channel_profile.json")
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump({
                "channel_name": "Deep Tech Insights",
                "niche": "SCIENCE_TECH",
                "host_mode": "NONE",
                "host_avatar_description": "",
                "aspect_ratio": "16:9",
            }, f)

        prof = load_channel_profile(tmp_dir)
        assert prof.channel_name == "Deep Tech Insights"
        assert prof.niche == "SCIENCE_TECH"
        assert prof.host_mode == "NONE"


def test_niche_specific_palettes():
    # Finance prompt
    finance_prompt = build_mode_a_prompt("market liquidity waterfall chart", niche="FINANCE_ECONOMICS")
    assert "market liquidity waterfall chart" in finance_prompt
    assert "graphite navy (#252C37)" in finance_prompt or "#252C37" in finance_prompt or "slate desk" in finance_prompt

    # History prompt
    history_prompt = build_mode_a_prompt("bronze age trade route map", niche="HISTORY_GEOPOLITICS")
    assert "bronze age trade route map" in history_prompt
    assert "parchment" in history_prompt
    assert "research table" not in history_prompt
