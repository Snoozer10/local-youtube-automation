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

## Known Failure Modes

### QSV Software-to-Hardware Frame Upload
- **What looks correct**: Setting `-pix_fmt yuv420p` in the encoder arguments or letting FFmpeg auto-convert from filtergraph outputs.
- **Why it's wrong**: Intel QuickSync (`h264_qsv`) native driver requires `nv12` pixel format inputs. Auto-selection or incorrect manual format targets lead to encoding crashes (`Invalid FrameType:0`) or bitstream corruption.
- **Correct approach**: Explicitly append the `format=nv12` filter to the end of the video filter complex when encoding with `h264_qsv`, and let the encoder output `-pix_fmt yuv420p` or `yuvj420p` for standard player compatibility.
