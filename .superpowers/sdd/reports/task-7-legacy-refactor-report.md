# Task 7 Report: Legacy Per-Clip Mode Refactor

## Summary
The legacy per-clip pipeline (used when `ENABLE_SINGLE_PASS=false`) was fully refactored inside `main()` during Task 6. No separate commit needed for code changes — the logic was integrated as part of the single-pass rewrite.

## What the legacy path now uses
- **Encoder**: `encoder_config["video_codec"]` + `encoder_config["encoder_args"]` (QSV/NVENC/CPU auto-detected).
- **Ken Burns**: `build_ken_burns_filter(config, duration, camera_action)` — single shared implementation.
- **Checkpoint**: `CheckpointManager` — `is_clip_done()` skips rendered clips; `mark_clip_done()` persists every clip; `get_concat_entries()` builds `concat.txt` from checkpoint (resume-safe).
- **Timeouts**: `config["FFMPEG_CLIP_TIMEOUT"]` (per-clip) + `config["FFMPEG_FINAL_TIMEOUT"]` (final).
- **Loudnorm**: `_measure_loudnorm(audio_path, config)` reuses the two-pass measure logic.
- **Subtitles**: `build_subtitle_style_string(config)` shared with single-pass.

## Validation
Ran `validate_legacy.py` (temp config: `ENABLE_SINGLE_PASS=false`, `ENCODER_FORCE=libx264`):
- 3 clips rendered (2s each, STATIC camera)
- Final compositing with subtitles + loudnorm succeeded
- Output: 1920x1080 h264 + aac
- `compile_checkpoint.json` deleted on success (auto-cleanup)

## Tests
No new unit test file added — legacy behavior is exercised by:
- `test_checkpoint.py` (checkpoint manager)
- `test_ken_burns.py` (filter builder used by both paths)
- `test_singlepass.py` (shared helpers)
- Manual integration via `validate_legacy.py`

## Files Touched
- `compile_video.py` — legacy branch inside `main()` (refactored during Task 6 commit `3a47566`)

## Commit
This report commits as Task 7 completion marker.