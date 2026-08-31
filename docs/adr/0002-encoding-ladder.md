# 0002: Lock 1440p master + adaptive proxy ladder

Baseline drift: `video_config.txt` advertised `2560x1440@30 yuv420p high@5.1` but `compile_video.py:280` skipped QSV `>1080p`, falling back to NVENC/libx264 for 1440p. We lock baseline verbatim and fix code to honor `2560x1440` QSV via `format=nv12` path, with `VBV 35000k/70000k`, `QSV_LOOKAHEAD=0` mandatory, `high@5.1`, `CFR fps_mode cfr`, `filter_complex_script >1K`, `CHUNK_SIZE 20` (not 40), fallback `h264_qsv → h264_nvenc → libx264 veryfast crf17 tune animation` verified via `ffmpeg -encoders`.

## Considered Options

- **Per-rendition separate encodes**: one ffmpeg per resolution. Rejected: repeats Ken Burns, risks frame drift between renditions, slower.
- **Conditional proxies (only if >10min)**: Rejected: adds branching, delivery needs predictable ladder.
- **Shared graph split→scale (chosen)**: one ffmpeg `split=3 [1440][1080][720]` each `scale=-2:height:flags=lanczos`, same Ken Burns before split, atomic writes, `frame_count == round(duration*30)` per clip and total, validated postflight via `ffprobe` duration ±0.02s.

## Consequences

- Always render `1080p` + `720p` proxies from same graph; no on-demand path. `FFMPEG_THREADS 4` master / `2` per proxy (total ≤6), workers cap `1` on `2C` libx264 remains as guard.
- Validation gates: preflight `ffmpeg -encoders` probe for `h264_qsv`/`hevc_qsv`, postflight `frame_count` zero-drift, file magic + `ffprobe` duration, log fallback chain used.
- Fix QSV skip to use `nv12` for 1440p QSV; keep `qsv→nvenc→libx264` order.

Status: accepted
