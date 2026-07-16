# Understood Errors & Failure Modes

## Error Patterns

### QSV Lookahead Stream Corruption
- **Cause**: Setting `-look_ahead 1` with a non-zero `-look_ahead_depth` on Intel QSV (`h264_qsv`) hardware encoder when feeding software-decoded frames causes frame pool exhaustion in the hardware memory driver. This leads to silent corruption of the output video bitstream (missing pictures in access units, invalid NAL unit sizes) despite FFmpeg exiting with return code 0.
- **Solution**: Disable lookahead by setting `QSV_LOOKAHEAD=0` in the configuration.
- **Prevention**: Ensure lookahead is deactivated when executing hybrid software-to-hardware transcode chains on this hardware/driver baseline.

## Known Failure Modes

### QSV Software-to-Hardware Frame Upload
- **What looks correct**: Setting `-pix_fmt yuv420p` in the encoder arguments or letting FFmpeg auto-convert from filtergraph outputs.
- **Why it's wrong**: Intel QuickSync (`h264_qsv`) native driver requires `nv12` pixel format inputs. Auto-selection or incorrect manual format targets lead to encoding crashes (`Invalid FrameType:0`) or bitstream corruption.
- **Correct approach**: Explicitly append the `format=nv12` filter to the end of the video filter complex when encoding with `h264_qsv`, and let the encoder output `-pix_fmt yuv420p` or `yuvj420p` for standard player compatibility.
