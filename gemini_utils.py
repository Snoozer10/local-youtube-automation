import re
import time

# Unified response selector to prevent tracking mismatches
RESPONSE_SELECTOR = "model-response div.markdown"


def find_input_box(page):
    """Locates the Gemini text input box using cascading selectors."""
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
            count = loc.count()
            for i in range(count):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    return el
        except Exception:
            continue
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=1000)
            box = page.locator(sel).first
            if box:
                return box
        except Exception:
            continue
    return None


def find_send_button(page):
    """Locates the Gemini send/submit button using cascading selectors."""
    selectors = [
        "button[aria-label*='Submit' i]",
        "button[aria-label*='Send message' i]",
        "button[aria-label*='Send' i]",
        "button.send-button",
        "div[class*='send-button-container'] button",
        "button[id*='send']"
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
            for i in range(count - 1, -1, -1):
                el = loc.nth(i)
                if el.is_visible() and el.is_enabled():
                    return el
        except Exception:
            continue
    return None


def get_last_response(page):
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


def wait_for_gemini_response(page, initial_count, timeout_seconds=180):
    """Waits for Gemini response to complete using growth monitoring and send button state."""
    start_time = time.time()

    print(f"Waiting for response to start rendering (initial_count={initial_count})...")
    response_started = False
    while time.time() - start_time < 90:
        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > initial_count:
                last_text = page.locator(RESPONSE_SELECTOR).nth(current_count - 1).inner_text().strip()
                if last_text:
                    response_started = True
                    print(f"Response rendering started: current_count={current_count}, text length={len(last_text)}")
                    break
        except Exception:
            pass
        time.sleep(0.5)

    if not response_started:
        print(f"Warning: Timeout waiting for response text to start rendering. (initial_count was {initial_count}, current_count is {page.locator(RESPONSE_SELECTOR).count()})")
        return get_last_response(page)

    print("Waiting for response to complete (monitoring text growth and stability)...")
    last_length = 0
    stable_cycles = 0

    while time.time() - start_time < timeout_seconds:
        try:
            send_btn = find_send_button(page)
            btn_ready = send_btn and send_btn.is_visible() and send_btn.is_enabled()

            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > initial_count:
                current_text = page.locator(RESPONSE_SELECTOR).nth(current_count - 1).inner_text().strip()
                current_length = len(current_text)

                if current_length > 0 and current_length == last_length:
                    stable_cycles += 1
                else:
                    stable_cycles = 0

                last_length = current_length

            if (btn_ready and stable_cycles >= 2) or stable_cycles >= 5:
                break
        except Exception:
            pass
        time.sleep(1.5)

    last_val = get_last_response(page)

    if "something went wrong" in last_val.lower() or "try reloading" in last_val.lower():
        print("\n[WARNING] Gemini flagged the content or encountered an active network crash.")

    return last_val


def start_clean_gemini_chat(page):
    """Navigates to Gemini and starts a fresh chat session."""
    print("Navigating to Gemini...")
    try:
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"Navigation warning (continuing): {e}")
    time.sleep(3)

    print("Requesting a clean chat session...")
    new_chat_selectors = [
        "[aria-label='New chat']",
        "[aria-label='Start a new chat']",
        "a[href='/app']",
        "a[href*='/app']",
        "div.new-chat-button",
        "button:has-text('New chat')"
    ]

    clicked_new_chat = False
    for sel in new_chat_selectors:
        try:
            btn = page.locator(sel).first
            # Use force=True to click even if hidden inside a collapsed sidebar menu
            btn.click(force=True, timeout=3000)
            clicked_new_chat = True
            print(f"Successfully started new chat using selector: '{sel}'")
            break
        except Exception:
            continue

    if not clicked_new_chat:
        print("Direct click failed. Injecting keyboard shortcut Control+Shift+O for a clean chat...")
        try:
            page.locator("body").first.click(timeout=1000)
            page.keyboard.press("Control+Shift+O")
            time.sleep(2)
        except Exception as e:
            print(f"Warning: Keyboard shortcut call returned an exception: {e}")

    print("Waiting for chat session to initialize and clear...")
    clear_start = time.time()
    while time.time() - clear_start < 10:
        try:
            count = page.locator(RESPONSE_SELECTOR).count()
            if count == 0:
                break
        except Exception:
            pass
        time.sleep(0.5)

    time.sleep(2)


def select_gemini_model(page, model_name):
    """Selects a specific Gemini model from the dropdown."""
    print(f"[SYSTEM] Attempting to select Gemini model: {model_name}")
    trigger_selectors = [
        "button[aria-haspopup='menu']:has-text('Flash')",
        "button[aria-haspopup='menu']:has-text('Pro')",
        "button:has-text('Flash')",
        "button:has-text('Pro')",
        "button:has-text('Gemini')",
        "button[aria-label*='model' i]",
        "button[aria-label*='Model' i]",
    ]

    btn = None
    for sel in trigger_selectors:
        try:
            elements = page.locator(sel)
            for i in range(elements.count()):
                if elements.nth(i).is_visible():
                    btn = elements.nth(i)
                    break
            if btn:
                break
        except Exception:
            continue

    if not btn:
        print("[WARNING] Could not find Gemini model dropdown trigger button in UI.")
        return False

    try:
        current_text = btn.inner_text().strip() if btn.inner_text() else ""
        if model_name.lower() in current_text.lower():
            print(f"[SYSTEM] Model '{model_name}' is already active.")
            return True

        btn.click()
        time.sleep(1.5)

        opt = page.locator("[role='menuitem'], [role='option'], li").filter(has_text=re.compile(model_name, re.IGNORECASE)).first
        if not opt.is_visible():
            opt = page.locator(f'text="{model_name}"').filter(visible=True).last

        if opt.is_visible():
            opt.click()
            print(f"[SYSTEM] Successfully switched model to {model_name}")
            time.sleep(1.5)
            return True
        else:
            print(f"[WARNING] Model option '{model_name}' not found in dropdown menu.")
            return False
    except Exception as e:
        print(f"[ERROR] Exception while selecting model: {e}")
        return False
