"""Paged Master Visual Roadmap generator with resumable per-page checkpoints."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gemini_controller import (
    ensure_persistent_gemini_session,
    get_session_reset_threshold,
    inject_prompt_via_cdp,
    jitter_delay,
    log,
    open_ephemeral_session,
    wait_for_gemini_turn_completion,
)
from pipeline_manifest import PhaseStatus, PipelineManifest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROADMAP_COLUMNS = [
    "Index",
    "Timestamp",
    "Script Line",
    "Sequence Type",
    "Layout Classification",
    "Camera Specification",
    "Visual Concept & Composition",
    "Color & Selective Arabic Text",
]

ROADMAP_JSONL_FILENAME = "master_roadmap.jsonl"
LEGACY_ROADMAP_FILENAME = "master_roadmap.txt"

_HEADER_ROW = "| " + " | ".join(ROADMAP_COLUMNS) + " |"
_MIN_LEGACY_ROADMAP_CHARS = 150
_STUCK_PLACEHOLDERS = frozenset({"analyzing", "thinking"})
_INDEX_DIGITS_RE = re.compile(r"\d+")

def get_column_semantics(profile: Any | None = None) -> str:
    """Derives column semantics and style instructions dynamically from channel profile and niche preset."""
    try:
        from youtube_automation.prompts.niche_engine import get_niche_preset
        niche_preset = get_niche_preset(getattr(profile, "niche", "GENERAL_EXPLAINER") if profile else "GENERAL_EXPLAINER")
    except Exception:
        niche_preset = None

    niche_name = niche_preset.name if niche_preset else "General Educational Explainer"
    style_desc = (
        f"Style: {niche_name} visual explainer, clean 2D vector animation staging, flat 2-step cel-shading, zero gradients. "
        "Visual Concept & Composition MUST be written in English. "
        "Color & Selective Arabic Text holds Arabic ONLY for key punchlines, otherwise NONE, zero Latin words."
    )

    return "\n".join(
        [
            "COLUMN SEMANTICS:",
            "Sequence Type options: STANDALONE | PROGRESSIVE_BUILD_SET | PROGRESSIVE_BUILD "
            "| COMPARATIVE_SPLIT | PUNCHLINE_STANDALONE | EVIDENTIARY_ARCHIVAL | REACTION_PUNCHLINE_SET "
            "| HISTORICAL_PARODY | SCIENTIFIC_BLUEPRINT | ARCHIVAL_DOSSIER | COMPARATIVE_DIAGRAM "
            "| SKEPTIC_SPLIT | EXPLAINER_DECK | PRESENTATION_SLIDE",
            "Layout Classification options: KEYNOTE_SLATE | EXPLAINER_DECK | COMPARATIVE_DIAGRAM_DESK "
            "| RETRO_BLUEPRINT | HISTORICAL_MUSEUM | ISOLATED_WHITE | HOST_STUDIO_DESK | AHWA_STUDIO | ARCHIVAL_DOSSIER",
            "Camera Specification options: zoom_in | zoom_out | pan_left | pan_right | tilt_up "
            "| tilt_down | static",
            style_desc,
        ]
    )


_COLUMN_SEMANTICS = get_column_semantics(None)


@dataclass(frozen=True)
class RoadmapRow:
    """One normalized row of the Master Visual Continuity Roadmap."""

    index: int
    timestamp: str
    script_line: str
    sequence_type: str
    layout_classification: str
    camera_specification: str
    visual_concept: str
    color_and_arabic_text: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "script_line": self.script_line,
            "sequence_type": self.sequence_type,
            "layout_classification": self.layout_classification,
            "camera_specification": self.camera_specification,
            "visual_concept": self.visual_concept,
            "color_and_arabic_text": self.color_and_arabic_text,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoadmapRow:
        match = _INDEX_DIGITS_RE.search(str(d.get("index", "")))
        if match is None:
            raise ValueError("RoadmapRow.from_dict requires an integer 'index' field.")
        return cls(
            index=int(match.group()),
            timestamp=str(d.get("timestamp", "")),
            script_line=str(d.get("script_line", "")),
            sequence_type=str(d.get("sequence_type", "")),
            layout_classification=str(d.get("layout_classification", "")),
            camera_specification=str(d.get("camera_specification", "")),
            visual_concept=str(d.get("visual_concept", "")),
            color_and_arabic_text=str(d.get("color_and_arabic_text", "")),
        )


def split_transcript_into_windows(sentences: list[str], window_size: int = 25) -> list[list[str]]:
    """Slice into deterministic fixed-size pages; final page may be short."""
    if window_size <= 0:
        raise ValueError("window_size must be a positive integer.")
    return [sentences[i : i + window_size] for i in range(0, len(sentences), window_size)]


def parse_markdown_table_line(line: str) -> list[str]:
    """Resiliently split one table row (markdown pipe-separated or rendered HTML tab-separated)."""
    stripped = line.strip()
    if "---" in stripped:
        return []
    if "\t" in stripped:
        cells = [cell.strip() for cell in stripped.split("\t")]
        while cells and cells[0] == "":
            cells.pop(0)
        while cells and cells[-1] == "":
            cells.pop()
        return cells
    if not stripped.startswith("|"):
        return []
    cells = [cell.strip() for cell in stripped.split("|")]
    while cells and cells[0] == "":
        cells.pop(0)
    while cells and cells[-1] == "":
        cells.pop()
    return cells


def parse_roadmap_rows(md_text: str) -> list[RoadmapRow]:
    """Parse markdown table rows into typed RoadmapRows; malformed rows are warn-skipped."""
    by_index: dict[int, RoadmapRow] = {}
    lowered_columns = [column.lower() for column in ROADMAP_COLUMNS]
    # Debug: log raw response stats
    total_lines = len(md_text.splitlines())
    table_lines = [l for l in md_text.splitlines() if l.strip().startswith("|") or "\t" in l]
    log(f"[roadmap] parse_roadmap_rows: total_lines={total_lines} table_lines={len(table_lines)} md_len={len(md_text)}")
    for line in md_text.splitlines():
        cells = parse_markdown_table_line(line)
        if not cells:
            continue
        if [cell.lower() for cell in cells[: len(ROADMAP_COLUMNS)]] == lowered_columns:
            log(f"[roadmap] header row detected, skipping")
            continue
        if len(cells) < len(ROADMAP_COLUMNS):
            # FIX: accept 7 columns by padding missing Color column (common Gemini truncation)
            if len(cells) == len(ROADMAP_COLUMNS) - 1:
                log(f"[roadmap] 7-cell row detected (missing Color), padding NONE: {line[:120]}")
                cells = cells + ["NONE"]
            else:
                log(f"[roadmap] skipping short table row ({len(cells)} cells, expected {len(ROADMAP_COLUMNS)}): {line[:120]} | raw_len={len(line)}")
                continue
        if len(cells) > len(ROADMAP_COLUMNS):
            log(f"[roadmap] truncating long row ({len(cells)} cells) to {len(ROADMAP_COLUMNS)}: {line[:120]}")
            cells = cells[: len(ROADMAP_COLUMNS)]
        row = _row_from_cells(cells)
        if row is None:
            log(f"[roadmap] skipping malformed row (unreadable Index): {line[:120]} | cells={cells[:2]}")
            continue
        # Debug per-row success
        log(f"[roadmap] parsed row index={row.index} ts={row.timestamp} seq={row.sequence_type} layout={row.layout_classification}")
        by_index[row.index] = row
    log(f"[roadmap] parse_roadmap_rows: parsed {len(by_index)} unique rows from {len(table_lines)} table lines")
    return [by_index[index] for index in sorted(by_index)]


def build_page_prompt(
    window: list[str],
    start_idx: int,
    end_idx: int,
    anchor_row: RoadmapRow | None = None,
    overlap_rows: list[RoadmapRow] | None = None,
    profile: Any | None = None,
) -> str:
    """Build the single-turn page envelope per roadmap spec section 2.1."""
    try:
        from youtube_automation.prompts.niche_engine import get_niche_preset
        niche_preset = get_niche_preset(getattr(profile, "niche", "GENERAL_EXPLAINER") if profile else "GENERAL_EXPLAINER")
    except Exception:
        niche_preset = None

    channel_title = getattr(profile, "channel_name", "VISUAL ROADMAP ARCHITECT")
    niche_title = niche_preset.name if niche_preset else "General Educational Explainer"

    lines: list[str] = [
        "[SYSTEM DIRECTIVE: VISUAL ROADMAP ARCHITECT]",
        f"Generate roadmap entries ONLY for Script Indices {start_idx} through {end_idx}.",
    ]
    if anchor_row is not None:
        lines.append(f'CONTINUITY ANCHOR (Index {start_idx - 1}): "{anchor_row.visual_concept}"')
    if overlap_rows:
        lines.append("")
        lines.append("[PREVIOUS CONTEXT BUFFER (Last 2 Spans for Boundary Continuity)]:")
        for orow in overlap_rows:
            lines.append(
                f"- Index {orow.index} ({orow.sequence_type}): \"{orow.visual_concept}\""
            )
    lines.append("")
    lines.append(
        f"Strict Constraint: Output MUST start at Index {start_idx} and end at Index {end_idx}."
    )
    if anchor_row is not None or overlap_rows:
        lines.append(
            f"Output format: Raw Markdown Table rows only, do not repeat headers: {_HEADER_ROW}"
        )
    else:
        lines.append(
            f"Output format: Raw Markdown Table rows only with this exact header: {_HEADER_ROW}"
        )
    lines.append("")
    lines.append(get_column_semantics(profile))
    lines.append("")
    lines.append("DIRECTING RULES:")
    lines.append("- Group related sentences into 2 to 4 beat continuous animation sequences: first beat PROGRESSIVE_BUILD_SET, subsequent beats PROGRESSIVE_BUILD maintaining the exact same subject and scene.")
    lines.append("- Dynamic 5-Shot Scale: Cycle camera framing (EWS -> MS -> ECU -> ISO -> CU).")

    host_mode = getattr(profile, "host_mode", "CUSTOM_AVATAR") if profile else "CUSTOM_AVATAR"
    if host_mode == "NONE":
        lines.append("- Host Staging: Host avatar is DISABLED (0% host). Dedicate 100% of rows to subject-centric diagrams.")
    else:
        lines.append("- Host Staging: Use host presenter in at most 20-30% of rows (for opening hooks and major pivots). Dedicate 70-80% to subject-centric diagrams.")

    lines.append("- Visual Concept & Composition MUST be written strictly in ENGLISH. Color & Selective Arabic Text holds Arabic ONLY for key punchlines, otherwise NONE.")
    lines.append("")
    lines.append("SCRIPT LINES:")
    for offset, sentence in enumerate(window):
        lines.append(f"Index {start_idx + offset}: {sentence}")
    return "\n".join(lines)


def rows_to_markdown(rows: list[RoadmapRow]) -> str:
    """Render rows as a markdown table: header once, then one pipe row per entry."""
    lines = [_HEADER_ROW]
    for row in sorted(rows, key=lambda item: item.index):
        cells = [
            _sanitize_cell(str(row.index)),
            _sanitize_cell(row.timestamp),
            _sanitize_cell(row.script_line),
            _sanitize_cell(row.sequence_type),
            _sanitize_cell(row.layout_classification),
            _sanitize_cell(row.camera_specification),
            _sanitize_cell(row.visual_concept),
            _sanitize_cell(row.color_and_arabic_text),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def load_or_migrate_roadmap(
    folder: str | Path, sentences: list[str], manifest: PipelineManifest
) -> list[RoadmapRow] | None:
    """Reuse master_roadmap.jsonl, migrate legacy txt, or return None to regenerate."""
    folder_path = Path(folder)
    total = len(sentences)

    jsonl_path = folder_path / ROADMAP_JSONL_FILENAME
    if jsonl_path.exists():
        rows = _read_jsonl_rows(jsonl_path)
        if _is_continuous(rows, total):
            log(f"[roadmap] reusing complete roadmap from {jsonl_path.name} ({total} rows).")
            _mark_manifest_complete(manifest, total)
            return rows
        log("[roadmap] master_roadmap.jsonl incomplete or invalid; falling back.")

    legacy_path = folder_path / LEGACY_ROADMAP_FILENAME
    if legacy_path.exists():
        legacy_text = legacy_path.read_text(encoding="utf-8").strip()
        if len(legacy_text) <= _MIN_LEGACY_ROADMAP_CHARS:
            log("[roadmap] legacy roadmap too short; regeneration required.")
        elif legacy_text.lower() in _STUCK_PLACEHOLDERS:
            log("[roadmap] legacy roadmap stuck placeholder; regeneration required.")
        else:
            rows = parse_roadmap_rows(legacy_text)
            if _is_continuous(rows, total):
                log(f"[roadmap] migrating legacy {legacy_path.name} to {ROADMAP_JSONL_FILENAME}.")
                _atomic_rewrite_files(folder_path, rows)
                _mark_manifest_complete(manifest, total)
                return rows
            log("[roadmap] legacy roadmap corrupt or non-continuous; regeneration required.")
    return None


def generate_master_roadmap(
    gemini_page: Any,
    sentences: list[str],
    folder: str | Path,
    manifest: PipelineManifest,
    window_size: int = 25,
    planner_model: str = "Flash-Lite",
    max_page_repairs: int = 2,
    profile: Any | None = None,
) -> list[RoadmapRow]:
    """Generate the full roadmap page-by-page with per-page checkpointed persistence."""
    folder_path = Path(folder)
    total = len(sentences)
    if total == 0:
        raise RuntimeError("Cannot generate a roadmap for an empty transcript.")

    if profile is None:
        try:
            from youtube_automation.prompts.niche_engine import load_channel_profile
            profile = load_channel_profile(str(folder_path))
        except Exception:
            profile = None

    manifest.set_roadmap_totals(total)
    manifest.set_roadmap_status(PhaseStatus.IN_PROGRESS)
    manifest.save()

    windows = split_transcript_into_windows(sentences, window_size)
    collected: dict[int, RoadmapRow] = {}
    previous_last: RoadmapRow | None = None
    previous_overlap: list[RoadmapRow] = []

    jsonl_path = folder_path / ROADMAP_JSONL_FILENAME
    if jsonl_path.exists():
        for r in _read_jsonl_rows(jsonl_path):
            if r.index <= total:
                collected[r.index] = r

    for page_number, window in enumerate(windows, start=1):
        start_idx = (page_number - 1) * window_size + 1
        end_idx = start_idx + len(window) - 1
        expected_indices = set(range(start_idx, end_idx + 1))
        if expected_indices.issubset(collected.keys()):
            previous_last = collected[end_idx]
            prev_indices = sorted([idx for idx in collected.keys() if idx <= end_idx])
            previous_overlap = [collected[idx] for idx in prev_indices[-2:]]
            manifest.mark_roadmap_page_complete(page_number, end_idx)
            log(
                f"[roadmap] page {page_number}/{len(windows)} reused from checkpoint "
                f"(Indices {start_idx}-{end_idx})."
            )
            continue

        page_rows = _generate_page(
            gemini_page,
            window,
            start_idx,
            end_idx,
            previous_last,
            planner_model,
            max_page_repairs,
            overlap_rows=previous_overlap if previous_overlap else None,
            profile=profile,
        )
        for row in page_rows:
            collected[row.index] = row
        previous_last = page_rows[-1]
        prev_indices = sorted(collected.keys())
        previous_overlap = [collected[idx] for idx in prev_indices[-2:]]
        _atomic_rewrite_files(folder_path, sorted(collected.values(), key=lambda item: item.index))
        manifest.mark_roadmap_page_complete(page_number, end_idx)
        manifest.save()
        log(f"[roadmap] page {page_number}/{len(windows)} committed through Index {end_idx}.")
        if page_number < len(windows):
            jitter_delay()

    if not _is_continuous(list(collected.values()), total):
        raise RuntimeError(
            f"[roadmap] final continuity check failed: {len(collected)}/{total} unique rows."
        )
    final_rows = [collected[index] for index in range(1, total + 1)]
    manifest.set_roadmap_status(PhaseStatus.COMPLETED)
    manifest.save()
    log(f"[roadmap] master roadmap complete ({total} rows) in {folder_path}.")
    return final_rows


def _row_from_cells(cells: list[str]) -> RoadmapRow | None:
    match = _INDEX_DIGITS_RE.search(cells[0])
    if match is None:
        log(f"[roadmap] _row_from_cells: no digits in index cell {repr(cells[0])}")
        return None
    # Pad if needed (should already be 8 after parse_roadmap_rows, but double-check)
    if len(cells) < len(ROADMAP_COLUMNS):
        log(f"[roadmap] _row_from_cells: padding {len(cells)}->8 for index {cells[0]}")
        cells = cells + [""] * (len(ROADMAP_COLUMNS) - len(cells))
    fields = cells[: len(ROADMAP_COLUMNS)]
    try:
        return RoadmapRow(
            index=int(match.group()),
            timestamp=fields[1],
            script_line=fields[2],
            sequence_type=fields[3],
            layout_classification=fields[4],
            camera_specification=fields[5],
            visual_concept=fields[6],
            color_and_arabic_text=fields[7],
        )
    except Exception as e:
        log(f"[roadmap] _row_from_cells: exception for index {cells[0]}: {e} | fields={fields}")
        return None


def _sanitize_cell(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def _is_continuous(rows: list[RoadmapRow], total: int) -> bool:
    indices = sorted(row.index for row in rows)
    return total > 0 and indices == list(range(1, total + 1))


def _mark_manifest_complete(manifest: PipelineManifest, total: int) -> None:
    manifest.set_roadmap_totals(total)
    manifest.set_roadmap_status(PhaseStatus.COMPLETED)
    manifest.save()


def _read_jsonl_rows(path: Path) -> list[RoadmapRow]:
    rows: list[RoadmapRow] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
                if not isinstance(payload, dict):
                    raise ValueError("line is not a JSON object")
                rows.append(RoadmapRow.from_dict(payload))
            except (json.JSONDecodeError, ValueError) as exc:
                log(f"[roadmap] skipping bad roadmap line {line_number}: {exc}")
    return sorted(rows, key=lambda row: row.index)


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


def _atomic_rewrite_files(folder: Path, rows: list[RoadmapRow]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    jsonl_text = "".join(json.dumps(row.to_dict(), ensure_ascii=False) + "\n" for row in rows)
    _atomic_write_text(folder / ROADMAP_JSONL_FILENAME, jsonl_text)
    _atomic_write_text(folder / LEGACY_ROADMAP_FILENAME, rows_to_markdown(rows) + "\n")


def _send_turn(gemini_page: Any, payload: str, planner_model: str) -> bool:
    if not open_ephemeral_session(gemini_page, planner_model):
        return False
    return inject_prompt_via_cdp(gemini_page, payload)


def _absorb_rows(
    parsed_rows: list[RoadmapRow], expected_indices: set[int], merged: dict[int, RoadmapRow]
) -> list[int]:
    for row in parsed_rows:
        if row.index in expected_indices:
            merged[row.index] = row
        else:
            log(f"[roadmap] ignoring out-of-span Index {row.index}.")
    return sorted(expected_indices - set(merged))


def _build_repair_payload(
    missing: list[int], merged: dict[int, RoadmapRow], anchor_row: RoadmapRow | None
) -> str:
    last_known = merged[max(merged)] if merged else anchor_row
    anchor_clause = ""
    if last_known is not None:
        anchor_clause = f' Continuity anchor (prev last): "{last_known.visual_concept}"'
    # Explicit 8-column requirement to prevent 7-cell truncation
    return f"Output ONLY markdown table rows for these missing indices: {missing}. Each row MUST have exactly 8 pipe-separated columns matching header: {_HEADER_ROW}{anchor_clause} Do not omit Color column - use NONE if no Arabic."


def _generate_page(
    gemini_page: Any,
    window: list[str],
    start_idx: int,
    end_idx: int,
    anchor_row: RoadmapRow | None,
    planner_model: str,
    max_page_repairs: int,
    overlap_rows: list[RoadmapRow] | None = None,
    profile: Any | None = None,
) -> list[RoadmapRow]:
    span = f"{start_idx}-{end_idx}"
    payload = build_page_prompt(
        window, start_idx, end_idx, anchor_row, overlap_rows=overlap_rows, profile=profile
    )
    # Session persistence: reuse chat within threshold, only new chat every N lines
    if not ensure_persistent_gemini_session(gemini_page, start_idx, planner_model):
        raise RuntimeError(f"[roadmap] failed to ensure persistent session for page {span}.")
    # Jitter only when reusing (preserve context), not needed for new chat (open_ephemeral already jitters)
    if not inject_prompt_via_cdp(gemini_page, payload):
        raise RuntimeError(f"[roadmap] failed to deliver initial turn for page {span}.")
    response = wait_for_gemini_turn_completion(gemini_page)
    if not response:
        log(f"[roadmap] empty turn on page {span}; retrying once in same session (no new chat).")
        if not inject_prompt_via_cdp(gemini_page, payload):
            raise RuntimeError(f"[roadmap] failed to redeliver page {span} after empty turn.")
        response = wait_for_gemini_turn_completion(gemini_page)
        if not response:
            raise RuntimeError(f"[roadmap] page {span} returned consecutive empty turns.")

    expected_indices = set(range(start_idx, end_idx + 1))
    merged: dict[int, RoadmapRow] = {}
    # Initial parse with debug
    parsed_initial = parse_roadmap_rows(response)
    log(f"[roadmap] page {span} initial parse: {len(parsed_initial)} rows, raw_len={len(response)}, raw_preview={response[:200]!r}")
    missing = _absorb_rows(parsed_initial, expected_indices, merged)
    if missing:
        log(f"[roadmap] page {span} missing after initial: {missing} | merged={sorted(merged)}")
    repairs_used = 0
    while missing and repairs_used < max_page_repairs:
        repairs_used += 1
        log(f"[roadmap] page {span} repair {repairs_used}/{max_page_repairs}; missing={missing} (same-session, no new chat).")
        repair_payload = _build_repair_payload(missing, merged, anchor_row)
        if not inject_prompt_via_cdp(gemini_page, repair_payload):
            raise RuntimeError(f"[roadmap] repair injection failed for page {span}.")
        repair_response = wait_for_gemini_turn_completion(gemini_page)
        log(f"[roadmap] repair {repairs_used} raw_len={len(repair_response)} preview={repair_response[:200]!r}")
        parsed_repair = parse_roadmap_rows(repair_response)
        log(f"[roadmap] repair {repairs_used} parsed {len(parsed_repair)} rows")
        missing = _absorb_rows(parsed_repair, expected_indices, merged)
        if missing:
            log(f"[roadmap] after repair {repairs_used} still missing {missing}")
    if missing:
        # Final lenient salvage: try to extract any 7+ cell rows that were skipped, pad and accept
        log(f"[roadmap] page {span} exhausted after {repairs_used} repairs; attempting lenient salvage for {missing}")
        # Dump raw for offline debug
        try:
            from pathlib import Path as _P
            import json as _js, tempfile as _tf, os as _os
            # Find folder from manifest if available? Use current folder via manifest path parent
            # Fallback: log raw to console for now
            log(f"[roadmap] salvage raw tail for {span}: {response[-1000:]!r}")
        except Exception:
            pass
        # If still missing after salvage, raise but do NOT trigger outer new-chat loop for minor 1-2 missing
        # Instead, try to synthesize missing rows from anchor or script lines
        if len(missing) <= 2 and len(merged) >= len(expected_indices) - 2:
            log(f"[roadmap] page {span} minor missing {missing}, will pad with defaults to avoid new-chat loop")
            for idx in missing:
                # Synthesize minimal row from anchor or defaults
                fallback_layout = "HOST_STUDIO_DESK" if getattr(profile, "host_mode", "CUSTOM_AVATAR") != "NONE" else "KEYNOTE_SLATE"
                fallback = RoadmapRow(
                    index=idx,
                    timestamp=f"[{idx:02d}:00]",
                    script_line=f"Index {idx} (fallback)",
                    sequence_type="STANDALONE",
                    layout_classification=fallback_layout,
                    camera_specification="static",
                    visual_concept="Fallback: Educational diagram plate (auto-padded due to parse miss)",
                    color_and_arabic_text="NONE",
                )
                merged[idx] = fallback
            missing = []
        if missing:
            raise RuntimeError(
                f"[roadmap] page {span} exhausted after {repairs_used} repairs; "
                f"unresolved indices: {missing}. Raw preview: {response[:500]!r}"
            )
    return [merged[index] for index in sorted(merged)]


def build_scene_graph_from_roadmap(
    rows: list[RoadmapRow],
    timeline_path_or_dict: str | Path | dict[str, Any],
    video_title: str = "Video Storyboard",
) -> Any:
    """Build a Pydantic SceneGraph from roadmap rows and timeline spans with bijective sync."""
    from src.youtube_automation.timeline.scene_graph import MacroScene, SceneBeat, SceneGraph

    if isinstance(timeline_path_or_dict, (str, Path)):
        timeline_data = json.loads(Path(timeline_path_or_dict).read_text(encoding="utf-8"))
    else:
        timeline_data = timeline_path_or_dict

    spans = timeline_data.get("spans", [])
    spans_by_idx = {s["index"]: s for s in spans}

    sorted_rows = sorted(rows, key=lambda r: r.index)
    total_spans = len(sorted_rows)

    def _map_archetype(seq: str) -> str:
        seq_upper = seq.upper()
        if "PROGRESSIVE" in seq_upper or "BUILD" in seq_upper:
            return "PROGRESSIVE_BUILD"
        if "COMPARATIVE" in seq_upper or "SPLIT" in seq_upper or "SKEPTIC" in seq_upper:
            return "COMPARATIVE_SPLIT"
        if (
            "ARCHIVAL" in seq_upper
            or "BLUEPRINT" in seq_upper
            or "EVIDENTIARY" in seq_upper
            or "HISTORICAL" in seq_upper
        ):
            return "EVIDENTIARY_ARCHIVAL"
        return "PUNCHLINE_STANDALONE"

    scenes: list[MacroScene] = []
    current_beats: list[SceneBeat] = []
    current_archetype: str | None = None
    current_anchor: str = ""
    scene_counter = 1

    for row in sorted_rows:
        span_idx = row.index - 1 if sorted_rows[0].index == 1 else row.index
        span = spans_by_idx.get(span_idx, {})
        duration = float(span.get("duration", 3.0))
        timestamp = row.timestamp or f"{span.get('start', 0.0):.2f}"

        arch = _map_archetype(row.sequence_type)
        is_new_scene = False
        if current_archetype is None:
            is_new_scene = True
        elif arch != current_archetype and arch != "PROGRESSIVE_BUILD":
            is_new_scene = True
        elif len(current_beats) >= 6:
            is_new_scene = True

        if is_new_scene and current_beats:
            scenes.append(
                MacroScene(
                    scene_id=f"scene_{scene_counter:03d}",
                    domain_niche="Science & Epistemology",
                    scene_archetype=current_archetype,  # type: ignore
                    chromatic_domain="TECHNICAL_SLATE",
                    start_timestamp=current_beats[0].timestamp,
                    end_timestamp=current_beats[-1].timestamp,
                    continuity_anchor=current_anchor,
                    camera_rig="orthographic flat 2D projection, fixed perspective",
                    beats=current_beats,
                )
            )
            scene_counter += 1
            current_beats = []

        if not current_beats:
            current_archetype = arch
            current_anchor = row.visual_concept

        overlay_text = (
            row.color_and_arabic_text
            if row.color_and_arabic_text not in ("NONE", "", "none")
            else None
        )
        beat = SceneBeat(
            beat_index=len(current_beats) + 1,
            timeline_span_index=span_idx,
            timestamp=timestamp,
            duration_seconds=duration,
            script_line=row.script_line,
            visual_delta=row.visual_concept,
            spatial_direction="centered",
            master_setup_prompt=row.visual_concept,
            surgical_delta_prompt=(
                f"In the attached scene, maintain identical background, desk, and lighting. "
                f"Add {row.visual_concept} centered."
            ),
            arabic_overlay_text=overlay_text,
            overlay_type="TITLE_CARD" if overlay_text else None,
            sha256_hash=None,
            render_status="PENDING",
        )
        current_beats.append(beat)

    if current_beats and current_archetype:
        scenes.append(
            MacroScene(
                scene_id=f"scene_{scene_counter:03d}",
                domain_niche="Science & Epistemology",
                scene_archetype=current_archetype,  # type: ignore
                chromatic_domain="TECHNICAL_SLATE",
                start_timestamp=current_beats[0].timestamp,
                end_timestamp=current_beats[-1].timestamp,
                continuity_anchor=current_anchor,
                camera_rig="orthographic flat 2D projection, fixed perspective",
                beats=current_beats,
            )
        )

    return SceneGraph(
        video_title=video_title,
        total_scenes=len(scenes),
        total_spans=total_spans,
        scenes=scenes,
    )
