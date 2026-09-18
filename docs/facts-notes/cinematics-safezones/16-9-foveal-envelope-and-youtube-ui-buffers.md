# Note: 16:9 Foveal Envelope and YouTube UI Buffers

**Category:** Cinematics & Safe Zones  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/prompts/prompt_enhancer.py`, `src/youtube_automation/prompts/validator.py`, `src/youtube_automation/prompts/socratic_engine.py`, `src/youtube_automation/visuals/asset_studio.py`  
**Audit Reference:** Section 4.3 (Part 3: 16:9 Safe Composition), Section 6.2 (Module 6B)  

### 1. Core Rule in Plain English
All visual prompt generation for 16:9 broadcast explainer videos must explicitly constrain subjects and primary diagrams to the Foveal Safe Envelope bounded by `X: 180 to 1740, Y: 90 to 980`, maintaining a `10% peripheral bleed padding` for automated pan and zoom while keeping YouTube UI overlays (scrubbers, title banners, channel badges) completely unobstructed.

### 2. The Failure Mode It Prevents
- **Typographic Hallucination Prior**: Vague padding instructions such as `"generous unencumbered negative space across upper 15% header zone and lower 20% subtitle zone"` contain words (`"header"`, `"subtitle"`) that activate text-overlay priors in diffusion models, generating pseudo-Latin gibberish banners.
- **YouTube UI Collisions**: Edge-to-edge subject placement leads to critical visual elements being masked by the YouTube seek bar, chapter titles, playback controls, and channel avatars.
- **Ken Burns Edge Clamping**: Without a 10% peripheral bleed padding, automated dynamic pan-and-zoom ($100\% \to 103\%$ or $125\%$ punches) clips the outer contours of subjects against screen raster edges.
- **Validator Collision**: Using the forbidden keyword `"margin"` directly triggers `\bmargin\b` rejections in `verify_pipeline_integrity()`. Using `"bleed padding"` and exempting `"bleed margin"` via `(?<!bleed\s)\bmargin\b` eliminates false-positive pipeline halts.

### 3. Implementation Specification
1. **Prompt Safe-Zone Invariant (`prompt_enhancer.py`, `socratic_engine.py`)**:
   ```python
   SOCRATIC_CAMERA_DNA = (
       "clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, "
       "leaving 10% peripheral bleed padding for automated pan and zoom, level eye-line perspective, "
       "orthographic flat 2D projection plane, zero barrel distortion, zero keystoning, telephoto equivalent perspective"
   )
   ```
2. **Asset Studio DNA Synchronization (`asset_studio.py`)**:
   ```python
   STYLE_DNA_TEXT: str = (
       "2D graphic vector animation explainer style, crisp 3px black vector outlines, "
       "flat 2-step cel-shading, 1-2-3 shape hierarchy, "
       "clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, "
       "leaving 10% peripheral bleed padding"
   )
   ```
3. **Lookbehind Regex Exemption (`validator.py`)**:
   ```python
   # Flag margin as separate word (left margin band) but allow marginalia/margins and bleed margin
   if _re.search(r"(?<!bleed\s)\bmargin\b", dump):
       violations.append(f"{label}: forbidden term 'margin' detected in payload.")
   ```

### 4. Verification Check
- Unit test in `tests/unit/test_prompt_enhancer.py:test_16_9_compositional_foveal_safe_zones` verifies explicit coordinates and bleed padding injection.
- Unit test in `tests/unit/test_validator.py:test_bleed_padding_and_margin_pass_integrity` verifies that both `"bleed padding"` and `"bleed margin"` pass integrity validation without raising `PipelineIntegrityError`.
- Verification command:
  ```bash
  python -m pytest tests/unit/test_prompt_enhancer.py tests/unit/test_validator.py -v
  ```
