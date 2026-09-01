# 0004: Text/subtitle collision guard (prompt + validator + OCR gate)

Prompt text collisions (burned-in subtitles, lower thirds, typos) cause harmonious failures. We had only `purge_subtitle_phrases` + `>20KB/PIL` gates, no rendered-text detection.

## Decision

Three-layer guard, all on `flow_image_generator.py` path (script_image_generator excluded):

1. **Prompt-level ban (deterministic, validator-injected)**: `negative_prompt` expanded to `no text, no subtitles, no letters, no watermark, no signature, no caption, no typography, no calligraphy, no vector, no cel-shading, no 3px, no burned-in subtitles, no lower thirds, no on-screen text` — injected by `validator.purge_subtitle_phrases` + `flatten`, not LLM-generated.
2. **Validator regex gate**: `purge_subtitle_phrases` runtime regex catches creative paraphrases missed by negative prompt; failure → `REPAIRED` then `FAILED` dump `debug/malformed_chunk_N.json`.
3. **OCR gate (post-generation, local-only, no cloud SDK)**: After existing gates (`>20KB`/`>50KB` screenshot, `PIL >100px`, PNG `89 50 4E 47`/JPEG `FF D8`), run local OCR (`pytesseract` if available, else fallback to lightweight MSER/edge heuristic). Reject if OCR finds text `len>=2` chars with `confidence >=60` and `bbox_area >=1%` of image. Thresholds: `OCR_CONFIDENCE_THRESHOLD=60`, `OCR_MIN_TEXT_LEN=2`, `OCR_MIN_BBOX_AREA_RATIO=0.01`. On reject: mark chunk `FAILED`, dump `debug/malformed_chunk_N.json` with `ocr_boxes`, `confidence`, `image_path`; one retry with strengthened negative `"ABSOLUTELY NO TEXT, NO LETTERS"` then final `FAILED`.

## Considered Options

- **No OCR, negative prompt only**: Rejected: Flow still renders text despite negative prompt (observed CORS/tainted canvas fallbacks), purge regex alone misses rendered glyphs.
- **Cloud Vision API**: Rejected: violates CDP-only, no cloud SDKs constraint.
- **Heavy EasyOCR/PaddleOCR everywhere**: Rejected: throughput hit; use `pytesseract` lightweight first, fallback heuristic keeps pipeline robust offline.

## Consequences

- Keeps existing gates; OCR runs only after they pass, so cost limited to valid images.
- One retry budget preserves pipeline throughput; second failure stays `FAILED` for manual review, not infinite loop.
- Side effect: adds `tesseract` binary as optional external (winget `tesseract-ocr`) but not hard-required due to heuristic fallback.

Status: accepted
