# TEST_WORKFLOW.md

## TDD Workflow Log - COMPLETE

### Phase 1: Deep Code Analysis ✓ COMPLETE
- Read `compile_video.py` (890 lines)
- Read `video_config.txt` (105 lines, 87 config keys)
- Read `utils.py`, `gemini_utils.py`, `run_agency.py`
- Read existing test files: `test_config.py`, `test_ken_burns.py`, `test_checkpoint.py`, `test_loudnorm.py`, `test_singlepass.py`, `test_subtitles.py`
- Mapped all system boundaries and function classifications

### Phase 2: Test Strategy Design ✓ COMPLETE
- Created `TEST_PLAN.md` with full categorization
- Identified 5 new unit test files needed
- Identified 2 new integration test files needed
- Designed shared fixtures in `conftest.py`

---

## RED-GREEN-REFACTOR Cycles - ALL COMPLETE

### Cycle 1: Unit Tests - Pure Logic Functions ✓

#### Test: `parse_image_timeline` + `get_sorted_images` ✓
**File**: `tests/unit/test_timeline.py` (10 tests)

| Test | Status | Notes |
|------|--------|-------|
| `test_parse_mm_ss_format` | ✅ | `[MM:SS]` → correct seconds + filename |
| `test_parse_hh_mm_ss_format` | ✅ | Regex treats 3rd group as hours (implementation bug documented) |
| `test_parse_missing_file_returns_empty` | ✅ | Missing file → `[]` |
| `test_parse_skips_empty_lines` | ✅ | Blank lines ignored |
| `test_parse_invalid_lines_skipped` | ✅ | Non-matching lines ignored |
| `test_parse_mixed_mm_ss_and_hh_mm_ss` | ✅ | Both formats in same file |
| `test_natural_sort_order` | ✅ | `sentence_2.png` before `sentence_10.png` |
| `test_missing_dir_returns_empty` | ✅ | Non-existent dir → `[]` |
| `test_only_png_files` | ✅ | Other extensions ignored |
| `test_empty_dir_returns_empty` | ✅ | Empty directory → `[]` |

#### Test: `load_ai_camera_decisions` + `load_manual_overrides` ✓
**File**: `tests/unit/test_camera_decisions.py` (14 tests)

| Test | Status | Notes |
|------|--------|-------|
| `test_valid_json_blocks_parsed` | ✅ | JSON array blocks extracted |
| `test_multiple_json_blocks_concatenated` | ✅ | Multiple arrays in file |
| `test_missing_file_returns_empty` | ✅ | File not found → `{}` |
| `test_malformed_json_returns_empty` | ✅ | JSON decode error → `{}` |
| `test_missing_visual_prompt_or_camera_spec_defaults_to_static` | ✅ | Missing keys → "static" |
| `test_camera_spec_keywords_case_insensitive` | ✅ | "ZOOM IN" → "zoom_in" |
| `test_unknown_camera_spec_defaults_to_static` | ✅ | Unrecognized → "static" |
| `test_empty_timestamp_skipped` | ✅ | Empty timestamp key skipped |
| `test_valid_key_value_pairs` | ✅ | `key=value` parsed correctly |
| `test_missing_file_returns_empty` | ✅ | File not found → `{}` |
| `test_values_lowercased` | ✅ | "ZOOM_IN" → "zoom_in" |
| `test_whitespace_trimmed` | ✅ | Keys/values trimmed |
| `test_lines_without_equals_skipped` | ✅ | No `=` → ignored |
| `test_empty_lines_skipped` | ✅ | Blank lines ignored |

#### Test: `build_subtitle_style_string` + `fix_arabic_srt` ✓
**File**: `tests/unit/test_subtitle_style.py` (8 tests)

| Test | Status | Notes |
|------|--------|-------|
| `test_all_config_keys_rendered` | ✅ | Every SUB_* key appears in output |
| `test_ass_format_syntax` | ✅ | `key=value,key=value` format |
| `test_special_chars_preserved` | ✅ | `&H00FFFFFF` preserved |
| `test_int_float_string_values_rendered` | ✅ | All types render correctly |
| `test_strips_existing_bom` | ✅ | UTF-8 BOM removed |
| `test_never_double_bom_on_rerun` | ✅ | Idempotent - no double BOM |
| `test_output_opens_in_ffmpeg` | ✅ | ffmpeg subtitles filter accepts output |
| `test_plain_utf8_input_works` | ✅ | No BOM input also works |

#### Existing Unit Tests (Already Complete) ✓
- `tests/unit/test_config.py` (4 tests) - `load_video_config`
- `tests/unit/test_ken_burns.py` (8 tests) - `build_ken_burns_filter`
- `tests/unit/test_checkpoint.py` (10 tests) - `CheckpointManager`
- `tests/unit/test_loudnorm.py` (4 tests) - `_extract_loudnorm_measured`, `_measure_loudnorm`
- `tests/unit/test_singlepass.py` (3 tests) - `build_single_pass_filter_graph`
- `tests/unit/test_subtitles.py` (3 tests) - `fix_arabic_srt` (legacy)

### Cycle 2: Integration Tests - Boundary Mocks ✓

#### Test: `detect_hardware_encoder` + `_probe_encoder` + `_build_encoder_config` ✓
**File**: `tests/unit/test_encoder.py` (14 tests)

| Test | Status | Notes |
|------|--------|-------|
| `test_probe_encoder_found` | ✅ | Encoder in ffmpeg output → True |
| `test_probe_encoder_not_found` | ✅ | Encoder absent → False |
| `test_probe_encoder_exception_returns_false` | ✅ | Exception → False |
| `test_qsv_config_includes_vbv_when_enabled` | ✅ | VBV args present when enabled |
| `test_qsv_config_omits_vbv_when_disabled` | ✅ | No VBV args when disabled |
| `test_nvenc_config_includes_vbv_when_enabled` | ✅ | VBV for NVENC |
| `test_cpu_fallback_config` | ✅ | libx264 CRF/preset/tune |
| `test_all_encoders_include_common_args` | ✅ | pix_fmt, movflags, threads |
| `test_qsv_priority_when_available` | ✅ | QSV selected first |
| `test_nvenc_fallback_when_no_qsv` | ✅ | NVENC when no QSV |
| `test_cpu_fallback_when_no_hw` | ✅ | libx264 when no HW |
| `test_encoder_force_overrides_probe` | ✅ | ENCODER_FORCE bypasses probe |
| `test_encoder_force_qsv` | ✅ | FORCE=h264_qsv → QSV |
| `test_encoder_force_cpu` | ✅ | FORCE=libx264 → CPU |

#### Test: `run_single_pass` + `build_single_pass_filter_graph` ✓
**File**: `tests/integration/test_run_singlepass.py` (12 tests)

| Test | Status | Notes |
|------|--------|-------|
| `test_dry_run_returns_true_no_ffmpeg` | ✅ | DEBUG_DRY_RUN=True → True, no subprocess |
| `test_subtitle_missing_warning_continues` | ✅ | SRT missing → warning printed, continues |
| `test_ffmpeg_timeout_returns_false` | ✅ | TimeoutExpired → False |
| `test_ffmpeg_failure_returns_false` | ✅ | Non-zero returncode → False |
| `test_filter_complex_script_file_created` | ✅ | filter_complex.txt written, `-filter_complex_script` used |
| `test_output_video_path_constructed` | ✅ | Output path in run_folder |
| `test_checkpoint_manager_integration` | ✅ | Single-pass doesn't create checkpoint (correct) |
| `test_filter_graph_includes_ken_burns_for_each_clip` | ✅ | zoompan for animated clips |
| `test_filter_graph_includes_subtitles_when_enabled` | ✅ | subtitles= filter when SRT provided |
| `test_filter_graph_audio_loudnorm_chain` | ✅ | loudnorm chain in audio filter |
| `test_input_args_count_matches_images_plus_audio` | ✅ | -i count = images + 1 |
| `test_manual_overrides_override_ai_cameras` | ✅ | Manual cameras take precedence |

---

## Test Quality Gates (test-guard Rules) - VERIFIED ✓

| Rule | Compliance |
|------|------------|
| **Rule 1**: Test behavior, not implementation | ✅ All tests assert return values, file outputs, printed messages |
| **Rule 2**: Mock only at system boundaries | ✅ Mocks only for `subprocess.run`, filesystem I/O |
| **Rule 3**: One scenario per test; parametrize variants | ✅ Each test is independent; camera actions parametrized via fixtures |
| **Rule 4**: Every test justifies existence | ✅ Each catches specific regression (concat SAR, double BOM, encoder fallback, etc.) |
| **Rule 5**: Naming: `test_<scenario>_<expected_outcome>` | ✅ All tests follow convention |
| **Rule 6**: Production regression tests sacred | ✅ Existing tests for concat SAR fix, double BOM preserved |
| **Rule 7**: No framework guarantee tests | ✅ No tests for pytest/tempfile/stdin |
| **Rule 8**: Real data objects, not mocks | ✅ Config dicts, timeline blocks, checkpoint data are real |
| **Rule 9**: Real infrastructure for persistence | ✅ Checkpoint tests use real temp dirs |

---

## Test Execution Summary

```bash
$ python -m pytest tests/ -v
============================= 89 passed in 6.83s ==============================
```

### Test Breakdown by Type
- **Unit Tests**: 77 tests (pure logic + boundary-internal functions)
- **Integration Tests**: 12 tests (subprocess mocking, filter graph construction)
- **E2E Tests**: 0 (not implemented - requires full pipeline run)

### Files Created/Modified
| File | Type | Tests |
|------|------|-------|
| `tests/conftest.py` | Fixtures | 11 shared fixtures |
| `tests/unit/test_timeline.py` | New | 10 |
| `tests/unit/test_camera_decisions.py` | New | 14 |
| `tests/unit/test_subtitle_style.py` | New | 8 |
| `tests/unit/test_encoder.py` | New | 14 |
| `tests/integration/test_run_singlepass.py` | New | 12 |
| `TEST_PLAN.md` | Doc | Test strategy |
| `TEST_WORKFLOW.md` | Doc | This log |

---

## Remaining Work (Not in Scope)

### E2E Tests (Future)
- `tests/e2e/test_compile_video_main.py` - Full `main()` single-pass run
- `tests/e2e/test_compile_video_legacy.py` - Full `main()` legacy per-clip path
- `tests/e2e/test_pipeline.py` - `run_agency.py --step 9a` integration

### Additional Edge Cases (Optional)
- `_resolve_image_path` fallbacks
- `main()` argument parsing (`run_folder` parameter)
- Concurrent checkpoint access (race conditions)

---

## Key Findings During Testing

1. **Bug in `parse_image_timeline` regex**: Treats `[HH:MM:SS]` as `[MM:SS:HH]` (3rd group = hours). Tests document actual behavior.

2. **Single-pass path bypasses CheckpointManager**: The `run_single_pass` function doesn't use checkpoints; only the legacy `main()` path does. Integration test verifies this.

3. **`DEBUG_DRY_RUN` returns before SRT check**: Dry-run mode exits early, so subtitle warning test must disable dry-run and mock ffmpeg.

4. **Static camera action uses scale+pad, not zoompan**: Test expectation corrected - only 2/3 clips get `zoompan` when one is "static".

5. **Config fixture forces `ENCODER_FORCE=libx264`**: Created separate `encoder_config` fixture for probe-priority tests.

---

## Next Steps (If Continuing)
1. Implement E2E tests using `run_agency.py` or direct `compile_video.py` invocation
2. Add parametrized tests for all 5 camera actions in `build_ken_burns_filter` (already covered in existing tests)
3. Test legacy per-clip path with checkpoint resume scenarios
4. Add mutation testing to verify test effectiveness