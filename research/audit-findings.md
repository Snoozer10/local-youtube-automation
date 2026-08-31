# Research Audit: Sync and Quality Pipeline — Ticket #5

**Branch:** `research/audit-sync-quality-pipeline`  
**Scope:** `image_generation/` root — files listed in #5  
**Date:** 2026-08-31  
**Mode:** facts only, no decisions — every claim cites `file:line`

---

## 1. Domain docs check (CONTEXT.md / docs/adr)

| Check | Result | Evidence |
|-------|--------|----------|
| `CONTEXT.md` at repo root | **absent** | `ls CONTEXT.md` → not found; `docs/agents/domain.md:7` says read CONTEXT.md or CONTEXT-MAP.md if exists |
| `docs/adr/` | **absent** | `ls docs/adr` → not found; only `docs/agents/` exists (`domain.md`, `issue-tracker.md`, `triage-labels.md`) |
| `docs/agents/domain.md` | exists 3 files | `docs/agents/domain.md:1` — single-context guidance |

> Implication for #5: no glossary/ADR to contradict; audit uses code as source of truth.

---

## 2. Sync anchor and canonical timeline

### 2.1 Canonical anchor

| Fact | Value | Citation |
|------|-------|----------|
| Sync anchor file | `image_timestamps.txt` — punctuated sentences with `[MM:SS]` or `[HH:MM:SS]` prefix | `faster_whisper_transcribe_audio.py:593-596` writes `image_timestamps.txt`; `transcribe_config.txt:26` comment says `image_timestamps.txt is sync anchor`; `compile_video.py:648` `parse_image_timeline` prefers `image_timestamps.txt` over `timestamped_transcript.txt` |
| Also written | `timestamped_transcript.txt` (duplicate of image timeline) | `faster_whisper_transcribe_audio.py:600-602` |
| SRT twins | `timestamped_transcript.srt` + `subtitle_chunks.srt` (same SRT content) | `faster_whisper_transcribe_audio.py:613-618` loop over two filenames |
| SRT enabled flag | `EXPORT_SRT=true` | `transcribe_config.txt:36`, `faster_whisper_transcribe_audio.py:29` default `True` |
| Timeline TXT flag | `EXPORT_TIMELINE_TXT=true` | `transcribe_config.txt:37`, `faster_whisper_transcribe_audio.py:30` |

### 2.2 How `image_timestamps.txt` is built (ASR → alignment → split)

| Stage | Fact | Citation |
|-------|------|----------|
| Whisper model default | `small`, language `ar`, beam `5`, VAD `true`, `min_speech_duration_ms 250` | `faster_whisper_transcribe_audio.py:19-23` DEFAULTS; `transcribe_config.txt:6-10` same |
| Whisper priming | slice `refined_script.txt`/`final_output.txt` to `INITIAL_PROMPT_MAX_WORDS=120` | `faster_whisper_transcribe_audio.py:22`, `214-230` `slice_initial_prompt`, `526-536` `read_initial_prompt` |
| VAD in transcribe call | `vad_filter=True`, `vad_parameters={"min_speech_duration_ms":250}` | `faster_whisper_transcribe_audio.py:560-561` |
| Device | forced CPU int8 (GPU path commented out) | `faster_whisper_transcribe_audio.py:410-419` `compute_type="int8"` |
| Alignment | `difflib.SequenceMatcher(None, script_norm, whisper_norm, autojunk=False)` — `autojunk=False` mandatory, only blocks `size>=2` become anchors | `faster_whisper_transcribe_audio.py:166-175` |
| Alignment interpolation | monotonic fix, `MIN_STEP=0.05` (50ms/word), leading gap evenly spread, monotonic enforcement `start <= prev_end +0.01` | `faster_whisper_transcribe_audio.py:263`, `268-293` |
| Sentence split trigger | commas `،,`, periods `.`, `!`, `؟?`, colons `:`, semicolons `؛;`, dashes `—-…` → `PUNCT_SPLIT_REGEX` | `faster_whisper_transcribe_audio.py:318` |
| Speaker tag split | `^(أبو\s+\w+|طنط\s+\w+|الراوي|المذيع|المقدم)\s*:` | `faster_whisper_transcribe_audio.py:320` |
| Split policy | punctuation **always** splits (max granularity for images); silence only merges if `duration < MIN_DURATION` | `faster_whisper_transcribe_audio.py:325-350` comment + logic |
| Silence handling | `SILENCE_SPLIT_GAP_SEC` default `0.55` in code vs `0.45` in DEFAULTS vs `0.40` config name — three values | `faster_whisper_transcribe_audio.py:35` DEFAULTS `0.45`; `faster_whisper_transcribe_audio.py:315` `get(...,0.55)` fallback; `transcribe_config.txt:29` `IMAGE_PAUSE_SPLIT_SEC=0.40` |
| Min fragment | `MIN_SENTENCE_DURATION_SEC` `0.8` default in code; not exposed in `transcribe_config.txt` (config exposes `IMAGE_MIN_DURATION_SEC` instead) | `faster_whisper_transcribe_audio.py:31` + `314` |
| Post-merge | only adjacent silence-gap fragments both `<MIN_DURATION` are merged | `faster_whisper_transcribe_audio.py:371-384` |

### 2.3 Drift sources (anchor ≠ render)

| Drift source | Mechanism | Citation |
|--------------|-----------|----------|
| **1. VAD vs image buckets mismatch** | VAD word timestamps drive `image_timestamps.txt`, but `transcribe_config.txt` image buckets (`2.2/3.5/4.8s`, `5-12 words`) are **not read by** `faster_whisper_transcribe_audio.py` — code uses `0.8s/0.45s` instead | `transcribe_config.txt:24-29` vs `faster_whisper_transcribe_audio.py:314-315` |
| **2. AudioSyncAligner snap** | compile-time waveform snap `±0.20s` to nearest silence trough (`window_ms 20`, threshold `400`) shifts cutpoints off transcript TS | `compile_video.py:739-802` `AudioSyncAligner`, `825-844` snap |
| **3. First-clip anchor** | `image_blocks[0]["sec"]=0.0` forces clip 0 to frame 0 covering intro dead-air before speech onset | `compile_video.py:816` |
| **4. Group <0.15s folding** | blocks within `0.15s` are grouped as multi-frame sets | `compile_video.py:835` |
| **5. Comedic weighting** | group_len 2 → `70/30`, 3 → `50/25/25`, else `1/N` — redistributes duration inside grouped TS | `compile_video.py:850-855` |
| **6. Zero-drift frame quantization** | `total_audio_frames = round(duration*30)` (CFR), per-clip `frame_count = round(duration*30)` then monotonic `start_frame`/`end_frame` with `end_frame = max(start+1, min(ideal_end, total-remaining))`; last clip takes remainder | `compile_video.py:873`, `884-898`, `build_ken_burns_filter:411` `force_original_aspect_ratio increase`, `fps_mode cfr:258` |
| **7. `correct_transcript_spelling.py` re-tokenization** | `SequenceMatcher` `replace` distributes proportionally `int((r_idx/len)*len(group))`; `insert` goes to nearest prior group — can shift words across TS boundaries without touching timestamps | `correct_transcript_spelling.py:130-158` |
| **8. `fix_timestamps.py` coercion** | folds `[HH:MM:SS]` → `[MM:SS]` via `total_min = h*60+m` (loses hour granularity); fallback `[00:00]` on no match | `fix_timestamps.py:50-58` |
| **9. Whisper time quantization** | word `start`/`end` from faster-whisper are float seconds; SRT uses integer ms math `round(seconds*1000)` | `faster_whisper_transcribe_audio.py:148-153` `format_srt_timestamp` |

---

## 3. Transcribe quality ladder (`transcribe_config.txt` + code defaults)

| Knob | Config value | Code default / fallback | File:line |
|------|--------------|-------------------------|-----------|
| `WHISPER_MODEL_SIZE` | `small` | `small` (`read_whisper_preset_fallback` overrides from `voice_option_notes.txt` if present) | `transcribe_config.txt:6`, `faster_whisper_transcribe_audio.py:19`, `175-190` |
| `WHISPER_LANGUAGE` | `ar` | `ar` | `transcribe_config.txt:7`, `faster_whisper_transcribe_audio.py:20` |
| `WHISPER_BEAM_SIZE` | `5` | `5` | `transcribe_config.txt:8`, `faster_whisper_transcribe_audio.py:21` |
| `WHISPER_VAD_FILTER` | `true` | `True` | `transcribe_config.txt:9`, `faster_whisper_transcribe_audio.py:22` |
| `WHISPER_MIN_SPEECH_DURATION_MS` | `250` | `250` | `transcribe_config.txt:10`, `faster_whisper_transcribe_audio.py:23` |
| `INITIAL_PROMPT_MAX_WORDS` | `120` | `120` | `transcribe_config.txt:13`, `faster_whisper_transcribe_audio.py:22` |
| `SUB_MAX_WORDS` / `SUB_TARGET_WORDS` / `SUB_MIN_GAP_SPLIT` | `4` / `2` / `0.35` | **not used** in current `faster_whisper_transcribe_audio.py` split (code uses punctuation, not word-count buckets) | `transcribe_config.txt:19-21` |
| `IMAGE_MIN_DURATION_SEC` | `2.2` | **code ignores** — uses `MIN_SENTENCE_DURATION_SEC 0.8` | `transcribe_config.txt:24` vs `faster_whisper_transcribe_audio.py:314` |
| `IMAGE_TARGET_DURATION_SEC` | `3.5` | ignored | `transcribe_config.txt:25` |
| `IMAGE_MAX_DURATION_SEC` | `4.8` | ignored; `MAX_SENTENCE_WORDS 14` also unused in split | `transcribe_config.txt:26`, `faster_whisper_transcribe_audio.py:33` |
| `IMAGE_MIN_WORDS` / `IMAGE_MAX_WORDS` | `5` / `12` | ignored | `transcribe_config.txt:27-28` |
| `IMAGE_PAUSE_SPLIT_SEC` | `0.40` | code reads `SILENCE_SPLIT_GAP_SEC` (`0.45` DEFAULTS, `0.55` fallback in `split...`) — **key name mismatch** | `transcribe_config.txt:29`, `faster_whisper_transcribe_audio.py:35`, `315` |
| `MIN_SENTENCE_DURATION_SEC` / `MAX_SENTENCE_WORDS` / `SILENCE_SPLIT_GAP_SEC` | n/a in config file | `0.8` / `14` / `0.45` DEFAULTS, `0.55` fallback | `faster_whisper_transcribe_audio.py:31-35`, `314-315` |

> Finding for ticket resolver: `transcribe_config.txt` advertises `2.2/3.5/4.8s` + `5-12 words` + `0.40s` as quality ladder, but the running code's split uses different knobs (`0.8s`, `0.45/0.55s`, punctuation-only). Doc/config vs code drift.

---

## 4. Spelling pipeline (`correct_transcript_spelling.py`)

| Fact | Detail | Citation |
|------|--------|----------|
| Reference priority | `refined_script.txt` else `final_output.txt` else abort | `correct_transcript_spelling.py:166-175` |
| Encoding | read `utf-8-sig` (strip BOM), write `utf-8` for `.txt`, `utf-8-sig` for `.srt` | `correct_transcript_spelling.py:66`, `151-153` |
| TXT TS preservation | `re.match(r"^(\[[0-9:\s\-]+\])\s*(.*)$"` captures timestamp verbatim; only text part is corrected | `correct_transcript_spelling.py:59` |
| SRT structure | blank-line blocks → `idx_str`, `time_str`, `text_lines` | `correct_transcript_spelling.py:75-95` |
| Junk guard | `autojunk=False` — prevents frequent Arabic tokens (`في/من/اللي`) being treated as junk | `correct_transcript_spelling.py:118-120` |
| Atomic write | `tmp + os.replace` to avoid truncating sole copy | `correct_transcript_spelling.py:154-156` |
| Targets | `timestamped_transcript.txt`, `timestamped_transcript.srt`, `image_timestamps.txt`, `subtitle_chunks.srt` | `correct_transcript_spelling.py:186-192` |
| Failure mode | empty `trans_words_seq` or `ref_words` → early return, leave file untouched (avoids truncation) | `correct_transcript_spelling.py:122-126` |

---

## 5. Timestamp injector (`fix_timestamps.py`)

| Fact | Detail | Citation |
|------|--------|----------|
| Inputs | `timestamped_transcript.txt` → `flow_prompts.json` | `fix_timestamps.py:33-35` |
| Map | 1-indexed `idx → "[MM:SS]"` via `re.match(r"^\[(\d{1,2}:\d{2})\]")`, fallback HH:MM:SS folded `h*60+m` | `fix_timestamps.py:40-57` |
| Fallback TS | `[00:00]` if line has no brackets | `fix_timestamps.py:57` |
| JSON tolerance | incremental `JSONDecoder.raw_decode` scanning for `[` — tolerates nested arrays, trailing commas, prose headers vs old single-regex splitter | `fix_timestamps.py:69-92` comment + loop |
| Injection | `item["timestamp"] = timestamps_map[item_idx]` if present; counts `injected_count` | `fix_timestamps.py:105-108` |
| Atomic guard | only `os.replace` if `master_list` non-empty; never overwrites source with partial on crash | `fix_timestamps.py:118-122` comment |

---

## 6. Planning manifest (`pipeline_manifest.py`)

| Fact | Detail | Citation |
|------|--------|----------|
| File | `pipeline_manifest.json` in topic subfolder | `pipeline_manifest.py:11` |
| Hash | `SHA256(transcript+"\n\x00\n"+template+"\n\x00\n"+presets)` hexdigests; mismatch invalidates caches (full reset) | `pipeline_manifest.py:28-31`, `70-78` |
| Phases | `roadmap_phase` (`total_lines`, `completed_pages`, `last_processed_index`), `planning_phase` (`chunk_size 15`, `total_chunks`, `chunks{}`), `rendering_phase` (`completed_indices`) | `pipeline_manifest.py:39-60` |
| Chunk states | `PENDING` `VERIFIED` `REPAIRED` `FAILED` | `pipeline_manifest.py:21-25` |
| Phase states | `PENDING` `IN_PROGRESS` `COMPLETED` `FAILED` | `pipeline_manifest.py:13-18` |
| Atomic save | `NamedTemporaryFile` + `fsync` + `os.replace` | `pipeline_manifest.py:94-108` |
| Done check | `all_chunks_done` → every chunk `VERIFIED` or `REPAIRED` | `pipeline_manifest.py:138-143` |
| Chunk dedup | `rendered_indices` sorted, deduped | `pipeline_manifest.py:59`, `144-147` |

---

## 7. Roadmap paging (`roadmap_orchestrator.py` — 25-row pages)

| Fact | Detail | Citation |
|------|--------|----------|
| Window size | `25` (`ROADMAP_WINDOW_SIZE` in `.env.example:57`, `window_size: int=25` in `split_transcript_into_windows` and `generate_master_roadmap`) | `roadmap_orchestrator.py:118`, `265` |
| Columns | 8: `Index`, `Timestamp`, `Script Line`, `Sequence Type`, `Layout Classification`, `Camera Specification`, `Visual Concept & Composition`, `Color & Selective Arabic Text` | `roadmap_orchestrator.py:18-27` |
| Files | `master_roadmap.jsonl` source of truth, `master_roadmap.txt` legacy mirror; atomic rewrite both | `roadmap_orchestrator.py:29-30`, `325-330` |
| Continuity | anchor = last row of prior page (`previous_last.visual_concept` injected as `CONTINUITY ANCHOR (Index N-1)`) | `roadmap_orchestrator.py:157-163`, `298-299` |
| Session | persistent via `ensure_persistent_gemini_session` with `GEMINI_SESSION_RESET_THRESHOLD=100` (only `Control+Shift+O` after 100 lines); otherwise reuse | `gemini_controller.py:28-92`, `roadmap_orchestrator.py:365-366` + `.env.example:90` |
| Parsing tolerance | 7-cell row padded `NONE` for missing Color; >8 truncated; header case-insensitive skip | `roadmap_orchestrator.py:146-154` |
| Repair | same-session repairs `max_page_repairs=2` without new chat; minor `missing<=2` synthesized as fallback `STANDALONE/AHWA_STUDIO/static` | `roadmap_orchestrator.py:265`, `390-442` |
| Jitter | `jitter_delay` 1.5-3.0s between pages | `roadmap_orchestrator.py:313` but also `gemini_controller.py:84-89` |
| No tail-merge | fixed 25-row pages, final page may be short — never merge tail | `roadmap_orchestrator.py:119-121` |

---

## 8. Chunk planning (`prompt_planner.py` — slice ±1)

| Fact | Detail | Citation |
|------|--------|----------|
| Chunk size | `15` (`FLOW_CHUNK_SIZE` in `.env.example:56`, `chunk_size: int=15` in `plan_all_chunks`) | `prompt_planner.py:387`, `pipeline_manifest.py:50` default 15 |
| Buffer | `PLANNING_BUFFER_ROWS=1` — slice is `[start-1, end+1]` sorted | `prompt_planner.py:26`, `108-113` `extract_roadmap_slice` |
| Prompt contract | `build_compact_preamble` + `ROADMAP CONTEXT` table + `SCRIPT LINES TO CONVERT: Index N [TS] sentence` + `Emit JSON array for Indices first..last` | `prompt_planner.py:167-189` |
| Schema hint | `[{"index": <int>, "timestamp": "[MM:SS]", "sequence_type": <enum>, ... "visual_prompt": {... "text_overlay_arabic": "<Arabic OR NONE>" ...}}]` | `prompt_planner.py:49-57` |
| Forbidden in preamble | `["subtitles","margin","watermark","Latin text","English overlay","photorealism","3D CGI","gradients"]` | `prompt_planner.py:39-45` |
| Validation | `clean_and_repair_json` → `FrameItem.model_validate`; empty `timestamp==""` auto-repaired from `timestamp_map` | `prompt_planner.py:252-266` |
| Self-heal | `max_repair_attempts=2` same-session; absorbs valid, collects `missing` + `errors_by_index` | `prompt_planner.py:305-337`, called at `278-334` `_plan_single_chunk` |
| Persist | `_persist_frames` atomic `NamedTemporaryFile+fsync+os.replace`; merges with baseline `flow_prompts.json` | `prompt_planner.py:205-213`, `_load_baseline_frames:184-202` |
| Skip logic | `_chunk_is_complete` if status `VERIFIED`/`REPAIRED` and all indices present in file | `prompt_planner.py:319-327` |
| Failure dump | `debug/malformed_chunk_N.json` with `raw_response` + `validation_errors` then `ChunkStatus.FAILED` + `ChunkPlanningError` | `prompt_planner.py:371-384`, `pipeline_manifest.py:132-136` |
| Final gate | missing any of `1..total` after all chunks → `ChunkPlanningError` | `prompt_planner.py:431-438` |

---

## 9. Validation ladder (`validator.py` — flatten / purge / enforce_arabic)

| Utility / Rule | Detail | Citation |
|----------------|--------|----------|
| `purge_subtitle_phrases` | removes `"\d+% bottom safe margin"`, `for subtitle(s)`, `subtitle overlay`, `caption(s)` | `validator.py:22-27` |
| `flatten_visual_prompt_to_diffusion_text` | str→json parse, purge `ABSENT`, purge subtitle triggers, 8-part ordered prompt: Action+Subject → Scene → Composition (default `Balanced 16:9...`) → Color/Lighting (`accent` or `Warm amber #E09F3E`) → Typography (`NONE` vs Kufic) → Style Anchor (purge `oil painting` for ahwa/host, default 2D vector `3px black outlines, 2-step cel-shading`) | `validator.py:35-122` |
| `enforce_arabic_in_prompt` | replaces `CHALLENGER/STAGE/STEP/BEFORE/AFTER/VS/English text` → Arabic (`التحدي`, `المرحلة` ...), safety bypass `Ahmed El-Ghandour→Al-Daheeh character`, `forged/forgery→theatrical prop`, etc; purges safe margin again; appends `Typography Directive` | `validator.py:124-197` |
| `TIMESTAMP_PATTERN` | `^\[\d{1,2}:\d{2}(:\d{2})?\]` — validator weak | `validator.py:18` |
| `FrameItem.timestamp` | allows `""` for upstream auto-repair, else must match pattern | `validator.py:226-230` |
| `parse_timestamp_seconds` | parses `[MM:SS]` or `[HH:MM:SS]` → total seconds | `validator.py:251-259` |
| `_auto_clean_item` | purges subtitle per visual_prompt field; Latin `text_overlay_arabic` → `NONE`; preserves `marginalia`/`margins of the` | `validator.py:262-276` |
| Content gate | flag `subtitle(s)` (case-insensitive) as forbidden; flag `\bmargin\b` but allow `marginalia`/`margins`; `text_overlay_arabic` must be `NONE` or contain `[\u0600-\u06FF]` and no `[A-Za-z]`; `style_anchor` must contain `3px` + `vector` + `cel-shading` | `validator.py:315-345` |
| Ordering | **weak monotonicity** `TS[i] ≤ TS[i+1]` (regress → violation, reset group); within equal-TS group strict `frame_index` must increase; duplicate `(index,frame_index)` → violation | `validator.py:348-380` summary + `validator.py:357-379` |
| Count/index gate | `len(items) != expected_total`, `missing = 1..N - present`, `duplicates` via `Counter` | `validator.py:394-405` |
| `verify_pipeline_integrity` | `auto_repair=True` by default; deep-copies then cleans; raises `PipelineIntegrityError` with violation list | `validator.py:385-418` |

---

## 10. JSON sanitizer (`json_sanitizer.py`)

| Tier | Action | Citation |
|------|--------|----------|
| 1 | strip ``` fences → trim prose to `[`/`{`...`]`/`}` → `json.loads` | `json_sanitizer.py:10-24`, `36-44` |
| 2 | fix inner quotes `(?<=:\s")([^"\\]*?)"([^"\\]*?)"(?=[\s,}])` → escaped, strip trailing commas, close unclosed `[` | `json_sanitizer.py:7`, `26-33`, `47-53` |
| 3 | balance brackets tracking string/escape state | `json_sanitizer.py:62-83` |
| 4 | salvage top-level `{...}` objects with `index` key via brace-depth scan | `json_sanitizer.py:86-110` |
| Fail | `ValueError("Failed to extract valid JSON structures")` | `json_sanitizer.py:8`, `143` |

---

## 11. Flow image generation (`flow_image_generator.py`)

### 11.1 Selectors & readiness

| Fact | Value | Citation |
|------|-------|----------|
| Flow URL | `https://labs.google/fx/tools/flow` | `flow_image_generator.py:108` |
| App ready gate | `Characters` sidebar visible + (`img`/`[aria-roledescription='draggable']`/`[contenteditable]`) + **3s stability** | `flow_image_generator.py:34-60` |
| Progress indicator | `[role='progressbar'], .animate-spin, mat-progress-spinner` + `\d+%` text | `flow_image_generator.py:111-112`, `553-576` handshake |
| Submit button | `button:has(i.google-symbols:text-is('arrow_forward'))` cascade → `Enter`/`Control+Enter` fallback | comment in `compile notes` + `flow_image_generator.py:816-835` + AGENTS.md Flow selectors |
| Characters nav | `button:has-text('Characters')` → verify `/characters` or `New character`/`Describe your character` | `flow_image_generator.py:753-778` |
| New Character input | `textarea[placeholder*='Describe your character' i]` or contenteditable with `innerText ~ describe your character`; never workspace bar `What do you want to create?` | `flow_image_generator.py:786-806` |
| Generation handshake | Phase 1 debounce `5s` for spinner mount, Phase 2 poll `timeout 180s` until spinner absent + `1.0s` settle, `5s` heartbeat | `flow_image_generator.py:543-576` |
| Asset drawer | `+` button left of `Agent` → `Search assets` → `Add to Prompt` chip `@asset` | `flow_image_generator.py:581-654` |
| Memoization | `flow_assets_profile_{index}.json` + `flow_workspace_url_profile_*.txt` per topic subfolder | `flow_image_generator.py:656-698` comment |

### 11.2 Tiered fetch & validation (failure modes)

| Tier | Method | Failure mode it solves | Citation |
|------|--------|------------------------|----------|
| 1 | inline `data:image` base64 decode | no network, but can be truncated | `flow_image_generator.py:287-298` |
| 2 | `blob:` URL → `fetch`→`FileReader`→`dataURL` in-page (same-origin, no CORS) | CDN cookie restrictions vs `page.request.get` | `flow_image_generator.py:305-322` comment “prioritize Blob/FileReader over page.request.get” |
| 2B | `http/https` → in-page `fetch(credentials:include)`→`FileReader` → fallback `canvas.drawImage`→`toDataURL` | CORS `canvas` taint is fallback only, not primary | `flow_image_generator.py:329-361` |
| 2C | `page.request.get(urljoin(page.url, src))` (inherits browser auth) | may lack CDN cookies → falls to screenshot | `flow_image_generator.py:365-376` |
| 3 | de-hovered atomic screenshot: `mouse.move(100,15)`, `requestAnimationFrame`, `scrollIntoView`, `screenshot(type="png")` → `validate` → `os.replace` | `canvas` CORS-tainted is never primary | `flow_image_generator.py:226-256`, `380` |

**Validation gate:**

| Check | Threshold | Citation |
|-------|-----------|----------|
| file exists + size | `>20KB` default (`min_size_kb=20` in `validate_image_file`, `50KB` in `atomic_screenshot_and_verify`) | `flow_image_generator.py:194-200`, `230` |
| PIL verify | `Image.open().verify()` + `w>100` and `h>100` | `flow_image_generator.py:210-212` |
| Header fallback | `PNG 89 50 4E 47` or `JPEG FF D8` magic bytes | `flow_image_generator.py:217-218` |
| CORS rule | never `<canvas>` primary — use `img_locator.screenshot` after de-hover | AGENTS.md gotcha + `flow_image_generator.py:226` |
| Atomic | `*.tmp` → `os.replace` to avoid partial/corrupt final | `flow_image_generator.py:248`, `294`, `360` |

---

## 12. Video compilation (`video_config.txt` + `compile_video.py`)

### 12.1 Config values

| Key | Value | Citation |
|-----|-------|----------|
| `OUTPUT_WIDTH x HEIGHT @ FPS` | `2560x1440@30` (default fallback `1920x1080@30`) | `video_config.txt:10-13`, `compile_video.py:44-47` DEFAULTS `1920x1080@30` |
| `OUTPUT_PIX_FMT` / `OUTPUT_PROFILE` / `LEVEL` | `yuv420p` / `high` / `5.1` (1440p → 5.1, else 4.1) | `video_config.txt:14-16`, `compile_video.py:260-273` |
| `CHUNK_SIZE` | `20` (code default `40`) | `video_config.txt:24`, `compile_video.py:40` |
| `QSV_LOOKAHEAD` | `0` mandatory | `video_config.txt:31`, `compile_video.py:46` |
| `QSV_LOOKAHEAD_DEPTH` | `20` | `video_config.txt:32`, `compile_video.py:47` |
| `VBV_MAXRATE` / `VBV_BUFSIZE` | `35000k` / `70000k` (code default `8000k`/`16000k`) | `video_config.txt:58-59`, `compile_video.py:55-56` |
| `FFMPEG_THREADS` | `4` | `video_config.txt:62` |
| `FFMPEG_CLIP_TIMEOUT` / `FINAL` | `600` / `5400` | `video_config.txt:64-65` |
| Ken Burns | `ZOOM_MIN 1.0`, `ZOOM_MAX 1.08`, `EASING smoothstep`, `UPSCALE 1.12`, `interp bicubic`, `pan 0.10 zoom 0.12` | `video_config.txt:43-49` |
| Audio | `aac 320k 48k`, `I -14 TP -1 LRA 11`, `linear true` | `video_config.txt:51-56` |

### 12.2 Encoding & zero-drift

| Fact | Detail | Citation |
|------|--------|----------|
| Encoder fallback | `h264_qsv` → `h264_nvenc` → `libx264` via `ffmpeg -encoders` probe; `ENCODER_FORCE` overrides; skips QSV if `>1080p` (Broadwell HD 5500 unreliable) | `compile_video.py:280-295` `_probe_encoder`, `detect_hardware_encoder` |
| Pix fmt | `nv12` for QSV else `yuv420p` | `compile_video.py:258`, `1193` |
| CFR | `-r fps -fps_mode cfr -video_track_timescale fps*1000 -g fps*2 -keyint_min fps -flags +cgop -avoid_negative_ts make_zero -fflags +genpts` | `compile_video.py:258-278` |
| Ken Burns math | upscale `W*1.12` even, `lanczos+accurate_rnd+full_chroma_int`, `ease = t^2*(3-2t)` smoothstep, `zoompan z=... x=... y=... d=frames s=WxH:fps` | `compile_video.py:410-470` |
| Clip 0 at frame 0 | first clip forced `start_frame=0` via `image_blocks[0].sec=0.0` + `current_frame=0` | `compile_video.py:816`, `883` |
| Zero-drift | `total_audio_frames = round(duration*30)`; `ideal_end = round(end_sec*fps)`; clamp `max(start+1, min(ideal, total-remaining))`; last clip `end=total`; degenerate guard truncates surplus blocks | `compile_video.py:873`, `887-898`, `879-881` |
| Filter graph limit | `>1K chars` → `temp_clips/filter_chunk_*.txt` + `-filter_complex_script` (Win 32KB cap) | `compile_video.py:1484-1488`, `1202-1228` pattern |
| Timeout scaling | `base<60` verbatim (tests); else `factor 4.0` (1440p libx264) / `3.0` (1080p libx264) / `1.8` (qsv/nvenc) `overhead 90`, floor `300` | `compile_video.py:1231-1257` |
| Workers | libx264 on `cpu<=4` → `1` worker (avoid `2× -threads 4` thrash); else qsv `2`, else `cpu//2` capped `2` | `compile_video.py:1260-1272` |
| Concat | per-chunk `chunk_####.mp4` → `concat_chunks.txt` + `-filter_complex_script filter_final_assembly.txt` | `compile_video.py:1821-1912` |
| Verify | `ffprobe` json `format=duration` + `codec_type` both `video`+`audio`, diff `<2.0s` | `compile_video.py:2122-2155` |

### 12.3 Resolve/fallback chain for visuals

| Priority | Source | Citation |
|----------|--------|----------|
| 1 | direct candidate list (`{ts}.png`, `{ts}_1.png`, `{ts}_frame1.png`, `sentence_{idx}.png`, etc) in `generated_images` + `generated_images_duplicates` | `compile_video.py:949-1000` |
| 2 | prefix `startswith(tv)` natural sort `min(occurrence-1, len-1)` | `compile_video.py:1006-1017` |
| 3 | sequential index `available_images[idx]` | `compile_video.py:1019-1023` |
| 4 | last valid image hold | `compile_video.py:1025-1027` |
| Fail | `(None,None)` → `validate_assets` reports `(idx, name)` | `compile_video.py:1029`, `1032-1056` |

---

## 13. Quality configs (`daheeh_config.json` + `audit_rubric.md`)

| Source | Fact | Citation |
|--------|------|----------|
| `daheeh_config.json:2` | `version 4.0.0`, target `Al-Daheeh (الدحيح)` | `daheeh_config.json:3-5` |
| `daheeh_config.json:8` | `fusha 0.3 / amiya 0.7` (30/70) | `daheeh_config.json:8` |
| `daheeh_config.json:9-21` | tashkeel lexicon: `كِدَه, بِيُقول, هُوبَّا, قِسط` + `دِي, دَه, مِعَلّم, ... خَازُوق` | `daheeh_config.json:9-21` |
| `daheeh_config.json:23-27` | pacing: `hook_sketch 90s`, `wpm 165 / rapid 195 / outro 90`, `skeptic_every 250 words` | `daheeh_config.json:23-27` |
| `daheeh_config.json:29-37` | tts tags: `expert_drop, street_logic, skeptic_shout, bureaucratic_mockery, existential_whisper, dramatic_pause, comedic_pause` | `daheeh_config.json:29-37` |
| `daheeh_config.json:40-41` | visual_diffusion: `Google Flow / Imagen 3`, style `2D editorial cartoon satire mixed with 18th-century oil painting cutout parody` | `daheeh_config.json:38-41` |
| `audit_rubric.md` 10-point | 1 Translatese, 2 Golden Ratio 30/70, 3 Jagged-Edge 1-3-1, 4 Cultural Grounding, 5 Acoustic Pauses `...`, 6 Rhetorical Pivots, 7 Bureaucratic Personification, 8 Phonetic Tashkeel, 9 Paragraph Punchline, 10 Existential Outro | `docs/audit_rubric.md:5-16` table rows |

---

## 14. Global pipeline knobs (`.env.example` + `video_config.txt` overlap)

| Knob | Value | Citations |
|------|-------|-----------|
| `FLOW_IMAGE_MODEL` | `Nano Banana 2 Lite` | `.env.example:51` |
| `FLOW_IMAGE_COUNT` | `1x` | `.env.example:52` |
| `FLOW_ASPECT_RATIO` | `16:9` | `.env.example:53` |
| `FLOW_DISABLE_AGENT` | `true` | `.env.example:54` |
| `FLOW_CHUNK_SIZE` | `15` | `.env.example:56` = `prompt_planner` chunk |
| `ROADMAP_WINDOW_SIZE` | `25` | `.env.example:57` = `roadmap_orchestrator` window |
| `GEMINI_SESSION_RESET_THRESHOLD` | `100` | `.env.example:90`, `gemini_controller.py:28-32` threshold |
| `CDP_PORT` | `9222` | `.env.example:9`, `utils.py:23` |
| `TTS_MODEL` | `gemini-2.5-pro-preview-tts`, voice `Achird`, temp `1.1`, reload `40` | `.env.example:29-32` (also noted in AGENTS.md config table) |
| `WHISPER_ENGINE` toggle | `faster_whisper` vs `hard_whisper` | `.env.example:78`, `run_agency` toggles |

---

## 15. Failure modes inventory (for resolver)

| ID | Component | Mode | Artifact / Signal | Citation |
|----|-----------|------|-------------------|----------|
| F1 | `prompt_planner` | `FAILED` chunk after 2 same-session repairs | `debug/malformed_chunk_N.json` + `ChunkPlanningError` with `missing_indices` | `prompt_planner.py:371-384`, `pipeline_manifest.py:133` |
| F2 | `roadmap_orchestrator` | page exhausted after 2 repairs | fallback synthesized rows or `RuntimeError` with raw preview | `roadmap_orchestrator.py:394-443` |
| F3 | `validator` | pipeline integrity violations (count, missing/dup, schema, `subtitle`/`margin`, Latin in Arabic, style_anchor keywords, monotonicity) | `PipelineIntegrityError` with `violations: list[str]` | `validator.py:283-418` |
| F4 | `json_sanitizer` | 4 tiers exhausted | `ValueError("Failed to extract...")` | `json_sanitizer.py:143` |
| F5 | `flow_image_generator` | CORS canvas taint | never canvas primary; tier escalation to screenshot | `flow_image_generator.py:226`, AGENTS.md gotcha |
| F6 | `flow_image_generator` | image corrupt/truncated/small | `>20KB` + PIL `verify` `>100px` else header check; atomic `*.tmp` | `flow_image_generator.py:194-223` |
| F7 | `flow_image_generator` | generation timeout | `wait_for_flow_generation_handshake` 180s → `debug_snapshots/flow_generation_timeout_*.png` | `flow_image_generator.py:560-576`, `86-106` |
| F8 | `compile_video` | HW encoder hang | probe fails → fallback `h264_qsv→nvenc→libx264`; stderr pump thread to keep `FFMPEG_CLIP_TIMEOUT` reachable | `compile_video.py:175-188`, `280-295`, `1313-1353` |
| F9 | `compile_video` | oversubscribed workers (8 threads on 2C/4T) | libx264 capped `1` worker on `cpu<=4` | `compile_video.py:1260-1272`, `1972-1980` |
| F10 | `compile_video` | 32KB CLI overflow | `-filter_complex_script` file instead of inline | `compile_video.py:1202-1228`, `1874-1912` |
| F11 | `compile_video` | checkpoint drift | `render_signature WxH@FPS`, `audio_duration ±0.05s`, `encoder` codec check → invalidate + reinit | `compile_video.py:437-506`, `pseudo in checkpoint manager 510-560` |
| F12 | `transcribe` | no run folder / no audio | `sys.exit(1)` after scanning `youtube_runs` by mtime | `faster_whisper_transcribe_audio.py:476-500` |
| F13 | `correct_spelling` | empty transcript/ref | early return, leave file untouched (avoid truncation) | `correct_transcript_spelling.py:122-126` |
| F14 | `fix_timestamps` | no valid JSON objects | warning `No valid JSON objects` + `folders_processed` counter | `fix_timestamps.py:123-124` |

---

## 16. Open facts vs spec deltas (no decisions, just deltas)

- `transcribe_config.txt:24-29` advertises image retention `2.2/3.5/4.8s` + word buckets `5-12`; code uses `0.8s` + punctuation-only split — **doc/config vs code drift**.
- `IMAGE_PAUSE_SPLIT_SEC` (`transcribe_config.txt:29`) vs `SILENCE_SPLIT_GAP_SEC` (`faster_whisper_transcribe_audio.py:35`) — **key name mismatch**; code fallback `0.55` differs from config `0.40`.
- `video_config.txt:24` `CHUNK_SIZE 20` vs `compile_video.py:40` default `40` — file wins when present; default is double.
- `video_config.txt:58-59` `VBV 35000k/70000k` vs `compile_video.py:55-56` default `8000k/16000k` — same pattern.
- `QSV_LOOKAHEAD=0` is correctly consistent across both — `video_config.txt:31` and `compile_video.py:46`.
- `validator.py:226` allows `timestamp==""` for auto-repair; upstream `prompt_planner.py:262` fills it — intentional tolerance, not a bug.
- `flow_image_generator.py` tier order comment says blob prioritized over `page.request.get` to bypass CDN cookies — matches implementation.

---

## 17. File inventory for ticket #5

All paths relative to `image_generation/`:

`faster_whisper_transcribe_audio.py:1`, `correct_transcript_spelling.py:1`, `transcribe_config.txt:1`, `fix_timestamps.py:1`, `pipeline_manifest.py:1`, `roadmap_orchestrator.py:1`, `prompt_planner.py:1`, `validator.py:1`, `json_sanitizer.py:1`, `flow_image_generator.py:1`, `video_config.txt:1`, `compile_video.py:1`, `daheeh_config.json:1`, `docs/audit_rubric.md:1`, `gemini_controller.py:1`, `gemini_utils.py:1`, `utils.py:1`, `.env.example:1`

No `CONTEXT.md`, no `docs/adr/` — see §1.
