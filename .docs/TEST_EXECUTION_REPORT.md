# TEST EXECUTION REPORT — `.tests/` Audit Suite

**Runner:** Python 3.11.9 · pytest 9.1.1 · Windows (win32)
**Invocation:** `python -m pytest .tests/unit -p no:cacheprovider -q`
**Final result:** **117 passed, 1 skipped, 0 failed** · `ruff check .tests` → *All checks passed*

---

## 1. TDD timeline (evidence-driven remediation)

| Stage | Passed | Failed | Errors | Meaning |
|-------|--------|--------|--------|---------|
| Baseline (pre-patch, first run) | 41 | 24 | 2 collection | Repros + harness noise |
| Harness corrected (pre-patch) | 40 | 19 | 3 | Pure production repros isolated |
| Post-Gamma patches | **117** | **0** | **0** | All repros green |

Collection errors at baseline were themselves the CRITICAL repro: `import utils` → `NameError` blocked `test_checkpoint_idempotency.py` and `test_tashkeel_lexicon.py` entirely.

## 2. Suite composition

| File | Tests | Targets |
|------|-------|---------|
| `test_timeline.py` | 10 | Zero-drift frame budget (contiguity, integer frames, exact coverage, 70/30 grouping weights, degenerate clips>frames clamp), `AudioSyncAligner` energy profile / snap-radius / non-WAV bypass |
| `test_tashkeel_lexicon.py` | 30 (1 skip) | Lexicon slug→vocalized injection against live `daheeh_config.json`, homograph rules, orphan `<thinking>`/`<slang_ledger>` purge, loanword transliteration, interjection de-dup, TTS acoustic punctuation, cadence validators, rhythm variance, safety-block detector, paragraph splitting, `_safe_path` traversal shield, checkpoint roundtrip/legacy/corrupt/atomicity |
| `test_checkpoint_idempotency.py` | 12 | refine checkpoint roundtrip + legacy str-list + corrupt→[] ; audacity checkpoint roundtrip/corrupt; `pipeline.json` default shape/partial merge/corrupt fallback; `CheckpointManager` schema v3, mark+reload, render-signature invalidation, corrupt→None, cleanup-on-success |
| `test_transcript_alignment.py` | 10 | Identity alignment, misspelling replacement landing in correct group, ASR-word deletion, BOM survival, 300-word autojunk equality corpus, empty-file no-crash, tmp-less atomic write, SRT block integrity/malformed-block tolerance |
| `test_whisper_align.py` | 15 | `[MM:SS]`/SRT ms formatting incl. negative clamp, Arabic normalization folds, anchor timing application, strict monotonicity with interpolated gaps, audio-bounds containment, ≥2-token anchor rule |
| `test_audio_stitch.py` | 6 | Sum-of-frames zero-loss stitching, param preservation, rate/channel/width mismatch rejection, gap detection contract (`found, missing`) |
| `test_audacity_ipc.py` | 6 | Terminator-formatted sends, blank-line response framing, EOF graceful partial read, macro command passthrough, missing-preset failure, per-effect `SelectAll:` dispatch |
| `test_gemini_stability.py` | 7 | Stability-window return on stable text, error-card fast-fail, timeout→"" , idle/generating probes via native-JS double |
| `test_utils_health.py` | 11 | Import-order NameError repro, profile-index mapping, env overrides/defaults for `PipelineConfig`, runtime-state roundtrip/corrupt-recovery, port probe truth table |

Skip rationale: lexicon lacks a nested-substring key pair to prove longest-match precedence — precondition-gated, not a silent pass.

## 3. Mock verification

- **Audacity pipes** (`mocks/audacity_stub.py`): line-faithful protocol double — every response replayed until the mandatory blank-line terminator; EOF path exercised without hang. Verified terminator handling matches `send_audacity_command`'s reader.
- **Gemini page** (`mocks/fake_gemini.py`): duck-typed `locator/evaluate/nth/count/is_visible` covering `wait_for_gemini_response` (adaptive polling branch), `check_gemini_error_state` selector sweep, and `is_gemini_generating`'s native-JS probe. Deterministic fake clock drives stability counters — no real sleeps beyond one bounded test (~1s).
- **docx stub** (`.tests/conftest.py`): unblocks `refine_script` import on machines without `python-docx`; production docx code paths are NOT covered by unit scope (by design).

No GUI, Audacity install, FFmpeg binary, or network is required for the suite.

## 4. Edge-case regression validation

| Edge case | Behavior before | Behavior after |
|-----------|-----------------|----------------|
| 300-word transcript, frequent في tokens | Words redistributed across timestamps (autojunk) | Byte-exact reference reconstruction |
| BOM'd txt transcript | First timestamp lost → cascade shift | Timestamp preserved |
| Nested arrays in flow_prompts.json | Chunk dropped + file overwritten with partial list | Full parse, atomic commit |
| Crash after last checkpoint save in refine | Deliverables lost on rerun (checkpoint deleted) | Regenerated from checkpoint pre-delete |
| Truncated model output with orphan tag | Planning residue leaked into script | Everything after orphan purged |
| Clips > available frames (degenerate) | end_frame overflow → negative tail duration | Budget clamped, monotonic starts |
| Mixed-rate chapter WAVs | Chipmunk-corrupted master | ValueError before any bytes written |
| Chapter_3 missing | Silent truncation | Hard exit naming the gap |
| Encoder silent hang mid-chunk | Timeout unreachable (blocking read) | Deadline fires; chunk skipped → HW→CPU fallback |
| Export never appears / size oscillates | Infinite wait | 900 s cap → skip, checkpoint preserved |
| `"index": "3"` in repaired JSON | Injection silently skipped | Coerced and injected |

## 5. Legacy suite cross-check

`python -m pytest tests/unit`: **40 passed / 11 failed**, with the failing set verified bit-identical on stashed HEAD (pre-patch) — zero regressions introduced. The 11 are stale expectations vs evolved production (occurrence keys, `raw_sec` field, real-hardware encoder probes) catalogued as M12 in AUDIT_REPORT.md.

## 6. Static hygiene

- `py_compile` clean across all modified modules.
- Safe `ruff --fix` applied to touched files: `compile_video.py` findings reduced **73 → 26** (residual = pre-existing categories: bare excepts, long lines, unused vars).
- `ruff check .tests` → clean.
- `black` not installed in this environment; formatting parity deferred to repo's pre-commit (`ruff-format`) — minimal-diff mandate prioritized over whole-file rewrites.
