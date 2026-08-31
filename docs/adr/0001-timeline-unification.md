# 0001: Unify sync sources into canonical timeline.json

We had fragmented sync files (`image_timestamps.txt` as anchor, `timestamped_transcript.txt/srt`, `transcribe_config.txt` buckets `2.2/3.5/4.8s` + `5-12 words`, and `master_roadmap.jsonl` 25-row pages) with 9 drift sources including VAD key-name mismatch and ±0.20s waveform snap. We unify to a single `timeline.json` as the sole sync truth: `words[]` is append-only (never mutate `start`/`end` after Whisper emits) plus derived `spans[]` (`spans[i].start == words[k].start`), where spans are snapped to the nearest VAD pause `>= VAD_SNAP_THRESHOLD=0.35s` and constrained to `2.5 <= d <= 4.5s` with cadence splits and pause-guarded merges (`pause_after < threshold`).

## Considered Options

- **Keep split files**: `image_timestamps.txt` + `master_roadmap.jsonl` stay co-equal sources. Rejected: perpetuates drift, config-vs-code bucket mismatches, and ambiguous trust when prompt and span disagree.
- **Unify to timeline.json (chosen)**: single artifact, legacy files become read-only shims auto-generated atomically (NamedTemporaryFile + os.replace + fsync) with `.sha256` sidecar; `compile_video.py:648` refuses stale fallback; deprecated aliases `IMAGE_PAUSE_SPLIT`/`SILENCE_SPLIT_GAP` map to `VAD_SNAP_THRESHOLD` with `DeprecationWarning` once per process, removed in 2 releases. `WAVEFORM_ALIGN_WINDOW_MS=20` is kept separate (sample-level alignment, not beat snapping).

## Consequences

- `master_roadmap.jsonl` stays as *planning input* (Gemini paging, 7-cell `NONE` pad, 2 repairs) — not a sync source. `timeline.json` is *sync output*; shims derive from timeline only. Document boundary to avoid trust ambiguity.
- Span invariants: `span.duration` hard-capped at `4.5s`; merge of `<2.5s` spans forbidden across `>=0.35s` pauses to preserve visual breaths; snap is nearest, not greediest.
- Deprecation timeline pinned here: shims deleted in v2.X (2 releases); sidecar check remains until then.
- Zero-drift CFR (`round(duration*30)`, `fps_mode cfr`) unchanged but now reads `duration` from spans, not buckets.

Status: accepted
