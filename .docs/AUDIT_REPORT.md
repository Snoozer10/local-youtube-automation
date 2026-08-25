# AUDIT REPORT — Al-Daheeh Pipeline (Test-Driven Hardening Pass)

**Scope:** `image_generation/` workspace — orchestration, linguistic, audio/IPC, ASR/video, browser-CDP layers.
**Method:** Static audit → failing repro tests in `.tests/` → surgical patches → green verification. No functional code was modified before the repro suite existed.
**Invariants upheld:** CDP-only AI access (no cloud SDKs introduced), checkpoint idempotency (all fixes preserve or *strengthen* resume semantics), integer frame math untouched except degenerate-input clamp, `subprocess` list-args + `shell=False` everywhere, Audacity `SelectAll:` protocol intact, UTF-8 console contract extended.

---

## Severity Index

| Sev | Found | Fixed | Deferred / Documented |
|-----|-------|-------|------------------------|
| CRITICAL | 2 | 2 | 0 |
| HIGH | 9 | 7 | 2 (H4, H9) |
| MEDIUM | 12 | 9 | 3 (M10-partial, M11, M12) |
| LOW | 6 | 1 | 5 |

---

## CRITICAL

### C1 — `utils.py:62` Module-level NameError kills every consumer
**Defect:** `CONFIG = PipelineConfig.from_env()` executed at line 62, but `get_config_value` is defined at line 65. Any `import utils` raised `NameError: name 'get_config_value' is not defined`. Seven production modules import utils (`automate_all`, `run_agency`, `refine_script`, `generate_voice`, `generate_thumbnail`, `flow_image_generator`, `script_image_generator`) — the entire pipeline was one cold-start away from total failure. Regression present in uncommitted working tree (`M utils.py` at session start).
**Root cause:** Definition-order bug; eager dataclass factory call placed above its dependency.
**Patch:** Relocated the `CONFIG = PipelineConfig.from_env()` assignment to immediately after `get_config_value`'s definition.
**Repro test:** `.tests/unit/test_utils_health.py::test_utils_module_imports_cleanly`

### C2 — `correct_transcript_spelling.py:106` `autojunk=True` corrupts long Arabic alignments
**Defect:** `difflib.SequenceMatcher(None, trans, ref)` uses the default `autojunk=True`; for sequences ≥200 items, tokens appearing in >1% of the reference (في، من، اللي…) are auto-classified as junk and can never form `equal` blocks. High-frequency function words get redistributed across timestamp groups via proportional `replace` mapping — silent transcript corruption on every long episode.
**Root cause:** Heuristic tuned for English prose is pathological for morphologically poor Arabic with a tiny type-token ratio.
**Patch:** `autojunk=False` (mirrors the already-correct usage in `faster_whisper_transcribe_audio.py:212`).
**Repro test:** `test_transcript_alignment.py::test_long_transcript_autojunk_keeps_frequent_words` (300-word corpus, exact-equality assertion).

---

## HIGH

### H1 — `fix_timestamps.py:70` Regex chunk-splitter truncates nested JSON, then destroys source
**Defect:** `\[\s*\{.*?\}\s*\]` stops at the first `}]`, so any prompt object containing a nested array failed `json.loads`, was **dropped with only a warning**, and the surviving partial list was written back over `flow_prompts.json` — permanent silent prompt loss.
**Root cause:** Single-pass regex parsing of non-flat JSON.
**Patch:** Incremental `json.JSONDecoder().raw_decode` scan from each `[` occurrence (handles arbitrary nesting, trailing prose, multi-array files); output committed via temp-file + `os.replace`; per-item coercion failures are counted and skipped without aborting the batch. The destructive-overwrite window no longer exists because parse robustness removes the drop-path and the write is atomic.

### H2 — `correct_transcript_spelling.py:164` Non-atomic overwrite of sole transcript copies
**Defect:** `open(file_path, "w")` truncates before writing; an interrupt between alignment and flush destroyed the only copy of `timestamped_transcript.txt/.srt`.
**Patch:** Write to `<file>.tmp` then `os.replace`. SRT keeps its conventional BOM on write; txt is written BOM-free for downstream plain-utf8 parsers.

### H3 — `refine_script.py:860-863` Checkpoint early-exit deletes state without deliverables
**Defect:** Crash between the last `save_checkpoint` and `save_refined_script`: on rerun `start_index >= len(paragraphs)` → "All paragraphs already refined" → checkpoint deleted → refined text lost forever; downstream voice-gen finds no `refined_script.txt`.
**Patch:** Before deleting, if `refined_script.txt` is absent and checkpoint holds turns, regenerate all deliverables via `save_refined_script(...)` first.

### H4 — Safety-block academic fallback missing *(deferred)*
`refine_paragraph` returns `None` on `is_safety_blocked`; the mandated neutralized-academic-Fusha retry variant does not exist anywhere. **Not patched** — requires prompt-engineering sign-off (new prompt text changes model behavior). Recommendation in ARCHITECTURE_HEALTH_CHECK.md §5.

### H5 — `correct_transcript_spelling.py:50` BOM breaks txt first-line timestamps
**Defect:** SRT reads used `utf-8-sig`, txt used plain `utf-8`; a BOM'd transcript defeated `^\[[0-9:\s\-]+\]` on line 1, shifting all early words into an untimed bucket.
**Patch:** All reads now `utf-8-sig` (harmless without BOM). Same fix applied in `fix_timestamps.py`.

### H6 — `generate_voice.py:129` Non-atomic voice manifest writes
**Defect:** Direct `"w"` truncate-write of `voice_generation_manifest.json`; crash mid-dump leaves zero-byte/truncated manifest → resume logic falls back to a fresh manifest, silently orphaning completed chapters/WAVs.
**Patch:** Temp file + `flush` + `os.fsync` + `os.replace`, with tmp cleanup on failure.

### H7 — `automate_audacity.py:348-360` Unbounded export waits hang the supervisor
**Defect:** `while not os.path.exists(...)` and size-stability loops had no deadline. A silent `Export2:` failure (license modal, disk full) stalled `run_agency.py` forever with no Telegram alert path reached.
**Patch:** Both loops bounded by `EXPORT_WAIT_TIMEOUT_SEC = 900`; timeout raises `TimeoutError`, caught per-file — chapter skipped **without** being marked polished, so resume retries it. Pipe close + Audacity kill moved to `finally`.

### H8 — `compile_video.render_chunk` blocking stderr read defeats chunk timeout
**Defect:** `process.stderr.read(256)` blocks until data arrives; a hardware encoder that hangs silently (documented QSV failure class) never returns bytes, so the `FFMPEG_CLIP_TIMEOUT` branch was unreachable — thread leaked, parallel pool wedged.
**Patch:** Dedicated daemon pump-thread feeds a `queue.Queue`; main loop uses `get(timeout=1.0)` so the deadline check executes regardless of encoder output; EOF sentinel + `poll()` gate termination exactly as before.

### H9 — `compile_video` checkpoint never updated during render *(deferred)*
`CheckpointManager.mark_clip_done/is_clip_done` are **never called** in `run_chunked_compile`; `initialize()` records `completed_clips: 0` forever. Resume therefore relies solely on chunk-file existence checks, and the fast-path skip (`completed == total and output exists`) can never fire after a final-video deletion → full re-render despite valid chunks. **Not patched**: wiring per-chunk checkpointing into the ThreadPool path alters resume semantics and deserves integration coverage before touching a hot path (invariant #2 caution). Full recommendation in HEALTH_CHECK §2.

---

## MEDIUM

### M1 — `stitch_chapters.py` blind frame concatenation across mismatched formats
Chapters with differing sample rate / channels / bit depth were concatenated frame-blind → pitch-corrupted master. **Fixed:** new pure `stitch_files(file_list, output_path)` validates `(framerate, nchannels, sampwidth)` homogeneity against chapter 1, raises `ValueError` on mismatch. Frame-exactness preserved (sum-of-frames test).

### M2 — Silent sequence-gap truncation
`Chapter_1,2,4` stitched only 1–2 with no signal. **Fixed:** `scan_sequential_chapters()` returns `(found, missing)`; `main()` hard-exits listing the gap instead of shipping a truncated episode.

### M3 — `refine_script.clean_refined_paragraph` unclosed tag residue
Paired-tag regexes require `</thinking>`; truncated Gemini output left planning prose in deliverables. **Fixed:** orphan-open fallbacks `re.sub(r"<thinking>.*\Z", …)` (same for `<slang_ledger>`) — everything after an unclosed block is treated as untrustworthy and purged.

### M4 — Account-rotation infinite loop
Rotation branch reset `retries = 0`; a uniformly failing profile fleet looped forever. **Fixed:** cumulative `total_failures` counter bounds the while-loop (`FAILURE_BUDGET = max(max_retries*5, 20)`); rotation still resets per-profile retries as designed.

### M5 — Lean prompt dropped contractual directives
Default `lean_prompt=True` path omitted the 30% Fusha : 70% Amiya ratio and `<final_script>` tagging rules. **Fixed:** `[RATIO LOCK]` + `[TAG LOCK]` lines re-anchored on every turn.

### M6 — Tashkeel engine silent-disable
Missing config / empty lexicon silently made `transform` a no-op. **Fixed:** explicit `[WARN] Tashkeel DISABLED…` on both paths (config-absent, lexicon-empty).

### M7 — `inject_json_timestamps.py:179` string index coercion
LLM-repaired JSON emits `"index": "3"`; int-keyed map lookup silently skipped injection. **Fixed:** `int(item.get("index", -1))` guarded by try/except.

### M8 — `flow_image_generator.mark_profile_assets_initialized` non-atomic memoization flag
Half-written flag misread as initialized on resume. **Fixed:** tmp + `os.replace`.

### M9 — `run_agency.save_pipeline_state` non-atomic
**Fixed:** tmp + `fsync` + `os.replace`; read side gains explicit utf-8.

### M10 — Missing UTF-8 console guards
`automate_all.py`, `run_agency.py`, `automate_audacity.py`, `inject_timestamps.py`, `inject_json_timestamps.py`, `fix_timestamps.py`, `stitch_chapters.py` printed Arabic folder names through cp1252 when piped. **Fixed:** guarded `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` in all seven.

### M11 — Encoder order NVENC→QSV vs directive QSV→NVENC *(accepted deviation)*
`detect_hardware_encoder` probes NVENC first and gates QSV behind `not is_high_res`, citing Broadwell HD5500 instability >1080p. Deliberate, commented, and safer than the nominal order on this fleet. Mid-render fallback remains HW→libx264 only. Left as-is; flagged for owner confirmation.

### M12 — Legacy `tests/unit` staleness *(documented)*
11 failures verified identical on **unpatched HEAD** (git-stash A/B): `test_camera_decisions` (6) expect dicts without occurrence-suffixed keys; `test_timeline::TestParseImageTimeline` (3) expect blocks without `raw_sec`; `test_encoder` (2) assume mocked encoder probing but hit real QSV/NVENC hardware. Tests are stale vs evolved production — not production bugs.

---

## LOW

| ID | Finding | Status |
|----|---------|--------|
| L1 | Empty transcript hit IndexError path in aligner | **Fixed** — graceful no-op return before opcodes |
| L2 | DEBUG print spam in `correct_transcript_spelling` | Kept (active debugging aid); log-level refactor recommended |
| L3 | Stability doc says "5 stable seconds", code counts 5 samples (~1.25–3.75s adaptive) | Cosmetic wording; behavior within AGENTS.md tolerance |
| L4 | `[MM:SS]` ≥100-min edge | Improved — HH:MM:SS folds hours into minutes; ≥100-min display remains out of contract |
| L5 | `get_latest_run_folder` duplicated ×10 modules | Refactor candidate: consolidate into `utils.py` |
| L6 | `leading_silence_sec` computed but unused by timeline prep | Harmless dead telemetry; anchor-to-zero is intentional |

---

## Files touched (production)

```
utils.py                      compile_video.py              refine_script.py
correct_transcript_spelling.py  stitch_chapters.py          generate_voice.py
automate_audacity.py          run_agency.py                 fix_timestamps.py
inject_json_timestamps.py     inject_timestamps.py          automate_all.py
flow_image_generator.py
```

## Verification snapshot

- `.tests/` suite: **117 passed / 1 skipped**, `ruff check .tests` clean.
- Legacy `tests/unit`: 40 passed / 11 pre-existing failures (bit-identical set pre/post patch).
- `py_compile` clean on all 13 modified modules; net ruff findings on `compile_video.py` reduced 73 → 26.
