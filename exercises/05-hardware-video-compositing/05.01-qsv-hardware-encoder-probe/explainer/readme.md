# Explainer: Intel QSV Hardware Encoder Probe & Invariants

## 1. Fast Synthetic Probing via FFmpeg Lavfi
Detecting whether a system supports hardware acceleration cannot rely merely on checking if the `ffmpeg -encoders` listing mentions `h264_qsv`. The binary might be compiled with QSV support, but the host machine might:
- Lack an Intel CPU / integrated graphics.
- Have outdated or missing Intel Media SDK / oneVPL graphics drivers.
- Suffer from DirectX / Media Foundation permission errors in headless environments.

The only reliable test is an end-to-end execution of a 1-frame encode using FFmpeg's synthetic `lavfi` source:
```bash
ffmpeg -y -hide_banner -loglevel error -f lavfi -i color=s=64x64:d=0.04 -c:v h264_qsv -f null -
```
If this command completes with exit code 0 in under 5 seconds, the driver pipeline is functional.

## 2. The `QSV_LOOKAHEAD=0` Invariant
Intel QSV provides a multi-frame lookahead rate-control mechanism (`-look_ahead 1 -look_ahead_depth N`).
While effective for live broadcasts, when combined with complex FFmpeg filtergraphs (such as hundreds of concatenated Ken Burns `zoompan` and `subtitles` filters):
- The lookahead thread buffers input frames waiting for future frames that the filtergraph has not yet rendered.
- The filtergraph thread waits for the encoder to consume buffered frames before emitting new ones.
- Result: **Total pipeline deadlock** — FFmpeg CPU/GPU drops to 0% and rendering hangs forever.

Therefore, `QSV_LOOKAHEAD=0` is strictly enforced across the pipeline.

## 3. NV12 Pixel Format Requirement
Intel QuickSync fixed-function hardware units operate natively on NV12 (semi-planar Y plane followed by interleaved UV plane).
Passing standard `yuv420p` causes FFmpeg to insert a hidden software format conversion filter (`swscale`) before the hardware surface upload, nullifying performance gains and introducing chroma subsampling artifacts. Enforcing `-pix_fmt nv12` guarantees zero-copy GPU memory mapping.
