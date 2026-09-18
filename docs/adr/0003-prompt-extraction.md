# 0003: Meaning-based visual prompt extraction (3-span, 8-part, English-only, semantic continuity)

We had literal-word prompts causing low relevance and text collisions. We lock meaning-based extraction: LLM reads sentence meaning from 3-span window (current ±1, ~10s) with `pause_before`/`pause_after` padding at chunk boundaries (not whole paragraph, not bloat), outputs structured 8-part JSON, validator deterministically injects negative prompt and English-only gate, continuity via semantic subject tracking.

## Considered Options

- **Whole-paragraph context**: 30s window hallucinates structure. Rejected: dilutes metaphor, bloats prompt.
- **Freeform diffusion text**: Rejected: breaks broadcast style consistency across chunks, fails 10-point audit; no preset fallback.
- **Expanded negative including poster/chart**: Rejected: rare failure modes, model rarely renders poster unless asked; keep `purge_subtitle_phrases` as runtime regex gate for creative paraphrases.
- **Literal ±2 spans for SUMMON_ASSET**: Rejected: same character reappears 5-8 spans later, literal "sheikh" ↔ "imam" misses coreference.

## Decision

- **Context (Q1)**: 3-span window, chunk-boundary spans pad with `pause_before`/`pause_after` from `timeline.json`.
- **Schema (Q2)**: Lock 8-part `subject, action, setting, mood, lighting, composition, style, negative_prompt` + `continuity_id`; LLM fills only fields with signal, missing → preset default at `flatten_visual_prompt_to_diffusion_text` time.
- **Negative (Q3)**: Expanded strict: `no text, no subtitles, no letters, no watermark, no signature, no caption, no typography, no calligraphy, no vector, no cel-shading, no 3px, no burned-in subtitles, no lower thirds, no on-screen text` (exclude poster/chart); injected by validator, not LLM; `purge_subtitle_phrases` remains runtime gate.
- **Arabic gate (Q4)**: Diffusion text English-only; LLM reads Arabic source but outputs English. Regex `[\u0600-\u06FF]` reject → one repair with "OUTPUT ENGLISH ONLY" reinforcement → fallback transliteration (e.g., `الكتاب`→`al-kutub`) before `ChunkPlanningError`; budget 2 repairs.
- **Continuity (Q5)**: Per-chunk subject table from prior `subject` fields, embedding similarity fallback (`multilingual-e5`/`bge-m3` local, cosine ≥0.78) widened to whole chunk; if nearest prior ≥ threshold emit `SUMMON_ASSET` `@asset` chip, else fresh; ±2 is soft hint. Ephemeral Gemini per `FLOW_CHUNK_SIZE 15` spans, jitter `1.5-3s`, `GEMINI_SESSION_RESET_THRESHOLD 100`, 2 repairs → `debug/malformed_chunk_N.json`.
- **Cross-cutting**: 8-part needs `continuity_id` for tracker; negative injected by validator keeps repair deterministic; English-only gate + 3-span window belong in planner input template, not validator.

## Consequences

- Style consistency via `STYLE_DNA_TEXT` and `FLOW_ASSET_PRESETS` in Python modules, not `visual_style.txt` (which is legacy and used only by `script_image_generator.py`); validator owns negative + Arabic gate deterministically.
- Subject tracking handles coreference and chapter-scale reappearance without cloud SDKs.
- Chunk-boundary padding prevents context-blind first spans.

Status: accepted
