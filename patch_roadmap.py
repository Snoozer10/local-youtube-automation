import pathlib
p = pathlib.Path('roadmap_orchestrator.py')
t = p.read_text(encoding='utf-8')

# 1. Enhance parse_roadmap_rows with explicit debug logging for every skip
old_parse = '''def parse_roadmap_rows(md_text: str) -> list[RoadmapRow]:
    """Parse markdown table rows into typed RoadmapRows; malformed rows are warn-skipped."""
    by_index: dict[int, RoadmapRow] = {}
    lowered_columns = [column.lower() for column in ROADMAP_COLUMNS]
    for line in md_text.splitlines():
        cells = parse_markdown_table_line(line)
        if not cells:
            continue
        if [cell.lower() for cell in cells[: len(ROADMAP_COLUMNS)]] == lowered_columns:
            continue
        if len(cells) < len(ROADMAP_COLUMNS):
            log(f"[roadmap] skipping short table row ({len(cells)} cells): {line[:80]}")
            continue
        row = _row_from_cells(cells)
        if row is None:
            log(f"[roadmap] skipping malformed row (unreadable Index): {line[:80]}")
            continue
        by_index[row.index] = row
    return [by_index[index] for index in sorted(by_index)]'''
new_parse = '''def parse_roadmap_rows(md_text: str) -> list[RoadmapRow]:
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
    return [by_index[index] for index in sorted(by_index)]'''
if old_parse in t:
    t = t.replace(old_parse, new_parse)
    print('parse_roadmap_rows patched')
else:
    print('parse_roadmap_rows not found')

# 2. Enhance _row_from_cells to log and pad
old_row = '''def _row_from_cells(cells: list[str]) -> RoadmapRow | None:
    match = _INDEX_DIGITS_RE.search(cells[0])
    if match is None:
        return None
    fields = cells[: len(ROADMAP_COLUMNS)]
    return RoadmapRow(
        index=int(match.group()),
        timestamp=fields[1],
        script_line=fields[2],
        sequence_type=fields[3],
        layout_classification=fields[4],
        camera_specification=fields[5],
        visual_concept=fields[6],
        color_and_arabic_text=fields[7],
    )'''
new_row = '''def _row_from_cells(cells: list[str]) -> RoadmapRow | None:
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
        return None'''
if old_row in t:
    t = t.replace(old_row, new_row)
    print('_row_from_cells patched')
else:
    print('_row_from_cells not found')

p.write_text(t, encoding='utf-8')
print('roadmap_orchestrator patched')
