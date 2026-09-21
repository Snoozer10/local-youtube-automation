"""Gemini Browser Automation Utilities.

This module provides high-level utilities for automating interactions with
Google Gemini via Playwright CDP. It handles session management, prompt
dispatching, response streaming, and model selection with robust
error recovery and adaptive polling.

All browser interactions use Chrome DevTools Protocol (CDP) over port 9222
with no external API dependencies.
"""

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


def is_gemini_generating(page: Page) -> bool:
    """Detect if Gemini is actively thinking, analyzing, or streaming.

    Uses a single browser-native evaluation to avoid CDP round-trip
    latency. Checks for stop buttons, spinners, and thinking indicators
    with robust visibility detection using checkVisibility() fallback.

    Args:
        page: Playwright page object connected to Gemini.

    Returns:
        True if Gemini is generating, False otherwise.
    """
    check_js = """
    () => {
        const isVisible = (el) => {
            if (!el) return false;
            if (typeof el.checkVisibility === 'function') return el.checkVisibility();
            return el.offsetParent !== null || el.getClientRects().length > 0;
        };
        const stopSelectors = [
            "button[aria-label*='Stop' i]",
            "button[aria-label*='Cancel' i]",
            "button[aria-label*='Interrupt' i]",
            "button[aria-label*='إيقاف' i]",
            "button[aria-label*='وقف' i]",
            "button[aria-label*='توقف' i]",
            "[data-test-id='stop-button']",
            "button[aria-label*='Stop generating' i]",
            "button:has(rect)"
        ];
        for (const sel of stopSelectors) {
            const el = document.querySelector(sel);
            if (isVisible(el)) return true;
        }
        const indicatorSelectors = [
            "mat-progress-spinner",
            "mat-progress-bar",
            ".thinking-indicator",
            "[aria-label='Thinking' i]",
            "[aria-label='Thinking...' i]",
            "[aria-label='يفكر' i]",
            "[aria-label='يفكر...' i]"
        ];
        for (const sel of indicatorSelectors) {
            const el = document.querySelector(sel);
            if (isVisible(el)) return true;
        }
        return false;
    }
    """
    try:
        return bool(page.evaluate(check_js))
    except Exception as exc:
        logger.debug("is_gemini_generating evaluation failed: %s", exc)
        return False


def wait_for_gemini_idle_native(page: Page, timeout_ms: int = 180_000) -> bool:
    """Wait for Gemini generation to complete using browser-native MutationObserver.

    Args:
        page: Playwright page object.
        timeout_ms: Maximum wait time in milliseconds.

    Returns:
        True if idle detected within timeout, False otherwise.
    """
    idle_js = """
    () => {
        const stopBtn = document.querySelector(
            "button[aria-label*='Stop' i], button[aria-label*='توقف' i], "
            "[data-test-id='stop-button'], button:has(rect)"
        );
        const spinner = document.querySelector(
            "mat-progress-spinner, mat-progress-bar, .thinking-indicator, [aria-label='Thinking' i], [aria-label='Thinking...' i], [aria-label='يفكر' i]"
        );
        return !stopBtn && !spinner;
    }
    """
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
            text = last_el.evaluate("el => el.innerText").strip()
            # Multi-lingual UI prefix stripping
            prefix_pattern = (
                r"^(?:Gemini\s+said|قال\s+Gemini|رد\s+Gemini|"
                r"Gemini\s+a\s+dit|Gemini\s+hat\s+gesagt)[:\s]*"
            )
            text = re.sub(prefix_pattern, "", text, flags=re.IGNORECASE).strip()
            return text
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
    timeout_seconds: int = 420,
) -> str:
    """Wait for Gemini to start streaming and monitor text stability until complete.

    Resilient against long deep-reasoning phases (up to 90s) and fast-fails on
    errors. Uses adaptive polling: 0.25s while waiting for generation to start,
    0.75s during active generation.

    Args:
        page: Playwright page object.
        initial_count: Number of response elements before prompt was sent.
        min_length: Minimum response length to consider valid.
        timeout_seconds: Maximum total wait time.

    Returns:
        Complete response text, or empty string on timeout/error.
    """
    start_time = time.time()

    # 1. Wait for response turn or thinking phase to start (allow up to 90s)
    new_response_started = False
    while time.time() - start_time < 90:
        if check_gemini_error_state(page):
            logger.error("Gemini displayed an error card / retry banner.")
            return ""

        if is_gemini_generating(page) or page.locator(RESPONSE_SELECTOR).count() > initial_count:
            new_response_started = True
            break
        time.sleep(0.25)  # Fast polling while waiting for generation to begin

    if not new_response_started:
        logger.error("Response turn did not start within 90s.")
        return ""

    # 2. Monitor stream growth and completion
    time.sleep(1.5)  # Buffer to allow initial render
    last_text = ""
    stable_count = 0

    while time.time() - start_time < timeout_seconds:
        if check_gemini_error_state(page):
            logger.error("Gemini encountered a generation error mid-stream.")
            return ""

        still_thinking = is_gemini_generating(page)

        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            # Guard against reading previous turns: only inspect if new response node exists
            if current_count > initial_count:
                last_el = page.locator(RESPONSE_SELECTOR).nth(current_count - 1)
                try:
                    current_text = last_el.evaluate("el => el.innerText", timeout=4000).strip()
                except Exception:
                    current_text = ""

                # Multi-lingual prefix cleanup
                prefix_pattern = (
                    r"^(?:Gemini\s+said|قال\s+Gemini|رد\s+Gemini|"
                    r"Gemini\s+a\s+dit|Gemini\s+hat\s+gesagt)[:\s]*"
                )
                current_text = re.sub(prefix_pattern, "", current_text, flags=re.IGNORECASE).strip()

                # Transient analysis placeholders
                if current_text.lower() in [
                    "analyzing",
                    "thinking",
                    "thinking...",
                    "visualizing the scenes",
                    "structuring the narrative",
                ]:
                    still_thinking = True

                # Must not be thinking, must be the new node, and must meet minimum length
                # Require 5 consecutive stable seconds for deep-reasoning models to avoid cutoffs
                if not still_thinking and len(current_text.strip()) >= min_length:
                    if current_text == last_text and current_text != "":
                        stable_count += 1
                        if stable_count >= 5:
                            return current_text
                    else:
                        last_text = current_text
                        stable_count = 1
                else:
                    last_text = current_text
                    stable_count = 0
            else:
                # If new response element hasn't mounted yet, keep waiting
                stable_count = 0
        except Exception:
            pass

        # Adaptive polling: faster when waiting for generation to start,
        # slower during active generation to reduce CPU
        if still_thinking:
            time.sleep(0.75)
        else:
            time.sleep(0.25)

    logger.error("Gemini response wait timed out after %ds.", timeout_seconds)
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
