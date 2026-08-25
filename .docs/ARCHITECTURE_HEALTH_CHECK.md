# ARCHITECTURE HEALTH CHECK — Al-Daheeh Pipeline

Post-audit assessment of systemic health, with prioritized recommendations. All findings respect the standing invariants (CDP-only AI, checkpoint idempotency, deterministic frame math, shell=False subprocess discipline).

---

## 1. Memory & resource hygiene

| Area | Observation | Recommendation |
|------|-------------|----------------|
| `flow_image_generator.py` (3.7k lines) | Long batch loops hold page/context for hours; debug snapshots accumulate unbounded in `debug_snapshots/` | Add rotating cap (e.g., keep last 20 snapshots per subfolder); consider periodic `context.new_page()` recycling every N frames to shed detached-node memory |
| `compile_video.py` ThreadPool render | `max_workers=2`; on timeout path the killed `Popen`'s stderr pipe is now drained by daemon thread — no leak, but killed-process temp files (`tmp_chunk_*.mp4`) persist | Extend fallback purge to `tmp_*.mp4` alongside `chunk_*.mp4` |
| Whisper model lifecycle | Model loaded once per run — correct | None |
| Audacity instances | Killed per-chapter via `/F /T` — clean | None |

## 2. Checkpoint architecture

- **Strengths:** refine/voice/audacity/agency checkpoints are now atomic (tmp+fsync+replace), corruption-tolerant (parse-fail → safe defaults or regeneration), and schema-versioned where it matters (`CheckpointManager` v3 + render signature).
- **Gap (H9):** `compile_checkpoint.json` is written but never advanced during chunked rendering; resume granularity is file-existence only.
  **Recommendation:** inside `run_chunked_compile`'s `as_completed` loop, call `checkpoint.mark_clip_done(chunk_idx, path, duration)` and gate re-render via `is_clip_done`. Add an integration test that kills mid-render and asserts assemble-only resumption before enabling.
- **Schema drift policy:** legacy readers already normalize str-list vs dict forms (refine) and tolerate unknown keys (pipeline.json merge). Keep this "read-wide, write-narrow" pattern for any new field.

## 3. Browser session stability (CDP)

- `kill_cdp_chrome` is correctly surgical: netstat table parse → PID>100 guard → tree kill → socket-release polling. No blind image-name kills anywhere in scope.
- Gemini wait layer is resilient (error-card fast-fail, transient-placeholder handling, adaptive 0.25/0.75 s polling, 5-sample stability).
- **Risks worth monitoring:**
  1. **Stability-window semantics drift** — code counts 5 consecutive equal samples (~1.25–3.75 s depending on branch), while docs/AGENTS say "~5–6 s". If cutoff regressions appear on slow Pro turns, raise threshold to time-based (≥4.0 s wall-clock since last text change) rather than sample-count.
  2. **Account rotation budget** — now bounded (`FAILURE_BUDGET`), but rotation still resets per-profile retries; ensure `FAILOVER_RETRY_LIMIT` stays ≥3 so a single flaky profile can't exhaust the global budget prematurely.
  3. **Hydration clicks** — `wait_for_flow_app_ready`'s 3 s window is honored at entry points audited; any *new* navigation helper must route through it (or `wait_for_predicate`) rather than fixed sleeps.

## 4. Determinism guarantees (audio/video)

- Frame math is integer-exact end-to-end: `round(duration*fps)` budget, contiguous start/end chains, last clip absorbs remainder, min-1-frame rule can no longer overflow the budget (degenerate clamp added).
- CFR enforced (`fps_mode cfr`, `-r`, timescale = fps·1000, CGOP); QSV path pins nv12; filter graphs always routed through `-filter_complex_script`.
- **Watch item:** `AudioSyncAligner.leading_silence_sec` is computed but unused — either wire it into a pre-roll trim decision or remove to avoid future confusion with the anchor-to-zero behavior.

## 5. Linguistic pipeline integrity

- Tashkeel engine: config-driven, longest-key-first, prefix-preserving; homograph rules independent of config by design. Silent-disable mode eliminated (loud warnings). **Note:** lexicon keys are Latin phonetic slugs mapping → diacritized Arabic; tests now encode that contract.
- Ratio enforcement is prompt-side only (`[RATIO LOCK]`). For mechanical enforcement, add a Fusha-marker density check (e.g., relative frequency of علاوة/حيثما-class connectors vs Amiya markers) into `validate_refinement_quality` — currently only banned-connector blacklisting exists.
- **Safety-block fallback (H4):** implement `academic_fallback_prompt(paragraph)` — neutralized Fusha rewrite request dispatched once before counting a retry. This satisfies the AGENTS.md mandate without loosening safety detection (`is_safety_blocked` remains the gate).

## 6. Codebase structure

1. **Consolidate `get_latest_run_folder`** — 10 near-identical copies (some CWD-relative, some script-relative). A single `utils.get_latest_run_folder(runs_path, anchor="script")` removes drift risk (automate_audacity's script-anchored variant differs semantically from the rest).
2. **Extract shared timestamp-map parser** — `fix_timestamps.py` vs `inject_json_timestamps.py` use different index-advance policies; one utility with an explicit policy flag prevents future desync between the two tools' maps.
3. **Legacy test refresh (M12)** — update `tests/unit/test_camera_decisions.py` (occurrence keys), `TestParseImageTimeline` (`raw_sec`), and mock `_probe_encoder` in `test_encoder.py` so hardware presence doesn't flip assertions machine-to-machine.
4. **Log-level hygiene** — DEBUG print scaffolding in `correct_transcript_spelling.py` should move behind `LOG_LEVEL` env once transcript-alignment work stabilizes.

## 7. Working-tree notes for the owner

- Session began with uncommitted modifications (`utils.py`, `refine_script.py`, `gemini_utils.py`, `automate_all.py`, …). The `utils.py` import-order regression arrived in that state; all audit patches are layered on top. Recommend committing the pre-existing work separately from these hardening changes for clean bisection.
- `black` is absent from the active interpreter (listed in `requirements-dev.txt`); repo convention routes formatting through pre-commit's `ruff-format`, which was intentionally not bulk-applied here to keep the patch surface reviewable.
