# HANDOFF — compile_video.py Phase 2 (Tasks 1–10)

> **For a new empty session:** Copy this entire file into the new session as the opening prompt, then continue from the "Next Move" section. All paths are absolute; the project root is:
> `C:\Users\Snoozer\Downloads\Antigravity\Youtube Automation 2\buckup\Version 4 before deepseek implementation plan\image_generation`

---

## Objective
Harden `compile_video.py` (YouTube automation pipeline, Windows, FFmpeg) for smooth cinematic Ken Burns + image/audio sync. Phase 1 (earlier session) fixed bugs + smooth animations (tested, produced 12:06 video @ -14.58 LUFS). Phase 2 externalizes config, auto-detects hardware encoder (QSV→NVENC→CPU), replaces 3-stage clip→concat→final with single-pass filter graph, adds checkpoint/resume, testable refactor via TDD.

## Critical Environment Facts
- Windows 10/11, i7-5600U (2C/4T), 16GB RAM, Intel HD 5500 (QSV=`h264_qsv`), NVIDIA 840M (NVENC=`h264_nvenc`).
- Python 3.11.9, ffmpeg/ffprobe on PATH, pytest installed (`pip install pytest`).
- **MUST-KNOW ffmpeg quirk:** this machine's `zoompan` filter does **NOT** support `interp_algo` (error: "Option not found"). Lanczos is applied via `scale` `flags=lanczos` instead. Never add `interp_algo` to zoompan.
- `video_config.txt` is `key=value` format (like `gemini_model.txt`). `run_agency.py` is orchestrator; must stay compatible.
- Shell is **PowerShell** (no `&&`/`||`; use `;` or `cd ...; command`). `ls -la` fails; use `dir`. UTF-8 for Arabic.
- All AI/CLAUDE/AGENTS.md instructions override defaults; skills/superpowers take precedence.

## Work State (all committed to git master)

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 1. video_config.txt schema (71 keys) | ✅ Done | early | Authoritative config |
| 2. Config loader `load_video_config()` | ✅ Done | `4ec410f` | + `tests/unit/test_config.py` (4 tests) |
| 3. Hardware encoder detect | ✅ Done | `70b86fa` | `_probe_encoder`, `_build_encoder_config`, `detect_hardware_encoder` |
| 4. CheckpointManager | ✅ Done | `c39e76b` | + `tests/unit/test_checkpoint.py` (9 tests) |
| 5. Ken Burns filter builder | ✅ Done | `2bdf99c` | `build_ken_burns_filter()` + `tests/unit/test_ken_burns.py` (6 tests) |
| 6. Single-pass filter graph | ✅ Done | `3a47566` | `build_single_pass_filter_graph`, `run_single_pass`, `_measure_loudnorm`, `_extract_loudnorm_measured` + `tests/unit/test_singlepass.py` (3 tests) |
| 7. Legacy per-clip refactor | ✅ Done | `66bd64d` | Done inside Task 6 `main()` rewrite; validated via `validate_legacy.py` |
| 8. run_agency.py Phase 9 integration | ✅ Done | `f5dd17d` | Passes `folder` explicitly + timeout=3600 + capture_output |
| **9. Loudnorm two-pass persistence** | ⏳ **TODO** | — | Code exists (Task 6); needs verify + own commit |
| **10. End-to-end validation** | ⏳ **TODO** | — | Run on real 116-clip data |

## Key Discoveries / Deviations (DO NOT REVERT)
1. `interp_algo` removed from `zoompan` (unsupported here) → lanczos via `scale flags=lanczos`.
2. Plan's final `concat=v=1:a=1[final]` is **invalid** → replaced with direct `-map [vscaled] -map [aout]`.
3. Plan applied `loudnorm` to **video** stream (wrong) → only audio normalized; video passes through.
4. `mark_clip_done` saves every clip (not interval) for reliable resume.
5. QSV single-pass verified working (software filter → `h264_qsv` auto-uploads).
6. `main(run_folder=None)` accepts explicit folder; `run_agency.py` now passes it.

## Functions in compile_video.py (signatures)
- `load_video_config(config_path="video_config.txt") -> dict` — typed loader, DEFAULTS dict.
- `detect_hardware_encoder(config) -> dict` — keys: `video_codec`, `encoder_name`, `hwaccel`, `encoder_args`. Priority QSV→NVENC→CPU; respects `ENCODER_FORCE`.
- `CheckpointManager(run_folder, config)` — `initialize`, `is_clip_done(i)`, `mark_clip_done(i,path,dur)`, `mark_clip_failed(i,err)`, `get_pending_indices()`, `get_concat_entries()`, `cleanup_on_success()`, `_load()`, `save()` (atomic).
- `build_ken_burns_filter(config, duration, camera_action) -> str` — actions: `zoom_in`,`zoom_out`,`pan_left`,`pan_right`,`static`.
- `build_subtitle_style_string(config) -> str` — ASS force_style from `SUB_*` keys.
- `build_single_pass_filter_graph(config, encoder_config, image_blocks, images_dir, audio_path, subtitle_path, ai_cameras, manual_cameras, anim_enabled) -> (input_args, filter_complex, video_label)`.
- `run_single_pass(config, encoder_config, image_blocks, images_dir, audio_path, run_folder) -> bool`.
- `_measure_loudnorm(audio_path, config) -> str` — loudnorm pass-1 measure + filter string.
- `_extract_loudnorm_measured(stderr, config, run_folder) -> dict` — parses measured values, persists to `video_config.local.txt`.
- `_resolve_image_path(block, idx, images_dir, available_images, last_valid_image) -> (path, name)`.
- `main(run_folder=None)` — single-pass default (`ENABLE_SINGLE_PASS=true`) + checkpoint-aware legacy fallback.

## Next Move (continue from here)
Execute **Task 9**, then **Task 10**. After each: run `python -m pytest tests/unit/ -q`, then commit.

### Task 9 — Loudnorm two-pass persistence (verify + commit)
- Code already in place (`_measure_loudnorm` + `_extract_loudnorm_measured` in `compile_video.py`).
- Verify: run `compile_video.py` on a small test run (or unit-test `_extract_loudnorm_measured` by feeding fake stderr JSON). Confirm `video_config.local.txt` is written in run folder with `LOUDNORM_MEASURED_*` keys.
- Add `tests/unit/test_loudnorm.py` (parse test: feed JSON string, assert measured values extracted + written).
- Write `.superpowers/sdd/reports/task-9-loudnorm-persistence-report.md`.
- Commit: `feat: loudnorm two-pass measurement persistence`.

### Task 10 — End-to-end validation (real 116-clip run)
- Test data: `youtube_runs/Everyday Habits That Boost Brain Power/` (116 images in `generated_images/`, `timestamped_transcript.txt`, `timestamped_transcript.srt`, `full_episode_voice.wav` ~12min).
- Run: `python compile_video.py` (single-pass default, auto QSV). Validate output `youtube_ready_video.mp4`:
  - `ffprobe`: 1920x1080, yuv420p, ~24fps, h264 (qsv) or libx264.
  - Audio: aac, 192k, 48kHz, loudnorm ~-16 LUFS.
  - VBV: `ffprobe -show_streams` maxrate/bufsize (10M/20M if enabled).
  - Subtitles burned (Arabic).
- Checkpoint resume test: interrupt mid-render, re-run, confirm it resumes (only do if `ENABLE_CHECKPOINT_RESUME=true` — but single-pass is one invocation, so resume matters more for legacy path; verify legacy `ENABLE_SINGLE_PASS=false` resumes from `compile_checkpoint.json`).
- Write `.superpowers/sdd/reports/task-10-e2e-validation-report.md` with measured results.
- Commit: `test: end-to-end validation on 116-clip run`.

## Validation Scripts (in repo root, temporary)
- `validate_legacy.py` — legacy path smoke test (`ENABLE_SINGLE_PASS=false`, CPU). Re-runnable.
- Delete after Task 10 or keep as integration scaffold.

## Relevant Files
- `compile_video.py` — main script (all Phase 2 logic).
- `video_config.txt` — 71-key schema.
- `run_agency.py` — orchestrator, Phase 9 at lines 197-224.
- `tests/unit/test_config.py`, `test_checkpoint.py`, `test_ken_burns.py`, `test_singlepass.py` — 22 tests total (all passing).
- `docs/superpowers/plans/2025-07-11-compile-video-phase2.md` — original 10-task plan.
- `.superpowers/sdd/reports/task-{3,4,5,6,7,8}-*.md` — per-task reports.
- `youtube_runs/Everyday Habits That Boost Brain Power/` — real test data.

## Quick Command Reference
```powershell
cd "C:\Users\Snoozer\Downloads\Antigravity\Youtube Automation 2\buckup\Version 4 before deepseek implementation plan\image_generation"
python -m pytest tests/unit/ -q          # run unit tests
python -m py_compile compile_video.py    # syntax check
python compile_video.py                  # run single-pass on latest run
python validate_legacy.py                # legacy path smoke test
```

## Open Questions (answered earlier, default behavior)
- Single-pass is the **default** (`ENABLE_SINGLE_PASS=true`). ✅ Keep.
- QSV auto-selected (fastest on this HW). ✅ Keep.
- User approved Tasks 7→10 scope (no adjustments).
