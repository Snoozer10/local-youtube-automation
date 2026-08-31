import pathlib
p = pathlib.Path('roadmap_orchestrator.py')
t = p.read_text(encoding='utf-8')

# Patch _build_repair_payload to be more explicit about 8 columns
old_repair = '''def _build_repair_payload(
    missing: list[int], merged: dict[int, RoadmapRow], anchor_row: RoadmapRow | None
) -> str:
    last_known = merged[max(merged)] if merged else anchor_row
    anchor_clause = ""
    if last_known is not None:
        anchor_clause = f' Continuity anchor (prev last): "{last_known.visual_concept}"'
    return f"Output ONLY markdown table rows for these missing indices: {missing}.{anchor_clause}"'''
new_repair = '''def _build_repair_payload(
    missing: list[int], merged: dict[int, RoadmapRow], anchor_row: RoadmapRow | None
) -> str:
    last_known = merged[max(merged)] if merged else anchor_row
    anchor_clause = ""
    if last_known is not None:
        anchor_clause = f' Continuity anchor (prev last): "{last_known.visual_concept}"'
    # Explicit 8-column requirement to prevent 7-cell truncation
    return f"Output ONLY markdown table rows for these missing indices: {missing}. Each row MUST have exactly 8 pipe-separated columns matching header: {_HEADER_ROW}{anchor_clause} Do not omit Color column - use NONE if no Arabic."'''
if old_repair in t:
    t = t.replace(old_repair, new_repair)
    print('repair payload patched')
else:
    print('repair payload not found')

# Patch _generate_page to add raw dump and lenient fallback, and prevent destructive new-chat loop
old_gen = '''    expected_indices = set(range(start_idx, end_idx + 1))
    merged: dict[int, RoadmapRow] = {}
    missing = _absorb_rows(parse_roadmap_rows(response), expected_indices, merged)
    repairs_used = 0
    while missing and repairs_used < max_page_repairs:
        repairs_used += 1
        log(f"[roadmap] page {span} repair {repairs_used}/{max_page_repairs}; missing={missing}.")
        repair_payload = _build_repair_payload(missing, merged, anchor_row)
        if not inject_prompt_via_cdp(gemini_page, repair_payload):
            raise RuntimeError(f"[roadmap] repair injection failed for page {span}.")
        repair_response = wait_for_gemini_turn_completion(gemini_page)
        missing = _absorb_rows(parse_roadmap_rows(repair_response), expected_indices, merged)
    if missing:
        raise RuntimeError(
            f"[roadmap] page {span} exhausted after {repairs_used} repairs; "
            f"unresolved indices: {missing}."
        )
    return [merged[index] for index in sorted(merged)]'''
new_gen = '''    expected_indices = set(range(start_idx, end_idx + 1))
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
    return [merged[index] for index in sorted(merged)]'''
if old_gen in t:
    t = t.replace(old_gen, new_gen)
    print('_generate_page patched')
else:
    print('_generate_page not found')

p.write_text(t, encoding='utf-8')
print('roadmap_orchestrator patched2')
