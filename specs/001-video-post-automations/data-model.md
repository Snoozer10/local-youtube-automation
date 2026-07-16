# Data Model: Post-Production Automations (P1)

**Date**: 2026-07-11

## Entities

### Refined Paragraph

Represents a single paragraph after Gemini refinement.

| Field | Type | Description |
|-------|------|-------------|
| `index` | integer | 1-based position in the script |
| `original_text` | string | Arabic text from `final_output.txt` before refinement |
| `refined_text` | string | Arabic text after Gemini refinement |
| `status` | enum | `pending`, `refined`, `failed` |

**State transitions**: `pending` → `refined` (on successful Gemini response) | `pending` → `failed` (on safety block, triggers retry)

### Refinement Checkpoint

Persisted to `youtube_runs/<Title>/refine_checkpoint.json`. Deleted on successful completion.

| Field | Type | Description |
|-------|------|-------------|
| `refined_paragraphs` | string[] | Array of refined Arabic text strings, indexed by position |

**Resume logic**: `len(refined_paragraphs)` = next paragraph index to process. Rerun loads checkpoint, skips completed paragraphs.

### Thumbnail Concept

Extracted from script by Gemini in Phase 1 of thumbnail pipeline.

| Field | Type | Description |
|-------|------|-------------|
| `emotion` | enum | `fear`, `wonder`, `anger`, `curiosity`, `excitement`, `shock`, `nostalgia` |
| `scene` | string | One-sentence visual description |
| `text_overlay` | string | Short Arabic text (3-5 words) for thumbnail |
| `style` | enum | `cinematic`, `dramatic`, `mysterious`, `confrontational`, `emotional` |

**Constraints**: 5 concepts per video. Each must target a different emotion.

### Nano Banana Pro Prompt

Structured prompt for Gemini image generation, derived from Thumbnail Concept.

| Field | Type | Description |
|-------|------|-------------|
| `subject` | string | Scene description from concept |
| `subject_details` | string | Expression, skin texture, focus details |
| `camera_specifications` | string | Camera body + lens + aperture + ISO + shutter + lighting |
| `environment` | string | Contextually appropriate background |
| `mood` | string | Emotional tone keywords |
| `text_overlay` | object | `{text, position, style}` |
| `negative` | object | `{content: string[], style: string}` |
| `aspect_ratio` | string | `"16:9"` (YouTube standard) |
| `resolution` | string | `"8K, ultra-detailed, photorealistic"` |

### Thumbnail Critique

Output from Gemini self-critique loop in Phase 3.

| Field | Type | Description |
|-------|------|-------------|
| `scores` | object[] | Array of `{index, click_appeal, emotional_impact, visual_clarity, total}` |
| `winners` | int[] | Indices of top 2 prompts |
| `improvements` | object | Map of index → improvement suggestion |

### Pipeline State

Extended existing `pipeline.json` with new `refine` key.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `refine` | bool | `false` | Arabic script refinement complete |
| `voice` | bool | `false` | Voice synthesis complete |
| `audacity` | bool | `false` | Audio polish complete |
| `stitch` | bool | `false` | Audio stitching complete |
| `transcribe` | bool | `false` | Whisper timestamping complete |
| `spellcheck` | bool | `false` | Transcript spelling complete |
| `images` | bool | `false` | Image generation complete |
| `fixtimes` | bool | `false` | Timestamp fixing complete |
| `video` | bool | `false` | Video compilation complete |

### Config Keys

New keys added to `gemini_model.txt`.

| Key | Default | Description |
|-----|---------|-------------|
| `REFINE_MODEL` | `Pro` | Gemini model for script refinement (already exists) |
| `THUMBNAIL_MODEL` | `Pro` | Gemini model for thumbnail concept extraction + critique |

## File Relationships

```
final_output.txt
    ↓ (input)
refine_script.py + refine_prompt.txt
    ↓ (output)
refined_script.txt + refined_script.docx
    ↓ (input)
generate_thumbnail.py + Nano Banana Pro prompts
    ↓ (output)
thumbnails/variant_1.png, variant_2.png
```

## Validation Rules

- `refined_paragraphs` array length must equal original paragraph count on completion
- `refined_text` must not be empty (Gemini must return non-empty refinement)
- `scores[].total` = `click_appeal + emotional_impact + visual_clarity` (max 30)
- `winners` array length must be exactly 2 (TOP_N = 2)
- `THUMBNAIL_MODEL` must match an available Gemini model name (Flash, Pro, etc.)
