# Drill 05.01: Intel QuickSync (QSV) Hardware Encoder Probe & Invariants

## Objectives
- Master hardware-accelerated video encoding diagnostics using FFmpeg.
- Probe hardware encoders (`h264_qsv`, `h264_nvenc`) using synthetic single-frame color pipelines (`lavfi color=s=64x64:d=0.04`).
- Enforce Intel QuickSync hardware constraints:
  - `QSV_LOOKAHEAD=0`: strictly disabling lookahead to prevent deadlocks and frame drop stalls in dynamic filtergraphs.
  - `format=nv12`: enforcing native 8-bit 4:2:0 semi-planar NV12 pixel format required by QuickSync silicon (avoiding CPU color matrix round-trips).
- Implement the 3-tier encoder selection fallback hierarchy (`h264_qsv` ──► `h264_nvenc` ──► `libx264`).
- Annotate hardware probe verification with `@pytest.mark.drill`.

## Architectural Context
In video rendering ([`encoder.py`](file:///C:/Users/Snoozer/Downloads/Antigravity/Youtube%20Automation%202/buckup/Version%204%20before%20deepseek%20implementation%20plan/image_generation/src/youtube_automation/video/encoder.py)), 1080p and 1440p episodes contain hundreds of Ken Burns animation segments. Software encoding via CPU `libx264` takes 15-20 minutes; Intel QuickSync reduces this to under 2 minutes.
However, if QSV drivers or parameters are misconfigured (e.g. `look_ahead > 0` with dynamic graphs), FFmpeg hangs indefinitely. Pre-flight probing validates hardware capability before initiating rendering:

```
[detect_hardware_encoder]
         │
         ├─ Probe 'h264_qsv' on synthetic frame ──► Success? ──► Use QSV (lookahead=0, nv12)
         │                                               │ No
         ├─ Probe 'h264_nvenc' on synthetic frame ◄──────┘
         │               │ Success?
         │               ├─ Yes ──► Use NVENC
         │               └─ No  ──► Fallback to CPU libx264 (animation tuned)
```

## Input/Output Contracts
- `probe_encoder(encoder_name: str, timeout: float = 5.0) -> bool`:
  - Executes `ffmpeg -y -hide_banner -loglevel error -f lavfi -i color=s=64x64:d=0.04 -c:v <encoder_name> -f null -`.
  - Returns `True` if exit code is 0 within timeout, `False` on non-zero exit or error.
- `build_encoder_arguments(encoder: str, config: dict[str, Any]) -> dict[str, Any]`:
  - Generates parameter dictionary including `video_codec`, `hwaccel`, and `encoder_args`.
  - Enforces `-look_ahead 0` and `-pix_fmt nv12` when `encoder == "h264_qsv"`.
- `resolve_pipeline_encoder(config: dict[str, Any], probe_func: Any = None) -> dict[str, Any]`:
  - Executes the hierarchy and returns the resolved configuration dictionary.

## Drill Variants
- [Detailed Architectural Explainer](explainer/readme.md)
- [Problem Workspace (Student)](problem/exercise.py)
- [Solution Reference](solution/exercise.py)
- [Solution Verification Tests](solution/test_exercise.py)
