import os
import re
import sys
import time
import glob
import subprocess
import ctypes
import random
import math
import json
import tempfile
import hashlib  # <-- NEW: Added for MD5 verification
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError # <-- NEW: Import TimeoutError safely
from utils import get_config_value, launch_browser_with_profile, rotate_profile_index, kill_cdp_chrome

# Selector constants for the standard Gemini Web App (matching automate_all.py)
RESPONSE_SELECTOR = "model-response div.markdown"

# Global tracker for human mouse emulation coordinates
current_mouse_pos = [100, 100]

# Windows API Constants for native clipboard manipulation using ctypes
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Declare types to support 64-bit Windows memory pointer structures
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p

kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p

kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_bool

user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p

user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClipboardData.restype = ctypes.c_void_p

def set_clipboard_text(text):
    """Sets Unicode text directly to the Windows system clipboard using native ctypes with retries."""
    opened = False
    for i in range(10):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.1)
    if not opened:
        return False
    try:
        user32.EmptyClipboard()
        encoded_text = text.encode('utf-16le') + b'\x00\x00'
        h_global_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded_text))
        if not h_global_mem:
            return False
        p_global_mem = kernel32.GlobalLock(h_global_mem)
        if not p_global_mem:
            return False
        ctypes.memmove(p_global_mem, encoded_text, len(encoded_text))
        kernel32.GlobalUnlock(h_global_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_global_mem)
    finally:
        user32.CloseClipboard()
    return True

# Preset Configuration File Parser
def read_voice_options():
    preset_path = "voice_option_notes.txt"
    options = {
        "model": "gemini-2.5-pro-preview-tts",
        "temperature": "1.1",
        "voice": "Achird"
    }
    if os.path.exists(preset_path):
        try:
            with open(preset_path, "r", encoding="utf-8") as f:
                for line in f:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        key = key.strip().lower()
                        val = val.strip()
                        if key in options:
                            options[key] = val
            print(f"Loaded voice configurations from '{preset_path}': {options}")
        except Exception as e:
            print(f"Warning: Could not parse preset file ({e}). Using default settings.")
    else:
        # Create a default preset file if missing
        try:
            with open(preset_path, "w", encoding="utf-8") as f:
                f.write("Model: gemini-2.5-pro-preview-tts\n")
                f.write("Temperature: 1.1\n")
                f.write("Voice: Achird\n")
            print(f"Created default preset file at '{preset_path}'")
        except Exception as e:
            print(f"Warning: Could not create default preset file ({e})")
    return options

# Human-like Mouse Emulation functions
def simulate_human_mouse_move(page, target_locator, steps=25):
    """Moves the mouse from current position to target element using organic Bezier curves."""
    global current_mouse_pos
    try:
        box = target_locator.bounding_box()
        if not box:
            return
        
        # Target center with small organic randomized offsets
        target_x = box['x'] + box['width'] / 2 + random.uniform(-box['width']*0.08, box['width']*0.08)
        target_y = box['y'] + box['height'] / 2 + random.uniform(-box['height']*0.08, box['height']*0.08)
    except Exception:
        return

    start_x, start_y = current_mouse_pos
    
    # Generate random control coordinates for Bezier curve path calculation
    ctrl_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.8) + random.uniform(-60, 60)
    ctrl_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.8) + random.uniform(-60, 60)
    
    for i in range(steps + 1):
        t = i / steps
        # Quadratic Bezier Curve Formula
        x = (1-t)**2 * start_x + 2*(1-t)*t * ctrl_x + t**2 * target_x
        y = (1-t)**2 * start_y + 2*(1-t)*t * ctrl_y + t**2 * target_y
        
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.004, 0.012))
        
    current_mouse_pos = [target_x, target_y]
    time.sleep(random.uniform(0.12, 0.28)) # Realistic hover pause

def human_click(page, target_locator):
    """Performs an organic click containing scrolling, path curves, and down/up click pauses."""
    try:
        target_locator.scroll_into_view_if_needed()
    except Exception:
        pass
    
    box = None
    try:
        box = target_locator.bounding_box()
    except Exception:
        pass
        
    if not box:
        try:
            target_locator.click(timeout=3000)
        except Exception:
            pass
        return
        
    try:
        simulate_human_mouse_move(page, target_locator)
        page.mouse.down()
        time.sleep(random.uniform(0.06, 0.14)) # Human finger-press delay
        page.mouse.up()
        time.sleep(random.uniform(0.1, 0.22))
    except Exception:
        try:
            target_locator.click(timeout=3000)
        except Exception:
            pass

def human_hover_and_click(page, locator):
    """Simulates organic mouse movement, hovers, pauses, then clicks the element."""
    try:
        locator.scroll_into_view_if_needed()
        # Moves cursor to the element using your Bezier curve emulator
        simulate_human_mouse_move(page, locator)
        time.sleep(random.uniform(0.4, 0.9))  # Human-like hover/decision pause
        
        # Emulate physical click sequence
        page.mouse.down()
        time.sleep(random.uniform(0.08, 0.15))
        page.mouse.up()
        time.sleep(random.uniform(0.2, 0.4))
        return True
    except Exception:
        try:
            locator.click(timeout=3000)
            return True
        except Exception:
            return False

def humanize_text_input(page, textbox, text):
    """Clicks, inputs the text, and triggers native event listeners with micro-edits."""
    try:
        textbox.click()
        textbox.fill(text)
        time.sleep(random.uniform(1.2, 2.5))  # Mimic human proofreading delay
        
        # Emulate a single backspace change to trigger natural input events
        page.keyboard.press("End")
        time.sleep(0.1)
        page.keyboard.type(" ")
        time.sleep(random.uniform(0.1, 0.3))
        page.keyboard.press("Backspace")
        time.sleep(random.uniform(0.4, 0.8))
        return True
    except Exception as e:
        print(f"Warning: Humanized fill failed. Falling back to native: {e}")
        try:
            textbox.fill(text)
            return True
        except Exception:
            return False

# Text Sanitization helper (Clean up programmatic loop tokens only)
def sanitize_script_text(text):
    """Cleans up raw programmatic control triggers, leaving the complete Gemini output completely intact."""
    # Remove markdown triple-backtick blocks
    text = re.sub(r"```[a-zA-Z0-9_-]*\n(.*?)\n```", r"\1", text, flags=re.DOTALL)
    text = text.replace("```", "")

    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        trimmed = line.strip()
        # Filter out control loop tokens on their own line
        if trimmed.upper() in ["COMPLETE", "FINISHED", "READY", "PROCEED"]:
            continue
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines).strip()

# Directory Scanning Helper
def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        print(f"Error: Directory '{runs_path}' does not exist.")
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
    if not folders:
        return None
    latest_folder = max(folders, key=os.path.getmtime)
    return latest_folder

# Helper selectors for Gemini inputs (gemini.google.com/app)
def find_input_box(page):
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

# Helper to clear chat and start a clean session
def start_clean_gemini_chat(page):
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
            if btn.is_visible() and btn.is_enabled():
                human_click(page, btn)
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

# Dynamic Text Stabilization Monitor (Direct DOM Extraction for Gemini Web App)
def wait_for_gemini_response(page, step_name="AI Response", max_wait_sec=120):
    print(f"Waiting for {step_name} to generate and stabilize...")
    last_length = 0
    stable_cycles = 0
    start_time = time.time()
    
    initial_count = page.locator(RESPONSE_SELECTOR).count()
    
    new_response_started = False
    while time.time() - start_time < 30:
        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > initial_count:
                new_response_started = True
                break
        except Exception:
            pass
        time.sleep(0.5)
        
    if not new_response_started:
        print(f"Warning: Timeout waiting for response to start rendering for {step_name}.")
        return get_last_response(page)
        
    while time.time() - start_time < max_wait_sec:
        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > 0:
                last_el = page.locator(RESPONSE_SELECTOR).nth(current_count - 1)
                current_text = last_el.evaluate("el => el.innerText").strip()
                if current_text.startswith("Gemini said"):
                    current_text = current_text[len("Gemini said"):].strip()
                    
                if "something went wrong" in current_text.lower() or "try reloading" in current_text.lower():
                    print("Warning: Gemini Web App reported an execution block or crash. Retrying...")
                    time.sleep(2)
                    continue
                    
                if current_text and len(current_text) == last_length:
                    stable_cycles += 1
                else:
                    stable_cycles = 0
                    last_length = len(current_text)
                
                if current_text and stable_cycles >= 3:
                    return current_text
        except Exception:
            pass
        time.sleep(0.5)
        
    return get_last_response(page)

def get_chrome_path():
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            return path
    print("Error: Google Chrome could not be found.")
    sys.exit(1)

def reapply_speech_settings(page, options):
    """Re-applies preset voice model settings from voice_option_notes.txt directly into the Speech Playground."""
    temp_val = options.get("temperature", "1.1")
    voice_name = options.get("voice", "Achird")
    
    print(f"Re-applying Speech Playground settings (Temperature {temp_val}, speaker {voice_name})...")
    
    # 1. Bypass Splash screen
    splash_selector = "text='Turn text into natural-sounding speech...'"
    try:
        if page.locator(splash_selector).is_visible():
            human_click(page, page.locator(splash_selector).first)
            time.sleep(2)
    except Exception:
        pass

    # 2. Text tab
    try:
        text_btn = page.locator("button:has-text('Text')").first
        if text_btn.is_visible():
            human_click(page, text_btn)
            time.sleep(1.2)
    except Exception as e:
        print(f"Text mode option check: {e}")

    # 3. Model settings sidebar toggle
    try:
        settings_btn = page.locator("ms-run-settings button[aria-label*='Model settings']").first
        if settings_btn.is_visible():
            human_click(page, settings_btn)
            time.sleep(1.2)
    except Exception as e:
        print(f"Model settings dropdown click: {e}")

    # 4. Temperature input setting
    try:
        temp_input = None
        temp_selectors = [
            "ms-run-settings input[type='number']", 
            "ms-run-settings input.slider-number-input",
            "input[type='number']", 
            "ms-run-settings input"
        ]
        for sel in temp_selectors:
            loc = page.locator(sel).first
            if loc.is_visible():
                temp_input = loc
                break
                
        if temp_input:
            human_click(page, temp_input)
            page.keyboard.press("Control+a")
            time.sleep(0.1)
            page.keyboard.press("Backspace")
            time.sleep(0.1)
            page.keyboard.type(temp_val)
            page.keyboard.press("Enter")
            print(f"Successfully set Temperature slider to: {temp_val}")
            time.sleep(1.2)
        else:
            print("Warning: Could not find Temperature input box.")
    except Exception as e:
        print(f"Could not adjust temperature slider input: {e}")

    # 5. Speaker configuration (Voice Selection)
    try:
        speaker_card = None
        card_selectors = [
            "ms-run-settings .active-voice-card",
            "ms-run-settings mat-card",
            "ms-run-settings .voice-card",
            "ms-run-settings [aria-label*='Speaker' i]",
            "ms-run-settings :text('Speaker 1')"
        ]
        for sel in card_selectors:
            loc = page.locator(sel).first
            if loc.is_visible():
                speaker_card = loc
                break
                
        if speaker_card:
            human_click(page, speaker_card)
            time.sleep(2.0)
            
            # Select target voice from pop-up modal selection menu
            voice_option = page.locator(f"mat-dialog-container :text('{voice_name}'), mat-dialog-container button:has-text('{voice_name}'), :text('{voice_name}')").first
            if voice_option.is_visible():
                human_click(page, voice_option)
                print(f"Successfully assigned speaker to: {voice_name}")
                time.sleep(1.2)
                
                # Dismiss voice options selector modal safely
                close_btn = page.locator("mat-dialog-container button:has-text('Close'), mat-dialog-container button:has-text('OK'), mat-dialog-container button[aria-label*='Close' i]").first
                if close_btn.is_visible():
                    human_click(page, close_btn)
                    time.sleep(1.2)
            else:
                print(f"Warning: Could not find voice '{voice_name}' in selection modal dialog.")
        else:
            print("Warning: Could not locate active speaker card button.")
    except Exception as e:
        print(f"Could not set speaker config: {e}")

    # 6. Collapse settings sidebar to make editing field fully open
    try:
        close_sidebar_btn = page.locator("button[aria-label*='Close run settings panel']").first
        if close_sidebar_btn.is_visible():
            human_click(page, close_sidebar_btn)
            print("Successfully closed sidebar settings panel.")
            time.sleep(1.2)
    except Exception as e:
        print(f"Could not collapse sidebar setting: {e}")

def get_file_md5(file_path):
    """Calculates the MD5 hash of a file to verify absolute uniqueness."""
    if not os.path.exists(file_path):
        return None
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Warning: Could not calculate MD5 for {file_path}: {e}")
        return None

def check_ai_studio_errors(page):
    error_selectors = [
        "text='Http response'",
        "text='status code'",
        "text='500 Internal Server Error'",  # <-- NEW
        "text='Quota Exceeded'",             # <-- NEW
        "text='quota exceeded'",             # <-- NEW (lowercase fallback)
        "mat-snack-bar-container",
        ".error-container"
    ]
    for sel in error_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                error_text = loc.inner_text().strip()
                print(f"[ALERT] Detected AI Studio Error Banner: '{error_text}'")
                # Attempt to dismiss the error banner safely
                dismiss_btn = page.locator("button:has-text('Close'), mat-snack-bar-container button").first
                if dismiss_btn.is_visible():
                    dismiss_btn.click()
                return True, error_text
        except Exception:
            continue
    return False, ""

def select_gemini_model(page, model_name):
    print(f"[SYSTEM] Attempting to select Gemini model: {model_name}")
    
    # 1. Find the model selector trigger button (now embedded in the chat bar)
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
        # 2. Check if desired model is already active
        current_text = btn.inner_text().strip() if btn.inner_text() else ""
        if model_name.lower() in current_text.lower():
            print(f"[SYSTEM] Model '{model_name}' is already active.")
            return True
            
        # 3. Click to open the menu
        btn.click()
        time.sleep(1.5) # Wait for Material UI menu animation to render
        
        # 4. Find the option in the dropdown using a flexible regex filter
        import re
        opt = page.locator("[role='menuitem'], [role='option'], li").filter(has_text=re.compile(model_name, re.IGNORECASE)).first
        
        if not opt.is_visible():
            # Fallback to any visible element containing the text
            opt = page.locator(f'text="{model_name}"').filter(visible=True).last
            
        if opt.is_visible():
            opt.click()
            print(f"[SYSTEM] Successfully switched model to {model_name}")
            time.sleep(1)
            return True
        else:
            print(f"[WARNING] Target model '{model_name}' not visible in dropdown menu.")
            
    except Exception as e:
        print(f"[WARNING] Model selection process failed: {e}")
        
    return False

def main():
    print("=============================================")
    print("Starting Voice Generation Automation (Security Upgraded)")
    print("=============================================")

    # Parse preset configuration choices (voice_option_notes.txt)
    voice_options = read_voice_options()
    target_model_name = voice_options.get("model", "gemini-2.5-pro-preview-tts")
    
    # NEW: Fetch target LLM model for Tab 2
    target_llm_model = get_config_value("VOICE_GENERATOR_MODEL", "Flash-Lite")

    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
    
    # 1. Establish potential file path options in order of preference
    refined_primary = os.path.join(latest_run, "refined_script.txt")
    refined_secondary = os.path.join(latest_run, "refine_script.txt")
    raw_final_output = os.path.join(latest_run, "final_output.txt")

    # 2. Sequential fallback file-check logic
    if os.path.exists(refined_primary):
        transcript_path = refined_primary
        print(f"[INPUT SOURCE] Active script file selected: '{transcript_path}'")
    elif os.path.exists(refined_secondary):
        transcript_path = refined_secondary
        print(f"[INPUT SOURCE] Active script file selected: '{transcript_path}'")
    elif os.path.exists(raw_final_output):
        transcript_path = raw_final_output
        print(f"[INPUT SOURCE] Refined script not found. Falling back to raw transcript: '{transcript_path}'")
    else:
        print(f"Error: No valid script file ('refined_script.txt' or 'final_output.txt') found in '{latest_run}'")
        print("Please run automate_all.py or refine_script.py first.")
        sys.exit(1)

    # NEW: Create a dedicated directory to store voice outputs cleanly
    voice_folder = os.path.join(latest_run, "voice_chapters")
    os.makedirs(voice_folder, exist_ok=True)
    print(f"[OUTPUT] Voice chapters will be saved inside: '{voice_folder}'")

    prompt_path = "TTS_PROMPT.txt"
    if not os.path.exists(prompt_path):
        print(f"Error: '{prompt_path}' not found in root folder.")
        sys.exit(1)

    with open(prompt_path, "r", encoding="utf-8") as f:
        tts_prompt = f.read().strip()

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_text = f.read().strip()

    print(f"Target Video Folder: {latest_run}")
    print("Verified input files. Connecting to Chrome debugging session...")

    # NEW: The Outer Recovery Loop
    while True:
        failover_triggered = False
        
        try:
            with sync_playwright() as p:
                # Issue 6/7: Multi-Profile & Multi-Browser Framework
                switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower()
                accounts_enabled = switch_enabled_str in ['true', '1', 'yes']
                current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                
                # NEW: Fetch browser type dynamically from config
                browser_type = get_config_value("BROWSER_TYPE", "chrome")
                
                try:
                    # Attempt to connect to an existing running session
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")
                    print(f"Successfully connected to existing {browser_type.capitalize()} session.")
                except Exception:
                    print(f"Debugging browser is closed or unreachable. Launching framework...")
                    # Call the unified launcher
                    if not launch_browser_with_profile(browser_type, current_profile_idx):
                        sys.exit(1)
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")

                context = browser.contexts[0]
                context.grant_permissions(["clipboard-read", "clipboard-write"])
                
                # Security Bypass: Inject anti-fingerprint script to delete webdriver property
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                # Create or fetch Tab 1: Speech Playground (AI Studio)
                print("\n--- PHASE 2 & 3: CONFIGURING TAB 1 (SPEECH PLAYGROUND) ---")
                tab1_speech = None
                for page in context.pages:
                    if "generate-speech" in page.url:
                        tab1_speech = page
                        break
                if not tab1_speech:
                    print("Opening Speech Generation Tab...")
                    tab1_speech = context.new_page()
                    # Navigate to the dynamic target model preset in the text file
                    speech_target_url = f"https://aistudio.google.com/generate-speech?model={target_model_name}"
                    tab1_speech.goto(speech_target_url, wait_until="domcontentloaded")
                    time.sleep(3)

                tab1_speech.bring_to_front()
                reapply_speech_settings(tab1_speech, voice_options)

                # Create or fetch Tab 2: Chat Orchestrator (Gemini Web App)
                print("\n--- PHASE 4: INITIALIZING TAB 2 (CHAT ORCHESTRATOR) ---")
                tab2_chat = None
                for page in context.pages:
                    if "gemini.google.com" in page.url:
                        tab2_chat = page
                        break
                if not tab2_chat:
                    print("Opening Gemini Web App Tab...")
                    tab2_chat = context.new_page()
                    tab2_chat.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                    time.sleep(3)

                tab2_chat.bring_to_front()
                start_clean_gemini_chat(tab2_chat)

                # NEW: Select the correct LLM Model before sending prompts
                select_gemini_model(tab2_chat, target_llm_model)

                # Target the chat input textarea box
                chat_box = find_input_box(tab2_chat)
                if not chat_box:
                    raise Exception("Could not find the Gemini Chat prompt input box. Make sure you are signed in.")

                # Paste custom guidelines
                print("Pasting guidelines payload (TTS_PROMPT) to Gemini...")
                chat_box.focus()
                human_click(tab2_chat, chat_box)
                set_clipboard_text(tts_prompt)
                tab2_chat.keyboard.press("Control+v")
                time.sleep(1.2)
                
                submit_btn = find_send_button(tab2_chat)
                if submit_btn:
                    human_click(tab2_chat, submit_btn)
                else:
                    tab2_chat.keyboard.press("Control+Enter")

                # Wait for model response to settle
                wait_for_gemini_response(tab2_chat, step_name="Rules Confirmation")

                # Upload final_output.txt script to Chat
                print("Submitting the raw transcript script to Gemini...")
                chat_box = find_input_box(tab2_chat)
                chat_box.focus()
                human_click(tab2_chat, chat_box)
                set_clipboard_text(f"This is My Transcript script:\n\n{transcript_text}")
                tab2_chat.keyboard.press("Control+v")
                time.sleep(1.2)
                
                submit_btn = find_send_button(tab2_chat)
                if submit_btn:
                    human_click(tab2_chat, submit_btn)
                else:
                    tab2_chat.keyboard.press("Control+Enter")

                # Wait for structural breakdown representation
                wait_for_gemini_response(tab2_chat, step_name="Breakdown Structure")

                # Send trigger to choose recommended archetype and kick-off synthesis loop
                print("Triggering run flow with 'Choose the recommended Vocal Archetype and proceed.' command...")
                chat_box = find_input_box(tab2_chat)
                chat_box.focus()
                human_click(tab2_chat, chat_box)
                set_clipboard_text("Choose the recommended Vocal Archetype and proceed.")
                tab2_chat.keyboard.press("Control+v")
                time.sleep(1.2)
                
                submit_btn = find_send_button(tab2_chat)
                if submit_btn:
                    human_click(tab2_chat, submit_btn)
                else:
                    tab2_chat.keyboard.press("Control+Enter")

                # Wait for the first chapter setup to generate
                wait_for_gemini_response(tab2_chat, step_name="Chapter 1 Text")

                # --- ALIGNMENT STEP: CONFIRM VOICE SELECTION TO TRIGGER SCRIPT GENERATION ---
                confirmation_text = get_last_response(tab2_chat)
                if "confirm" in confirmation_text.lower() or "ready with the first" in confirmation_text.lower():
                    print("Gemini is waiting for voice confirmation. Sending 'proceed' to trigger Section 1 script generation...")
                    chat_box = find_input_box(tab2_chat)
                    chat_box.focus()
                    human_click(tab2_chat, chat_box)
                    set_clipboard_text("proceed")
                    tab2_chat.keyboard.press("Control+v")
                    time.sleep(1.2)
                    
                    submit_btn = find_send_button(tab2_chat)
                    if submit_btn:
                        human_click(tab2_chat, submit_btn)
                    else:
                        tab2_chat.keyboard.press("Control+Enter")
                        
                    # Wait for the actual Section 1 script text to be generated on screen
                    wait_for_gemini_response(tab2_chat, step_name="Actual Section 1 Script Text")

                # Checkpoint loading
                checkpoint_path = os.path.join(latest_run, "voice_checkpoint.json")
                completed_chapters = 0
                if os.path.exists(checkpoint_path):
                    try:
                        with open(checkpoint_path, "r", encoding="utf-8") as f:
                            checkpoint_data = json.load(f)
                            completed_chapters = checkpoint_data.get("completed_chapters", 0)
                            print(f"Found active voice checkpoint. Fast-forwarding chat history to resume at chapter {completed_chapters + 1}...")
                    except Exception as e:
                        print(f"Warning: Could not read voice checkpoint file ({e}). Starting from scratch.")
                        completed_chapters = 0

                # Fast-forward chat to match checkpoint by sending 'proceed' exactly completed_chapters times
                if completed_chapters > 0:
                    print(f"Fast-forwarding chat by sending 'proceed' {completed_chapters} times...")
                    for ff_idx in range(completed_chapters):
                        print(f"  Fast-forwarding step {ff_idx + 1} of {completed_chapters}...")
                        chat_box = find_input_box(tab2_chat)
                        human_click(tab2_chat, chat_box)
                        set_clipboard_text("proceed")
                        tab2_chat.keyboard.press("Control+v")
                        time.sleep(1.2)
                        submit_btn = find_send_button(tab2_chat)
                        if submit_btn:
                            human_click(tab2_chat, submit_btn)
                        else:
                            tab2_chat.keyboard.press("Control+Enter")
                        wait_for_gemini_response(tab2_chat, step_name=f"Fast-forward Chapter {ff_idx + 2}")
                    print("Fast-forward complete.")

                chapter_idx = completed_chapters + 1

                # Initialize attempt tracker on main function object
                main.attempt_count = 0

                # Track chapters generated since the last clean page reload
                chapters_since_reload = 0

                print("\n--- PHASE 5: RUNNING DYNAMIC SYNTHESIS LOOP ---")
                while True:
                    print(f"\nProcessing Turn Chapter/Section {chapter_idx}...")

                    # --- PROACTIVE SESSION REFRESH (Every 8 chapters) ---
                    if chapters_since_reload >= 8:
                        print(f"\n[MAINTENANCE] Proactively refreshing Speech Playground session...")
                        tab1_speech.bring_to_front()
                        
                        # Focus Tab 1 first
                        try:
                            tab1_speech.locator("body").first.click(timeout=1000)
                            time.sleep(0.5)
                        except Exception:
                            pass
                            
                        tab1_speech.reload(wait_until="domcontentloaded")
                        time.sleep(5)
                        reapply_speech_settings(tab1_speech, voice_options)
                        chapters_since_reload = 0  # Reset the counter

                    tab2_chat.bring_to_front()

                    # Direct DOM Extraction: Grab the final text block programmatically (already generated on screen)
                    raw_content = get_last_response(tab2_chat)
                    if not raw_content or len(raw_content.strip()) < 10:
                        print(f"Warning: Current response for Chapter {chapter_idx} is empty or not loaded yet. Waiting...")
                        time.sleep(3)
                        continue

                    # Check if the raw response has no Arabic characters at all (indicates final English completion text)
                    has_arabic = bool(re.search(r"[\u0600-\u06FF]", raw_content))
                    if not has_arabic:
                        print("Detecting final English completion response. Voice Generation Complete!")
                        checkpoint_path = os.path.join(latest_run, "voice_checkpoint.json")
                        if os.path.exists(checkpoint_path):
                            try:
                                os.remove(checkpoint_path)
                                print("Voice checkpoint file cleared successfully.")
                            except Exception as ec:
                                print(f"Warning: Could not delete voice checkpoint file ({ec})")
                        break

                    # Cleans up markdown code ticks and loop control keywords only
                    markdown_content = sanitize_script_text(raw_content)
                    if not markdown_content:
                        print("Warning: Sanitizer removed entire text contents. Retrying...")
                        time.sleep(3)
                        continue

                    print(f"Successfully captured Chapter {chapter_idx} text (length: {len(markdown_content)}).")

                    # --- ERROR RECOVERY RELOAD ---
                    if getattr(main, 'attempt_count', 0) > 0:
                        print(f"[RECOVER] Reloading Speech Playground Tab to refresh credentials...")
                        tab1_speech.bring_to_front()
                        
                        # Focus Tab 1 first
                        try:
                            tab1_speech.locator("body").first.click(timeout=1000)
                            time.sleep(0.5)
                        except Exception:
                            pass
                            
                        tab1_speech.reload(wait_until="domcontentloaded")
                        time.sleep(5)
                        reapply_speech_settings(tab1_speech, voice_options)
                        chapters_since_reload = 0  # Reset maintenance counter
                    
                    # --- TRANSITION TO TAB 1 ---
                    tab1_speech.bring_to_front()
                    
                    # Globally focus Tab 1 by clicking a neutral, safe area of the page body first
                    try:
                        tab1_speech.locator("body").first.click(timeout=1000)
                        time.sleep(0.5)
                    except Exception:
                        pass

                    # Locate Speech Playground input area
                    speech_input = tab1_speech.locator("textarea[aria-label='Enter a prompt']").first
                    if not speech_input.is_visible():
                        print("Speech Playground input box was hidden. Retrying context...")
                        time.sleep(2)
                        continue

                    # Native, bulletproof text entry (Bypasses OS clipboard entirely)
                    print("Entering new chapter text using humanized entry...")
                    humanize_text_input(tab1_speech, speech_input, markdown_content)

                    # --- DYNAMIC COOLDOWN (Scales based on text length to respect quotas) ---
                    text_length = len(markdown_content)
                    base_delay = 3.0
                    
                    # Longer text blocks require more backend processing time; scale the delay
                    scaled_delay = (text_length / 500.0) * random.uniform(1.2, 2.8)
                    cooldown_time = base_delay + scaled_delay
                    
                    print(f"Applying dynamic safety cooldown of {cooldown_time:.2f}s for {text_length} characters...")
                    time.sleep(cooldown_time)

                    # --- SYNTHESIS EXECUTION ---
                    # Click Run inside Speech Playground
                    run_btn = tab1_speech.locator("button[type='submit'], button:has-text('Run')").first
                    try:
                        human_hover_and_click(tab1_speech, run_btn)
                    except Exception:
                        tab1_speech.keyboard.press("Control+Enter")

                    # Dynamic completion wait
                    print("Chapter audio synthesis started. Waiting dynamically for rendering to finish...")
                    started_rendering = False
                    try:
                        # Wait up to 8 seconds for the 'Stop' button to verify rendering has begun
                        tab1_speech.wait_for_selector("button:has-text('Stop')", timeout=8000)
                        print("Synthesis processing started...")
                        started_rendering = True
                    except Exception:
                        # If 'Stop' didn't show up, check if a 403/500 modal blocked it
                        has_error, err_msg = check_ai_studio_errors(tab1_speech)
                        if has_error:
                            print(f"Synthesis failed to start due to AI Studio error: {err_msg}")
                        else:
                            print("Warning: Synthesis 'Stop' button did not appear within 8 seconds.")

                    if not started_rendering:
                        # Force a reload, increase attempt counter, and repeat the loop for the same chapter
                        print("[RETRY TRIGGER] Synthesis failed to start. Forcing page reload to clear session...")
                        target_dest = os.path.join(voice_folder, f"Chapter_{chapter_idx}.wav")  # <-- CHANGED
                        if os.path.exists(target_dest):
                            try:
                                os.remove(target_dest)
                            except Exception:
                                pass
                        main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                        continue

                    try:
                        tab1_speech.wait_for_selector("button:has-text('Run')", timeout=300000)
                        print("Synthesis complete!")
                    except Exception as e:
                        print(f"Warning: Timeout or error waiting for synthesis to complete: {e}")

                    # --- THE FIX: WAIT FOR AUDIO BLOB BINDING ---
                    # Pauses briefly to let the browser's JS thread bind the new audio to the download element.
                    print("Synthesis complete! Pausing briefly to allow audio blob binding...")
                    time.sleep(2.0)

                    # Intercept download
                    target_dest = os.path.join(voice_folder, f"Chapter_{chapter_idx}.wav")  # <-- CHANGED
                    download_btn = tab1_speech.locator("button[aria-label*='Download' i], button:has-text('Download')").first
                    try:
                        download_btn.wait_for(state="visible", timeout=10000)
                    except Exception:
                        pass
                    if download_btn.is_visible():
                        download_success = False
                        try:
                            # Edge Case A: Wrap in try/except with a strict timeout so it doesn't hang if UI fails silently
                            with tab1_speech.expect_download(timeout=15000) as download_info:
                                human_hover_and_click(tab1_speech, download_btn)
                            
                            download = download_info.value
                            
                            # Edge Case B: save_as natively blocks until the file is completely written to disk
                            download.save_as(target_dest)
                            print(f"File downloaded and saved to: {target_dest}")
                            download_success = True

                        except PlaywrightTimeoutError:
                            print("\n[TIMEOUT] Playwright timed out waiting for the download event to trigger. Possible silent 500 error.")
                        except Exception as e:
                            print(f"\n[ERROR] Error downloading or saving audio file: {e}")

                        if download_success:
                            # Edge Case C: MD5 Duplicate Verification (Only if chapter > 1)
                            is_duplicate = False
                            if chapter_idx > 1:
                                previous_dest = os.path.join(voice_folder, f"Chapter_{chapter_idx - 1}.wav")  # <-- CHANGED
                                if os.path.exists(previous_dest):
                                    current_md5 = get_file_md5(target_dest)
                                    previous_md5 = get_file_md5(previous_dest)
                                    
                                    if current_md5 and previous_md5 and current_md5 == previous_md5:
                                        is_duplicate = True
                                        print(f"\n[ALERT] MD5 Hash Match! Google served stale audio (Duplicate of Chapter {chapter_idx - 1}).")
                                        
                            if is_duplicate:
                                # Clean up the bad file, increment attempts, and restart loop to trigger [RECOVER] block
                                try:
                                    os.remove(target_dest)
                                except Exception:
                                    pass
                                main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                                continue

                            # If successful and unique, save progress checkpoint
                            try:
                                checkpoint_path = os.path.join(latest_run, "voice_checkpoint.json")
                                checkpoint_data = {"completed_chapters": chapter_idx}
                                with open(checkpoint_path, "w", encoding="utf-8") as f:
                                    json.dump(checkpoint_data, f, ensure_ascii=False, indent=4)
                                print(f"Progress checkpoint saved for chapter {chapter_idx}.")
                            except Exception as ec:
                                print(f"Warning: Failed to save progress checkpoint ({ec})")
                        else:
                            # If download_success is False (Timeout or other error), force retry
                            main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                            continue
                    else:
                        print("\n[WARNING] Download button not found on screen.")
                        main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                        continue

                    # Switch back to Tab 2 to request next turn
                    tab2_chat.bring_to_front()

                    # Every 5 chapters, trigger a soft UI interaction to reset idle timers
                    if chapter_idx % 5 == 0:
                        print("Sending a heartbeat ping to prevent Gemini session timeout...")
                        tab2_chat.bring_to_front()
                        try:
                            chat_box = find_input_box(tab2_chat)
                            if chat_box:
                                human_click(tab2_chat, chat_box)
                            time.sleep(1)
                        except Exception as eh:
                            print(f"Warning: Heartbeat ping failed ({eh})")

                    # --- VERIFICATION & RETRY CHECK ---
                    target_dest = os.path.join(voice_folder, f"Chapter_{chapter_idx}.wav")  # <-- CHANGED
                    
                    if os.path.exists(target_dest) and os.path.getsize(target_dest) > 100:
                        print(f"[SUCCESS] Chapter {chapter_idx} was successfully generated and saved.")
                        
                        # Increment successful generation counter
                        chapters_since_reload += 1
                        
                        # Reset attempt tracker for the next chapter
                        attempt_count = 0 
                        main.attempt_count = 0
                        
                        # Switch back to Tab 2 to request next turn
                        tab2_chat.bring_to_front()
                        
                        # Send proceed trigger to Gemini Chat
                        print("Requesting next chapter generation with 'proceed' command...")
                        chat_box = find_input_box(tab2_chat)
                        chat_box.focus()
                        human_click(tab2_chat, chat_box)
                        set_clipboard_text("proceed")
                        tab2_chat.keyboard.press("Control+v")
                        time.sleep(1.2)
                        
                        submit_btn = find_send_button(tab2_chat)
                        if submit_btn:
                            human_click(tab2_chat, submit_btn)
                        else:
                            tab2_chat.keyboard.press("Control+Enter")

                        # Wait for next block generation response to settle dynamically
                        wait_for_gemini_response(tab2_chat, step_name=f"Chapter {chapter_idx + 1} Text")
                        chapter_idx += 1
                    else:
                        attempt_count = getattr(main, 'attempt_count', 0) + 1
                        main.attempt_count = attempt_count
                        
                        retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))
                        
                        if attempt_count >= retry_limit:
                            if accounts_enabled:
                                print(f"\n[FAILOVER ALERT] Chapter {chapter_idx} failed {retry_limit} times. Triggering Account Rotation...")
                                rotate_profile_index()
                                kill_cdp_chrome()
                                failover_triggered = True
                                break # Break out of the synthesis loop
                            else:
                                print(f"\n[FATAL ERROR] Chapter {chapter_idx} failed to generate after {retry_limit} attempts. Pausing execution.")
                                sys.exit(1)
                            
                        print(f"\n[RETRY ALERT] Chapter {chapter_idx} audio was not generated correctly (Attempt {attempt_count}/{retry_limit}).")
                        print("Reloading Speech Playground and retrying the same chapter...")
                        
                        # --- EXPONENTIAL BACKOFF (Slows retries progressively on blocks) ---
                        attempt_count = getattr(main, 'attempt_count', 0)
                        
                        # Calculates delay based on attempt: 5.0s, 10.0s, 20.0s
                        backoff_delay = 5.0 * (2.0 ** (attempt_count - 1))
                        
                        print(f"Applying exponential backoff of {backoff_delay:.2f} seconds before retry attempt {attempt_count}...")
                        time.sleep(backoff_delay)
                        
                if failover_triggered:
                    break

        except Exception as e:
            print(f"[RECOVERY] Playwright context closed or browser crashed: {e}")

        # Catch the failover outside the inner while loop
        if failover_triggered:
            print("\n[SYSTEM] Reinitializing Playwright environment with new profile. Fast-forwarding...\n")
            main.attempt_count = 0 # Reset attempts for the new profile
            time.sleep(3)
            continue # Restart the 'while True' outer loop
        else:
            break # Exit loop


def read_prompts():
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            p1 = f.read().strip()
    except FileNotFoundError:
        print("Error: 'prompt.txt' not found. Please create it in VS Code.")
        sys.exit(1)

    try:
        with open("prompt_phase3.txt", "r", encoding="utf-8") as f:
            p3 = f.read().strip()
    except FileNotFoundError:
        print("Error: 'prompt_phase3.txt' not found. Please create it in VS Code.")
        sys.exit(1)
        
    return p1, p3

if __name__ == "__main__":
    main()
