import pathlib
p = pathlib.Path('gemini_controller.py')
t = p.read_text(encoding='utf-8')
old = '''from gemini_utils import (
    RESPONSE_SELECTOR,
    check_gemini_error_state,
    find_input_box,
    is_gemini_generating,
    select_gemini_model,
)'''
new = '''from gemini_utils import (
    RESPONSE_SELECTOR,
    check_gemini_error_state,
    find_input_box,
    is_gemini_generating,
    select_gemini_model,
)

try:
    from utils import get_config_value
except Exception:
    import os as _os
    def get_config_value(k, d=""):
        v = _os.getenv(k)
        return v if v is not None else d'''
if old in t:
    t = t.replace(old, new)
    print('import patched')
else:
    print('import not found')

# Add threshold helper and session persistence after constants
old_const = '''_SETTLE_SLEEP_SECONDS = 0.35
_READBACK_MATCH_PERCENT = 95
_RESPONSE_MOUNT_GRACE_SECONDS = 20.0'''
new_const = '''_SETTLE_SLEEP_SECONDS = 0.35
_READBACK_MATCH_PERCENT = 95
_RESPONSE_MOUNT_GRACE_SECONDS = 20.0

# --- Persistent session via threshold (avoids per-chunk Control+Shift+O) ---
def get_session_reset_threshold() -> int:
    \"\"\"Read GEMINI_SESSION_RESET_THRESHOLD with robust fallback to 100.\"\"\"
    raw = get_config_value("GEMINI_SESSION_RESET_THRESHOLD", "100")
    try:
        val = int(str(raw).strip().strip('"').strip("'"))
        if val <= 0:
            return 100
        return val
    except Exception:
        return 100

_last_session_start_index: int | None = None
_last_session_model: str | None = None

def _should_reset_session(current_start_idx: int, planner_model: str) -> bool:
    global _last_session_start_index, _last_session_model
    threshold = get_session_reset_threshold()
    if _last_session_start_index is None:
        return True
    if _last_session_model is not None and _last_session_model != planner_model:
        return True
    # Reset only when we have crossed threshold lines since last reset
    if current_start_idx - _last_session_start_index >= threshold:
        return True
    return False

def ensure_persistent_gemini_session(page, current_start_idx: int, planner_model: str) -> bool:
    \"\"\"Reuse chat within threshold; only Control+Shift+O when threshold exceeded.
    Preserves Gemini context and avoids duplicate chats in sidebar.
    \"\"\"
    global _last_session_start_index, _last_session_model
    if _should_reset_session(current_start_idx, planner_model):
        log(f"[session] threshold {get_session_reset_threshold()} exceeded or first page (last={_last_session_start_index}, cur={current_start_idx}, model={planner_model}), opening new chat")
        ok = open_ephemeral_session(page, planner_model)
        if ok:
            _last_session_start_index = current_start_idx
            _last_session_model = planner_model
        return ok
    else:
        # Reuse existing chat - ensure input box still live, no new chat
        log(f"[session] reusing chat (last={_last_session_start_index}, cur={current_start_idx}, threshold={get_session_reset_threshold()}, model={planner_model})")
        # Light health check: input box must exist, not generating
        try:
            from gemini_utils import find_input_box as _fib
            if _fib(page) is None:
                log("[session] input box missing on reuse, forcing new chat")
                ok = open_ephemeral_session(page, planner_model)
                if ok:
                    _last_session_start_index = current_start_idx
                    _last_session_model = planner_model
                return ok
        except Exception:
            pass
        return True

def reset_session_tracker():
    global _last_session_start_index, _last_session_model
    _last_session_start_index = None
    _last_session_model = None'''
if old_const in t:
    t = t.replace(old_const, new_const)
    print('const patched')
else:
    print('const not found')

p.write_text(t, encoding='utf-8')
print('gemini_controller patched')
