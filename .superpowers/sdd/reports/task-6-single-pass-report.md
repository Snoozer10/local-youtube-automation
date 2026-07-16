# Task 6 Report: Single-Pass Filter Graph

## Implementation

Added the single-pass render path to `compile_video.py`, replacing the legacy
3-stage (clip → concat → final) pipeline with one FFmpeg invocation that does
per-clip Ken Burns → concat → subtitles → audio loudnorm → mux.

### Functions added
- `build_subtitle_style_string(config)` — ASS `force_style` from `SUB_*` keys
- `build_single_pass_filter_graph(config, encoder_config, image_blocks, images_dir,
  audio_path, subtitle_path, ai_cameras, manual_cameras, anim_enabled)`
  → `(input_args, filter_complex, video_label)`
- `run_single_pass(config, encoder_config, image_blocks, images_dir, audio_path, run_folder)` → bool
- `_measure_loudnorm(audio_path, config)` — loudnorm pass-1 measure + filter string (Task 9 partial)
- `_extract_loudnorm_measured(stderr, config, run_folder)` — parse + persist measured values (Task 9)
- `_resolve_image_path(...)` — shared image fallback (also used by legacy loop)

### Critical bug fixed during implementation
The plan's final `[vscaled][aout]concat=v=1:a=1[final]` step **fails** with
`Cannot find an unused video input stream to feed the unlabeled input pad concat`.
A `concat` for muxing one video + one audio is unnecessary — the two streams are
mapped directly (`-map [vscaled] -map [aout]`). Verified with ffmpeg: works.

### Loudnorm correction
The plan erroneously applied `loudnorm` to the **video** stream. Loudnorm is an
audio filter; the video path now passes through (`copy`/scale) and only the audio
stream (`[N:a]loudnorm...[aout]`) is normalized. Two-pass is achieved via
`_measure_loudnorm` (measure pass) feeding measured values into the single combined
audio+video pass — 2 invocations total instead of 3.

### main() refactor
`main(run_folder=None)` now:
- Single-pass path when `ENABLE_SINGLE_PASS=true` (default) → `run_single_pass`
- Legacy path when disabled, now checkpoint-aware (Task 7) + config/encoder driven
- Cleans `temp_clips/` on single-pass success unless `DEBUG_SAVE_INTERMEDIATES`

### Verification
- Unit: `tests/unit/test_singlepass.py` (3 tests) — graph structure, triple return,
  subtitle path. All pass.
- Integration: rendered a 3-image / 6s synthetic clip → **1920x1080 h264 + aac**,
  subtitles burned, loudnorm applied. Validated with **both** `libx264` (forced) and
  the default `h264_qsv` encoder — QSV single-pass works on this hardware.

### Files
- `compile_video.py` — single-pass functions + main() refactor
- `tests/unit/test_singlepass.py` — new, 3 tests
