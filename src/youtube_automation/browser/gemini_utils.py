"""Gemini Browser Automation Utilities.

This module provides high-level utilities for automating interactions with
Google Gemini via Playwright CDP. It handles session management, prompt
dispatching, response streaming, and model selection with robust
error recovery and adaptive polling.

All browser interactions use Chrome DevTools Protocol (CDP) over port 9222
with no external API dependencies.
"""

import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

from playwright._impl._errors import TargetClosedError
from playwright.sync_api import Page

from youtube_automation.prompts import loader

logger = logging.getLogger("Pipeline")

# Unified response container selector for multi-lingual UI states
RESPONSE_SELECTOR = "model-response, .model-response, [data-test-id='model-response']"
USER_QUERY_SELECTOR = "user-query, [data-test-id='user-query']"

_RESPONSE_PREFIX_PATTERN = re.compile(
    r"^(?:Gemini\s+said|قال\s+Gemini|رد\s+Gemini|"
    r"Gemini\s+a\s+dit|Gemini\s+hat\s+gesagt)[:\s]*",
    re.IGNORECASE,
)

TRANSIENT_PLACEHOLDERS = {
    "analyzing",
    "thinking",
    "thinking...",
    "visualizing the scenes",
    "structuring the narrative",
    "يفكر",
    "يفكر...",
    "تحليل",
}

STOP_GENERATING_SELECTORS: tuple[str, ...] = (
    "button[aria-label*='Stop generating' i]",
    "button[aria-label*='Stop generation' i]",
    "button[aria-label*='Stop response' i]",
    "button[aria-label='Stop' i]",
    "button[aria-label*='Cancel response' i]",
    "button[aria-label*='Cancel generation' i]",
    "button[aria-label='Interrupt' i]",
    "button[aria-label*='إيقاف الإنشاء' i]",
    "button[aria-label*='إيقاف الرد' i]",
    "button[aria-label*='إيقاف التوليد' i]",
    "button[aria-label='إيقاف' i]",
    "button[aria-label='توقف' i]",
    "button[aria-label='وقف' i]",
    "[data-test-id='stop-button']",
    "[data-test-id='stop-generating-button']",
    "button.stop-button",
)

EXCLUDED_AUDIO_PLAYBACK_KEYWORDS: tuple[str, ...] = (
    "audio",
    "playback",
    "listen",
    "sound",
    "صوت",
    "تشغيل",
    "استماع",
    "قراءة",
)

STOP_TEXT_KEYWORDS: tuple[str, ...] = (
    "stop",
    "stop generating",
    "إيقاف",
    "توقف",
    "وقف",
    "إيقاف الإنشاء",
)

FORBIDDEN_BROAD_SELECTORS: tuple[str, ...] = (
    "button:has(rect)",
    "mat-progress-spinner",
    "mat-progress-bar",
)


def _build_stop_control_check_js(
    stop_selectors: tuple[str, ...],
    audio_keywords: tuple[str, ...],
    text_keywords: tuple[str, ...],
) -> str:
    stop_selectors_json = json.dumps(list(stop_selectors), ensure_ascii=False)
    audio_keywords_json = json.dumps(list(audio_keywords), ensure_ascii=False)
    text_keywords_json = json.dumps(list(text_keywords), ensure_ascii=False)
    return f"""() => {{
    const isVisible = (el) => {{
        if (!el) return false;
        if (typeof el.checkVisibility === 'function') return el.checkVisibility();
        return el.offsetParent !== null || el.getClientRects().length > 0;
    }};
    const stopSelectors = {stop_selectors_json};
    const audioKeywords = {audio_keywords_json};
    const textKeywords = new Set({text_keywords_json});

    const isAudioOrPlayback = (el) => {{
        const label = (el.getAttribute('aria-label') || '').toLowerCase();
        for (const kw of audioKeywords) {{
            if (label.includes(kw)) return true;
        }}
        return false;
    }};

    for (const sel of stopSelectors) {{
        const elements = document.querySelectorAll(sel);
        for (const el of elements) {{
            if (!isVisible(el)) continue;
            if (isAudioOrPlayback(el)) continue;
            return true;
        }}
    }}
    const textButtons = document.querySelectorAll("button, [role='button']");
    for (const el of textButtons) {{
        if (!isVisible(el)) continue;
        const text = (el.innerText || '').trim().toLowerCase();
        if (textKeywords.has(text)) {{
            if (isAudioOrPlayback(el)) continue;
            return true;
        }}
    }}
    return false;
}}"""


STOP_CONTROL_CHECK_JS = _build_stop_control_check_js(
    STOP_GENERATING_SELECTORS,
    EXCLUDED_AUDIO_PLAYBACK_KEYWORDS,
    STOP_TEXT_KEYWORDS,
)


def _clean_response_prefix(text: str) -> str:
    return _RESPONSE_PREFIX_PATTERN.sub("", text).strip()


def _is_transient_placeholder(text: str) -> bool:
    cleaned = text.strip().lower()
    return cleaned in TRANSIENT_PLACEHOLDERS or cleaned.rstrip(".") in {
        "analyzing",
        "thinking",
        "visualizing the scenes",
        "structuring the narrative",
        "يفكر",
        "تحليل",
    }


def _log_response_diagnostic(
    baseline_count: int,
    new_count: int,
    gen_control_visible: bool,
    stable_polls: int,
    response_len: int,
    decision: str,
) -> None:
    logger.info(
        "[gemini_detector] baseline_count=%d new_count=%d gen_control=%s stable_polls=%d response_len=%d decision=%s",
        baseline_count,
        new_count,
        "visible" if gen_control_visible else "absent",
        stable_polls,
        response_len,
        decision,
    )


def _normalize_rendered_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _rendered_query_matches_prompt(rendered: str, prompt: str) -> bool:
    """Match both ends so a restored prompt with the same generic preamble cannot pass."""
    actual = _normalize_rendered_text(rendered)
    expected = _normalize_rendered_text(prompt)
    if not expected:
        return False
    width = min(160, len(expected))
    return expected[:width] in actual and expected[-width:] in actual


def _model_label_matches(rendered: str, requested: str) -> bool:
    """Match the model name exactly; `Flash` must not accept `Flash-Lite`."""
    first_line = _normalize_rendered_text(rendered.splitlines()[0] if rendered else "").lower()
    normalized = re.sub(r"^\d+(?:\.\d+)?\s+", "", first_line)
    return normalized == requested.strip().lower()


def find_input_box(page: Page) -> Any | None:
    """Locate the Gemini rich-text input box across English & Arabic UI variations.

    Scans from bottom-most element first to prioritize the active input
    in the conversation thread.

    Args:
        page: Playwright page object connected to Gemini.

    Returns:
        Locator for the input element, or None if not found.
    """
    selectors = [
        "rich-textarea div[contenteditable='true']",
        "rich-textarea .ql-editor",
        "div[contenteditable='true'][role='textbox']",
        "rich-textarea [contenteditable='true']",
        "div[contenteditable='true']",
        "rich-textarea textarea",
        "textarea[aria-label*='prompt' i]",
        "textarea[aria-label*='Gemini' i]",
        "rich-textarea",
    ]

    # Try locating visible, enabled element (scanning from bottom-most first)
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
            for i in range(count - 1, -1, -1):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    try:
                        el.scroll_into_view_if_needed(timeout=1000)
                    except Exception:
                        pass
                    return el
        except Exception:
            continue

    # Fallback: Force wait on primary container
    for sel in selectors[:4]:
        try:
            page.wait_for_selector(sel, timeout=1500)
            box = page.locator(sel).last
            if box and box.is_visible():
                return box
        except Exception:
            continue

    return None


def find_send_button(page: Page) -> Any | None:
    """Locate the Gemini send/submit button.

    Safely ignores buttons when they are in an active Stop/Cancel/Interrupt
    state to prevent accidental generation termination.

    Args:
        page: Playwright page object connected to Gemini.

    Returns:
        Locator for the send button, or None if not found.
    """
    selectors = [
        "button[aria-label*='Submit' i]",
        "button[aria-label*='Send message' i]",
        "button[aria-label*='Send' i]",
        "button.send-button",
        "div[class*='send-button-container'] button",
        "button[id*='send']",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(loc.count() - 1, -1, -1):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    aria_label = (el.get_attribute("aria-label") or "").lower()
                    btn_text = (el.evaluate("e => e.innerText") or "").lower()
                    combined = aria_label + " " + btn_text
                    if any(w in combined for w in ["stop", "cancel", "interrupt", "وقف"]):
                        continue
                    return el
        except Exception:
            continue
    return None


def is_gemini_stop_control_visible(page: Page) -> bool:
    """Detect if Gemini has a real visible Stop-generating control.

    Uses narrowly scoped semantic selectors for English and Arabic Gemini UIs.
    Disqualifies audio playback / TTS controls and ignores generic SVG/rect
    buttons or unrelated page spinners.

    Args:
        page: Playwright page object connected to Gemini.

    Returns:
        True if an active generation stop control is visible, False otherwise.
    """
    try:
        return bool(page.evaluate(STOP_CONTROL_CHECK_JS))
    except Exception as exc:
        logger.debug("is_gemini_stop_control_visible evaluation failed: %s", exc)
        return False


def is_gemini_generating(page: Page) -> bool:
    """Detect if Gemini is actively thinking, analyzing, or streaming.

    Narrowly scopes detection to visible Stop-generating controls and
    excludes generic SVG/rect buttons and unrelated page spinners.

    Args:
        page: Playwright page object connected to Gemini.

    Returns:
        True if Gemini is generating, False otherwise.
    """
    return is_gemini_stop_control_visible(page)


def wait_for_gemini_idle_native(page: Page, timeout_ms: int = 180_000) -> bool:
    """Wait for Gemini generation to complete using browser-native MutationObserver.

    Args:
        page: Playwright page object.
        timeout_ms: Maximum wait time in milliseconds.

    Returns:
        True if idle detected within timeout, False otherwise.
    """
    idle_js = f"() => !({STOP_CONTROL_CHECK_JS})()"
    try:
        page.wait_for_function(idle_js, timeout=timeout_ms)
        return True
    except Exception as exc:
        logger.debug("wait_for_gemini_idle_native timeout: %s", exc)
        return False


def wait_until_gemini_idle(page: Page, timeout_seconds: int = 180) -> bool:
    """Ensure Gemini is completely idle before pasting or sending a new turn.

    Args:
        page: Playwright page object.
        timeout_seconds: Maximum wait time in seconds.

    Returns:
        True if idle confirmed, False on timeout.
    """
    start = time.time()
    while time.time() - start < timeout_seconds:
        if not is_gemini_generating(page):
            time.sleep(2)  # Extra buffer to let DOM settle
            if not is_gemini_generating(page):
                return True
        time.sleep(1)
    return False


def get_last_response(page: Page) -> str:
    """Read the text content of the last Gemini response element.

    Handles multi-lingual UI prefixes (English, Arabic, French, German).

    Args:
        page: Playwright page object.

    Returns:
        Cleaned response text, or empty string if not found.
    """
    try:
        elements = page.locator(RESPONSE_SELECTOR)
        count = elements.count()
        if count > 0:
            last_el = elements.nth(count - 1)
            text = str(last_el.evaluate("el => el.innerText") or "").strip()
            return _clean_response_prefix(text)
    except Exception as exc:
        logger.warning("Error reading last response: %s", exc)
    return ""


class GeminiSessionClient:
    """Encapsulate browser automation interactions for Gemini conversations.

    Attributes:
        page: Playwright page object.
        model_name: Target Gemini model name (e.g., "Pro", "Flash").
    """

    def __init__(self, page: Page, model_name: str = "Pro") -> None:
        self.page = page
        self.model_name = model_name

    def initialize_session(
        self, setup_prompt: str, expected_ack_tokens: list[str] | None = None
    ) -> bool:
        """Start a clean chat, select model, and send setup prompt.

        Args:
            setup_prompt: Initial prompt to establish refinement rules.
            expected_ack_tokens: Tokens to look for in response. Defaults to refine prompt ack tokens.

        Returns:
            True if session initialized successfully, False otherwise.
        """
        start_clean_gemini_chat(self.page)
        select_gemini_model(self.page, self.model_name)
        time.sleep(1)

        success, initial_count = self.dispatch_prompt(setup_prompt)
        if not success:
            return False

        response = wait_for_gemini_response(
            self.page, initial_count=initial_count, timeout_seconds=120
        )
        expected = expected_ack_tokens or loader.ack_tokens("refine")
        return bool(
            response and any(kw.lower() in response.lower() for kw in expected)
        )

    def dispatch_prompt(self, text: str) -> tuple[bool, int]:
        """Dispatch a prompt to Gemini and return initial response count.

        Args:
            text: Prompt text to send.

        Returns:
            Tuple of (success: bool, initial_response_count: int).
        """
        wait_for_gemini_idle_native(self.page, timeout_ms=5000)
        initial_count = self.page.locator(RESPONSE_SELECTOR).count()
        initial_query_count = self.page.locator(USER_QUERY_SELECTOR).count()
        try:
            target = find_input_box(self.page)
            if not target:
                return False, initial_count

            target.focus()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.keyboard.insert_text(text)

            # Dispatch Angular/Lit change notifications so UI enables Send button
            target.evaluate("""(el) => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""")
            time.sleep(0.3)

            send_btn = find_send_button(self.page)
            if send_btn and send_btn.is_visible() and send_btn.is_enabled():
                send_btn.click()
            else:
                self.page.keyboard.press("Control+Enter")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                queries = self.page.locator(USER_QUERY_SELECTOR)
                if queries.count() > initial_query_count:
                    rendered = queries.nth(queries.count() - 1).evaluate(
                        "el => el.innerText"
                    )
                    if _rendered_query_matches_prompt(str(rendered or ""), text):
                        return True, initial_count
                    if not _is_clean_chat_url(self.page.url):
                        logger.error("Historical Gemini conversation replaced the submitted turn.")
                        return False, initial_count
                time.sleep(0.25)
            logger.error("Submitted Gemini prompt did not mount as a matching user turn.")
            return False, initial_count
        except Exception as exc:
            logger.error("Failed to dispatch prompt: %s", exc)
            return False, initial_count

    def refine_turn(self, prompt: str, timeout_seconds: int = 420) -> str | None:
        """Send a refinement prompt and wait for response.

        Args:
            prompt: Refinement prompt text.
            timeout_seconds: Maximum wait time for response.

        Returns:
            Response text or None on failure.
        """
        success, initial_count = self.dispatch_prompt(prompt)
        if not success:
            return None
        return wait_for_gemini_response(
            self.page, initial_count=initial_count, timeout_seconds=timeout_seconds
        )


def check_gemini_error_state(page: Page) -> bool:
    """Detect if Gemini displayed an error card, network crash, or regenerate prompt.

    Args:
        page: Playwright page object.

    Returns:
        True if error state detected, False otherwise.
    """
    error_selectors = [
        "div[data-test-id='error-message']",
        ".error-card",
        "button:has-text('Try again')",
        "button:has-text('إعادة المحاولة')",
        "div:has-text('Something went wrong')",
        "div:has-text('حدث خطأ ما')",
    ]
    for sel in error_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            pass
    return False


def wait_for_gemini_response(
    page: Page,
    initial_count: int = 0,
    min_length: int = 1,
    timeout_seconds: float = 420,
    *,
    stability_polls: int = 3,
    poll_interval: float = 0.5,
) -> str:
    """Wait for Gemini to start streaming and monitor text stability until complete.

    Resilient against long deep-reasoning phases and fast-fails on errors.
    Requires a new response node (beyond initial_count), absence of the real
    Stop-generating control, and stable response text across consecutive polls.
    Performs a final DOM observation at the timeout boundary to prevent false
    timeouts when generation finishes during the last poll interval.
    Never logs prompt or response contents.

    Args:
        page: Playwright page object connected to Gemini.
        initial_count: Number of response elements before prompt was sent.
        min_length: Minimum response length to consider valid.
        timeout_seconds: Maximum total wait time in seconds.
        stability_polls: Consecutive identical polls required for stability.
        poll_interval: Seconds to wait between polling observations.

    Returns:
        Complete response text, or empty string on timeout/error.
    """
    start_time = time.monotonic()
    total_timeout = float(timeout_seconds)
    deadline = start_time + total_timeout
    phase1_timeout = min(90.0, total_timeout)
    phase1_deadline = start_time + phase1_timeout

    # 1. Wait for response turn or generation to start
    new_response_started = False
    while time.monotonic() < phase1_deadline:
        if check_gemini_error_state(page):
            logger.error("Gemini displayed an error card / retry banner.")
            _log_response_diagnostic(
                baseline_count=initial_count,
                new_count=0,
                gen_control_visible=False,
                stable_polls=0,
                response_len=0,
                decision="error_card",
            )
            return ""

        current_count = page.locator(RESPONSE_SELECTOR).count()
        stop_visible = is_gemini_stop_control_visible(page)

        if stop_visible or current_count > initial_count:
            new_response_started = True
            break

        now = time.monotonic()
        if now >= phase1_deadline:
            break
        wait_ms = min(int(poll_interval * 1000), 250)
        rem_ms = int(max(0, (phase1_deadline - now) * 1000))
        actual_wait = min(wait_ms, rem_ms)
        if actual_wait > 0:
            page.wait_for_timeout(actual_wait)

    if not new_response_started:
        # Final phase-one observation at deadline boundary before declaring start_timeout
        if check_gemini_error_state(page):
            logger.error("Gemini showed error card before generating response.")
            _log_response_diagnostic(
                baseline_count=initial_count,
                new_count=initial_count,
                gen_control_visible=False,
                stable_polls=0,
                response_len=0,
                decision="error_card_before_start",
            )
            return ""

        current_count = page.locator(RESPONSE_SELECTOR).count()
        stop_visible = is_gemini_stop_control_visible(page)
        if stop_visible or current_count > initial_count:
            new_response_started = True

    if not new_response_started:
        logger.error("Response turn did not start within %ds.", int(phase1_timeout))
        current_count = page.locator(RESPONSE_SELECTOR).count()
        _log_response_diagnostic(
            baseline_count=initial_count,
            new_count=current_count,
            gen_control_visible=False,
            stable_polls=0,
            response_len=0,
            decision="start_timeout",
        )
        return ""

    # 2. Monitor stream growth and stability
    last_text = ""
    stable_count = 0
    last_count = initial_count
    stop_visible = False

    while time.monotonic() < deadline:
        if check_gemini_error_state(page):
            logger.error("Gemini encountered a generation error mid-stream.")
            _log_response_diagnostic(
                baseline_count=initial_count,
                new_count=last_count,
                gen_control_visible=stop_visible,
                stable_polls=stable_count,
                response_len=len(last_text),
                decision="error_card_mid_stream",
            )
            return ""

        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            last_count = current_count
            stop_visible = is_gemini_stop_control_visible(page)

            if current_count > initial_count:
                last_el = page.locator(RESPONSE_SELECTOR).nth(current_count - 1)
                try:
                    raw_text = last_el.evaluate("el => el.innerText", timeout=4000) or ""
                    current_text = _clean_response_prefix(str(raw_text).strip())
                except Exception:
                    current_text = ""

                is_placeholder = _is_transient_placeholder(current_text)

                # Track text stability independently while the Stop control is visible
                if not is_placeholder and len(current_text) >= min_length:
                    if current_text == last_text and current_text != "":
                        stable_count += 1
                    else:
                        last_text = current_text
                        stable_count = 1
                else:
                    last_text = current_text
                    stable_count = 0

                # Return only when:
                # a. a new response node exists (current_count > initial_count)
                # b. the real Stop control is absent (not stop_visible)
                # c. the text is not a placeholder and meets min_length
                # d. the configured stability_polls threshold has actually been reached
                if (
                    not stop_visible
                    and not is_placeholder
                    and len(current_text) >= min_length
                    and stable_count >= stability_polls
                ):
                    _log_response_diagnostic(
                        baseline_count=initial_count,
                        new_count=current_count,
                        gen_control_visible=False,
                        stable_polls=stable_count,
                        response_len=len(current_text),
                        decision="completed",
                    )
                    return current_text
            else:
                # Still waiting for the new response element to mount
                stable_count = 0
                last_text = ""
        except Exception as poll_exc:
            logger.debug("Exception during response polling observation: %s", poll_exc)

        # Polling sleep using page.wait_for_timeout, capped against monotonic deadline
        now = time.monotonic()
        if now >= deadline:
            break
        sleep_dur = poll_interval if not stop_visible else min(poll_interval * 1.5, 0.75)
        rem_ms = int(max(0, (deadline - now) * 1000))
        actual_wait = min(int(sleep_dur * 1000), rem_ms)
        if actual_wait > 0:
            page.wait_for_timeout(actual_wait)

    # 3. Final DOM observation at timeout boundary
    # Must preserve the exact same stability and completion criteria:
    # a. new response node exists (final_count > initial_count)
    # b. real Stop control is absent (not final_stop_visible)
    # c. text is not a placeholder and meets min_length
    # d. stability_polls threshold has actually been reached (stable_count >= stability_polls)
    try:
        if check_gemini_error_state(page):
            logger.error("Gemini displayed an error card at timeout boundary.")
            _log_response_diagnostic(
                baseline_count=initial_count,
                new_count=last_count,
                gen_control_visible=stop_visible,
                stable_polls=stable_count,
                response_len=len(last_text),
                decision="error_card_at_boundary",
            )
            return ""

        final_count = page.locator(RESPONSE_SELECTOR).count()
        final_stop_visible = is_gemini_stop_control_visible(page)

        if final_count > initial_count:
            last_el = page.locator(RESPONSE_SELECTOR).nth(final_count - 1)
            raw_text = last_el.evaluate("el => el.innerText", timeout=4000) or ""
            final_text = _clean_response_prefix(str(raw_text).strip())
            is_placeholder = _is_transient_placeholder(final_text)

            if not is_placeholder and len(final_text) >= min_length:
                if final_text == last_text and final_text != "":
                    stable_count += 1
                else:
                    last_text = final_text
                    stable_count = 1
            else:
                last_text = final_text
                stable_count = 0

            if (
                not final_stop_visible
                and not is_placeholder
                and len(final_text) >= min_length
                and stable_count >= stability_polls
            ):
                _log_response_diagnostic(
                    baseline_count=initial_count,
                    new_count=final_count,
                    gen_control_visible=False,
                    stable_polls=stable_count,
                    response_len=len(final_text),
                    decision="boundary_accepted",
                )
                return final_text
    except Exception as boundary_exc:
        logger.debug("Exception during final timeout boundary observation: %s", boundary_exc)

    _log_response_diagnostic(
        baseline_count=initial_count,
        new_count=last_count,
        gen_control_visible=stop_visible,
        stable_polls=stable_count,
        response_len=len(last_text),
        decision="timeout",
    )
    logger.error("Gemini response wait timed out after %ds.", int(total_timeout))
    return ""


def select_gemini_model(page: Page, model_name: str = "Pro", timeout_seconds: float = 20.0) -> bool:
    """Select a specific Gemini model ('Pro', 'Flash', etc.).

    Compatible with Gemini 2.0/Advanced model selector dropdowns.
    Filters out upgrade/CTA buttons to avoid false positive clicks.
    Polls up to timeout_seconds to allow the SPA UI to hydrate.

    Args:
        page: Playwright page object.
        model_name: Target model name.
        timeout_seconds: Max seconds to wait for model selector to appear.

    Returns:
        True if model selected successfully, False otherwise.
    """
    logger.info("Attempting to select Gemini model: '%s'", model_name)
    target_clean = model_name.strip().lower()

    # 1. Broad selector list covering top header, mode switcher, and input toolbar
    pill_selectors = [
        "button[data-test-id='model-switcher-button']",
        "button[aria-haspopup='menu']:has-text('Flash')",
        "button[aria-haspopup='menu']:has-text('Pro')",
        "button[aria-haspopup='menu']:has-text('Gemini')",
        "button[aria-label*='model' i]",
        "button[aria-label*='Mode' i]",
        "button[aria-label*='Gemini' i]",
        "button:has-text('2.5 Pro')",
        "button:has-text('2.0 Flash')",
        "button:has-text('Pro')",
        "button:has-text('Flash')",
        "button:has-text('Advanced')",
        "div[role='button'][aria-haspopup='menu']",
        "[data-test-id*='model']",
        ".bard-mode-menu-button",
    ]

    start_time = time.time()
    model_btn = None
    while time.time() - start_time < timeout_seconds:
        # Iterate and check .last because active model picker sits in bottom toolbar
        for sel in pill_selectors:
            try:
                locs = page.locator(sel)
                count = locs.count()
                for i in range(count - 1, -1, -1):
                    el = locs.nth(i)
                    if el.is_visible() and el.is_enabled():
                        try:
                            btn_text = (el.evaluate("e => e.innerText") or "").strip().lower()
                        except Exception:
                            continue
                        # Ensure we are inspecting a mode switcher button, not an upgrade prompt
                        if "upgrade" in btn_text or "اشتراك" in btn_text:
                            continue
                        # Check if already active (exact model badge match)
                        if _model_label_matches(btn_text, target_clean):
                            logger.info("Model '%s' is already active.", model_name)
                            return True
                        if any(
                            m in btn_text for m in ["pro", "flash", "lite", "model", "2.0", "2.5"]
                        ):
                            model_btn = el
                            break
                if model_btn:
                    break
            except TargetClosedError:
                logger.warning("Model selector poll aborted: page/target closed mid-iteration.")
                return False
            except Exception:
                continue

        if model_btn:
            break
        time.sleep(0.5)

    if not model_btn:
        logger.warning("Could not locate Gemini model selector button.")
        return False

    try:
        logger.info("Switching Gemini model to '%s'...", model_name)
        model_btn.click(force=True)
        time.sleep(1.2)

        # 2. Click the target option inside the opened menu
        menu_selectors = [
            "[role='menuitem']",
            "[role='option']",
            ".mat-mdc-menu-item",
            ".mat-menu-item",
            "button[role='menuitem']",
            "li[role='menuitem']",
        ]

        option_clicked = False
        for menu_sel in menu_selectors:
            try:
                opts = page.locator(menu_sel).all()
                for opt in opts:
                    option_text = (opt.evaluate("e => e.innerText") or "").strip()
                    if opt.is_visible() and _model_label_matches(option_text, target_clean):
                        opt.click(force=True)
                        option_clicked = True
                        logger.info("Successfully selected model: '%s'", model_name)
                        break
                if option_clicked:
                    break
            except Exception:
                continue

        if not option_clicked:
            logger.warning("Model option '%s' not found in dropdown.", model_name)
            page.keyboard.press("Escape")

        time.sleep(1)
        return option_clicked

    except TargetClosedError:
        logger.warning("Model selection aborted: page/target closed mid-dropdown interaction.")
        return False
    except Exception as exc:
        logger.error("Exception during model selection: %s", exc)
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False


def _is_clean_chat_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.netloc == "gemini.google.com" and parsed.path.rstrip("/") == "/app"


def _wait_for_clean_chat_surface(
    page: Page, *, timeout_seconds: float = 15, stable_polls: int = 4
) -> bool:
    """Require a blank `/app` surface long enough to exclude late history hydration."""
    deadline = time.monotonic() + timeout_seconds
    stable = 0
    while time.monotonic() < deadline:
        try:
            input_box = find_input_box(page)
            input_text = (
                input_box.evaluate("el => el.innerText || el.value || ''") if input_box else ""
            )
            clean = (
                _is_clean_chat_url(page.url)
                and page.locator(RESPONSE_SELECTOR).count() == 0
                and not str(input_text or "").strip()
            )
            stable = stable + 1 if clean else 0
            if stable >= stable_polls:
                return True
        except Exception:
            stable = 0
        time.sleep(0.5)
    return False


def start_clean_gemini_chat(page: Page) -> None:
    """Navigate to Gemini and start a fresh chat session.

    Waits for interactive input box to ensure previous conversation
    history has loaded before checking session state.

    Args:
        page: Playwright page object.
    """
    logger.info("Navigating to Gemini...")
    if urlsplit(page.url).netloc != "gemini.google.com":
        try:
            page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:
            logger.warning("Navigation warning (continuing): %s", exc)

    # Wait only for the shell. A zero response count here is not proof of a clean chat:
    # saved history can hydrate after the input, so always request a new conversation.
    try:
        page.wait_for_selector("rich-textarea, div[contenteditable='true']", timeout=10000)
    except Exception:
        pass

    logger.info("Requesting a clean chat session...")
    new_chat_selectors = [
        "a[aria-label='New chat'][href='/app']",
        "a[href='/app']",
        "[aria-label='New chat']",
        "[aria-label='Start a new chat']",
        "a[href*='/app']",
        "div.new-chat-button",
        "button:has-text('New chat')",
    ]

    clicked = False
    for sel in new_chat_selectors:
        try:
            btn = page.locator(sel).first
            btn.click(force=True, timeout=3000)
            clicked = True
            logger.info("Successfully started new chat using selector: '%s'", sel)
            break
        except Exception:
            continue

    if not clicked:
        logger.info("Direct click failed. Injecting keyboard shortcut Control+Shift+O...")
        try:
            page.locator("body").first.click(timeout=1000)
            page.keyboard.press("Control+Shift+O")
            time.sleep(2)
        except Exception as exc:
            logger.warning("Keyboard shortcut failed: %s", exc)

    if not _wait_for_clean_chat_surface(page):
        raise RuntimeError(
            "Gemini clean chat did not stabilize; refusing to reuse historical responses"
        )
    time.sleep(1.5)
