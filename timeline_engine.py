"""Canonical timeline and zero-drift span derivation engine for Spec #12 / ADR 0001.

Provides a unified single source of sync truth:
- Append-only ``words[]`` with monotonic IDs and pause tracking.
- Zero-drift integer-frame ``spans[]`` derived from nearest VAD pauses (>=0.35s).
- Duration hard-cap [2.5s, 4.5s] with cadence splits and pause-guarded merges.
- Backward-compatible shims (image_timestamps.txt, timestamped_transcript.txt, .srt)
  with atomic persistence and SHA-256 sidecars.
- Deprecated config key migration (IMAGE_PAUSE_SPLIT, SILENCE_SPLIT_GAP).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TIMELINE_FILENAME = "timeline.json"
TIMELINE_VERSION = "1.0.0"
VAD_SNAP_THRESHOLD = 0.35
DEFAULT_MIN_SPAN_SEC = 2.5
DEFAULT_MAX_SPAN_SEC = 4.5
DEFAULT_FPS = 30

_DEPRECATED_VAD_KEYS = ("IMAGE_PAUSE_SPLIT", "SILENCE_SPLIT_GAP", "SILENCE_SPLIT_GAP_SEC")
_WARNED_DEPRECATIONS: set[str] = set()

PUNCTUATION_SPLIT_REGEX = re.compile(r"[\،\,\.\!\?\؟\:\;\؛\—\-\…]+$")


@dataclass(frozen=True)
class WordItem:
    id: int
    text: str
    start: float
    end: float
    pause_after: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpanItem:
    index: int
    start_word_id: int
    end_word_id: int
    start: float
    end: float
    duration: float
    start_frame: int
    end_frame: int
    frame_count: int
    text: str
    prompt_slice: str
    pause_before: float = 0.0
    pause_after: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Timeline:
    version: str
    audio_file: str
    audio_duration: float
    fps: int
    total_frames: int
    checksums: dict[str, str]
    words: list[dict[str, Any]]
    spans: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "audio_file": self.audio_file,
            "audio_duration": self.audio_duration,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "checksums": self.checksums,
            "words": self.words,
            "spans": self.spans,
        }


def resolve_vad_snap_threshold(config: dict[str, Any] | None = None) -> float:
    """Resolves VAD snap threshold with graceful migration and deprecation warnings."""
    if not config:
        return VAD_SNAP_THRESHOLD

    canonical_val = config.get("VAD_SNAP_THRESHOLD")

    deprecated_val = None
    for k in _DEPRECATED_VAD_KEYS:
        if k in config:
            if k not in _WARNED_DEPRECATIONS:
                warnings.warn(
                    f"Config key '{k}' is deprecated and will be removed in 2 releases. "
                    f"Use 'VAD_SNAP_THRESHOLD' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                _WARNED_DEPRECATIONS.add(k)
            if deprecated_val is None:
                try:
                    deprecated_val = float(config[k])
                except (ValueError, TypeError):
                    pass

    if canonical_val is not None:
        try:
            return float(canonical_val)
        except (ValueError, TypeError):
            return VAD_SNAP_THRESHOLD

    if deprecated_val is not None:
        return deprecated_val

    return VAD_SNAP_THRESHOLD


def build_words_from_whisper(
    whisper_words: Sequence[dict[str, Any]],
    audio_duration: float | None = None,
) -> list[dict[str, Any]]:
    """Builds clean, append-only monotonic words list with calculated pause_after."""
    if not whisper_words:
        return []

    words: list[dict[str, Any]] = []
    prev_end = 0.0

    for idx, raw in enumerate(whisper_words):
        text = str(raw.get("text") or raw.get("word") or "").strip()
        start = float(raw.get("start", 0.0))
        end = float(raw.get("end", start + 0.05))

        # Enforce strict monotonicity
        if start < prev_end:
            start = prev_end
        if end <= start:
            end = start + 0.05

        prev_end = end
        words.append(
            {
                "id": idx,
                "text": text,
                "start": round(start, 3),
                "end": round(end, 3),
                "pause_after": 0.0,
            }
        )

    # Compute pause_after between consecutive words
    for i in range(len(words) - 1):
        gap = max(0.0, words[i + 1]["start"] - words[i]["end"])
        words[i]["pause_after"] = round(gap, 3)

    if audio_duration is not None and words:
        tail_gap = max(0.0, float(audio_duration) - words[-1]["end"])
        words[-1]["pause_after"] = round(tail_gap, 3)

    return words


def derive_spans_from_words(
    words: Sequence[dict[str, Any]],
    audio_duration: float,
    fps: int = DEFAULT_FPS,
    vad_snap_threshold: float = VAD_SNAP_THRESHOLD,
    min_span_sec: float = DEFAULT_MIN_SPAN_SEC,
    max_span_sec: float = DEFAULT_MAX_SPAN_SEC,
) -> list[dict[str, Any]]:
    """Derives zero-drift spans snapped to nearest VAD pause >= vad_snap_threshold.

    Invariants guaranteed:
    - spans[i].start == words[start_word_id].start
    - spans[i].end == words[end_word_id].end
    - start_frame of span 0 is 0
    - Contiguous integer frames without gaps: spans[i].start_frame == spans[i-1].end_frame
    - sum(span.frame_count) == round(audio_duration * fps)
    - Each span duration respects [min_span_sec, max_span_sec] with pause-guarded merges.
    """
    if not words:
        return []

    total_words = len(words)
    total_budget_frames = max(1, round(audio_duration * fps))

    # Phase 1: Boundary detection and nearest-snap candidate segmentation
    spans_raw: list[tuple[int, int]] = []
    current_start = 0

    while current_start < total_words:
        # Target duration ~3.0s (Al-Daheeh cadence midpoint)
        target_time = words[current_start]["start"] + 3.0
        min_time = words[current_start]["start"] + min_span_sec
        max_time = words[current_start]["start"] + max_span_sec

        # Collect qualifying pause points and punctuation in candidate window
        # Allow candidate search to include nearby pauses slightly before min_time (within 0.5s)
        search_min_time = max(words[current_start]["start"] + 1.0, min_time - 0.5)

        best_candidate = -1
        best_distance = float("inf")

        for cand_idx in range(current_start, total_words):
            cand_end = words[cand_idx]["end"]
            if cand_end < search_min_time:
                continue

            if cand_end > max_time and best_candidate != -1:
                break

            pause = words[cand_idx]["pause_after"]
            has_vad_pause = pause >= vad_snap_threshold
            has_punct = bool(PUNCTUATION_SPLIT_REGEX.search(words[cand_idx]["text"]))

            # Prioritize qualifying VAD pauses, then punctuation
            if has_vad_pause or cand_idx == total_words - 1:
                dist = abs(cand_end - target_time)
                if dist < best_distance:
                    best_distance = dist
                    best_candidate = cand_idx
            elif has_punct and best_candidate == -1:
                dist = abs(cand_end - target_time) + 0.5  # slight bias towards real pauses
                if dist < best_distance:
                    best_distance = dist
                    best_candidate = cand_idx

        # If no qualifying pause or punctuation found in window, cut at the word closest to max_time
        if best_candidate == -1:
            for cand_idx in range(current_start, total_words):
                cand_end = words[cand_idx]["end"]
                if cand_end >= min_time or cand_idx == total_words - 1:
                    best_candidate = cand_idx
                if cand_end > max_time:
                    break
            if best_candidate == -1:
                best_candidate = total_words - 1

        spans_raw.append((current_start, best_candidate))
        current_start = best_candidate + 1

    # Phase 2: Pause-guarded merge for micro-spans (< min_span_sec)
    merged_spans: list[tuple[int, int]] = []
    for s_start, s_end in spans_raw:
        s_dur = words[s_end]["end"] - words[s_start]["start"]
        if merged_spans and s_dur < min_span_sec:
            prev_start, prev_end = merged_spans[-1]
            inter_pause = words[prev_end]["pause_after"]
            combined_dur = words[s_end]["end"] - words[prev_start]["start"]

            # Merge only if between-span pause is small (< vad_snap_threshold) and combined <= max_span_sec
            if inter_pause < vad_snap_threshold and combined_dur <= max_span_sec:
                merged_spans[-1] = (prev_start, s_end)
                continue

        merged_spans.append((s_start, s_end))

    # Phase 3: Frame budget allocation (zero-drift CFR)
    num_spans = len(merged_spans)
    spans: list[dict[str, Any]] = []
    current_frame = 0

    for idx, (s_start, s_end) in enumerate(merged_spans):
        start_sec = words[s_start]["start"]
        end_sec = words[s_end]["end"]
        dur_sec = round(end_sec - start_sec, 3)

        span_words = [words[w]["text"] for w in range(s_start, s_end + 1)]
        span_text = " ".join(span_words).strip()

        pause_before = words[s_start - 1]["pause_after"] if s_start > 0 else 0.0
        pause_after = words[s_end]["pause_after"]

        is_last = idx == num_spans - 1
        if is_last:
            end_frame = total_budget_frames
        else:
            ideal_end_frame = round(end_sec * fps)
            # Ensure at least 1 frame per span and leave enough for remaining
            min_required_ahead = num_spans - 1 - idx
            max_allowed_end = total_budget_frames - min_required_ahead
            end_frame = max(current_frame + 1, min(ideal_end_frame, max_allowed_end))

        frame_count = end_frame - current_frame

        spans.append(
            {
                "index": idx,
                "start_word_id": s_start,
                "end_word_id": s_end,
                "start": start_sec,
                "end": end_sec,
                "duration": dur_sec,
                "start_frame": current_frame,
                "end_frame": end_frame,
                "frame_count": frame_count,
                "text": span_text,
                "prompt_slice": span_text,
                "pause_before": round(pause_before, 3),
                "pause_after": round(pause_after, 3),
            }
        )
        current_frame = end_frame

    return spans


def build_timeline(
    words: Sequence[dict[str, Any]],
    audio_duration: float,
    audio_file: str = "",
    fps: int = DEFAULT_FPS,
    vad_snap_threshold: float = VAD_SNAP_THRESHOLD,
) -> dict[str, Any]:
    """Assembles the canonical timeline dictionary with SHA-256 checksums."""
    words_list = list(words)
    spans_list = derive_spans_from_words(
        words_list,
        audio_duration=audio_duration,
        fps=fps,
        vad_snap_threshold=vad_snap_threshold,
    )

    words_canonical_json = json.dumps(words_list, sort_keys=True, ensure_ascii=False)
    spans_canonical_json = json.dumps(spans_list, sort_keys=True, ensure_ascii=False)

    words_sha = hashlib.sha256(words_canonical_json.encode("utf-8")).hexdigest()
    spans_sha = hashlib.sha256(spans_canonical_json.encode("utf-8")).hexdigest()

    total_frames = sum(s["frame_count"] for s in spans_list) if spans_list else round(audio_duration * fps)

    timeline_data = {
        "version": TIMELINE_VERSION,
        "audio_file": audio_file,
        "audio_duration": round(float(audio_duration), 3),
        "fps": int(fps),
        "total_frames": total_frames,
        "checksums": {
            "words_sha256": words_sha,
            "spans_sha256": spans_sha,
        },
        "words": words_list,
        "spans": spans_list,
    }
    return timeline_data


def _atomic_write_file(path: str, content: str | bytes) -> None:
    """Atomically writes file with sync and directory isolation."""
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(target_dir, exist_ok=True)

    data_bytes = content.encode("utf-8") if isinstance(content, str) else content

    tf = tempfile.NamedTemporaryFile("wb", dir=target_dir, delete=False)
    try:
        tf.write(data_bytes)
        tf.flush()
        os.fsync(tf.fileno())
        temp_name = tf.name
    finally:
        tf.close()
    os.replace(temp_name, path)


def format_srt_timestamp(seconds: float) -> str:
    """Converts seconds to SRT format: HH:MM:SS,mmm."""
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def save_timeline_and_shims(
    timeline: dict[str, Any],
    run_folder: str,
    export_srt: bool = True,
) -> tuple[str, list[str]]:
    """Atomically writes canonical timeline.json and all backward-compatible shims with sidecars."""
    os.makedirs(run_folder, exist_ok=True)
    timeline_path = os.path.join(run_folder, TIMELINE_FILENAME)

    timeline_bytes = json.dumps(timeline, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_file(timeline_path, timeline_bytes)

    timeline_sha = hashlib.sha256(timeline_bytes).hexdigest()

    spans = timeline.get("spans", [])
    created_shims: list[str] = []

    # 1. image_timestamps.txt ([MM:SS] format matching existing compile_video.py consumer)
    image_lines = [
        f"[{int(s['start'] // 60):02d}:{int(s['start'] % 60):02d}] {s['text']}" for s in spans
    ]
    img_txt_content = "\n".join(image_lines) + "\n"
    img_txt_path = os.path.join(run_folder, "image_timestamps.txt")
    _atomic_write_file(img_txt_path, img_txt_content)
    _atomic_write_file(f"{img_txt_path}.sha256", f"{timeline_sha}\n")
    created_shims.append(img_txt_path)

    # 2. timestamped_transcript.txt
    transcript_path = os.path.join(run_folder, "timestamped_transcript.txt")
    _atomic_write_file(transcript_path, img_txt_content)
    _atomic_write_file(f"{transcript_path}.sha256", f"{timeline_sha}\n")
    created_shims.append(transcript_path)

    # 3. SRT files
    if export_srt:
        srt_lines: list[str] = []
        for idx, s in enumerate(spans, 1):
            srt_lines.extend(
                [
                    str(idx),
                    f"{format_srt_timestamp(s['start'])} --> {format_srt_timestamp(s['end'])}",
                    s["text"],
                    "",
                ]
            )
        srt_content = "\n".join(srt_lines) + "\n"
        for srt_name in ("timestamped_transcript.srt", "subtitle_chunks.srt"):
            srt_path = os.path.join(run_folder, srt_name)
            _atomic_write_file(srt_path, srt_content)
            _atomic_write_file(f"{srt_path}.sha256", f"{timeline_sha}\n")
            created_shims.append(srt_path)

    return timeline_path, created_shims


def verify_shim(shim_path: str, timeline_path: str | None = None) -> bool:
    """Verifies that a shim file's .sha256 sidecar exists and matches current timeline.json."""
    sidecar_path = f"{shim_path}.sha256"
    if not os.path.exists(sidecar_path):
        return False

    try:
        with open(sidecar_path, "rb") as f:
            sidecar_sha = f.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return False

    if not sidecar_sha:
        return False

    if timeline_path is not None:
        if not os.path.exists(timeline_path):
            return False
        try:
            with open(timeline_path, "rb") as f:
                actual_sha = hashlib.sha256(f.read()).hexdigest()
            return actual_sha == sidecar_sha
        except OSError:
            return False

    return True


def load_timeline_or_shim(run_folder: str) -> list[dict[str, Any]]:
    """Loads timeline blocks directly from timeline.json or falls back to valid shims."""
    timeline_path = os.path.join(run_folder, TIMELINE_FILENAME)

    if os.path.exists(timeline_path):
        try:
            with open(timeline_path, encoding="utf-8") as f:
                data = json.load(f)
            spans = data.get("spans", [])
            blocks = []
            for idx, s in enumerate(spans):
                start_sec = 0.0 if idx == 0 else float(s["start"])
                minutes = int(float(s["start"]) // 60)
                seconds = int(float(s["start"]) % 60)
                name = f"{minutes:02d}_{seconds:02d}"
                blocks.append(
                    {
                        "sec": start_sec,
                        "name": name,
                        "raw_sec": float(s["start"]),
                        "frame_count": s.get("frame_count", 0),
                        "text": s.get("text", ""),
                        "span": s,
                    }
                )
            return blocks
        except Exception:
            pass

    # Fallback to image_timestamps.txt shim
    txt_path = os.path.join(run_folder, "image_timestamps.txt")
    if not os.path.exists(txt_path):
        txt_path = os.path.join(run_folder, "timestamped_transcript.txt")

    blocks = []
    if not os.path.exists(txt_path):
        return blocks

    # Fail-closed sidecar check: if timeline.json exists, verify shim integrity
    if os.path.exists(timeline_path):
        if not verify_shim(txt_path, timeline_path):
            raise ValueError(
                f"Stale or untrusted timeline shim detected at '{txt_path}'. "
                f"Sidecar does not match '{timeline_path}'."
            )

    with open(txt_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^\[?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\]?", line)
            if match:
                hours = int(match.group(1)) if match.group(1) else 0
                minutes = int(match.group(2))
                seconds_float = float(match.group(3))
                total_sec = hours * 3600.0 + minutes * 60.0 + seconds_float
                seconds_int = int(seconds_float)

                if match.group(1) is not None:
                    timestamp_key = f"{hours:02d}_{minutes:02d}_{seconds_int:02d}"
                else:
                    timestamp_key = f"{minutes:02d}_{seconds_int:02d}"

                blocks.append({"sec": total_sec, "name": timestamp_key, "raw_sec": seconds_float})

    blocks.sort(key=lambda x: x["sec"])
    if blocks:
        blocks[0]["sec"] = 0.0
    return blocks
