"""Stateless Phase-2 planning engine: converts script lines into Flow keyframe JSON.

Consumes the Master Visual Continuity Roadmap produced by ``roadmap_orchestrator``
and drives Gemini through per-chunk, single-turn conversations that emit
``flow_prompts.json`` payloads validated against :class:`validator.FrameItem`.
Every chunk is checkpointed in the shared ``PipelineManifest`` so reruns skip
completed work, self-heal gaps in the same session, and merge cleanly with any
surviving baseline file.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, TypeGuard

from pydantic import ValidationError

from gemini_controller import (
    inject_prompt_via_cdp,
    jitter_delay,
    log,
    open_ephemeral_session,
    wait_for_gemini_turn_completion,
)
from json_sanitizer import clean_and_repair_json
from pipeline_manifest import ChunkStatus, PipelineManifest
from roadmap_orchestrator import RoadmapRow
from validator import FrameItem

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
    '"visual_prompt": {"subject_details": "<verbatim character token>", '
    '"subject_action_increment": "<micro-action>", '
    '"environment_coordinates": "<verbatim layout token>", '
    '"composition_layout": "<framing geometry>", "camera_specifications": <enum>, '
    '"text_overlay_arabic": "<Arabic OR NONE>", "accent_color_hook": "<palette color>", '
    '"style_anchor": "<STYLE_DNA verbatim>"}}]'
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
            "TYPOGRAPHY: text_overlay_arabic = bold modern Arabic Kufic calligraphy "
            '(1-3 words) OR exactly "NONE"; Latin letters prohibited',
            "OUTPUT: ONE raw JSON array covering EXACTLY the requested Index span; no prose, "
            "no fences, no repeated objects",
        ]
    )
    return "\n".join(lines)


def build_chunk_payload(
    preamble: str,
    slice_rows: list[RoadmapRow],
    script_lines: list[tuple[int, str, str]],
) -> str:
    """Single-turn prompt: preamble + buffered roadmap table + script lines + span directive."""
    lines: list[str] = [preamble, "", "CRITICAL: timestamp field must be copied VERBATIM from SCRIPT LINES including brackets, e.g. [00:00] - never leave empty", "", "ROADMAP CONTEXT (target span +/- buffer):"]
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
        lines.append(f"Index {global_index} [{timestamp}] {_condense(sentence)}")
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
    raw_response: str, start_idx: int, end_idx: int,
    timestamp_map: dict[int, str] | None = None,
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

    payload = build_chunk_payload(preamble, slice_rows, script_lines)
    attempts = 0

    jitter_delay()
    if not open_ephemeral_session(gemini_page, planner_model):
        raise RuntimeError(f"[planner] failed to open ephemeral session for {chunk_id}.")
    if not inject_prompt_via_cdp(gemini_page, payload):
        log(f"[planner] {chunk_id} injection failed; retrying once with a fresh session.")
        jitter_delay()
        if not open_ephemeral_session(gemini_page, planner_model):
            raise RuntimeError(f"[planner] session reopen failed for {chunk_id}.")
        if not inject_prompt_via_cdp(gemini_page, payload):
            dump_path = _dump_debug(
                folder,
                f"malformed_{chunk_id}_payload.json",
                {"chunk_id": chunk_id, "error": "prompt_injection_failed", "payload": payload},
            )
            raise ChunkPlanningError(
                f"[planner] prompt injection failed twice for {chunk_id}.",
                chunk_id,
                [],
                dump_path,
            )
    attempts += 1
    response = wait_for_gemini_turn_completion(gemini_page)
    if not response:
        log(f"[planner] {chunk_id} empty turn; resending once with a fresh session.")
        jitter_delay()
        if not open_ephemeral_session(gemini_page, planner_model):
            raise RuntimeError(f"[planner] session reopen failed for empty turn on {chunk_id}.")
        if not inject_prompt_via_cdp(gemini_page, payload):
            dump_path = _dump_debug(
                folder,
                f"malformed_{chunk_id}_payload.json",
                {"chunk_id": chunk_id, "error": "prompt_injection_failed", "payload": payload},
            )
            raise ChunkPlanningError(
                f"[planner] redelivery injection failed for {chunk_id}.", chunk_id, [], dump_path
            )
        attempts += 1
        response = wait_for_gemini_turn_completion(gemini_page)

    # Build timestamp map for auto-repair and debug
    timestamp_map = {idx: ts for idx, ts, _ in script_lines}
    valid, errors = _absorb_valid_items(response, start_idx, end_idx, timestamp_map)
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
        repaired, repair_errors = _absorb_valid_items(last_raw, start_idx, end_idx, timestamp_map)
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
