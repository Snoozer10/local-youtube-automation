# Note: Cumulative Integer Quantization and Frame Budgeting

**Category:** Timeline Synchronization & Video Kinematics  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/video/compiler.py`, `src/youtube_automation/timeline/engine.py`, `tests/unit/test_timeline_quantization_invariants.py`  
**Audit Reference:** Section 6.3 (Timeline Frame Mathematics, Beat Taxonomy & Storyboard Matrix Engineering), Module 6C  

### 1. Core Rule in Plain English
When converting audio clause timestamps into video timeline cuts:
1. **Canonical Ingestion Bypass**: If input image blocks are canonical spans loaded from `timeline.json` (indicated by the presence of `"span"` in blocks), the video compiler must directly preserve the pre-quantized `start_frame`, `end_frame`, and `frame_count` attributes without executing legacy acoustic re-snapping or comedic grouping.
2. **Monotonic Chaining Guarantee**: The starting frame of each clip must strictly lock to the ending frame of the preceding clip (`start_frame = current_frame`), eliminating inter-clip voids or overlaps.
3. **Cumulative Integer Quantization**: Invariant total frame budget is derived as $\text{Total Audio Frames} = \text{round}(\text{Audio Duration} \times \text{FPS})$. The final clip's `end_frame` is strictly clamped to $\text{Total Audio Frames}$, ensuring zero-drift over long-form productions (e.g., exactly 40,030 frames over 1334.34s).
4. **Sample-Exact WAV Duration**: Audio duration must be computed directly from the WAV header sample count and sample rate (`wf.getnframes() / float(wf.getframerate())`), eliminating sub-second ffprobe container rounding drift.
5. **Multi-Shot Occurrence Isolation**: A local occurrence counter must track the 1-based occurrence per timestamp name, preventing multi-shot cuts sharing the same second alias (e.g. `01_15_01.png` and `01_15_02.png`) from clobbering one another in downstream asset resolution.

### 2. The Failure Mode It Prevents
- **Dual-Timeline Drift**: Re-running acoustic silence snapping and ad-hoc grouping inside `compiler.py` when `timeline.json` was already computed causes cut points to shift away from speech boundaries, causing visual cuts to lag or lead spoken words.
- **Inter-Clip Voids**: Independently rounding floating-point timestamps (`round(start * fps)` and `round(end * fps)`) can introduce 1-to-3 frame dead-air black holes or frame collisions between adjacent clips.
- **Multi-Shot Clamping Bug**: Incrementing occurrence globally (`occurrence = idx + 1`) rather than per-name causes multi-shot cuts within the same second to clamp to `len(matching) - 1`, repeatedly rendering the last variant and dropping earlier images.
- **Terminal Desync Crashes**: A single frame mismatch between total video packets and rounded audio duration causes `validate_post_encode` to throw a fatal error.

### 3. Implementation Specification
Implemented in `src/youtube_automation/video/compiler.py`:
```python
def prepare_synchronized_timeline(
    image_blocks: list, audio_duration: float, fps: int, audio_path: str = None
) -> list:
    if not image_blocks:
        return []

    # 1. Canonical timeline ingestion bypass
    if all(isinstance(b, dict) and "span" in b for b in image_blocks):
        final_timeline = []
        fps_float = float(fps)
        total_audio_frames = max(1, int(round(audio_duration * fps_float)))
        num_blocks = len(image_blocks)

        # Degenerate-input guard: fold surplus blocks if blocks exceed available audio frames
        if num_blocks > total_audio_frames:
            image_blocks = image_blocks[:total_audio_frames]
            num_blocks = len(image_blocks)

        name_counts: dict[str, int] = {}
        current_frame = 0

        for idx, b in enumerate(image_blocks):
            span = b["span"]
            name = str(b.get("name", "clip"))

            # Track 1-based occurrence per timestamp name to prevent asset resolution clobbering
            name_counts[name] = name_counts.get(name, 0) + 1
            occurrence = b.get("occurrence") or name_counts[name]

            start_frame = current_frame

            if idx == num_blocks - 1:
                end_frame = total_audio_frames
            else:
                raw_end = span.get("end_frame")
                if raw_end is not None:
                    ideal_end = int(raw_end)
                else:
                    ideal_end = int(round(float(span.get("end", b.get("raw_sec", b["sec"]))) * fps_float))

                remaining = num_blocks - 1 - idx
                end_frame = max(start_frame + 1, min(ideal_end, total_audio_frames - remaining))

            frame_count = max(1, end_frame - start_frame)
            current_frame = end_frame

            final_timeline.append(
                {
                    "name": name,
                    "sec": start_frame / fps_float,
                    "end_sec": end_frame / fps_float,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "frame_count": frame_count,
                    "duration": frame_count / fps_float,
                    "occurrence": occurrence,
                    "span": span,
                    "text": b.get("text", span.get("text", "")),
                }
            )
        return final_timeline
```

In `src/youtube_automation/timeline/engine.py`:
```python
def get_wav_duration(wav_path: str) -> float:
    """Computes exact audio duration directly from WAV header sample count and sample rate."""
    import wave
    with wave.open(wav_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        if rate <= 0:
            raise ValueError(f"Invalid WAV sample rate: {rate}")
        return frames / float(rate)
```

### 4. Verification & Validation Evidence
1. **Unit Test Suite**: `tests/unit/test_timeline_quantization_invariants.py` (6/6 tests PASS):
   - `test_wav_header_duration_precision`: Verifies header calculation against synthesized test WAVs.
   - `test_canonical_timeline_ingestion_bypasses_resnapping`: Asserts exact 1:1 match of all 293 production spans (`start_frame`, `end_frame`, `frame_count`).
   - `test_cumulative_integer_quantization_zero_drift`: Verifies total frame count equals exactly 40,030 with zero inter-clip gaps or overlaps.
   - `test_legacy_blocks_fallback_unaffected`: Verifies that legacy ad-hoc blocks route to acoustic snapping without regressions.
   - `test_multi_shot_timestamp_occurrence_isolation`: Verifies unique `occurrence: 1`, `occurrence: 2` assignments on duplicate timestamp keys.
   - `test_canonical_timeline_degenerate_surplus_fold`: Verifies surplus blocks are folded safely without inversion.
2. **Regression Suites**:
   - `tests/unit/test_timeline_sync.py` and `tests/unit/test_ffprobe_duration.py` (27/27 tests PASS).
   - Full unit test suite: 488/488 tests PASS in 26.63s (0 regressions).
   - Exercise scaffold linter: 35/35 files verified clean (`python tools/lint_exercises.py`).
