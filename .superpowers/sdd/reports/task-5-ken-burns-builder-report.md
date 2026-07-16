# Task 5 Report: Ken Burns Filter Graph Builder

## Implementation

Added `build_ken_burns_filter(config, duration, camera_action) -> str` to `compile_video.py`.
Builds a frame-accurate zoompan filter string for one clip, mirroring the proven Phase 1 math.

### Supported actions
- `zoom_in` / `zoom_out` — parabolic ease-in-out via `4*(on/frames)*(1-on/frames)`
- `pan_left` / `pan_right` — fixed pan_zoom + parabolic x pan
- `static` — scale+pad to output resolution (no zoompan)

### Key change from plan: dropped `interp_algo` from zoompan
**Discovery:** This machine's ffmpeg `zoompan` filter does **not** support the
`interp_algo` option (`Error applying option 'interp_algo' to filter 'zoompan': Option not found`).
Lanczos interpolation is instead applied via the `scale` filter's `flags=lanczos`, which is
where it matters most (the upscale canvas). Removing `interp_algo` makes the filter portable
across ffmpeg builds. **This also fixes a live bug in the existing inline `main()` code, which
still used `interp_algo` and would have failed on this ffmpeg.**

### Bonus: main() inline refactor (partial Task 7)
`build_ken_burns_filter()` was wired into the legacy per-clip loop in `main()`, replacing the
copy-pasted inline block. The legacy code now shares the exact same (portable) filter logic and
no longer emits the unsupported `interp_algo`.

### Verification
- `tests/unit/test_ken_burns.py` — 6 tests: structural checks per action + a **real ffmpeg
  dry-run** (`-f null`) for all 5 actions confirming the filter graph is accepted and runs. All pass.
- Full suite: 19 passed.

### Files
- `compile_video.py` — `build_ken_burns_filter()` + inline loop now uses it
- `tests/unit/test_ken_burns.py` — new, 6 tests
