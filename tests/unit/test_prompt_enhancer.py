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


def test_asset_studio_socratic_presets():
    from youtube_automation.visuals.asset_studio import FLOW_ASSET_PRESETS, STYLE_DNA_TEXT
    assert "1-2-3 shape hierarchy" in STYLE_DNA_TEXT
    host_info = FLOW_ASSET_PRESETS["CHARACTERS"]["HOST"]["info"]
    assert "1-2-3 shape hierarchy" in host_info or "shape hierarchy" in host_info
    ahwa_prompt = FLOW_ASSET_PRESETS["SCENES"]["AHWA_STUDIO"]["scene_prompt"]
    assert "sfumato" in ahwa_prompt.lower() or "chiaroscuro" in ahwa_prompt.lower() or "1-2-3 shape hierarchy" in ahwa_prompt.lower()


def test_transform_prompts_file_roundtrip(tmp_path):
    import json
    from youtube_automation.prompts.prompt_enhancer import transform_prompts_file

    input_file = tmp_path / "flow_prompts.json"
    output_file = tmp_path / "flow_prompts_socratic.json"

    dummy_data = [
        {
            "index": 1,
            "timestamp": "[00:00]",
            "sequence_type": "STANDALONE",
            "layout_classification": "ISOLATED_WHITE",
            "sequence_metadata": {"set_id": "SET_01", "frame_index": 1, "total_frames_in_set": 1},
            "visual_density": "MINIMALIST_MACRO",
            "visual_prompt": {
                "subject": "Terence Howard stylized 2D portrait",
                "style": "2D graphic vector",
            },
        },
        {
            "index": 2,
            "timestamp": "[00:03]",
            "sequence_type": "STANDALONE",
            "layout_classification": "ISOLATED_WHITE",
            "sequence_metadata": {"set_id": "SET_02", "frame_index": 1, "total_frames_in_set": 1},
            "visual_density": "MINIMALIST_MACRO",
            "visual_prompt": {
                "subject": "glowing padlock",
                "style": "2D graphic vector",
            },
        },
    ]
    input_file.write_text(json.dumps(dummy_data), encoding="utf-8")

    out = transform_prompts_file(str(input_file), str(output_file))
    assert len(out) == 2
    assert output_file.exists()

    with open(output_file, encoding="utf-8") as f:
        loaded = json.load(f)
    assert len(loaded) == 2
    assert "1-2-3 shape hierarchy" in loaded[0]["visual_prompt"]["style"].lower()


def test_transform_roadmap_jsonl_roundtrip(tmp_path):
    import json
    from youtube_automation.prompts.prompt_enhancer import transform_roadmap_jsonl

    input_file = tmp_path / "master_roadmap.jsonl"
    output_file = tmp_path / "master_roadmap_socratic.jsonl"

    rows = [
        {"index": 1, "timestamp": "00:00 - 00:03", "visual_concept": "Portrait of host", "color_and_arabic_text": "NONE"},
        {"index": 2, "timestamp": "00:03 - 00:06", "visual_concept": "Glowing padlock", "color_and_arabic_text": "NONE"},
    ]
    with open(input_file, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    out = transform_roadmap_jsonl(str(input_file), str(output_file))
    assert len(out) == 2
    assert output_file.exists()

    with open(output_file, encoding="utf-8") as f:
        loaded = [json.loads(line) for line in f if line.strip()]
    assert len(loaded) == 2
    assert "1-2-3 shape hierarchy" in loaded[0]["visual_concept"]


