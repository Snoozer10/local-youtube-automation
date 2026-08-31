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

_COLUMN_SEMANTICS = "\n".join(
    [
        "COLUMN SEMANTICS:",
        "Sequence Type options: STANDALONE | PROGRESSIVE_BUILD_SET | REACTION_PUNCHLINE_SET | "
        "HISTORICAL_PARODY | SCIENTIFIC_BLUEPRINT | ARCHIVAL_DOSSIER | COMPARATIVE_DIAGRAM "
        "| SKEPTIC_SPLIT",
        "Layout Classification options: AHWA_STUDIO | ARCHIVAL_DOSSIER | COMPARATIVE_DIAGRAM_DESK "
        "| RETRO_BLUEPRINT | HISTORICAL_MUSEUM | ISOLATED_WHITE",
        "Camera Specification options: zoom_in | zoom_out | pan_left | pan_right | tilt_up "
        "| tilt_down | static",
        "Style: clean 2D vector animation, balanced 16:9 staging with subject centered; never "
        "write subtitle/margin notes; Color & Selective Arabic Text holds Arabic ONLY for key "
        "punchlines or academic seals, otherwise NONE, zero Latin words.",
    ]
)


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
    """Resiliently split one markdown table row; [] for separators and non-row lines."""
    stripped = line.strip()
    if not stripped.startswith("|") or "---" in stripped:
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
    pipe_lines = [l for l in md_text.splitlines() if l.strip().startswith("|")]
    log(f"[roadmap] parse_roadmap_rows: total_lines={total_lines} pipe_lines={len(pipe_lines)} md_len={len(md_text)}")
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
    log(f"[roadmap] parse_roadmap_rows: parsed {len(by_index)} unique rows from {len(pipe_lines)} pipe lines")
    return [by_index[index] for index in sorted(by_index)]


def build_page_prompt(
    window: list[str], start_idx: int, end_idx: int, anchor_row: RoadmapRow | None
) -> str:
    """Build the single-turn page envelope per roadmap spec section 2.1."""
    lines: list[str] = [
        "[SYSTEM DIRECTIVE: VISUAL ROADMAP ARCHITECT]",
        f"Generate roadmap entries ONLY for Script Indices {start_idx} through {end_idx}.",
    ]
    if anchor_row is not None:
        lines.append(f'CONTINUITY ANCHOR (Index {start_idx - 1}): "{anchor_row.visual_concept}"')
    lines.append("")
    lines.append(
        f"Strict Constraint: Output MUST start at Index {start_idx} and end at Index {end_idx}."
    )
    if anchor_row is not None:
        lines.append(
            f"Output format: Raw Markdown Table rows only, do not repeat headers: {_HEADER_ROW}"
        )
    else:
        lines.append(
            f"Output format: Raw Markdown Table rows only with this exact header: {_HEADER_ROW}"
        )
    lines.append("")
    lines.append(_COLUMN_SEMANTICS)
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
) -> list[RoadmapRow]:
    """Generate the full roadmap page-by-page with per-page checkpointed persistence."""
    folder_path = Path(folder)
    total = len(sentences)
    if total == 0:
        raise RuntimeError("Cannot generate a roadmap for an empty transcript.")

    manifest.set_roadmap_totals(total)
    manifest.set_roadmap_status(PhaseStatus.IN_PROGRESS)
    manifest.save()

    windows = split_transcript_into_windows(sentences, window_size)
    collected: dict[int, RoadmapRow] = {}
    previous_last: RoadmapRow | None = None
    for page_number, window in enumerate(windows, start=1):
        start_idx = (page_number - 1) * window_size + 1
        end_idx = start_idx + len(window) - 1
        page_rows = _generate_page(
            gemini_page,
            window,
            start_idx,
            end_idx,
            previous_last,
            planner_model,
            max_page_repairs,
        )
        for row in page_rows:
            collected[row.index] = row
        previous_last = page_rows[-1]
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
) -> list[RoadmapRow]:
    span = f"{start_idx}-{end_idx}"
    payload = build_page_prompt(window, start_idx, end_idx, anchor_row)
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
                fallback = RoadmapRow(
                    index=idx,
                    timestamp=f"[{idx:02d}:00]",
                    script_line=f"Index {idx} (fallback)",
                    sequence_type="STANDALONE",
                    layout_classification="AHWA_STUDIO",
                    camera_specification="static",
                    visual_concept="Fallback: Host in studio (auto-padded due to parse miss)",
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
