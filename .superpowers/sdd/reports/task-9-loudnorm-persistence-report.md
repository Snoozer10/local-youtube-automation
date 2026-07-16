# Task 9 Report: Loudnorm Two-Pass Persistence (verify + commit)

## Summary
Verified the two-pass loudnorm measurement path. **Verification surfaced two real bugs**
in the "code already in place" (from Task 6): the measurement produced no usable data and
fell back to single-pass loudnorm, so the persisted `video_config.local.txt` was never written.

## Bugs Found (and Fixed)
1. **`-loglevel error` suppressed the JSON summary.** loudnorm emits its
   `print_format=json` measurement at `AV_LOG_INFO`. With `error` level the JSON never
   reached stderr, so `measured` stayed empty and `_measure_loudnorm` returned the
   single-pass fallback every time. Fixed: measure command now uses `-loglevel info`.
2. **Single-line JSON matching failed.** The JSON is pretty-printed across multiple
   lines (`{` on its own line, `}` later). The old parser checked
   `line.strip().startswith('{') and endswith('}')` per line — never true. Fixed:
   `_extract_loudnorm_measured` now slices `stderr[stderr.find('{'):stderr.rfind('}')+1]`
   and `json.loads` the whole block.

## Fixes (compile_video.py)
- `_measure_loudnorm` (line ~495): `-loglevel error` → `-loglevel info`.
- `_extract_loudnorm_measured` (line ~462): robust multi-line JSON extraction via
  substring between first `{` and last `}`; drops the broken per-line loop.

## Validation
- Unit test `tests/unit/test_loudnorm.py` (4 tests: parse values, persist local config,
  in-place config update, empty-input no-op) — all pass.
- Real audio `youtube_runs/Everyday Habits That Boost Brain Power/full_episode_voice.wav`
  (12:06) measured successfully:
  - `Measured: I=-19.1 TP=-0.9 LRA=4.5`
  - Two-pass filter string produced with `measured_I/TP/LRA/thresh` + `offset` + `linear=true`.
  - `video_config.local.txt` written to run folder with `LOUDNORM_MEASURED_*` + `LOUDNORM_OFFSET`.
- Full suite: `python -m pytest tests/unit/ -q` → 26 passed (22 prior + 4 new).

## Files Touched
- `compile_video.py` — `_measure_loudnorm`, `_extract_loudnorm_measured`
- `tests/unit/test_loudnorm.py` — new (4 tests)

## Commit
`feat: loudnorm two-pass measurement persistence`
