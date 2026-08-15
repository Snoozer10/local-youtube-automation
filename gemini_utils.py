import os
import re
import sys
import time

# Unified response container selector
RESPONSE_SELECTOR = "model-response"


def find_input_box(page):
    """Locates the Gemini rich text input box using cascading selectors."""
    selectors = [
        "rich-textarea div[contenteditable='true']",
        "rich-textarea [contenteditable='true']",
        "div[contenteditable='true'][role='textbox']",
        "[role='textbox']",
        "rich-textarea"
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    return el
        except Exception:
            continue
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=1000)
            box = page.locator(sel).first
            if box and box.is_visible():
                return box
        except Exception:
            continue
    return None


def find_send_button(page):
    """
    Locates the Gemini send/submit button.
    Safely ignores buttons when they are in an active Stop/Cancel/Interrupt state.
    """
    selectors = [
        "button[aria-label*='Submit' i]",
        "button[aria-label*='Send message' i]",
        "button[aria-label*='Send' i]",
        "button.send-button",
        "div[class*='send-button-container'] button",
        "button[id*='send']",
        "button:has(svg)",
        "rich-textarea + div button"
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


def is_gemini_generating(page) -> bool:
    """Detects if Gemini is actively thinking, analyzing, or streaming."""
    stop_selectors = [
        "button[aria-label*='Stop' i]",
        "button[aria-label*='Cancel' i]",
        "button[aria-label*='Interrupt' i]",
        "button[aria-label*='وقف' i]",
        "button:has(svg path[d*='M6 6h12v12H6z'])",
        "button:has(rect)",
        "[data-test-id='stop-button']"
    ]
    for sel in stop_selectors:
        try:
            if page.locator(sel).first.is_visible():
                return True
        except Exception:
            pass

    # Check for thinking/analyzing spinners or status indicators
    try:
        if page.locator("mat-progress-spinner, .thinking-indicator, [aria-label*='Thinking' i]").first.is_visible():
            return True
    except Exception:
        pass

    return False


def wait_until_gemini_idle(page, timeout_seconds: int = 180) -> bool:
    """Ensures Gemini is completely idle before pasting or sending a new turn."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        if not is_gemini_generating(page):
            time.sleep(2)  # Extra buffer to let DOM settle
            if not is_gemini_generating(page):
                return True
        time.sleep(1)
    return False


def get_last_response(page) -> str:
    """Reads the text content of the last Gemini response element."""
    try:
        elements = page.locator(RESPONSE_SELECTOR)
        count = elements.count()
        if count > 0:
            last_el = elements.nth(count - 1)
            text = last_el.evaluate("el => el.innerText").strip()
            if text.startswith("Gemini said"):
                text = text[len("Gemini said"):].strip()
            return text
    except Exception as e:
        print(f"Error reading last response: {e}")
    return ""


def wait_for_gemini_response(page, initial_count: int = 0, min_length: int = 20, timeout_seconds: int = 180) -> str:
    """
    Waits for Gemini to start streaming and monitors text stability until complete.
    Compatible with all existing scripts.
    """
    start_time = time.time()
    
    # 1. Wait for response turn to start
    new_response_started = False
    while time.time() - start_time < 35:
        if is_gemini_generating(page) or page.locator(RESPONSE_SELECTOR).count() > initial_count:
            new_response_started = True
            break
        time.sleep(0.5)
        
    if not new_response_started:
        print(f"  [WARN] Response turn did not start within 35s. Reading last available DOM state...")
        return get_last_response(page)

    # 2. Monitor stream growth and stability
    time.sleep(2)  # Buffer to skip past initial "Analyzing" / "Thinking" transient state
    last_text = ""
    stable_count = 0
    
    while time.time() - start_time < timeout_seconds:
        still_thinking = is_gemini_generating(page)
        
        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > 0:
                last_el = page.locator(RESPONSE_SELECTOR).nth(current_count - 1)
                try:
                    current_text = last_el.evaluate("el => el.innerText", timeout=4000).strip()
                except Exception:
                    current_text = ""
                
                if current_text.startswith("Gemini said"):
                    current_text = current_text[len("Gemini said"):].strip()
                
                # Transient analysis placeholders
                if current_text.lower() in ["analyzing", "thinking", "thinking...", "visualizing the scenes"]:
                    still_thinking = True

                # Must not be thinking AND must exceed minimum length
                if not still_thinking and len(current_text) >= min_length:
                    if current_text == last_text:
                        stable_count += 1
                        # 4 stable samples (~4-5 seconds of text stability)
                        if stable_count >= 4:
                            return current_text
                    else:
                        last_text = current_text
                        stable_count = 0
                else:
                    last_text = current_text
                    stable_count = 0
        except Exception:
            pass
            
        time.sleep(1.2)
        
    print(f"  [WARN] Gemini response wait reached timeout ({timeout_seconds}s).")
    return get_last_response(page)


def select_gemini_model(page, model_name: str = "Pro") -> bool:
    """Selects a specific Gemini model from the dropdown with robust word-boundary matching."""
    print(f"[SYSTEM] Attempting to select Gemini model: '{model_name}'")
    
    btn_candidates = [
        page.locator("button:has-text('Flash'), button:has-text('Pro'), button:has-text('Lite')").first,
        page.locator("button[aria-label*='model' i], button[aria-label*='mode' i]").first,
        page.locator("rich-textarea ~ * button").first
    ]
    
    model_btn = None
    for loc in btn_candidates:
        try:
            if loc.is_visible() and loc.is_enabled():
                model_btn = loc
                break
        except Exception:
            continue

    if not model_btn:
        print("[WARNING] Could not locate Gemini model selector button in UI.")
        return False

    try:
        active_text = model_btn.inner_text().strip().lower() if model_btn.inner_text() else ""
        target_clean = model_name.strip().lower()

        # Check if already active using exact word boundaries
        is_active = bool(re.search(rf"\b{re.escape(target_clean)}\b", active_text))
        if target_clean == "flash" and "lite" in active_text:
            is_active = False

        if is_active:
            print(f"[SYSTEM] Model '{model_name}' is already active.")
            return True

        print(f"[SYSTEM] Switching Gemini model to '{model_name}'...")
        model_btn.click(force=True)
        time.sleep(1.5)

        pattern = re.compile(rf"(\b{re.escape(target_clean)}\b|\d+\.\d+\s*{re.escape(target_clean)})", re.IGNORECASE)
        option_clicked = False

        try:
            opts = page.get_by_text(pattern).all()
            for opt in opts:
                if opt.is_visible():
                    opt.click(force=True)
                    option_clicked = True
                    print(f"[SYSTEM] Successfully selected model: '{model_name}'")
                    break
        except Exception:
            pass

        if not option_clicked:
            try:
                opts = page.locator("div, button, [role='option'], [role='menuitem'], span").filter(has_text=pattern).all()
                for opt in reversed(opts):
                    if opt.is_visible():
                        opt.click(force=True)
                        option_clicked = True
                        print(f"[SYSTEM] Successfully selected model: '{model_name}'")
                        break
            except Exception:
                pass

        if not option_clicked:
            print(f"[WARNING] Model option '{model_name}' not found in dropdown.")
            page.keyboard.press("Escape")

        time.sleep(1.5)
        return option_clicked

    except Exception as e:
        print(f"[ERROR] Exception during model selection: {e}")
        page.keyboard.press("Escape")
        return False


def start_clean_gemini_chat(page):
    """Navigates to Gemini and starts a fresh chat session."""
    print("Navigating to Gemini...")
    try:
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"Navigation warning (continuing): {e}")
    time.sleep(2)

    # If the page has 0 response cards, it is already a clean session
    if page.locator(RESPONSE_SELECTOR).count() == 0:
        return

    print("Requesting a clean chat session...")
    new_chat_selectors = [
        "[aria-label='New chat']",
        "[aria-label='Start a new chat']",
        "a[href='/app']",
        "a[href*='/app']",
        "div.new-chat-button",
        "button:has-text('New chat')"
    ]

    clicked = False
    for sel in new_chat_selectors:
        try:
            btn = page.locator(sel).first
            btn.click(force=True, timeout=3000)
            clicked = True
            print(f"Successfully started new chat using selector: '{sel}'")
            break
        except Exception:
            continue

    if not clicked:
        print("Direct click failed. Injecting keyboard shortcut Control+Shift+O...")
        try:
            page.locator("body").first.click(timeout=1000)
            page.keyboard.press("Control+Shift+O")
            time.sleep(2)
        except Exception as e:
            print(f"Warning: Keyboard shortcut failed: {e}")

    # Wait for response cards to clear
    clear_start = time.time()
    while time.time() - clear_start < 10:
        try:
            if page.locator(RESPONSE_SELECTOR).count() == 0:
                break
        except Exception:
            pass
        time.sleep(0.5)
    time.sleep(1.5)