# Image Generation — Sync Timeline

Canonical sync layer that turns Whisper word timestamps and VAD pauses into image spans for Flow generation and FFmpeg compilation. Single source of truth is `timeline.json`; all legacy timestamp files are read-only shims.

## Language

**timeline**:
Canonical `timeline.json` holding `words[]` (append-only, never mutate `start`/`end` after Whisper emits) and derived `spans[]` where `spans[i].start == words[k].start`. Sole truth for sync; compile and Flow read it, shims mirror it.
_Avoid_: `image_timestamps.txt` as source, `master_roadmap.jsonl` as sync source

**beat**:
A candidate for an image cut derived from a semantic sentence/clause boundary, not a commitment. Beats are snapped to VAD pauses to become spans; downstream code must not treat every beat as a span.
_Avoid_: span, cut point

**span**:
A contiguous word group mapped to one image, snapped to the nearest VAD pause `>= VAD_SNAP_THRESHOLD`; duration constrained to `2.5 <= d <= 4.5` seconds (hard cap), split at cadence marks if longer. Merge candidates must have `pause_after < VAD_SNAP_THRESHOLD` between them.
_Avoid_: beat, chunk, segment

**snap**:
Adjustment of a beat boundary to the *nearest* VAD pause `>= VAD_SNAP_THRESHOLD` (0.35s), not the first pause `>= threshold` left-to-right. Symmetric nearest-snap prevents drift.
_Avoid_: align, waveform snap

**shim**:
A read-only legacy file generated atomically from `timeline.json` (NamedTemporaryFile + os.replace + fsync) with a `.sha256` sidecar for staleness detection; `compile_video.py:648` must refuse a stale shim. Read-only; deleted in v2.X (2 releases after introduction). Covers `image_timestamps.txt`, `timestamped_transcript.txt/srt`, `subtitle_chunks.srt`. Aliases `IMAGE_PAUSE_SPLIT` and `SILENCE_SPLIT_GAP` are deprecated shims mapping to `VAD_SNAP_THRESHOLD`.
_Avoid_: source file, manual copy

**master**:
Archival rendition `2560x1440@30` `yuv420p` (nv12 for QSV) `high@5.1` `VBV 35000k/70000k` `QSV_LOOKAHEAD=0` CFR `fps_mode cfr`, fallback `h264_qsv → h264_nvenc → libx264 veryfast crf17 tune animation` verified via `ffmpeg -encoders`.
_Avoid_: 4K, source resolution

**proxy**:
Scaled rendition (`1080p`/`720p`) derived from same `filter_complex_script` via `split→scale` (lanczos), shares Ken Burns and `frame_count == round(duration*30)` with master; `FFMPEG_THREADS 2` each.
_Avoid_: separate encode, transcode

**ladder**:
Ordered set `[1440p master, 1080p proxy, 720p proxy]` rendered in one ffmpeg invocation; `CHUNK_SIZE 20` locked, `FFMPEG_THREADS 4` master / `2` per proxy, atomically written.
_Avoid_: single-rendition, per-file config

**visual_prompt**:
Structured 8-part JSON per span (`subject, action, setting, mood, lighting, composition, style, negative_prompt`) plus `continuity_id` handle, derived from 3-span window (current ±1 with `pause_before`/`pause_after` padding at chunk boundaries); LLM fills only fields with signal, missing fields fallback to `visual_style.txt` preset at `flatten` time, not invented.
_Avoid_: freeform diffusion text, forced hallucination

**negative_prompt**:
Deterministic ban injected by validator `purge_subtitle_phrases` + `flatten`: `no text, no subtitles, no letters, no watermark, no signature, no caption, no typography, no calligraphy, no vector, no cel-shading, no 3px, no burned-in subtitles, no lower thirds, no on-screen text` (poster/chart excluded).
_Avoid_: LLM-generated negative, prompt-level ban only

**continuity_id**:
Stable handle in 8-part visual_prompt for subject tracking across chunk; built per chunk from prior `subject` fields with embedding similarity fallback (`multilingual-e5`/`bge-m3` local, cosine ≥0.78); if nearest prior match within same chunk ≥ threshold emit `SUMMON_ASSET` with `@asset` chip, else fresh; `±2` spans is soft hint, not hard cutoff.
_Avoid_: literal name match only, fresh every span
