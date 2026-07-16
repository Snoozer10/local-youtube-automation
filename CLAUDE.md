# YouTube Video Automation Pipeline

## Tech Stack
- **Language**: Python 3.10+ (Windows only)
- **Video Processing**: FFmpeg (direct CLI subprocess execution)
- **Audio Processing**: Audacity Macro automation (PyAutoGUI, named pipes)
- **Browser Automation**: Playwright (connecting to Chrome/Opera via remote CDP)
- **Testing**: pytest (unit and integration tests)

## Commands
- **Run Video compiler**: `python compile_video.py`
- **Run full test suite**: `python -m pytest tests/ -v`
- **Run single test file**: `python -m pytest tests/unit/test_timeline.py -v`

## Key Conventions & Gotchas
- **Intel QSV Lookahead**: Always keep `QSV_LOOKAHEAD=0` in configuration. Enabling QSV lookahead with software-decoded input streams causes hardware frame pool starvation and silent bitstream corruption.
- **Explicit Pixel Formatting**: Always append `format=nv12` (for QSV hardware encoder) or `format=yuv420p` (for CPU/nvenc) at the very end of the video filter complex before mapping.
- **Hardware Fallback**: All single-pass FFmpeg rendering must implement the retry loop with automatic fallback to software `libx264` if hardware acceleration fails.
- **Asset Validation**: Verify clip images exist on disk and have non-zero size before calling FFmpeg.
- **Windows Command Length Limits**: Filter graphs exceeding ~32K characters must be written to a temporary file and loaded using `-/filter_complex` (FFmpeg v5+) rather than passed directly via command line arguments.
