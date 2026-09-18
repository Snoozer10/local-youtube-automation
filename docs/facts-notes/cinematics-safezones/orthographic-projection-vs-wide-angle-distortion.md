# Note: Orthographic Projection vs. Wide-Angle Lens Distortion

**Category:** Cinematics & Optical Perspective  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/prompts/prompt_enhancer.py`, `src/youtube_automation/prompts/validator.py`, `src/youtube_automation/prompts/socratic_engine.py`, `src/youtube_automation/timeline/scene_graph.py`, `roadmap_orchestrator.py`  
**Audit Reference:** Section 4.1 (Optical Keystoning vs. 2D Vector Plane), Section 6.2 (Module 6B)  

### 1. Core Rule in Plain English
Diffusion prompts for 2D graphic vector explainer videos must specify an `orthographic flat 2D projection plane, zero barrel distortion, zero keystoning, telephoto equivalent perspective` and strictly ban `24mm lens`, `wide-angle distortion`, `fisheye`, `barrel distortion`, and `keystone distortion` in negative prompt space.

### 2. The Failure Mode It Prevents
Specifying `24mm wide-angle lens` in conjunction with `2D graphic vector animation` forces diffusion models to calculate a wide-angle focal perspective ($f \le 24\text{ mm}$), causing radial barrel distortion ($x_{\text{distorted}} = x(1 + k_1 r^2 + k_2 r^4)$). Straight diagrammatic axes, drafting placards, rectangular schematics, and subtitles bow outward and undergo severe keystoning warping, destroying technical legibility and visual authority.

### 3. Implementation Specification
1. **Positive Optical Anchoring (`prompt_enhancer.py`, `socratic_engine.py`)**:
   ```python
   SOCRATIC_CAMERA_DNA = (
       "clean centered 16:9 widescreen framing, level eye-line perspective, "
       "orthographic flat 2D projection plane, zero barrel distortion, zero keystoning, "
       "telephoto equivalent perspective, balanced negative space"
   )
   ```
2. **Defensive Legacy Keyword Purge (`prompt_enhancer.py`)**:
   ```python
   result = re.sub(
       r"\b24\s*mm(\s+wide[- ]angle)?(\s+lens|\s+optics|\s+framing)?\b|\bwide[- ]angle\s+lens\b|\bfisheye(\s+lens)?\b",
       "orthographic flat 2D projection plane",
       result,
       flags=re.IGNORECASE,
   )
   ```
3. **Deterministic Negative Enforcement (`validator.py`, `prompt_enhancer.py`)**:
   ```python
   STRICT_NEGATIVE_PROMPT = (
       "no text, no subtitles, no letters, no watermark, no signature, no caption, "
       "no typography, no calligraphy, "
       "no burned-in subtitles, no lower thirds, no on-screen text, "
       "no 24mm lens, no wide-angle lens, no fisheye, no barrel distortion, no keystone distortion"
   )
   ```
4. **Mutual Exclusion Safeguard**:
   `MAD_CONTRADICTORY_NEGATIVE_TOKENS` includes `"orthographic"`, `"no orthographic"`, `"telephoto"`, `"no telephoto"`, `"2d"`, `"no 2d"`.

### 4. Verification Check
- Unit test assertions in `tests/unit/test_prompt_enhancer.py` verify that `enhance_visual_prompt()` outputs `orthographic`, `zero barrel distortion`, and `zero keystoning`.
- `tests/unit/test_validator.py:test_strict_negative_prompt_free_of_style_dna()` verifies negative prompt enforcement.
- Verification command:
  ```bash
  python -m pytest tests/unit/test_prompt_enhancer.py tests/unit/test_validator.py tests/unit/test_viewer_generator.py -v
  ```
