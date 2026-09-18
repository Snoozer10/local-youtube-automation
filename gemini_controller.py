"""Gemini browser controller: tiered prompt injection and Tri-Factor turn completion.

Owns the low-level Gemini conversation lifecycle on top of gemini_utils helpers:
readback-gated prompt injection, stream-completion detection, SPA-first session
reset, and ephemeral session bootstrapping. Browser-only via Playwright CDP.
"""

import random
import re
import sys
import time
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from gemini_utils import (
    RESPONSE_SELECTOR,
    check_gemini_error_state,
    find_input_box,
    find_send_button,
    is_gemini_generating,
    select_gemini_model,
)

try:
    from utils import get_config_value
except Exception:
    import os as _os
    def get_config_value(k, d=""):
        v = _os.getenv(k)
        return v if v is not None else d

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

GEMINI_APP_URL = "https://gemini.google.com/app"
INPUT_BOX_SELECTOR = "rich-textarea div[contenteditable='true']"

_LAST_RESPONSE_SELECTOR = "model-response"
_ACTION_BAR_SELECTOR = (
    "button[aria-label*='Copy' i], button[aria-label*='Share' i], .response-container-footer"
)
_RESPONSE_PREFIX_PATTERN = re.compile(
    r"^(?:Gemini\s+said|قال\s+Gemini|رد\s+Gemini|" r"Gemini\s+a\s+dit|Gemini\s+hat\s+gesagt)[:\s]*",
    re.IGNORECASE,
)
_NEW_CHAT_SELECTORS = (
    "button[aria-label*='New chat' i]",
    "button:has-text('New chat')",
    "button:has(mat-icon:text-is('add'))",
)
_SETTLE_SLEEP_SECONDS = 0.35
_READBACK_MATCH_PERCENT = 95
_RESPONSE_MOUNT_GRACE_SECONDS = 20.0

# --- Persistent session via threshold (avoids per-chunk Control+Shift+O) ---
def get_session_reset_threshold() -> int:
    """Read GEMINI_SESSION_RESET_THRESHOLD with robust fallback to 100."""
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
    """Reuse chat within threshold; only Control+Shift+O when threshold exceeded.
    Preserves Gemini context and avoids duplicate chats in sidebar.
    Handles dummy page objects used in unit tests.
    """
    global _last_session_start_index, _last_session_model
    # Handle dummy objects in unit tests (no url, no find_input_box) - simulate without calling real open_ephemeral_session
    is_dummy = False
    try:
        has_url = hasattr(page, "url")
        has_locator = hasattr(page, "locator")
        if not has_url or not has_locator:
            is_dummy = True
    except Exception:
        is_dummy = True
    if is_dummy:
        if _should_reset_session(current_start_idx, planner_model):
            _last_session_start_index = current_start_idx
            _last_session_model = planner_model
            log(f"[session] dummy page, threshold {get_session_reset_threshold()} - simulated new chat for {current_start_idx}")
        else:
            log(f"[session] dummy page, reusing chat for {current_start_idx}")
        return True
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
        # Light health check: input box must exist, no error state
        try:
            from gemini_utils import check_gemini_error_state as _ces
            from gemini_utils import find_input_box as _fib
            if _fib(page) is None or _ces(page):
                log("[session] input box missing or error state on reuse, forcing new chat")
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
    _last_session_model = None


def log(msg: str) -> None:
    """Print a timestamped UTF-8 log line with immediate buffer flush."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def jitter_delay(lo: float = 1.5, hi: float = 3.0) -> float:
    """Sleep a randomized human-like delay between lo and hi seconds; return it."""
    delay = random.uniform(lo, hi)
    time.sleep(delay)
    return delay


def read_gemini_input_text(page: Page) -> str:
    """Read current prompt-box text via inner_text; contenteditable has no .value."""
    box = find_input_box(page)
    if box is None:
        return ""
    try:
        raw = str(box.inner_text() or "")
        # Directive: handle rich-textarea contenteditable innerText stripping cleanly
        # Normalize zero-width spaces, non-breaking spaces, and collapsed whitespace
        sanitized = raw.replace("\u200b", "").replace("\u00a0", " ").replace("\r", " ")
        sanitized = " ".join(sanitized.split())
        return sanitized
    except Exception as exc:
        log(f"[read] input box read failed: {exc}")
        return ""


def _strip_response_prefix(text: str) -> str:
    """Strip multi-lingual 'Gemini said' style prefixes from a response body."""
    return _RESPONSE_PREFIX_PATTERN.sub("", text.strip()).strip()


def inject_prompt_via_cdp(page: Page, text: str, fill_limit: int = 500) -> bool:
    """Inject prompt text through escalating tiers with a >=95% readback gate.

    Each tier clears the field first so partial inserts never accumulate. The
    readback gate compares stripped inner_text length against the payload before
    any tier counts as success; failure escalates to the next tier.
    """
    payload_len = len(text)

    def _readback_matches() -> bool:
        readback = read_gemini_input_text(page).strip()
        # Compare normalized lengths; contenteditable may drop trailing newline artifacts
        return len(readback) * 100 >= _READBACK_MATCH_PERCENT * payload_len

    def _focus_and_clear(box: Any) -> None:
        box.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")

    def _tier_keyboard_insert(box: Any) -> None:
        page.keyboard.insert_text(text)

    def _tier_clipboard_paste(box: Any) -> None:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        page.evaluate("t => navigator.clipboard.writeText(t)", text)
        box.click()
        page.keyboard.press("Control+v")

    def _tier_exec_command(box: Any) -> None:
        page.evaluate("(t) => document.execCommand('insertText', false, t)", text)

    def _tier_fill(box: Any) -> None:
        box.fill(text)

    tiers: list[tuple[str, Callable[[Any], None], bool]] = [
        ("keyboard-insert_text", _tier_keyboard_insert, True),
        ("clipboard-paste", _tier_clipboard_paste, True),
        ("exec_command-insertText", _tier_exec_command, True),
        ("locator-fill", _tier_fill, payload_len <= fill_limit),
    ]

    for index, (name, action, allowed) in enumerate(tiers, start=1):
        if not allowed:
            continue
        try:
            box = find_input_box(page)
            if box is None:
                log("[inject] input box unavailable; aborting injection.")
                return False
            _focus_and_clear(box)
            action(box)
            time.sleep(_SETTLE_SLEEP_SECONDS)
            if _readback_matches():
                log(f"[inject] prompt injected via tier {index} ({name}).")
                # Submit the turn after successful readback gate
                try:
                    send_btn = find_send_button(page)
                    if send_btn and send_btn.is_visible() and send_btn.is_enabled():
                        send_btn.click()
                        log(f"[inject] submit via send button (tier {index}).")
                    else:
                        page.keyboard.press("Enter")
                        time.sleep(0.2)
                        # Fallback Control+Enter if generation not started
                        if not is_gemini_generating(page):
                            page.keyboard.press("Control+Enter")
                except Exception as submit_exc:
                    log(f"[inject] submit attempt failed: {submit_exc}")
                    try:
                        page.keyboard.press("Enter")
                    except Exception:
                        pass
                time.sleep(0.5)
                return True
            log(f"[inject] tier {index} ({name}) failed readback gate; escalating.")
        except Exception as exc:
            log(f"[inject] tier {index} ({name}) raised {type(exc).__name__}: {exc}; escalating.")
    log("[inject] all injection tiers exhausted.")
    return False


def wait_for_gemini_turn_completion(
    page: Page,
    timeout_seconds: float = 180.0,
    stability_polls: int = 3,
    poll_interval: float = 0.5,
) -> str:
    """Wait until the Gemini turn completes using the Tri-Factor Handshake.

    Factor A (hard): generation indicators absent. Factor B (hard): last
    model-response innerText identical and non-empty across `stability_polls`
    consecutive polls spaced `poll_interval`. Factor C (soft): action-bar
    presence is logged only and never blocks completion. Returns the final
    prefix-stripped response text, "" on error card, raises on timeout.
    """
    start = time.time()
    last_text = ""
    stable_count = 0
    ever_mounted = False
    last_footer_state: bool | None = None

    while time.time() - start < timeout_seconds:
        if check_gemini_error_state(page):
            log("[turn] Gemini error card detected during wait.")
            reset_session_tracker()
            return ""


        try:
            mounted = page.locator(_LAST_RESPONSE_SELECTOR).count() > 0
        except Exception:
            mounted = False

        if not mounted:
            if not ever_mounted and time.time() - start >= _RESPONSE_MOUNT_GRACE_SECONDS:
                raise PlaywrightTimeoutError(
                    "No Gemini response element mounted within 20 seconds."
                )
            time.sleep(poll_interval)
            continue
        ever_mounted = True

        generating = is_gemini_generating(page)

        footer_present = False
        try:
            footer_present = page.locator(_ACTION_BAR_SELECTOR).count() > 0
        except Exception:
            footer_present = False
        if last_footer_state is None or footer_present != last_footer_state:
            log(
                f"[turn] action bar {'present' if footer_present else 'absent'} "
                "(soft signal, non-blocking)."
            )
            last_footer_state = footer_present

        current = ""
        try:
            current = str(
                page.locator(_LAST_RESPONSE_SELECTOR).last.evaluate("el => el.innerText || ''")
                or ""
            )
        except Exception:
            current = ""

        if generating:
            stable_count = 0
            last_text = current
        elif current:
            if current == last_text:
                stable_count += 1
            else:
                last_text = current
                stable_count = 1
            if stable_count >= stability_polls:
                final_text = _strip_response_prefix(current)
                log(f"[turn] response stable after {stable_count} polls ({len(final_text)} chars).")
                return final_text
        else:
            stable_count = 0
            last_text = ""

        time.sleep(poll_interval)

    raise PlaywrightTimeoutError("Gemini response stream timed out before DOM stabilized.")


def reset_chat_session(page: Page) -> bool:
    """Reset to a clean chat: SPA '+ New chat' first, full navigation as fallback."""
    try:
        spa_ready = page.url.startswith(GEMINI_APP_URL) and find_input_box(page) is not None
        if spa_ready:
            clicked = False
            for selector in _NEW_CHAT_SELECTORS:
                try:
                    candidate = page.locator(selector)
                    if candidate.count() > 0:
                        candidate.first.click()
                        clicked = True
                        log(f"[reset] clicked new chat via '{selector}'.")
                        break
                except Exception:
                    continue
            if not clicked:
                page.keyboard.press("Control+Shift+O")
                clicked = True
                log("[reset] new-chat hotkey Control+Shift+O dispatched.")
            if clicked:
                deadline = time.time() + 10.0
                while time.time() < deadline:
                    try:
                        cleared = page.locator(RESPONSE_SELECTOR).count() == 0
                        if cleared and find_input_box(page) is not None:
                            log("[reset] SPA new chat ready.")
                            return True
                    except Exception:
                        pass
                    time.sleep(0.25)
                log("[reset] SPA reset did not settle; falling back to navigation.")

        log("[reset] navigating to a fresh Gemini session...")
        page.goto(GEMINI_APP_URL, wait_until="domcontentloaded", timeout=45000)
        deadline = time.time() + 15.0
        while time.time() < deadline:
            try:
                if page.locator(INPUT_BOX_SELECTOR).first.is_visible():
                    log("[reset] fresh session ready after navigation.")
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        log("[reset] input box never became visible after navigation.")
        return False
    except Exception as exc:
        log(f"[reset] session reset failed: {exc}")
        return False


def open_ephemeral_session(page: Page, target_model: str) -> bool:
    """Open a clean chat bound to `target_model`; verify the input box is live."""
    if not reset_chat_session(page):
        log("[session] chat reset failed; aborting ephemeral session.")
        return False
    if not select_gemini_model(page, target_model):
        log(f"[session] model '{target_model}' selection failed (continuing with default model).")
    if find_input_box(page) is None:
        log("[session] input box missing after session setup.")
        return False
    time.sleep(0.5)
    log(f"[session] ephemeral session ready with model '{target_model}'.")
    return True
