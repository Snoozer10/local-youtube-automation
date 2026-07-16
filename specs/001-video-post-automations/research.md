# Research: Post-Production Automations (P1)

**Date**: 2026-07-11

## R1: Gemini Helper Extraction Strategy

**Decision**: Extract 5 functions from `automate_all.py` into `gemini_utils.py` — pure mechanical extraction, no new logic.

**Rationale**: `find_input_box`, `find_send_button`, `wait_for_gemini_response`, `start_clean_gemini_chat`, `select_gemini_model` are copy-pasted across 5+ files with slight variations. The `automate_all.py` versions are the most robust (5-6 fallback selectors, growth monitoring, safety detection).

**Alternatives considered**:
- Extracting from `generate_voice.py` — rejected: simpler implementations, fewer fallback selectors
- Creating a GeminiPage class — rejected: over-engineering, existing scripts use functional style, YAGNI
- Merging into `utils.py` — rejected: `utils.py` is for config/browser/TTS, not Gemini UI DOM interaction

**Source functions** (all from `automate_all.py`):

| Function | Line | Selectors/Logic |
|----------|------|-----------------|
| `find_input_box` | 222-249 | 5 fallback selectors + fallback wait |
| `find_send_button` | 251-270 | 6 fallback selectors, reverse iteration |
| `wait_for_gemini_response` | 289-351 | Growth monitoring + send button state + safety detection |
| `start_clean_gemini_chat` | 84-135 | 6 new-chat selectors + keyboard shortcut fallback + response count zeroing |
| `select_gemini_model` | 406-453 | 7 trigger selectors + active check + menu item filter |
| `get_last_response` | 272-284 | Helper for `wait_for_gemini_response` |

**RESPONSE_SELECTOR**: `"model-response div.markdown"` — shared constant, documented as fragile (Principle I).

## R2: Refinement Prompt Architecture

**Decision**: Two-turn interaction (setup + paragraph performance), matching existing `prompt_phase3.txt` pattern.

**Rationale**: The existing translation prompt uses a 3-part interaction (style guide → proof of mastery → performance). Refinement is simpler — it operates on already-translated Arabic, not English→Arabic translation. A 2-turn approach (rules acknowledgment → paragraph refinement) is sufficient and cheaper.

**Alternatives considered**:
- Single-turn system prompt — rejected: no calibration step means Gemini may drift on dialect/rhythm rules
- Three-turn with separate hook/outro pass — rejected: over-engineering, hook/outro can be handled as first/last paragraph rules
- One-shot full-script refinement — rejected: token limits, no checkpoint/resume, contradicts Principle II

**Prompt structure**:
- Turn 1 (setup): 7 rules covering dialect, fluency, rhythm, meaning preservation, TTS-friendliness, hook, outro. Gemini replies "UNDERSTOOD".
- Turn 2 (per paragraph): `"Refine paragraph {i} of {total}. Return ONLY the refined Arabic text...\n\n{paragraph}"`
- Paragraph 1 gets HOOK rule applied. Last paragraph gets OUTRO CTA rule. Middle paragraphs get rules 1-5 only.

## R3: Thumbnail Pipeline Architecture

**Decision**: 4-phase pipeline: concept extraction → Nano Banana Pro prompt generation → self-critique → image generation. Uses Gemini's judgment to pick winners.

**Rationale**: Nano Banana Pro camera architecture (from `awesome-nanobanana-pro` repo, 10.2k stars) produces high-fidelity results when prompts include exact camera body, lens, aperture, ISO, and lighting setup. Self-critique loop leverages Gemini's understanding of click appeal to select the best 2 variants.

**Alternatives considered**:
- Single-thumbnail generation — rejected: no A/B testing capability, user wants 3-5 variants
- Templated variants (fixed styles × topic) — rejected: less creative, Gemini can generate better concepts
- Full 5-variant image generation (no critique) — rejected: wasteful, 2 winners is sufficient for A/B testing
- Reuse first storyboard frame — rejected: user specified separate from storyboard

**Nano Banana Pro camera variants by style**:

| Style | Camera | Lens | Lighting |
|-------|--------|------|----------|
| Cinematic | Sony A7III | 85mm f/1.4 | Golden hour + rim light |
| Dramatic | Canon EOS R5 | 50mm f/1.2 | Narrow beam spotlight |
| Mysterious | Hasselblad X1D | 45mm f/3.5 | Low-key, deep shadows |
| Confrontational | Sony A7III | 35mm f/2.8 | Hard flash, high contrast |
| Emotional | Kodak Portra 400 | 50mm f/1.4 | Soft diffused, warm tones |

**Self-critique scoring**: click appeal (1-10), emotional impact (1-10), visual clarity (1-10). Top 2 winners selected. Improvements suggested and applied before final generation.

## R4: Pipeline Wiring Strategy

**Decision**: `refine_script.py` as step 1b in `run_agency.py`, right after `automate_all.py`. Existing runs without `refine` key auto-skip (backward compatible).

**Rationale**: Refinement must happen before voice generation (step 2) because the refined script is what gets converted to speech. The `pipeline.json` state machine pattern already supports adding new keys — `.get("refine", False)` returns `False` for missing keys.

**Alternatives considered**:
- Run refinement inside `automate_all.py` — rejected: violates single-responsibility, harder to rerun independently
- Add as step 2 (after voice) — rejected: voice should use refined script, not raw translation
- Separate orchestrator — rejected: over-engineering, `run_agency.py` already handles the pipeline

**Backward compatibility**: If `"refine" not in state` (existing pipeline.json), set `state["refine"] = True` to skip. New runs get `refine: False` by default.

## R5: Config Extension

**Decision**: Add `THUMBNAIL_MODEL=Pro` to `gemini_model.txt`. Read via `get_config_value("THUMBNAIL_MODEL", "Pro")` with fallback to `REFINE_MODEL`.

**Rationale**: Thumbnails need dialect nuance for concept extraction and text overlay. Pro is appropriate. Fallback to `REFINE_MODEL` avoids redundant config if both use the same model.

**Alternatives considered**:
- Reuse `SCRIPT_TRANSLATOR_MODEL` — rejected: different purpose, confusing naming
- No config (hardcode Pro) — rejected: violates Principle IX (YAGNI), user may want to experiment
- Separate model for concept extraction vs critique — rejected: over-engineering, same model works for both
