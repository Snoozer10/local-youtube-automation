# Test Plan: compile_video.py

## Overview
This document outlines the comprehensive test strategy for the video compilation pipeline in `compile_video.py`. The pipeline supports two compilation paths:
1. **Single-pass** (Phase 2 default): One FFmpeg invocation with complex filtergraph
2. **Legacy per-clip**: Checkpoint-resume per clip, then concat + final mux

## System Boundaries (Mock Targets)

| Boundary | Type | Mock Strategy |
|----------|------|---------------|
| `ffmpeg` / `ffprobe` subprocess | External process | Patch `subprocess.run` / `subprocess.check_output` |
| Filesystem I/O (`youtube_runs/`) | Local FS | `tempfile.mkdtemp` fixtures with real files |
| `video_config.txt` parsing | Config file | Real parser with temp files |
| `flow_prompts.json` / `manual_animations.txt` | JSON/Text files | Real parser with temp files |
| Audio duration (`ffprobe`) | External process | Mock `get_audio_duration` return value |
| Loudnorm measurement (`ffmpeg -af loudnorm`) | External process | Mock `_measure_loudnorm` return value |

## Function Classification

### Unit Tests (Pure Logic - No Mocks Needed)
| Function | Test File | Key Scenarios |
|----------|-----------|---------------|
| `load_video_config` | `tests/unit/test_config.py` ✓ | Missing file → defaults; type coercion (bool/int/float/str); unknown keys ignored; comment/blank handling |
| `build_ken_burns_filter` | `tests/unit/test_ken_burns.py` ✓ | All 5 camera actions (zoom_in/out, pan_left/right, static); boundary durations (MIN/MAX_CLIP_DURATION); parabolic easing formula; SAR/pixfmt normalization; concat compatibility |
| `parse_image_timeline` | **NEW** `tests/unit/test_timeline.py` | `[MM:SS]` and `[HH:MM:SS]` formats; missing file → empty list; empty lines skipped; timestamp→filename mapping |
| `load_ai_camera_decisions` | **NEW** `tests/unit/test_camera_decisions.py` | Valid JSON blocks; malformed JSON; missing keys; camera_spec parsing (zoom in/out/pan left/right/static) |
| `load_manual_overrides` | **NEW** `tests/unit/test_camera_decisions.py` | Valid `key=value` lines; missing file → empty dict; case-insensitive values |
| `build_subtitle_style_string` | **NEW** `tests/unit/test_subtitles.py` | All config keys rendered correctly; ASS format escaping |
| `fix_arabic_srt` | `tests/unit/test_subtitles.py` ✓ | UTF-8 BOM stripping; no double BOM; ffmpeg compatibility |
| `get_sorted_images` | **NEW** `tests/unit/test_timeline.py` | Natural sort (sentence_2 before sentence_10); missing dir → empty list |
| `CheckpointManager` | `tests/unit/test_checkpoint.py` ✓ | Atomic write (tmp+replace); resume from partial; clip_done verifies file exists; cleanup on success |

### Integration Tests (Boundary Mocking)
| Function | Test File | Mock Targets |
|----------|-----------|--------------|
| `detect_hardware_encoder` | `tests/unit/test_encoder.py` (NEW) | `subprocess.run` for `ffmpeg -encoders`; ENCODER_FORCE override; QSV→NVENC→CPU priority |
| `_measure_loudnorm` | `tests/unit/test_loudnorm.py` ✓ | `subprocess.run` for loudnorm measure pass; JSON parsing; local config persistence |
| `build_single_pass_filter_graph` | `tests/unit/test_singlepass.py` ✓ | Real filter construction; subtitle injection; loudnorm chain; command-line length workaround |
| `run_single_pass` | **NEW** `tests/integration/test_run_singlepass.py` | Dry-run mode; subtitle missing warning; FFmpeg timeout; checkpoint integration |

### E2E Tests (Full Pipeline)
| Scenario | Test File | Invocation |
|----------|-----------|------------|
| Single-pass render | `tests/e2e/test_compile_video.py` (NEW) | `python compile_video.py <run_folder>` |
| Legacy per-clip + checkpoint resume | `tests/e2e/test_compile_video.py` (NEW) | `ENABLE_SINGLE_PASS=false python compile_video.py <run_folder>` |
| run_agency.py step 9a integration | `tests/e2e/test_pipeline.py` (NEW) | `python run_agency.py --step 9a` |

## Test Quality Gates (test-guard Rules)

Every test must satisfy:
- **Rule 1**: Test BEHAVIOR not implementation (assert return values/state, not internal calls)
- **Rule 2**: Mock ONLY at system boundaries (ffmpeg, filesystem, network)
- **Rule 3**: One scenario per test; `@pytest.mark.parametrize` for variants
- **Rule 4**: Justify existence: "What bug does this catch?"
- **Rule 5**: Name pattern: `test_<scenario>_<expected_outcome>`
- **Rule 6**: Production regression tests are sacred (never delete)
- **Rule 7**: No tests for framework guarantees (pytest, stdlib, ffmpeg CLI)
- **Rule 8**: Use REAL data objects (config dicts, timeline blocks, checkpoint data)
- **Rule 9**: Real infrastructure when persistence is under test (not needed here)

## Coverage Map

| Module | Functions | Unit | Integration | E2E |
|--------|-----------|------|-------------|-----|
| config | `load_video_config` | ✅ | - | - |
| ken_burns | `build_ken_burns_filter` | ✅ | - | - |
| timeline | `parse_image_timeline`, `get_sorted_images` | 🆕 | - | - |
| camera | `load_ai_camera_decisions`, `load_manual_overrides` | 🆕 | - | - |
| subtitles | `fix_arabic_srt`, `build_subtitle_style_string` | ✅/🆕 | - | - |
| checkpoint | `CheckpointManager` | ✅ | - | - |
| encoder | `detect_hardware_encoder`, `_probe_encoder`, `_build_encoder_config` | - | 🆕 | - |
| loudnorm | `_measure_loudnorm`, `_extract_loudnorm_measured` | ✅ | ✅ | - |
| singlepass | `build_single_pass_filter_graph`, `run_single_pass` | ✅ | 🆕 | - |
| main | `main()` single-pass path | - | - | 🆕 |
| main | `main()` legacy path | - | - | 🆕 |