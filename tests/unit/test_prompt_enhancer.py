"""Unit tests for the Socratic Prompt Enhancer module.

Validates the operationalization of the 5 empirical NotebookLM principles:
1. Modular prompt scaffolding & single-generation pass
2. 1-2-3 shape hierarchy (primary silhouette, sub-structures, small accents)
3. Da Vinci Sfumato chiaroscuro lighting against desaturated negative space
4. Orthographic flat 2D projection plane with telephoto perspective (zero barrel distortion, zero keystoning)
5. Strict negative latent suppression (~94% compliance filter)
6. English-only compliance (ADR 0003: zero Arabic characters in diffusion prompts)
"""


from youtube_automation.prompts.prompt_enhancer import (
    enhance_diffusion_prompt,
    enhance_frame_item,
    enhance_visual_prompt,
)
from youtube_automation.prompts.validator import (
    FrameItem,
    VisualPrompt,
    validate_english_only_prompt,
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
    assert "razor-sharp shadow falloff" in enhanced.lighting.lower() or "zero gradients" in enhanced.lighting.lower()


def test_enhance_visual_prompt_injects_camera_optics():
    vp = VisualPrompt(
        subject="scientific blueprint layout",
        style="2D vector",
        composition="centered framing",
    )
    enhanced = enhance_visual_prompt(vp)
    assert "orthographic" in enhanced.composition.lower()
    assert "zero barrel distortion" in enhanced.composition.lower()
    assert "zero keystoning" in enhanced.composition.lower()


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
    assert "razor-sharp shadow falloff" in enhanced_text.lower() or "zero gradients" in enhanced_text.lower()
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


def test_neutralize_surfaces():
    from youtube_automation.prompts.prompt_enhancer import neutralize_surfaces

    raw = "A professor writing 'E=mc^2' on a chalkboard, with important documents and a red 'REJECTED' stamp on the desk."
    neutralized = neutralize_surfaces(raw)
    assert "dark matte chalkboard with clean geometric diagrams and non-linguistic coordinate axes" in neutralized
    assert "drafting placard displaying abstract non-textual ratio diagrams" in neutralized
    assert "stylized wax seal emblem" in neutralized
    assert "REJECTED" not in neutralized
    assert "E=mc^2" not in neutralized


def test_neutralize_surfaces_preserves_compound_nouns():
    """Verify that compound nouns are not corrupted by solitary noun replacements."""
    from youtube_automation.prompts.prompt_enhancer import neutralize_surfaces

    # Case 1: circuit board
    t1 = "A technician inspecting a stylized vector circuit board on the desk."
    out1 = neutralize_surfaces(t1)
    assert "circuit blank unmarked wooden board" not in out1
    assert "printed circuit schematic board with copper trace paths" in out1

    # Case 2: split-screen
    t2 = "A split-screen view of human head silhouette with mechanical brain."
    out2 = neutralize_surfaces(t2)
    assert "split-blank dark glass monitor" not in out2
    assert "split-screen dual composition with bilateral comparative panels" in out2

    # Case 3: open book (antonymous state collision prevention)
    t3 = "Popping up directly above an open retro book resting on the table."
    out3 = neutralize_surfaces(t3)
    assert "open retro blank closed book" not in out3
    assert "open technical reference ledger" in out3


def test_neutralize_surfaces_idempotence():
    """Verify that multiple passes do not multiply phrases or duplicate tokens."""
    from youtube_automation.prompts.prompt_enhancer import neutralize_surfaces

    raw = "technical schematic grid with circuit board and open book"
    pass1 = neutralize_surfaces(raw)
    pass2 = neutralize_surfaces(pass1)
    pass3 = neutralize_surfaces(pass2)
    assert pass1 == pass2 == pass3
    assert "clean 2D vector schematics clean 2D vector schematics" not in pass3


def test_mad_token_conflict_purge():
    """Verify that negative prompt builder never outputs 'no 3px', 'no vector', or 'no cel-shading'."""
    from youtube_automation.prompts.prompt_enhancer import sanitize_negative_prompt
    from youtube_automation.prompts.validator import STRICT_NEGATIVE_PROMPT

    # Verify constant itself is cleansed
    assert "no 3px" not in STRICT_NEGATIVE_PROMPT.lower()
    assert "no vector" not in STRICT_NEGATIVE_PROMPT.lower()
    assert "no cel-shading" not in STRICT_NEGATIVE_PROMPT.lower()

    # Verify builder with user overrides that try to inject 'no vector'
    built = sanitize_negative_prompt("no vector, no 3px, custom watermark")
    assert "no vector" not in built.lower()
    assert "no 3px" not in built.lower()
    assert "custom watermark" in built


def test_build_mode_a_prompt():
    from youtube_automation.prompts.prompt_enhancer import (
        build_mode_a_prompt,
    )

    prompt = build_mode_a_prompt("antique brass double-pan balance scale", setting="dark walnut drafting table")
    assert "antique brass double-pan balance scale" in prompt
    assert "Orthographic flat 2D projection plane" in prompt
    assert "zero barrel distortion" in prompt
    assert "neutral light studio limbo ground (#F8F8FA)" in prompt
    assert "High-end 2D graphic vector animation explainer style" in prompt
    assert "da vinci sketchbook" not in prompt.lower()
    # Length check: 60-110 words typical
    word_count = len(prompt.split())
    assert 60 <= word_count <= 110


def test_build_mode_b_prompt():
    from youtube_automation.prompts.prompt_enhancer import build_mode_b_prompt

    prompt = build_mode_b_prompt("small brass weight", spatial_direction="in the left pan")
    assert prompt.startswith("In the attached reference image, maintain identical subject, background, and lighting. Add small brass weight in the left pan.")
    assert len(prompt.split()) < 25


def test_16_9_compositional_foveal_safe_zones():
    vp = VisualPrompt(
        subject="scientific apparatus",
        style="2D vector",
    )
    enhanced = enhance_visual_prompt(vp)
    assert "X: 180 to 1740" in enhanced.composition
    assert "Y: 90 to 980" in enhanced.composition
    assert "10% peripheral bleed padding" in enhanced.composition


def test_universal_6part_grammar_mode_a():
    from youtube_automation.prompts.prompt_enhancer import build_mode_a_prompt

    prompt = build_mode_a_prompt(
        subject="quantum wave packet",
        spatial_direction="centered focal composition",
        setting="SCENE_ISOLATED_WHITE_ENV",
    )
    # Part 1: Master Style Anchor
    assert "High-end 2D graphic vector animation explainer style" in prompt
    assert "uniform 3px deep charcoal (#2D3444) contour linework" in prompt
    assert "flat 2-step cel-shading" in prompt
    assert "zero gradients" in prompt

    # Part 2: Camera Optical Model
    assert "Orthographic flat 2D projection plane" in prompt
    assert "zero barrel distortion" in prompt
    assert "zero keystoning" in prompt

    # Part 3: 16:9 Safe Composition
    assert "coordinates X: 180 to 1740, Y: 90 to 980" in prompt
    assert "10% peripheral bleed padding" in prompt

    # Part 4: Substrate Ground
    assert "Locked studio substrate" in prompt
    assert "isolated clean white background (#FFFFFF)" in prompt

    # Part 5: Semantic Data Entity
    assert "quantum wave packet" in prompt
    assert "abstract non-textual proportion meters" in prompt

    # Part 6: Codec-Safe Accents
    assert "60%" in prompt and "30%" in prompt and "10%" in prompt
    assert "#00E5FF" in prompt
    assert "#FFB300" in prompt
    assert "#EB191E" in prompt

    # Word count
    word_count = len(prompt.split())
    assert 60 <= word_count <= 110


def test_unified_substrate_and_codec_safe_color_anchoring():
    from youtube_automation.prompts.prompt_enhancer import (
        AHWA_STUDIO_GROUND,
        CODEC_SAFE_RED,
        LIGHT_LIMBO_SUBSTRATE,
        STRICT_ZERO_TEXT_NEGATIVE,
        build_mode_a_prompt,
        sanitize_negative_prompt,
    )

    assert "#F8F8FA" in LIGHT_LIMBO_SUBSTRATE
    assert "#2A2420" in AHWA_STUDIO_GROUND
    assert CODEC_SAFE_RED == "#EB191E"

    # Default fallback is Light Limbo
    prompt_default = build_mode_a_prompt("quantum gyroscope")
    assert "#F8F8FA" in prompt_default
    assert "#EB191E" in prompt_default
    assert "60% base ground" in prompt_default

    # Ahwa studio substrate
    prompt_ahwa = build_mode_a_prompt("philosophical debate", setting="SCENE_AHWA_STUDIO_ENV")
    assert "#2A2420" in prompt_ahwa

    # Negative bans pure red RGB(255,0,0) and crushed blacks
    assert "no saturated pure red" in STRICT_ZERO_TEXT_NEGATIVE
    assert "no pure red RGB(255,0,0)" in STRICT_ZERO_TEXT_NEGATIVE
    sanitized_neg = sanitize_negative_prompt()
    assert "no saturated pure red" in sanitized_neg
    assert "no pure red RGB(255,0,0)" in sanitized_neg
