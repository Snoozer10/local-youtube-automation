# Understood Errors & Failure Modes

## Error Patterns

### QSV Lookahead Stream Corruption
- **Cause**: Setting `-look_ahead 1` with a non-zero `-look_ahead_depth` on Intel QSV (`h264_qsv`) hardware encoder when feeding software-decoded frames causes frame pool exhaustion in the hardware memory driver. This leads to silent corruption of the output video bitstream (missing pictures in access units, invalid NAL unit sizes) despite FFmpeg exiting with return code 0.
- **Solution**: Disable lookahead by setting `QSV_LOOKAHEAD=0` in the configuration.
- **Prevention**: Ensure lookahead is deactivated when executing hybrid software-to-hardware transcode chains on this hardware/driver baseline.

### Gemini Model Selector Hydration Timing
- **Cause**: Immediately after a Gemini SPA chat reset (`reset_chat_session`), the model selector button may still be mounting in the DOM. An immediate single-pass scan fails to find the button and returns `False`. If `open_ephemeral_session` treats model selection failure as a hard error, the entire orchestration turn aborts with `RuntimeError: [roadmap] failed to deliver initial turn`.
- **Solution**: (1) Add a polling deadline loop (up to 8s) in `select_gemini_model` to allow the SPA UI to hydrate. (2) Make `open_ephemeral_session` soft-fail if model selection still cannot locate the button, continuing with the session's default model as long as the prompt input box is live.
- **Prevention**: Never assume newly navigated or SPA-reset DOM nodes mount instantaneously; poll with a reasonable timeout, and treat non-critical UI customizations (like model dropdown selection) as resilient soft-failures.

### Post-Encode Validation in Mock Subprocess Environments
- **Cause**: Calling real post-encode validation (`ffprobe`) on output targets in unit/integration test suites that mock `subprocess.Popen` via `FakePopen` (which emits no physical video file on disk).
- **Solution**: Guard post-encode probing in assembly: validate strictly when physical files exist; in mock test environments (`PYTEST_CURRENT_TEST` or `MOCK_FFMPEG`), skip probing if no file was emitted on disk, while testing `validate_post_encode` directly in its dedicated unit test suite.
- **Prevention**: Always distinguish physical hardware/subprocess execution from mocked Popen test harnesses.

## Known Failure Modes

### QSV Software-to-Hardware Frame Upload
- **What looks correct**: Setting `-pix_fmt yuv420p` in the encoder arguments or letting FFmpeg auto-convert from filtergraph outputs.
- **Why it's wrong**: Intel QuickSync (`h264_qsv`) native driver requires `nv12` pixel format inputs. Auto-selection or incorrect manual format targets lead to encoding crashes (`Invalid FrameType:0`) or bitstream corruption.
- **Correct approach**: Explicitly append the `format=nv12` filter to the end of the video filter complex when encoding with `h264_qsv`, and let the encoder output `-pix_fmt yuv420p` or `yuvj420p` for standard player compatibility.

### Dynamic Ken Burns Duration Scale Assertion Mismatch
- **What looks correct**: Asserting a fixed `min(1.08` zoom constraint in filtergraph tests when `KEN_BURNS_ZOOM_MAX=1.08` is configured.
- **Why it's wrong**: Per Spec Line 85, dynamic duration scaling (`clamp(1.06 + (duration - 2.5)/2 * 0.04, 1.06, 1.10)`) is active by default. For a 3.0s span (90 frames at 30 fps), dynamic scale evaluates to `1.07`. Fixed bounds are only applied if dynamic scaling is explicitly disabled (`KEN_BURNS_DYNAMIC_SCALE=False`).
- **Correct approach**: Test both the dynamic scaling expression under default settings and the fixed bound under `KEN_BURNS_DYNAMIC_SCALE=False`.
