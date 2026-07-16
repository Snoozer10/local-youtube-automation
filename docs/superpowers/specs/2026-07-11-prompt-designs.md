# Prompt Designs: Script Refinement + Thumbnail Generation

Date: 2026-07-11
Status: Approved
Scope: P1 — refine_script.py prompt + thumbnail prompt pipeline

---

## 1. Script Refinement Prompt (`refine_prompt.txt`)

### Approach: Two-Turn Interaction (Setup + Refine)

Matches existing `prompt_phase3.txt` pattern. Turn 1 establishes rules, Turn 2 performs refinement.

### Turn 1 — Setup (sent once per video, Gemini acknowledges)

```
You are a Khaleeji White Dialect Script Editor. Your job: refine an already-translated Arabic script for natural fluency, dialect consistency, and audience engagement.

RULES:
1. DIALECT ENFORCEMENT: Saudi Khaleeji "White" dialect. Use "مو" (not "مش"), "كذا" (not "كده"), "يعني" freely. Avoid Egyptian, Levantine, or Gulf-internal variations.
2. FLUENCY PASS: Fix literal translation artifacts. Arabic should read as if originally written in Arabic, not translated. Short sentences, natural rhythm.
3. RHYTHM MANDATE: Short, Short, Long, Short, rhetorical Question every 4-6 sentences. Vary sentence length for TTS prosody.
4. PRESERVE MEANING: Do NOT add, remove, or alter factual content. You are polishing, not rewriting.
5. TTS-FRIENDLY: Use Arabic commas (،) for breath pauses. Sparse tashkeel only on genuinely ambiguous words. No excessive diacritics.
6. FIRST PARAGRAPH = HOOK: The opening must grab attention in the first 15 seconds. Start mid-action, with a provocative question, or a bold claim. No slow buildups.
7. LAST PARAGRAPH = OUTRO CTA: End with a compelling call-to-action — subscribe, comment their opinion, or tease the next video. Make it feel natural, not corporate.

Reply with "UNDERSTOOD" when ready to refine.
```

### Turn 2 — Refinement (per paragraph)

```
Refine paragraph {i} of {total}. Return ONLY the refined Arabic text, no commentary, no translation, no explanation.

{paragraph_text}
```

### Behavior

- Paragraph 1: HOOK rule (6) applied
- Last paragraph: OUTRO CTA rule (7) applied
- Middle paragraphs: Rules 1-5 only
- Checkpoint after each paragraph to `refine_checkpoint.json`
- Output: `refined_script.txt` (+ `.docx`)

---

## 2. Thumbnail Prompt Pipeline (`generate_thumbnail.py`)

### Approach: Creative Prompt + Self-Critique Loop

5 concepts → Nano Banana Pro prompts → Gemini critique → refine winners → 2 final images.

### Phase 1 — Concept Extraction (Gemini text turn)

```
Analyze this video script and extract 5 thumbnail concepts. For each, provide:
- EMOTION: The core emotion (fear, wonder, anger, curiosity, excitement)
- SCENE: A single visual moment that captures the video's hook
- TEXT_OVERLAY: Short Arabic text (3-5 words) for the thumbnail
- STYLE: One of: cinematic, dramatic, mysterious, confrontational, emotional

SCRIPT:
{refined_script_excerpt}

Return JSON array of 5 objects with keys: emotion, scene, text_overlay, style
```

### Phase 2 — Nano Banana Pro Prompt Generation (per concept)

Structured prompt per nano-banana-pro-prompting skill architecture:

```json
{
  "subject": "{scene_description}",
  "subject_details": "emotional expression: {emotion}, high detail facial features, photorealistic skin texture",
  "camera": {
    "body": "Sony A7III or Canon EOS R5 (varies per variant)",
    "lens": "85mm f/1.4 for portraits, 35mm f/2.8 for scenes",
    "aperture": "f/1.4 - f/2.8",
    "iso": "100-400",
    "angle": "slightly low angle for authority, eye level for intimacy",
    "shot_type": "close-up for emotion, medium for scene"
  },
  "environment": "contextually appropriate to script topic",
  "lighting": "dramatic three-point OR golden hour OR narrow beam spotlight (varies per style)",
  "mood": "{emotion}",
  "text_overlay": {
    "text": "{arabic_text}",
    "position": "bottom third or top left",
    "style": "bold white with shadow, or gold accent"
  },
  "negative": {
    "content": ["Multiple characters", "blurry", "low resolution"],
    "style": "No watermarks, no AI artifacts, no text errors"
  },
  "aspect_ratio": "16:9",
  "resolution": "8K, ultra-detailed"
}
```

**Camera variants by style:**

| Style | Camera | Lens | Lighting |
|-------|--------|------|----------|
| Cinematic | Sony A7III | 85mm f/1.4 | Golden hour + rim light |
| Dramatic | Canon EOS R5 | 50mm f/1.2 | Narrow beam spotlight |
| Mysterious | Hasselblad X1D | 45mm f/3.5 | Low-key, deep shadows |
| Confrontational | Sony A7III | 35mm f/2.8 | Hard flash, high contrast |
| Emotional | Kodak Portra 400 (film) | 50mm f/1.4 | Soft diffused, warm tones |

### Phase 3 — Self-Critique Loop

```
You generated 5 thumbnail prompts for a YouTube video about {topic}.
Here are the 5 prompts: [all 5 prompts]

Rate each on: click appeal (1-10), emotional impact (1-10), visual clarity (1-10).
Pick the TOP 2 winners and explain why.
For the top 2, suggest one improvement each.
Return JSON with scores, winners, and improvements.
```

### Phase 4 — Refine & Generate

- Take top 2 prompts
- Apply suggested improvements
- Send to Gemini image generation
- Output 2 final thumbnails to `youtube_runs/<Title>/thumbnails/`

---

## 3. Config Changes

| File | Key | Value | Purpose |
|------|-----|-------|---------|
| `gemini_model.txt` | `REFINE_MODEL` | `Pro` | Already added by speckit |
| `gemini_model.txt` | `THUMBNAIL_MODEL` | `Pro` | New — model for thumbnail concept extraction + critique |

---

## 4. File Map

| File | Action | Purpose |
|------|--------|---------|
| `refine_prompt.txt` | Create | Two-turn refinement prompt |
| `refine_script.py` | Create | Paragraph-level refinement via CDP |
| `generate_thumbnail.py` | Create | 5-variant thumbnail pipeline |
| `gemini_utils.py` | Create (FR-008) | 5 extracted Gemini helpers |
| `run_agency.py` | Edit (FR-007) | Add refine as step 1b |
| `gemini_model.txt` | Edit | Add THUMBNAIL_MODEL |

---

## 5. Validation

- [x] Refinement prompt handles all 3 pain points (artifacts, dialect, hook/outro)
- [x] Thumbnail prompts follow nano-banana-pro-prompting architecture
- [x] Self-critique loop leverages Gemini judgment for quality
- [x] Camera specs vary by thumbnail style (not one-size-fits-all)
- [x] Negative prompts included for artifact suppression
- [x] 16:9 aspect ratio for YouTube thumbnails
- [x] Both prompts are testable independently
