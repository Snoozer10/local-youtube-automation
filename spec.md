# Spec: Robust Dynamic Harmonious Video Pipeline (Wayfinder Map #4)

*Source: synthesized from 7 wayfinder decisions (map #4), CONTEXT.md glossary, ADRs 0001-0005, audit on research/audit-sync-quality-pipeline. No interview; do not re-grill.*

---

## Problem Statement

As a creator running the YouTube Al-Daheeh automation pipeline, I get low-quality videos where images drift from the spoken audio and the visuals feel static or literal. The pipeline today uses split timestamp files, fixed duration buckets, and a single static Ken Burns zoom; quality falls back inconsistently and any rendered text in images collides with subtitles. I need the whole chain — from word timestamps to final encode — to stay in sync, stay sharp at 1440p with proxies, move with the speaker's cadence, show the *meaning* of the sentence not just its words, and never burn text into the frame.

## Solution

A hand-off ready spec that makes the pipeline **robust, dynamic, and harmonious** by unifying sync, locking quality, and making motion and prompts follow the speaker:

- One canonical **timeline** (`words[]` append-only + derived `spans[]` where `spans[i].start == words[k].start`) replaces split files; legacy files become read-only **shims** with `.sha256` sidecars. Beats are candidates, **snaps** go to the nearest VAD pause `>=0.35s`, spans hard-capped `2.5-4.5s` with pause-guarded merges.
- A locked **ladder** always renders `1440p master` + `1080p/720p proxies` in one `split→scale` graph with `VBV 35M/70M`, `QSV_LOOKAHEAD=0`, `CFR`, zero-drift `frame_count == round(duration*30)`.
- A meaning-based **visual_prompt** per span from a `3-span` window, structured 8-part JSON with `continuity_id`, missing fields fallback to preset; deterministic **negative_prompt** bans text; English-only diffusion with 2-repair transliteration; semantic `SUMMON_ASSET` continuity via local embeddings.
- A **prototype-proven** dynamic Ken Burns per **span** (4-direction pool, `1.06-1.10` scale, smoothstep, `1.12` upscale) with strict CFR.
- A three-layer **text_gate** (prompt ban + validator regex + local OCR `60/2/1%` one retry) on the Flow path only.
- A locked **audio chain** (`YouTube_Voice_Optimizer`, Named Pipes, `-14 LUFS/-1 dBTP/LRA 11`) as fixed input feeding the timeline.

Seams and contracts below keep the change to two high seams; existing pure seams are reused.

---

## Seams for Testing (preferred, highest possible)

**Seam 1 — Timeline seam (highest, primary).** Input: Whisper word timestamps + VAD pauses → Output: `timeline.json` (`words` + `spans`). Existing pure seams reused: validator `flatten / enforce_arabic / purge`, sanitizer tiers, manifest atomic save. Ideal single seam — validates sync without Flow or FFmpeg. Propose to add `VAD_SNAP_THRESHOLD` and `WAVEFORM_ALIGN_WINDOW_MS` as config seams here, not new code.

**Seam 2 — Compilation seam (secondary, for quality).** Input: `timeline.json` spans + image assets → Output: video files via shared filter graph + ladder. Existing seams: `frame_count` derivation, `AudioSyncAligner` window, `filter_complex_script` generation, encoder fallback probe.

Fewer seams is better — one (timeline) is ideal; two is acceptable because quality needs encode. No new low-level seams (no per-pixel mocks). Confirm these two cover your expectation; new seams only if probe shows gap.

---

## User Stories

1. As a viewer, I want images to change exactly when the speaker pauses for breath, so that cuts feel natural, not arbitrary.
2. As a viewer, I want no image to stay on screen less than a breath nor linger past a thought, so that pacing feels human (2.5-4.5s).
3. As a viewer, I want the same person to look the same when they reappear minutes later, so that I don't get confused by a new face.
4. As a viewer, I want no burned-in subtitles or watermarks on generated images, so that subtitles remain readable and the frame stays clean.
5. As a viewer, I want motion to vary (zoom in, zoom out, pan) with smooth easing, so that the video feels directed, not static.
6. As a viewer, I want 1440p archival quality plus crisp 1080p/720p proxies, so that playback is sharp on any device.
7. As a viewer, I want no stutter or AV drift even on long videos, so that audio and images stay locked to the last frame.
8. As a creator, I want the visual to show the *meaning* of the sentence (“a metaphor for betrayal”), not just its literal words, so that images feel editorial.
9. As a creator, I want style to stay consistent across a video when the LLM omits lighting, so that broadcast look doesn't drift.
10. As a creator, I want Arabic speech to stay in audio while prompts stay English, so that diffusion doesn't render Arabic glyphs.
11. As a creator, I want a span that would be 2.0s to not merge across a real breath, so that visual breaths are preserved.
12. As a creator, I want the first image of a chunk to still have context, so that chunk boundaries don't produce blind prompts.
13. As a creator, I want the prompt not to invent lighting when none is cued, so that hallucinations don't enter diffusion text.
14. As a creator, I want the next span to snap to the *nearest* qualifying pause, not the first, so that drift doesn't accumulate rightward.
15. As an operator, I want one canonical `timeline.json` to inspect, so that I don't chase three divergent timestamp files.
16. As an operator, I want legacy timestamp files to auto-regenerate as read-only shims with a staleness hash, so that old tools keep working but can't be trusted when stale.
17. As an operator, I want deprecated pause keys to warn once and map to the single threshold, so that old configs migrate gracefully.
18. As an operator, I want a rejected image (text detected) to be retryable once with a stronger ban before marking failed, so that throughput stays high without infinite loops.
19. As an operator, I want a failed chunk to dump a debug artifact with OCR boxes, so that I can diagnose why it failed.
20. As an operator, I want encoder fallback (`qsv→nvenc→libx264`) to be probed before encode and logged, so that I know which path was used.
21. As an operator, I want post-encode validation to check `frame_count` vs `round(duration*30)` and duration vs audio ±0.02s, so that drift is caught immediately.
22. As an operator, I want the pipeline to wipe Audacity session data before DSP and always `SelectAll:` before effects, so that runs are deterministic.
23. As an operator, I want Word timestamps to be append-only after Whisper emits, so that a span-derivation fix can't corrupt the source stream.
24. As an operator, I want the same timeline to drive both Flow generation and final compilation, so that there is no second source of truth.
25. As a pipeline, I want to know whether to render proxies always or on-demand, so that I don't branch unpredictably — always render both proxies.
26. As a pipeline, I want Ken Burns scale to be `1.06-1.10` derived from span duration, so that longer thoughts get slightly more motion but never exceed broadcast limits.
27. As a pipeline, I want the shared filter graph to split and scale in one invocation, so that master and proxies stay frame-identical.
28. As a QA, I want a harness to measure AV sync drift and image relevance, so that “harmonious” can be scored, not guessed. _(Deferred to implementation follow-up; will be a separate ticket with its own spec.)_

---

## Implementation Decisions

*No file paths or code snippets except the prototype-derived state shape below. Modules are named logically, not by path.*

- **Canonical timeline:** Introduce unified artifact holding `words[]` (text, start, end, pause_after) append-only + derived `spans[]` (index, start, end, duration, frame_count, text, prompt_slice, pause_before/after). Invariant `spans[i].start == words[k].start`. Legacy timestamp artifacts (`image_timestamps`, `timestamped_transcript`, `subtitle_chunks`) become read-only shims atomically written (`tmp + replace + fsync`) with `.sha256` sidecar; consumer must refuse stale shim. The sidecar is `sha256(timeline.json)`, written by the timeline derivation module and verified by every shim consumer before read. Shims for `image_timestamps.txt` emit `[MM:SS]` format matching the existing `parse_image_timeline` consumer — `MM:SS` is derived from `span.start` seconds, truncated (not rounded), zero-padded to 2 digits. Deprecated keys `IMAGE_PAUSE_SPLIT`/`SILENCE_SPLIT_GAP` alias to `VAD_SNAP_THRESHOLD=0.35s` with once-per-process deprecation warning, removed in two releases. If both a deprecated alias and `VAD_SNAP_THRESHOLD` are set, `VAD_SNAP_THRESHOLD` wins; deprecated aliases are ignored when the canonical key is present. Deprecation warning fires regardless. `WAVEFORM_ALIGN_WINDOW_MS=20` is distinct (sample-level alignment) and not aliased.

- **Beat/span discipline:** Beats are candidates from semantic sentence/clause boundaries; spans are committed images. Snaps go to *nearest* pause `>=0.35s` (symmetric, not greedy left-to-right). Duration hard-capped `2.5-4.5s`: if semantic sentence >4.5s, split at strongest cadence mark inside window; if <2.5s, merge only if `pause_after < 0.35s` between candidates (preserves visual breath). Merge/split logic lives in timeline derivation, not in validator.

- **Ladder:** Lock archival master `2560x1440@30` `yuv420p` ( `nv12` for QSV) `high@5.1` `VBV 35000k/70000k` `QSV_LOOKAHEAD=0` `CFR` `CHUNK_SIZE 20`. Fallback chain `h264_qsv → h264_nvenc → libx264 veryfast crf17 tune animation` probed via encoder list. Always render ladder `[1440p master, 1080p proxy, 720p proxy]` in one invocation via shared `filter_complex_script` (`split=3 → scale=-2:height:flags=lanczos`) where Ken Burns is applied before split. Threads `4` master / `2` per proxy, atomically written.

- **Prompt extraction (3-span, 8-part, English-only, semantic continuity):** Planner receives `timeline.json` spans; per span it builds a 3-span window (current ±1, ~10s) padded at chunk boundaries with `pause_before`/`pause_after` from timeline; whole-paragraph context is rejected. LLM emits structured JSON `{subject, action, setting, mood, lighting, composition, style, negative_prompt, continuity_id}`; only fields with signal filled, missing → preset default from `STYLE_DNA_TEXT` in `prompt_planner.py` at flatten time. Prompt output is English-only diffusion text; LLM reads Arabic source but must not emit `[\u0600-\u06FF]`; validator `enforce_arabic` rejects Arabic script → one repair with explicit English-only reinforcement → transliteration fallback then `ChunkPlanningError` after 2 repairs. Chunking `FLOW_CHUNK_SIZE 15` spans = one ephemeral Gemini session, jitter `1.5-3s`, `GEMINI_SESSION_RESET_THRESHOLD 100`, 2 repairs → `debug/malformed_chunk`.

  *Prototype-derived shape (trimmed, decision-rich):*
  ```ts
  // span motion assignment — from prototype/ken-burns-per-beat
  type SpanMotion = { dir: 'ZI'|'ZO'|'PL'|'PR', scale: number, easing: 'smoothstep' }
  scale = clamp(1.06 + (duration - 2.5)/2 * 0.04, 1.06, 1.10) // duration 2.5-4.5
  smoothstep = t => t*t*(3-2*t) // t in [0,1]
  frame_count = round(duration * 30) // CFR 30, zero-drift, clip0 at 0, last takes remainder
  dir = pool[(index) % 4] // round-robin, stable per span, reproducible
  ```

- **Continuity:** Per-chunk subject table built from prior `subject` fields; local embedding similarity fallback (`multilingual-e5`/`bge-m3`, cosine `>=0.78`) widens to whole chunk; if nearest prior ≥ threshold emit `SUMMON_ASSET` with `@asset` chip else fresh; `±2` is soft hint, not hard cutoff. `@asset` memo (`flow_assets`) reused.

- **Negative injection:** Expanded strict list injected deterministically by validator `purge_subtitle_phrases` + `flatten`, not LLM-generated: `no text, no subtitles, no letters, no watermark, no signature, no caption, no typography, no calligraphy, no vector, no cel-shading, no 3px, no burned-in subtitles, no lower thirds, no on-screen text` (poster/chart excluded as rare). Prevents prompt-level evasion and keeps repair deterministic.

- **Text gate:** Three layers on Flow path only (script path excluded, existing `>20KB`/`>50KB` screenshot `>100px` PNG/JPEG magic gates stay): (1) deterministic negative, (2) validator regex, (3) post-generation local OCR (`pytesseract` if present else MSER/edge heuristic) reject if `len>=2` and `confidence>=60` and `bbox_area>=1%` of image (`OCR_CONFIDENCE 60`, `MIN_TEXT_LEN 2`, `MIN_BBOX 0.01`). On reject: mark `FAILED`, dump debug with `ocr_boxes`, one retry with strengthened negative `ABSOLUTELY NO TEXT, NO LETTERS` then final `FAILED`.

- **Ken Burns per span:** 4-direction pool round-robin per span index, scale per duration as above, smoothstep easing, `upscale 1.12`, strict `round(duration*30)` CFR 30, zero-drift cumulative `start_frame`, clip0 at 0. Prototype `prototype-ken-burns-per-beat.html` proves no jitter across `QSV(nv12)/NVENC/CPU(yuv420p)` — same frame counts, fallback only changes `pix_fmt`.

- **Audio chain locked as fixed input:** `YouTube_Voice_Optimizer` macros via `%APPDATA%\audacity\macros`, wipe `SessionData`/`AutoSave` before open, Named Pipes `ToSrvPipe/FromSrvPipe` `\n` + empty-line, always `SelectAll:` before DSP, lossless Wave stitch via `stitch_chapters`, `EBU R128 -14 LUFS / -1 dBTP / LRA 11`. `TTS_MODEL gemini-2.5-pro-preview-tts` voice `Achird` `1.1` reload `40` unchanged; pause-aware transcript feeds timeline `words`, timestamps untouched by spelling corrector (`difflib` with `autojunk=False`).

- **Pipeline contracts:** `pipeline_manifest` remains state machine (`PENDING/VERIFIED/REPAIRED/FAILED` chunks, `PENDING/IN_PROGRESS/COMPLETED/FAILED` phases) with `script_hash=SHA256`; `master_roadmap.jsonl` is planning input (25-row pages for Gemini paging, 7-cell pad `NONE`, 2 repairs) — not sync source. Timeline is sync output; shims derive from timeline only. Document boundary to avoid trust ambiguity; shims deleted in `v6.0` (current 4.0.0 + 2 minor releases).

---

## Testing Decisions

*Only test external behavior, not implementation details. Existing seams preferred.*

- **What makes a good test:** Assert on observable artifacts (`timeline.json` spans, video frame counts/durations, prompt bans, OCR reject) not on internal helpers. A test that knows about `SelectedPipes` pipe names is brittle; a test that asserts `frame_count == round(duration*30)` and `total_frames == round(sum durations*30)` is durable. Use pure seams where possible.

- **Modules under test:**
  - Timeline seam (primary): word → span derivation, nearest snap, `2.5-4.5s` cap, pause-guarded merge, append-only words, shim generation + `.sha256` staleness, deprecated alias warning. Prior art: audit's 9 drift sources as regression fixtures; existing `tests/unit/test_timeline` pattern if present, else new `test_timeline` at seam.
  - Compilation seam (secondary): shared `split→scale` graph generates `frame_count`, ladder renditions share counts, encoder probe, VBV/ladder params, `QSV_LOOKAHEAD=0` enforcement. Prior art: `ffmpeg lavfi` integration tests (need real `ffmpeg -encoders`); unit tests mock `ffprobe` duration check.
  - Prompt seam: 3-span windowing, 8-part JSON → `flatten` with preset fallback, `enforce_arabic` English-only, `purge_subtitle_phrases` negative injection, `continuity_id` subject table with embedding threshold `0.78`. Prior art: validator pure utils tests (`flatten`, `purge`, `enforce_arabic`) already exist — reuse.
  - Text gate seam: `>20KB/PIL>100px/magic` + OCR `60/2/1%` one-retry, `debug/malformed_chunk` dump. Prior art: `flow_image_generator` tiered fetch tests; add OCR gate as integration with `pytesseract` stub or MSER fallback.

- **Prior art reused:** `pytest -v --strict-markers --tb=short` via `tests/conftest.py` (repo root on sys.path); `ruff` + `mypy --strict` as quality gates; integration tests require real `ffmpeg`; `filter_complex_script` >1K already tested via temp file indirection.

---

## Out of Scope

- Changing TTS model (`gemini-2.5-pro-preview-tts` voice `Achird`) or temperature/reload — audio is fixed input.
- Adding cloud SDKs (`google-generativeai`/`openai`/`anthropic`) — CDP `127.0.0.1:9222` only.
- New language beyond Arabic `30/70 Fusha/Amiya` + English sources.
- UI/dashboard rebuild — pipeline spec only, not operator UX.
- Flow vs script path deprecation beyond noting Flow-only scope (script path stays unused, not removed).
- Thumbnail harmonization, full evaluation harness, cost/perf tuning of LLM batching — deferred to implementation follow-up (remain in Not yet specified as future tickets, not blocking spec).

---

## Further Notes

- Wayfinder map #4 is 7/7 decisions closed (100% sub_issues completed) — Research Audit (branch `research/audit-sync-quality-pipeline`), Canonical timeline (0001), Ladder (0002), Prompts (0003), Ken Burns prototype (branch `prototype/ken-burns-per-beat`), Text gate (0004), Audio DSP (0005). Glossary in `CONTEXT.md` now holds 11 terms; `docs/agents/domain.md` is consumer guide. Do not re-grill — synthesize from closed tickets.

- Implementation should start tracer-bullet after this spec: `to-tickets` will split into tickets with native GitHub blocking edges, worked `blockers-first`, each `implement` drives `tdd` internally then `code-review` (Standards+Spec) before commit. Keep `grill→spec→tickets` in one unbroken window until `to-tickets`; each `implement` starts fresh.

