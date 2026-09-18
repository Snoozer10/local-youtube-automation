# Note: Mutually Assured Destruction (MAD) Token Conflicts and Hygiene

**Category:** Prompt Engineering  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/prompts/validator.py`, `src/youtube_automation/prompts/prompt_enhancer.py`, `tests/unit/test_validator.py`, `tests/unit/test_prompt_enhancer.py`  
**Audit Reference:** Section 2.2, Section 4.3  

### 1. Core Rule in Plain English
Negative prompt strings must never contain tokens that contradict or prohibit the positive visual style DNA (`STRICT_NEGATIVE_PROMPT` must be free of `vector`, `3px`, `cel-shading`, and positive lighting must not specify painterly `Da Vinci Sfumato` while negative prompts forbid sketchbooks and oil paintings). Negative builders must actively filter user overrides against a strict conflict blacklist.

### 2. The Failure Mode It Prevents
When a positive prompt requests `"bold 3px black contour linework, flat 2-step cel-shading, High-end 2D graphic vector animation style"` while the negative prompt contains `"no vector, no cel-shading, no 3px"`, diffusion text encoders (such as T5 and CLIP in Google Flow / Imagen 3) are driven into mathematical null-space. The model attempts to fulfill two mutually exclusive latent vectors, causing line degradation, blurred outlines, noisy raster artifacts, and macroblocking. Similarly, requesting `"Da Vinci Sfumato"` alongside `"no da vinci sketchbook, no oil painting"` produces hazy grey haloing and smudged contours.

### 3. Implementation Specification
1. **Purged `STRICT_NEGATIVE_PROMPT` in `validator.py`**:
   Removed `"no vector, no cel-shading, no 3px, "` from the baseline negative prompt:
   ```python
   STRICT_NEGATIVE_PROMPT = (
       "no text, no subtitles, no letters, no watermark, no signature, no caption, "
       "no typography, no calligraphy, "
       "no burned-in subtitles, no lower thirds, no on-screen text"
   )
   ```
2. **Abolished Positive Sfumato**:
   Updated `SOCRATIC_LIGHTING_DNA` in `prompt_enhancer.py`:
   ```python
   SOCRATIC_LIGHTING_DNA = (
       "high-key clean studio illumination, sharp contrast, razor-sharp shadow falloff, zero gradients on isolated clean white background (#FFFFFF)"
   )
   ```
   Added `"no sfumato"` to `STRICT_ZERO_TEXT_NEGATIVE`.
3. **Hardened Negative Sanitizer (`sanitize_negative_prompt`)**:
   Filters both raw tokens and `"no "` prefixed variations against `MAD_CONTRADICTORY_NEGATIVE_TOKENS`:
   ```python
   MAD_CONTRADICTORY_NEGATIVE_TOKENS: set[str] = {
       "3px", "no 3px", "3 px", "no 3 px",
       "vector", "no vector",
       "cel-shading", "no cel-shading", "cel shading", "no cel shading",
       "contour", "contour linework",
       "linework", "2d graphic", "graphic vector",
       "clean lines", "sharp lines",
   }
   ```
   Returns deterministic `", ".join(sorted(tokens))` preventing cache invalidations.

### 4. Verification Check
Run targeted test suite:
```bash
python -m pytest tests/unit/test_validator.py tests/unit/test_prompt_enhancer.py tests/unit/test_generate_thumbnail.py -v
```
Verifies:
- `test_strict_negative_prompt_free_of_style_dna`: Invariant test asserting `STRICT_NEGATIVE_PROMPT` is free of `3px`, `vector`, and `cel-shading`.
- `test_mad_token_conflict_purge`: Asserts `sanitize_negative_prompt()` blocks user overrides attempting to inject prohibited negative tokens while preserving custom non-conflicting tokens.
- `test_enhance_visual_prompt_injects_sfumato_lighting` & `test_enhance_diffusion_prompt_standalone_string`: Asserts razor-sharp shadow falloff and zero gradients.
- `test_build_webcomic_thumbnail_prompt_includes_strict_negative_prompt`: Verifies thumbnail generation remains in lockstep and uncompromised.
