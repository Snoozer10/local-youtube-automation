# Note: Universal 6-Part Prompt Grammar

**Category:** Prompt Engineering & Schema Design  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/prompts/prompt_enhancer.py`, `src/youtube_automation/visuals/flow_generator.py`, `tests/unit/test_prompt_enhancer.py`  
**Audit Reference:** Section 4.3 (Universal 6-Part Prompt Grammar Standard), Module 6A & 6B  

### 1. Core Rule in Plain English
All Master Setup (Mode A) visual prompts for diffusion models must strictly follow the deterministic 6-Part Universal Prompt Grammar standard in linear sequence:
1. **Master Style Anchor**: Vector animation aesthetic, uniform 3px deep charcoal (#2D3444) contour linework, flat 2-step cel-shading, razor-sharp shadow edges, zero gradients.
2. **Camera Optical Model**: Orthographic flat 2D projection plane, zero barrel distortion, zero keystoning, telephoto equivalent perspective.
3. **16:9 Safe Composition**: Clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, leaving 10% peripheral bleed padding for automated pan and zoom.
4. **Substrate Ground**: Locked studio substrate, isolated clean white background (#FFFFFF) or registered studio surface, zero luminance strobing.
5. **Semantic Data Entity**: Clear subject description, spatial focal direction, abstract non-textual proportion meters and node linkages.
6. **Codec-Safe Accents**: 60-30-10 chromatic attention law (60% base ground, 30% charcoal lines, 10% kinetic accents: Electric Cyan #00E5FF, Amber #FFB300, Codec-Safe Red #EB191E).

The resulting prompt must stay strictly within the 60 to 110-word budget.

### 2. The Failure Mode It Prevents
- **Ad-Hoc Structural Drift**: Arbitrary prompt token ordering leads to unpredictable diffusion attention allocation, where camera parameters or color palettes override core semantic subjects.
- **Luminance Strobing**: Changing background substrates between adjacent cuts without a locked studio ground causes eye fatigue and perceived brightness flicker across fast cuts.
- **Text Gibberish Prior**: Omitting abstract telemetry guidance invites diffusion models to render illegible pseudo-Latin equations or labels on empty negative space.
- **RGB Clipping & Chroma Distortion**: Unchecked pure saturated colors (e.g., pure red RGB 255, 0, 0) cause severe 4:2:0 chroma subsampling artifacts and bleeding upon H.264 video compression.

### 3. Implementation Specification
Implemented in `src/youtube_automation/prompts/prompt_enhancer.py`:
```python
def build_mode_a_prompt(
    subject: str,
    spatial_direction: str = "centered focal composition",
    setting: str = "SCENE_ISOLATED_WHITE_ENV",
    domain_palette: str = "TECHNICAL_SLATE",
) -> str:
    clean_subj = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(purge_subtitle_phrases(subject))))

    # Part 1: Master Style Anchor
    part1 = "High-end 2D graphic vector animation explainer style, uniform 3px deep charcoal (#2D3444) contour linework, flat 2-step cel-shading with razor-sharp shadow edges, zero gradients."

    # Part 2: Camera Optical Model
    part2 = "Orthographic flat 2D projection plane, zero barrel distortion, zero keystoning, telephoto equivalent perspective."

    # Part 3: 16:9 Safe Composition
    part3 = "Clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, leaving 10% peripheral bleed padding for automated pan and zoom."

    # Part 4: Substrate Ground
    setting_desc = "isolated clean white background (#FFFFFF)"
    if setting and setting != "SCENE_ISOLATED_WHITE_ENV" and "white" not in setting.lower():
        clean_setting = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(setting)))
        setting_desc = f"{clean_setting}, isolated clean white background (#FFFFFF)"
    part4 = f"Locked studio substrate, {setting_desc}, zero luminance strobing."

    # Part 5: Semantic Data Entity
    part5 = f"{clean_subj.rstrip('.')}. {spatial_direction}, abstract non-textual proportion meters and node linkages."

    # Part 6: Codec-Safe Accents (60-30-10 chromatic attention law)
    part6 = "Palette: 60% base ground, 30% charcoal lines, 10% kinetic accents (Electric Cyan #00E5FF, Amber #FFB300, Codec-Safe Red #EB191E)."

    return f"{part1} {part2} {part3} {part4} {part5} {part6}"
```

Integrated into `build_dual_mode_prompt()` in `src/youtube_automation/visuals/flow_generator.py` for automated master setup synthesis.

### 4. Verification Check
- Unit test `tests/unit/test_prompt_enhancer.py:test_universal_6part_grammar_mode_a` verifies the presence of all 6 parts and enforces word count `60 <= word_count <= 110`.
- Unit test `tests/unit/test_prompt_enhancer.py:test_build_mode_a_prompt` verifies integration of master style, orthographic projection, and isolated clean white canvas.
- Verification command:
  ```bash
  python -m pytest tests/unit/test_prompt_enhancer.py -v -k "grammar or mode_a"
  ```
