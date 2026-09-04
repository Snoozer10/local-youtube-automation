"""Stateless Phase-2 planning engine: converts script lines into Flow keyframe JSON.

Consumes the Master Visual Continuity Roadmap produced by ``roadmap_orchestrator``
and drives Gemini through per-chunk, single-turn conversations that emit
``flow_prompts.json`` payloads validated against :class:`validator.FrameItem`.
Every chunk is checkpointed in the shared ``PipelineManifest`` so reruns skip
completed work, self-heal gaps in the same session, and merge cleanly with any
surviving baseline file.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, TypeGuard

from pydantic import ValidationError

from gemini_controller import (
    ensure_persistent_gemini_session,
    inject_prompt_via_cdp,
    jitter_delay,
    log,
    wait_for_gemini_turn_completion,
)
from json_sanitizer import clean_and_repair_json
from pipeline_manifest import ChunkStatus, PipelineManifest
from roadmap_orchestrator import RoadmapRow
from validator import (
    FrameItem,
    transliterate_arabic_fallback,
    validate_english_only_prompt,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

FLOW_PROMPTS_FILENAME = "flow_prompts.json"
DEBUG_DIRNAME = "debug"
PLANNING_BUFFER_ROWS = 1
_ERROR_EXCERPT_LIMIT = 200
_DONE_STATUSES = frozenset({ChunkStatus.VERIFIED.value, ChunkStatus.REPAIRED.value})

STYLE_DNA_TEXT = (
    "2D graphic vector animation explainer style, crisp 3px black vector outlines, "
    "flat 2-step cel-shading, 16:9 widescreen"
)
_FORBIDDEN_TERMS: list[str] = [
    "subtitles",
    "margin",
    "watermark",
    "Latin text",
    "English overlay",
    "photorealism",
    "3D CGI",
    "gradients",
]
_SEQUENCE_TYPE_ENUM = (
    "STANDALONE | PROGRESSIVE_BUILD_SET | REACTION_PUNCHLINE_SET | HISTORICAL_PARODY | "
    "SCIENTIFIC_BLUEPRINT | ARCHIVAL_DOSSIER | COMPARATIVE_DIAGRAM | SKEPTIC_SPLIT"
)
_LAYOUT_ENUM = (
    "AHWA_STUDIO | ARCHIVAL_DOSSIER | COMPARATIVE_DIAGRAM_DESK | RETRO_BLUEPRINT | "
    "HISTORICAL_MUSEUM | ISOLATED_WHITE"
)
_CAMERA_ENUM = "zoom_in | zoom_out | pan_left | pan_right | tilt_up | tilt_down | static"
_VISUAL_DENSITY_ENUM = "DENSE_SCENE | MINIMALIST_MACRO | MEDIUM_ACTION"
_SCHEMA_HINT = (
    '[{"index": <int>, "timestamp": "[MM:SS]", "sequence_type": <enum>, '
    '"layout_classification": <token>, '
    '"sequence_metadata": {"set_id": "SET_NN", "frame_index": <int>, '
    '"total_frames_in_set": <int>}, "visual_density": <enum>, '
    '"visual_prompt": {"subject": "<character/subject in English>", '
    '"action": "<action description in English>", '
    '"setting": "<environment/background in English>", '
    '"mood": "<emotional tone in English>", '
    '"lighting": "<lighting style in English or omit>", '
    '"composition": "<framing geometry in English>", '
    '"style": "<2D vector animation style or omit>", '
    '"negative_prompt": "<negative elements or omit>", '
    '"continuity_id": "<SUBJ_NN or NONE>"}}]'
)


class ChunkPlanningError(RuntimeError):
    """Raised when a chunk cannot be planned, validated, or persisted."""

    def __init__(
        self,
        message: str,
        chunk_id: str = "",
        missing_indices: list[int] | None = None,
        debug_dump_path: str = "",
    ) -> None:
        super().__init__(message)
        self.chunk_id = chunk_id
        self.missing_indices: list[int] = list(missing_indices) if missing_indices else []
        self.debug_dump_path = debug_dump_path


def _condense(text: str) -> str:
    return " ".join(text.split())


def _is_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def build_3span_window_context(
    spans: list[dict[str, Any]],
    target_index: int,
) -> dict[str, Any]:
    """
    Constructs a 3-span window context ([i-1, i, i+1]) with boundary pause padding (ADR 0003).
    """
    spans_by_idx = {s["index"]: s for s in spans if isinstance(s, dict) and "index" in s}
    current = spans_by_idx.get(target_index)
    if current is None:
        raise ValueError(f"Span index {target_index} not found in spans")

    prev_span = spans_by_idx.get(target_index - 1)
    next_span = spans_by_idx.get(target_index + 1)

    pause_before = float(current.get("pause_before", 0.0))
    pause_after = float(current.get("pause_after", 0.0))

    return {
        "current_span": current,
        "prev_span": prev_span,
        "next_span": next_span,
        "pause_before": pause_before,
        "pause_after": pause_after,
    }


class SubjectContinuityTracker:
    """
    Tracks and matches subjects across spans in a chunk/video session (ADR 0003).
    Emits SUMMON_ASSET continuity references when cosine/token similarity >= 0.78.
    """

    def __init__(self, similarity_threshold: float = 0.78) -> None:
        self.similarity_threshold = similarity_threshold
        self._table: list[dict[str, Any]] = []

    def register_subject(self, canonical_name: str, subject_text: str) -> str:
        continuity_id = f"SUBJ_{len(self._table) + 1:02d}"
        self._table.append({
            "continuity_id": continuity_id,
            "canonical_name": canonical_name,
            "subject_text": subject_text,
        })
        return continuity_id

    def _similarity(self, s1: str, s2: str) -> float:
        t1, t2 = s1.lower().strip(), s2.lower().strip()
        if not t1 or not t2:
            return 0.0
        if t1 == t2 or t1 in t2 or t2 in t1:
            return 1.0
        words1 = set(re.findall(r"\w+", t1))
        words2 = set(re.findall(r"\w+", t2))
        if not words1 or not words2:
            return 0.0

        stopwords = {"with", "and", "or", "at", "the", "in", "on", "a", "an", "for", "to", "of", "character"}
        w1_clean = words1 - stopwords
        w2_clean = words2 - stopwords
        if not w1_clean or not w2_clean:
            w1_clean, w2_clean = words1, words2

        shared = w1_clean & w2_clean
        overlap = len(shared) / min(len(w1_clean), len(w2_clean))

        matcher = difflib.SequenceMatcher(None, t1, t2)
        match = matcher.find_longest_match(0, len(t1), 0, len(t2))
        longest_match_len = match.size

        # If significant named phrase (>=12 chars) or >=2 core content words overlap with >=50% coverage
        if longest_match_len >= 12 or (len(shared) >= 2 and overlap >= 0.5):
            return max(0.85, overlap)

        jaccard = len(words1 & words2) / len(words1 | words2)
        ratio = matcher.ratio()
        return max(overlap, jaccard, ratio)

    def resolve_subject(self, query_subject: str) -> tuple[str, float, bool]:
        best_id = ""
        best_sim = 0.0
        for entry in self._table:
            sim_name = self._similarity(query_subject, entry["canonical_name"])
            sim_desc = self._similarity(query_subject, entry["subject_text"])
            sim = max(sim_name, sim_desc)
            if sim > best_sim:
                best_sim = sim
                best_id = entry["continuity_id"]

        is_match = best_sim >= self.similarity_threshold
        return (best_id if is_match else "", best_sim, is_match)

    find_match = resolve_subject


def extract_roadmap_slice(
    roadmap_rows: list[RoadmapRow],
    start_idx: int,
    end_idx: int,
    buffer: int = PLANNING_BUFFER_ROWS,
) -> list[RoadmapRow]:
    """Rows whose index falls inside [start - buffer, end + buffer], sorted ascending."""
    return sorted(
        (row for row in roadmap_rows if start_idx - buffer <= row.index <= end_idx + buffer),
        key=lambda row: row.index,
    )


def _render_preset_section(title: str, specs: dict[str, Any], description_key: str) -> list[str]:
    lines = [f"{title}:"]
    for token, spec in specs.items():
        if not isinstance(spec, dict):
            continue
        name = _condense(str(spec.get("name", token)))
        description = _condense(str(spec.get(description_key, "")))
        lines.append(f'  {token}: "{name}. {description}"')
    return lines


def build_compact_preamble(presets: dict[str, Any] | None) -> str:
    """Token-dense YAML-style block anchoring asset tokens, style DNA, and output contract."""
    lines: list[str] = ["# KEYFRAME PROMPT ARCHITECT (AL-DAHEEH VISUAL STYLE V5)"]
    if presets:
        characters = presets.get("CHARACTERS")
        if isinstance(characters, dict):
            lines.extend(_render_preset_section("CHARACTERS", characters, "info"))
        scenes = presets.get("SCENES")
        if isinstance(scenes, dict):
            lines.extend(_render_preset_section("SCENES", scenes, "scene_prompt"))
    lines.extend(
        [
            f"ENUM sequence_type: {_SEQUENCE_TYPE_ENUM}",
            f"ENUM layout_classification: {_LAYOUT_ENUM}",
            f"ENUM camera_specifications: {_CAMERA_ENUM}",
            f"ENUM visual_density: {_VISUAL_DENSITY_ENUM}",
            f"SCHEMA: {_SCHEMA_HINT}",
            f'STYLE_DNA: "{STYLE_DNA_TEXT}"',
            f"FORBIDDEN: {json.dumps(_FORBIDDEN_TERMS, ensure_ascii=False)}",
            "TYPOGRAPHY & LANGUAGE: Prompt text must be strictly in ENGLISH. Zero Arabic characters allowed in visual_prompt fields (Arabic Kufic typography prohibited, text overlay must be \"NONE\"). Zero on-screen text, zero watermarks, zero typography overlays.",
            "OUTPUT: ONE raw JSON array covering EXACTLY the requested Index span; no prose, "
            "no fences, no repeated objects",
        ]
    )
    return "\n".join(lines)


def build_chunk_payload(
    preamble: str,
    slice_rows: list[RoadmapRow],
    script_lines: list[tuple[int, str, str]],
    spans: list[dict[str, Any]] | None = None,
) -> str:
    """Single-turn prompt: preamble + buffered roadmap table + 3-span windowed script lines + span directive."""
    lines: list[str] = [
        preamble,
        "",
        "CRITICAL: timestamp field must be copied VERBATIM from SCRIPT LINES including brackets, e.g. [00:00] - never leave empty",
        "",
        "ROADMAP CONTEXT (target span +/- buffer):",
    ]
    for row in slice_rows:
        cells = [
            _condense(str(row.index)),
            _condense(row.timestamp),
            _condense(row.script_line),
            _condense(row.sequence_type),
            _condense(row.layout_classification),
            _condense(row.camera_specification),
            _condense(row.visual_concept),
            _condense(row.color_and_arabic_text),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "SCRIPT LINES TO CONVERT:"])
    for global_index, timestamp, sentence in script_lines:
        span_ctx = None
        if spans:
            try:
                span_ctx = build_3span_window_context(spans, global_index)
            except Exception:
                span_ctx = None
        line_desc = f"Index {global_index} [{timestamp}] {_condense(sentence)}"
        if span_ctx:
            p_before = span_ctx.get("pause_before", 0.0)
            p_after = span_ctx.get("pause_after", 0.0)
            prev_s = span_ctx.get("prev_span")
            next_s = span_ctx.get("next_span")
            prev_txt = f" | Prev: '{_condense(prev_s.get('text', ''))}'" if prev_s and prev_s.get("text") else ""
            next_txt = f" | Next: '{_condense(next_s.get('text', ''))}'" if next_s and next_s.get("text") else ""
            line_desc += f" (pause_before={p_before:.2f}s, pause_after={p_after:.2f}s{prev_txt}{next_txt})"
        lines.append(line_desc)
    first = script_lines[0][0] if script_lines else 0
    last = script_lines[-1][0] if script_lines else 0
    lines.append("")
    lines.append(f"Emit the JSON array for Indices {first}..{last} now.")
    return "\n".join(lines)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=str(path.parent), delete=False, encoding="utf-8", suffix=".tmp"
        ) as handle:
            tmp_path = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        tmp_path = None
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _load_baseline_frames(prompts_path: Path) -> dict[int, dict[str, Any]]:
    if not prompts_path.exists():
        return {}
    try:
        with open(prompts_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        log(f"[planner] unreadable {prompts_path.name}: {exc}; starting from empty baseline.")
        return {}
    frames: dict[int, dict[str, Any]] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and _is_int(item["index"]):
                frames[item["index"]] = item
    return frames


def _persist_frames(prompts_path: Path, frames_by_index: dict[int, dict[str, Any]]) -> None:
    prompts_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [frames_by_index[index] for index in sorted(frames_by_index)]
    _atomic_write_text(prompts_path, json.dumps(ordered, ensure_ascii=False, indent=2))


def _dump_debug(folder: Path, filename: str, payload: dict[str, Any]) -> str:
    debug_dir = folder / DEBUG_DIRNAME
    debug_dir.mkdir(parents=True, exist_ok=True)
    dump_path = debug_dir / filename
    _atomic_write_text(dump_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return str(dump_path)


def _validation_error_excerpt(exc: ValidationError) -> str:
    fragments = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        fragments.append(f"{location}: {error.get('msg', 'invalid value')}")
    return "; ".join(fragments)[:_ERROR_EXCERPT_LIMIT]


def _absorb_valid_items(
    raw_response: str,
    start_idx: int,
    end_idx: int,
    timestamp_map: dict[int, str] | None = None,
    continuity_tracker: SubjectContinuityTracker | None = None,
) -> tuple[dict[int, dict[str, Any]], dict[int, str]]:
    try:
        items = clean_and_repair_json(raw_response)
    except ValueError as exc:
        log(f"[planner] response cleanup yielded nothing: {exc}")
        return {}, {}
    valid: dict[int, dict[str, Any]] = {}
    errors: dict[int, str] = {}
    for item in items:
        raw_index = item.get("index")
        if not _is_int(raw_index) or not start_idx <= raw_index <= end_idx:
            continue
        # Auto-repair empty timestamp from expected map (fixes Gemini empty ts bug)
        if item.get("timestamp") == "" and timestamp_map and raw_index in timestamp_map:
            repaired_ts = timestamp_map[raw_index]
            log(f"[planner] auto-repair empty timestamp for index {raw_index} -> {repaired_ts}")
            item["timestamp"] = repaired_ts

        # Auto-repair Arabic characters in visual prompt English fields (ADR 0003 & Spec #12)
        vp = item.get("visual_prompt")
        if isinstance(vp, dict):
            for field in (
                "subject",
                "action",
                "setting",
                "mood",
                "lighting",
                "composition",
                "style",
                "negative_prompt",
                "subject_details",
                "subject_action_increment",
                "environment_coordinates",
                "composition_layout",
                "style_anchor",
            ):
                val = vp.get(field)
                if isinstance(val, str) and val:
                    valid_en, _ = validate_english_only_prompt(val)
                    if not valid_en:
                        log(f"[planner] transliterating Arabic in index {raw_index} field {field}")
                        vp[field] = transliterate_arabic_fallback(val)

            # Continuity tracking (Spec line 91)
            subj = (vp.get("subject") or vp.get("subject_details", "")).strip()
            if subj and continuity_tracker:
                c_id, sim, is_match = continuity_tracker.find_match(subj)
                if is_match:
                    vp["continuity_id"] = c_id
                elif not vp.get("continuity_id") or vp.get("continuity_id") == "NONE":
                    vp["continuity_id"] = continuity_tracker.register_subject(
                        f"Subject_{raw_index}", subj
                    )

        try:
            FrameItem.model_validate(item)
        except ValidationError as exc:
            err_excerpt = _validation_error_excerpt(exc)
            errors[raw_index] = err_excerpt
            log(f"[planner] validation failed index {raw_index}: {err_excerpt} | raw_ts={repr(item.get('timestamp'))} | raw_item_keys={list(item.keys())}")
            continue
        valid[raw_index] = item
    if errors:
        log(f"[planner] _absorb summary: {len(valid)} valid, {len(errors)} errors, missing={[i for i in range(start_idx, end_idx+1) if i not in valid]}")
    return valid, errors


def _build_repair_payload(
    missing: list[int],
    script_lines_by_index: dict[int, tuple[str, str]],
    row_by_index: dict[int, RoadmapRow],
    errors_by_index: dict[int, str],
) -> str:
    lines: list[str] = [
        f"You missed these specific indices: {missing}. Output ONLY a raw JSON array containing "
        "objects for these missing indices; no prose, no fences, no repeated objects."
    ]
    for index in missing:
        timestamp, sentence = script_lines_by_index.get(index, ("", ""))
        lines.append(f"Index {index} [{timestamp}] {sentence}")
        row = row_by_index.get(index)
        if row is not None:
            lines.append(
                f"Roadmap: {row.sequence_type}/{row.layout_classification}/"
                f"{row.camera_specification} - {_condense(row.visual_concept)}"
            )
        error_excerpt = errors_by_index.get(index)
        if error_excerpt:
            lines.append(f"Rejected because: {error_excerpt}")
    return "\n".join(lines)


def _build_chunks(total: int, chunk_size: int) -> list[tuple[str, int, int]]:
    chunks: list[tuple[str, int, int]] = []
    for offset in range(0, total, chunk_size):
        start_idx = offset + 1
        end_idx = min(offset + chunk_size, total)
        chunks.append((f"chunk_{offset // chunk_size + 1}", start_idx, end_idx))
    return chunks


def _chunk_is_complete(
    chunk_id: str,
    start_idx: int,
    end_idx: int,
    manifest: PipelineManifest,
    frames_by_index: dict[int, dict[str, Any]],
) -> bool:
    chunk = manifest.get_chunk(chunk_id)
    status = str(chunk.get("status", "")) if chunk else ""
    if status not in _DONE_STATUSES:
        return False
    return all(index in frames_by_index for index in range(start_idx, end_idx + 1))


def _plan_single_chunk(
    gemini_page: Any,
    manifest: PipelineManifest,
    folder: Path,
    chunk_id: str,
    preamble: str,
    sentences: list[str],
    timestamps: list[str],
    roadmap_rows: list[RoadmapRow],
    start_idx: int,
    end_idx: int,
    planner_model: str,
    max_repair_attempts: int,
) -> dict[int, dict[str, Any]]:
    slice_rows = extract_roadmap_slice(roadmap_rows, start_idx, end_idx)
    script_lines = [(i, timestamps[i - 1], sentences[i - 1]) for i in range(start_idx, end_idx + 1)]
    script_lines_by_index = {index: (ts, sentence) for index, ts, sentence in script_lines}
    row_by_index = {row.index: row for row in slice_rows}
    expected = list(range(start_idx, end_idx + 1))

    # Construct or load canonical spans for 3-span window context (Spec line 79)
    spans: list[dict[str, Any]] = []
    timeline_path = folder / "timeline.json"
    if timeline_path.exists():
        try:
            with open(timeline_path, encoding="utf-8") as f:
                t_data = json.load(f)
                spans = t_data.get("spans", [])
        except Exception:
            spans = []
    if not spans:
        for idx in range(1, len(sentences) + 1):
            ts = timestamps[idx - 1] if idx <= len(timestamps) else "[00:00]"
            sent = sentences[idx - 1] if idx <= len(sentences) else ""
            spans.append({
                "index": idx,
                "timestamp": ts,
                "text": sent,
                "pause_before": 0.0,
                "pause_after": 0.0,
            })

    continuity_tracker = SubjectContinuityTracker()
    payload = build_chunk_payload(preamble, slice_rows, script_lines, spans=spans)
    attempts = 0

    jitter_delay()
    # Session persistence: reuse chat within threshold (every 100 lines by default)
    if not ensure_persistent_gemini_session(gemini_page, start_idx, planner_model):
        raise RuntimeError(f"[planner] failed to ensure persistent session for {chunk_id}.")
    if not inject_prompt_via_cdp(gemini_page, payload):
        log(f"[planner] {chunk_id} injection failed; retrying once in same session.")
        jitter_delay()
        if not inject_prompt_via_cdp(gemini_page, payload):
            dump_path = _dump_debug(
                folder,
                f"malformed_{chunk_id}_payload.json",
                {"chunk_id": chunk_id, "error": "prompt_injection_failed", "payload": payload},
            )
            raise ChunkPlanningError(
                f"[planner] prompt injection failed twice for {chunk_id} (same session).",
                chunk_id,
                [],
                dump_path,
            )
    attempts += 1
    response = wait_for_gemini_turn_completion(gemini_page)
    if not response:
        log(f"[planner] {chunk_id} empty turn; resending once in same session (no new chat).")
        jitter_delay()
        if not inject_prompt_via_cdp(gemini_page, payload):
            dump_path = _dump_debug(
                folder,
                f"malformed_{chunk_id}_payload.json",
                {"chunk_id": chunk_id, "error": "prompt_injection_failed", "payload": payload},
            )
            raise ChunkPlanningError(
                f"[planner] redelivery injection failed for {chunk_id} (same session).", chunk_id, [], dump_path
            )
        attempts += 1
        response = wait_for_gemini_turn_completion(gemini_page)

    # Build timestamp map for auto-repair and debug
    timestamp_map = {idx: ts for idx, ts, _ in script_lines}
    valid, errors = _absorb_valid_items(
        response, start_idx, end_idx, timestamp_map, continuity_tracker=continuity_tracker
    )
    missing = [index for index in expected if index not in valid]
    if missing:
        log(f"[planner] initial missing after absorb: {missing} | errors={errors} | raw_len={len(response)}")
    repairs_used = 0
    last_raw = response
    while missing and repairs_used < max_repair_attempts:
        repairs_used += 1
        attempts += 1
        log(f"[planner] {chunk_id} repair {repairs_used}/{max_repair_attempts}; missing={missing}.")
        repair_payload = _build_repair_payload(missing, script_lines_by_index, row_by_index, errors)
        if not inject_prompt_via_cdp(gemini_page, repair_payload):
            log(f"[planner] {chunk_id} repair injection failed; attempt consumed.")
            continue
        last_raw = wait_for_gemini_turn_completion(gemini_page)
        repaired, repair_errors = _absorb_valid_items(
            last_raw, start_idx, end_idx, timestamp_map, continuity_tracker=continuity_tracker
        )
        if repair_errors:
            log(f"[planner] repair {repairs_used} errors: {repair_errors}")
        errors.update(repair_errors)
        valid.update(repaired)
        missing = [index for index in expected if index not in valid]
        if missing:
            log(f"[planner] after repair {repairs_used} still missing: {missing}")


    if missing:
        dump_path = _dump_debug(
            folder,
            f"malformed_{chunk_id}.json",
            {
                "chunk_id": chunk_id,
                "missing_indices": missing,
                "raw_response": last_raw,
                "validation_errors": {str(key): value for key, value in errors.items()},
            },
        )
        manifest.set_chunk_status(chunk_id, expected, ChunkStatus.FAILED, attempts)
        raise ChunkPlanningError(
            f"[planner] {chunk_id} exhausted {max_repair_attempts} repairs; missing={missing}.",
            chunk_id,
            missing,
            dump_path,
        )

    status = ChunkStatus.REPAIRED if repairs_used > 0 else ChunkStatus.VERIFIED
    manifest.set_chunk_status(chunk_id, expected, status, attempts)
    return valid


def plan_all_chunks(
    gemini_page: Any,
    sentences: list[str],
    timestamps: list[str],
    roadmap_rows: list[RoadmapRow],
    folder: str | Path,
    manifest: PipelineManifest,
    chunk_size: int = 15,
    planner_model: str = "Flash-Lite",
    max_repair_attempts: int = 2,
    presets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Plan every pending chunk and return the complete sorted flow_prompts frame list."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    folder_path = Path(folder)
    prompts_path = folder_path / FLOW_PROMPTS_FILENAME
    total = len(sentences)

    chunks = _build_chunks(total, chunk_size)
    if manifest.get_chunk("chunk_1") is None:
        manifest.init_planning(chunk_size, len(chunks))

    frames_by_index = _load_baseline_frames(prompts_path)
    preamble = build_compact_preamble(presets)

    for chunk_id, start_idx, end_idx in chunks:
        if _chunk_is_complete(chunk_id, start_idx, end_idx, manifest, frames_by_index):
            log(f"[planner] skipping {chunk_id} ({start_idx}-{end_idx}); already verified.")
            continue
        log(f"[planner] planning {chunk_id} (Indices {start_idx}-{end_idx}).")
        planned = _plan_single_chunk(
            gemini_page,
            manifest,
            folder_path,
            chunk_id,
            preamble,
            sentences,
            timestamps,
            roadmap_rows,
            start_idx,
            end_idx,
            planner_model,
            max_repair_attempts,
        )
        frames_by_index.update(planned)
        _persist_frames(prompts_path, frames_by_index)
        log(f"[planner] {chunk_id} committed through Index {end_idx}.")

    missing_final = [index for index in range(1, total + 1) if index not in frames_by_index]
    if missing_final:
        raise ChunkPlanningError(
            f"[planner] final coverage check failed; missing={missing_final}.",
            "",
            missing_final,
            "",
        )
    log(f"[planner] {FLOW_PROMPTS_FILENAME} complete ({total} frames) in {folder_path}.")
    return [frames_by_index[index] for index in range(1, total + 1)]
