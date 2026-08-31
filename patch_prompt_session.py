import pathlib
p = pathlib.Path('prompt_planner.py')
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
    inject_prompt_via_cdp,
    jitter_delay,
    log,
    open_ephemeral_session,
    wait_for_gemini_turn_completion,
)'''
if old_import in t:
    t = t.replace(old_import, new_import)
    print('import patched prompt')
else:
    print('import not found prompt')

old_plan = '''    jitter_delay()
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
        response = wait_for_gemini_turn_completion(gemini_page)'''
new_plan = '''    jitter_delay()
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
        response = wait_for_gemini_turn_completion(gemini_page)'''
if old_plan in t:
    t = t.replace(old_plan, new_plan)
    print('_plan_single_chunk patched')
else:
    print('_plan_single_chunk not found')
    # debug
    import re
    m=re.search(r"jitter_delay\(\)\s+if not open_ephemeral_session.*?attempts \+= 1.*?response = wait_for_gemini_turn_completion", t, re.S)
    print(m.group(0)[:500] if m else 'not found')

p.write_text(t, encoding='utf-8')
print('prompt_planner patched')
