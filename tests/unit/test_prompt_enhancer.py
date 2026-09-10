"""Unit tests for the Socratic Prompt Enhancer module.

Validates the operationalization of the 5 empirical NotebookLM principles:
1. Modular prompt scaffolding & single-generation pass
2. 1-2-3 shape hierarchy (primary silhouette, sub-structures, small accents)
3. Da Vinci Sfumato chiaroscuro lighting against desaturated negative space
4. 24mm wide-angle optics with f/1.8 shallow depth of field
5. Strict negative latent suppression (~94% compliance filter)
6. English-only compliance (ADR 0003: zero Arabic characters in diffusion prompts)
"""

import pytest
from pydantic import ValidationError

from youtube_automation.prompts.validator import (
    FrameItem,
    VisualPrompt,
    validate_english_only_prompt,
)
from youtube_automation.prompts.prompt_enhancer import (
    SOCRATIC_NEGATIVE_PROMPT,
    SOCRATIC_STYLE_DNA,
    enhance_diffusion_prompt,
    enhance_frame_item,
    enhance_visual_prompt,
)


def test_enhance_visual_prompt_injects_shape_hierarchy():
    vp = VisualPrompt(
        subject="cartoon host holding teacup",
        action="explaining physics",
        setting="ahwa studio",
        mood="dramatic",
        lighting="warm keylight",
        composition="medium shot",
        style="2D graphic vector animation",
        negative_prompt="photorealism",
    )
    enhanced = enhance_visual_prompt(vp)
    assert "1-2-3 shape hierarchy" in enhanced.style.lower() or "1-2-3 shape hierarchy" in enhanced.composition.lower()


def test_enhance_visual_prompt_injects_sfumato_lighting():
    vp = VisualPrompt(
        subject="Al-Daheeh host",
        style="2D vector",
        lighting="studio illumination",
    )
    enhanced = enhance_visual_prompt(vp)
    assert "sfumato" in enhanced.lighting.lower() or "chiaroscuro" in enhanced.lighting.lower()


def test_enhance_visual_prompt_injects_camera_optics():
    vp = VisualPrompt(
        subject="scientific blueprint layout",
        style="2D vector",
        composition="centered framing",
    )
    enhanced = enhance_visual_prompt(vp)
    assert "24mm" in enhanced.composition.lower()


def test_enhance_visual_prompt_reinforces_negative_filter():
    vp = VisualPrompt(
        subject="cartoon host",
        style="2D vector",
        negative_prompt="watermark",
    )
    enhanced = enhance_visual_prompt(vp)
    for forbidden in ["burned subtitles", "chalkboard", "specular glare", "typography"]:
        assert forbidden in enhanced.negative_prompt.lower()


def test_enhance_frame_item_preserves_indices_and_timestamps():
    item = FrameItem(
        index=15,
        timestamp="[00:45]",
        sequence_type="STANDALONE",
        visual_prompt=VisualPrompt(
            subject="bifurcated comparative stage",
            style="2D vector",
        ),
    )
    enhanced_item = enhance_frame_item(item)
    assert enhanced_item.index == 15
    assert enhanced_item.timestamp == "[00:45]"
    assert enhanced_item.visual_prompt.subject == "bifurcated comparative stage"
    assert "1-2-3 shape hierarchy" in enhanced_item.visual_prompt.style.lower() or "1-2-3 shape hierarchy" in enhanced_item.visual_prompt.composition.lower()


def test_english_only_guarantee():
    vp = VisualPrompt(
        subject="Al-Daheeh host مع كوب شاي",
        style="2D vector",
    )
    enhanced = enhance_visual_prompt(vp)
    flattened = enhance_diffusion_prompt(enhanced)
    valid, reason = validate_english_only_prompt(flattened)
    assert valid is True, f"Prompt contains Arabic script: {reason}"


def test_enhance_diffusion_prompt_standalone_string():
    raw_prompt = "A stylized 2D portrait of Terence Howard in deep thought, centered against white backdrop."
    enhanced_text = enhance_diffusion_prompt(raw_prompt)
    assert "1-2-3 shape hierarchy" in enhanced_text.lower()
    assert "sfumato" in enhanced_text.lower() or "chiaroscuro" in enhanced_text.lower()
    assert "negative prompt:" in enhanced_text.lower()
