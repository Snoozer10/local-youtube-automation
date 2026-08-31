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
