# Note: Unified Substrate and Codec-Safe Color Anchoring

**Category:** Cinematics & Safe Zones  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/prompts/prompt_enhancer.py`, `src/youtube_automation/visuals/asset_studio.py`, `tests/unit/test_prompt_enhancer.py`  
**Audit Reference:** Section 3.2 (Persistent Studio Substrate), Section 6.1 (Module 6A: Unified Substrate System), Section 6.2 (Module 6B: Codec Defense)  

### 1. Core Rule in Plain English
1. **Unified Studio Substrate**: All generation scenes across multiple channel niches must consolidate into two canonical workspace substrates to eliminate retinal luminance whiplash:
   - `LIGHT_LIMBO_SUBSTRATE` (`#F8F8FA`, ~97% non-glare luminance) for default educational, scientific, comparative, and technical infographic plates.
   - `AHWA_STUDIO_GROUND` (`#2A2420`, warm dark mahogany workbench at ~35% luminance) for dialogic host and comedic scenes.
   Secondary environments (e.g., retro blueprints, historical museum documents) must never render as full-screen pitch-black voids or dark crimson rooms; they are rendered as orthographic drafting placards or archival folios resting flat on the studio workbench.
2. **60-30-10 Chromatic Attention Law**:
   - $60\%$ Neutral Substrate Base: `#F8F8FA` (or `#2A2420`).
   - $30\%$ Structural Lines & Cel Fills: Deep charcoal (`#2D3444`).
   - $10\%$ Kinetic Accents: Electric Cyan (`#00E5FF`), Amber (`#FFB300`), Spring Green (`#00E676`), and Codec-Safe Red (`#EB191E`).
3. **Streaming Codec Defense**:
   - All red accents must anchor to codec-safe RGB(235, 25, 30) (`#EB191E`) to eliminate H.264/H.265 4:2:0 chroma subsampling bleeding and macroblocking.
   - Negative prompts explicitly prohibit pure saturated boundaries: `no saturated pure red, no pure red RGB(255,0,0), no crushed blacks RGB(0,0,0)`.
   - The negative prompt tokenizer uses parenthesis-aware splitting (`_split_negative_tokens`) so tuples like `RGB(255,0,0)` are never corrupted across comma boundaries.

### 2. The Failure Mode It Prevents
- **Retinal Luminance Whiplash**: Cycling between 100% white void, 35% warm cafe, and 12% deep navy blueprints across 15 scene cuts triggers violent pupil dilation/constriction cycles every 2.5 seconds, causing viewer visual fatigue and early drop-off.
- **Cognitive World Fragmentation**: Teleporting the viewer between 6 unrelated physical universes (white void, cafe, museum gallery, navy blueprint void) destroys spatial continuity and overburdens working memory.
- **Chroma Subsampling Smear**: Pure saturated red ($\text{RGB } 255, 0, 0$) clips digital color spaces and bleeds across high-contrast edges when compressed to YUV 4:2:0 for YouTube streaming.
- **Negative Token Tuple Fragmentation**: Standard `.split(",")` functions split `RGB(255, 0, 0)` into broken tokens (`RGB(255`, `0`, `0)`), corrupting negative prompt syntax and causing test failures.

### 3. Implementation Specification
1. **Substrates and Palette Constants (`prompt_enhancer.py`, `asset_studio.py`)**:
   ```python
   LIGHT_LIMBO_SUBSTRATE: str = "neutral light studio limbo ground (#F8F8FA)"
   AHWA_STUDIO_GROUND: str = "warm dark mahogany studio workbench (#2A2420)"
   CODEC_SAFE_RED: str = "#EB191E"  # RGB(235, 25, 30)
   STRUCTURAL_CHARCOAL: str = "#2D3444"
   ACCENT_ELECTRIC_CYAN: str = "#00E5FF"
   ACCENT_AMBER: str = "#FFB300"
   ACCENT_SPRING_GREEN: str = "#00E676"

   CHROMATIC_PALETTE_60_30_10: str = (
       "Palette: 60% base ground, 30% charcoal lines, "
       "10% kinetic accents (Electric Cyan #00E5FF, Amber #FFB300, Spring Green #00E676, Codec-Safe Red #EB191E)"
   )
   ```

2. **Parenthesis-Aware Negative Token Splitting (`prompt_enhancer.py`)**:
   ```python
   def _split_negative_tokens(text: str) -> list[str]:
       """Splits negative prompt strings on commas while preserving parenthesized tuples like RGB(255,0,0)."""
       tokens, current, in_paren = [], [], False
       for char in text:
           if char == "(":
               in_paren = True
           elif char == ")":
               in_paren = False
           if char == "," and not in_paren:
               tok = "".join(current).strip()
               if tok:
                   tokens.append(tok)
               current = []
           else:
               current.append(char)
       tok = "".join(current).strip()
       if tok:
           tokens.append(tok)
       return tokens
   ```

3. **Substrate Routing in `build_mode_a_prompt()` (`prompt_enhancer.py`)**:
   ```python
   def build_mode_a_prompt(
       subject: str,
       spatial_direction: str = "centered focal composition",
       setting: str = "SCENE_LIGHT_LIMBO_ENV",
       domain_palette: str = "TECHNICAL_SLATE",
   ) -> str:
       # Part 4: Substrate Ground
       setting_desc = "neutral light studio limbo ground (#F8F8FA)"
       if setting:
           if setting == "SCENE_AHWA_STUDIO_ENV" or "ahwa" in setting.lower():
               setting_desc = "warm dark mahogany studio workbench (#2A2420)"
           elif setting == "SCENE_LIGHT_LIMBO_ENV" or "limbo" in setting.lower():
               setting_desc = "neutral light studio limbo ground (#F8F8FA)"
           elif setting == "SCENE_ISOLATED_WHITE_ENV" or "white" in setting.lower():
               setting_desc = "isolated clean white background (#FFFFFF)"
           else:
               clean_setting = purge_banned_visual_keywords(neutralize_surfaces(_ensure_english_text(setting)))
               setting_desc = f"{clean_setting}, neutral light studio limbo ground (#F8F8FA)"
       part4 = f"Locked studio substrate, {setting_desc}, zero luminance strobing."
   ```

### 4. Verification Check
- Unit test `tests/unit/test_prompt_enhancer.py:test_unified_substrate_and_codec_safe_color_anchoring` verifies substrate constant values, default Light Limbo injection, Ahwa desk routing, and negative bans on `pure red RGB(255,0,0)`.
- Unit test `tests/unit/test_prompt_enhancer.py:test_build_mode_a_prompt` verifies substrate injection and 60-110 word count compliance across custom settings.
- Verification command:
  ```bash
  python -m pytest tests/unit/test_prompt_enhancer.py -v
  ```
