# Spec #12: Robust Dynamic Harmonious Video Pipeline
*Status:* Accepted / Amended  
*Tracking Issue:* [GitHub Issue #12](https://github.com/Snoozer10/local-youtube-automation/issues/12)

---

## 1. Overview & Goals
Unify the video generation, sync, prompt planning, and compilation pipeline around a single, drift-free architecture:
- Single canonical sync anchor: `timeline.json` (retires disparate `.txt` / `.srt` anchor drift).
- Zero-drift 30fps CFR video compilation via hardware-accelerated encoding ladder (`h264_qsv` (nv12) $\rightarrow$ `h264_nvenc` $\rightarrow$ `libx264` (yuv420p)).
- 3-span windowed prompt planning (8-part schema, English-only diffusion text, style preservation, semantic `@asset` continuity).
- Multi-layer Text Gate (deterministic negative prompt injection, regex validator, local OCR verification).
- Content-aware Ken Burns animation math and EBU R128 (-14 LUFS / -1 dBTP) audio mastering integration.

---

## 2. Canonical `timeline.json` Schema & Rules

### Header & Word Records
```json
{
  "$schema": "timeline-v1",
  "version": "1",
  "script_hash": "sha256(refined_script.txt)",
  "wav_sha256": "sha256(full_episode_voice.wav)",
  "vad_threshold_used": 0.35,
  "created_at": "ISO-8601 Timestamp",
  "words": [
    {
      "id": 0,
      "word": "مرحبا",
      "start": 1.230,
      "end": 1.560,
      "score": 0.92,
      "pause_after": 0.410
    }
  ],
  "spans": [
    {
      "id": 0,
      "start": 1.230,
      "end": 4.100,
      "duration": 2.870,
      "frame_count": 86,
      "start_frame": 0,
      "end_frame": 86,
      "pause_before": 0.410,
      "pause_after": 0.380,
      "text": "مرحبا بكم في الحلقة",
      "word_indices": [0, 5],
      "visual_prompt_id": "vp_000",
      "is_short": false,
      "weak_snap": false,
      "status": "pending"
    }
  ]
}
```

### Invariants & Partitioning Policies
1. **Append-Only Words:** `words[]` is immutable once transcribed; timestamps are never mutated by lexical correctors.
2. **Derived Integer Spans:**
   $$\text{end\_frame} = \text{round}(\text{end\_sec} \times 30), \quad \text{frame\_count} = \text{end\_frame} - \text{start\_frame}$$
   Guarantees zero cumulative drift across 100+ clips. Total video frames = $\sum \text{frame\_count}$.
3. **Nearest Snap & Fast Amiya Cadence:**
   - Search radius $\pm1.5\text{s}$ for VAD pauses $\ge 0.35\text{s}$.
   - If no qualifying pause exists, snap to nearest word boundary, set `weak_snap = true`, and log a warning.
4. **Short-Span Handling:**
   - Spans with $1.5\text{s} \le \text{duration} < 2.5\text{s}$ are marked `is_short = true` and padded to 75 frames (2.5s @ 30fps) using last-frame freeze-hold instead of triggering illegal merge errors.

---

## 3. Hardware-Accelerated Encoding Ladder

1. **Probe Hierarchy:**
   - Probe `h264_qsv` (`format=nv12`, `QSV_LOOKAHEAD=0`, high profile 5.1). No 1080p resolution caps.
   - Probe `h264_nvenc` (`format=nv12`, p4 preset, VBV 35000k/70000k).
   - Fallback `libx264` (`format=yuv420p`, veryfast, CRF 17).
2. **Filter Complex Script:** Always write FFmpeg complex filter graphs to a temp file in the run folder when $>512$ characters to avoid Windows `MAX_PATH` / command-line length limits.
3. **Configuration Sync:** Ensure `video_config.txt` and `transcribe_config.txt` match ADR-0002 lock settings.

---

## 4. Prompt Planning & Text Gate

1. **3-Span Window Context:** Prompts planned using current span $\pm1$ neighbor context with `pause_before` / `pause_after` boundary padding.
2. **Style vs Negative Prompt Separation:**
   - `style_anchor` (e.g., `3px black vector outlines, 2-step cel-shading`) is explicitly exempt from `purge_subtitle_phrases`.
   - Negative bans target text overlays only: `no text, no letters, no subtitles, no watermark, no signature, no caption, no typography`.
3. **OCR Verification:** Pytesseract confidence threshold calibrated to $\ge 75\%$ for 1440p vector linework to eliminate false positives on geometric hatching.

---

## 5. Checkpoint & Invalidation Contract

1. **Atomic Invalidation:**
   `compile_checkpoint.json` binds its cache state to:
   $$\text{render\_signature} = \text{"{W}x{H}@{fps}:{timeline\_sha256[:8]}:{encoder}"}$$
   Regenerating or altering `timeline.json` automatically triggers a clean recompilation.