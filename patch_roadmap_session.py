import pathlib
p = pathlib.Path('roadmap_orchestrator.py')
t = p.read_text(encoding='utf-8')
old_import = '''from gemini_controller import (
    inject_prompt_via_cdp,
    jitter_delay,
    log,
    open_ephemeral_session,
    wait_for_gemini_turn_completion,
)'''
new_import = '''from gemini_controller import (
    ensure_persistent_gemini_session,
    get_session_reset_threshold,
    inject_prompt_via_cdp,
    jitter_delay,
    log,
    open_ephemeral_session,
    wait_for_gemini_turn_completion,
)'''
if old_import in t:
    t = t.replace(old_import, new_import)
    print('import patched roadmap')
else:
    print('import not found roadmap')

# Patch _generate_page to use persistent session
old_gen = '''def _generate_page(
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
    if not _send_turn(gemini_page, payload, planner_model):
        raise RuntimeError(f"[roadmap] failed to deliver initial turn for page {span}.")
    response = wait_for_gemini_turn_completion(gemini_page)'''
new_gen = '''def _generate_page(
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
    response = wait_for_gemini_turn_completion(gemini_page)'''
if old_gen in t:
    t = t.replace(old_gen, new_gen)
    print('_generate_page patched')
else:
    print('_generate_page not found')

# Also patch the empty-turn retry to use persistent session (no new chat)
old_retry = '''    response = wait_for_gemini_turn_completion(gemini_page)
    if not response:
        log(f"[roadmap] empty turn on page {span}; retrying once with a fresh session.")
        if not _send_turn(gemini_page, payload, planner_model):
            raise RuntimeError(f"[roadmap] failed to redeliver page {span} after empty turn.")
        response = wait_for_gemini_turn_completion(gemini_page)
        if not response:
            raise RuntimeError(f"[roadmap] page {span} returned consecutive empty turns.")'''
new_retry = '''    response = wait_for_gemini_turn_completion(gemini_page)
    if not response:
        log(f"[roadmap] empty turn on page {span}; retrying once in same session (no new chat).")
        if not inject_prompt_via_cdp(gemini_page, payload):
            raise RuntimeError(f"[roadmap] failed to redeliver page {span} after empty turn.")
        response = wait_for_gemini_turn_completion(gemini_page)
        if not response:
            raise RuntimeError(f"[roadmap] page {span} returned consecutive empty turns.")'''
if old_retry in t:
    t = t.replace(old_retry, new_retry)
    print('empty retry patched')
else:
    print('empty retry not found')

p.write_text(t, encoding='utf-8')
print('roadmap patched')
