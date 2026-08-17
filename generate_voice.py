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
import hashlib
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from utils import get_config_value, launch_browser_with_profile, rotate_profile_index, kill_cdp_chrome

# Selector constants for the standard Gemini Web App
RESPONSE_SELECTOR = "model-response div.markdown"
MANIFEST_FILE_NAME = "voice_generation_manifest.json"

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

kernel32.GlobalUnlock.argtypes = [ctypes.c_bool]
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
        "model": get_config_value("TTS_MODEL", "gemini-2.5-pro-preview-tts"),
        "temperature": get_config_value("TTS_TEMPERATURE", "1.1"),
        "voice": get_config_value("TTS_VOICE_NAME", "Achird")
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
        try:
            with open(preset_path, "w", encoding="utf-8") as f:
                f.write("Model: gemini-2.5-pro-preview-tts\n")
                f.write("Temperature: 1.1\n")
                f.write("Voice: Achird\n")
            print(f"Created default preset file at '{preset_path}'")
        except Exception as e:
            print(f"Warning: Could not create default preset file ({e})")
    return options

# Manifest Checkpoint Persistence Helpers
def get_manifest_path(latest_run):
    return os.path.join(latest_run, MANIFEST_FILE_NAME)

def load_or_create_manifest(latest_run, voice_options):
    manifest_path = get_manifest_path(latest_run)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[MANIFEST] Loaded active manifest checkpoint from '{manifest_path}'.")
                if "voice_config" not in data or not data["voice_config"]:
                    data["voice_config"] = voice_options
                return data
        except Exception as e:
            print(f"[MANIFEST WARNING] Could not parse manifest ({e}). Creating fresh manifest.")

    initial_manifest = {
        "voice_config": voice_options,
        "archetype_plan": "",
        "gemini_completed": False,
        "chapters": []
    }
    save_manifest(latest_run, initial_manifest)
    return initial_manifest

def save_manifest(latest_run, manifest_data):
    manifest_path = get_manifest_path(latest_run)
    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[MANIFEST WARNING] Failed to write manifest checkpoint: {e}")

def check_is_gemini_complete(manifest, transcript_text):
    """Determines if Gemini text generation is complete based on manifest state, chapter count, and text coverage."""
    if manifest.get("gemini_completed"):
        return True
        
    chapters = manifest.get("chapters", [])
    if not chapters:
        return False
        
    total_transcript_len = len(transcript_text.strip())
    total_manifest_text_len = sum(len(c.get("text", "")) for c in chapters)
    
    completion_ratio = (total_manifest_text_len / total_transcript_len) if total_transcript_len > 0 else 0
    
    last_chap_text = chapters[-1].get("text", "")
    ending_keywords = [
    "سلام",
    "لايك",
    "شير",
    "الختام",
    "الليفل اللي جاي",
    "اشترك",
    "متابعة",
    "FINISHED",
    "READY",
    "بس كدا يا عزيزي",
    "المصادر",
    "الحلقات اللي فاتت",
]
    has_ending_keywords = any(kw in last_chap_text for kw in ending_keywords)
    
    if len(chapters) >= 3 and (completion_ratio >= 0.80 or has_ending_keywords):
        return True
        
    return False

# Human-like Mouse Emulation functions
def simulate_human_mouse_move(page, target_locator, steps=25):
    """Moves the mouse from current position to target element using organic Bezier curves."""
    global current_mouse_pos
    try:
        box = target_locator.bounding_box()
        if not box:
            return
        
        target_x = box['x'] + box['width'] / 2 + random.uniform(-box['width']*0.08, box['width']*0.08)
        target_y = box['y'] + box['height'] / 2 + random.uniform(-box['height']*0.08, box['height']*0.08)
    except Exception:
        return

    start_x, start_y = current_mouse_pos
    
    ctrl_x = start_x + (target_x - start_x) * random.uniform(0.2, 0.8) + random.uniform(-60, 60)
    ctrl_y = start_y + (target_y - start_y) * random.uniform(0.2, 0.8) + random.uniform(-60, 60)
    
    for i in range(steps + 1):
        t = i / steps
        x = (1-t)**2 * start_x + 2*(1-t)*t * ctrl_x + t**2 * target_x
        y = (1-t)**2 * start_y + 2*(1-t)*t * ctrl_y + t**2 * target_y
        
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.004, 0.012))
        
    current_mouse_pos = [target_x, target_y]
    time.sleep(random.uniform(0.12, 0.28))

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
        time.sleep(random.uniform(0.06, 0.14))
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
        simulate_human_mouse_move(page, locator)
        time.sleep(random.uniform(0.4, 0.9))
        
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
        time.sleep(random.uniform(1.2, 2.5))
        
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

def sanitize_script_text(text):
    """Cleans up raw programmatic control triggers, leaving the complete Gemini output completely intact."""
    text = re.sub(r"```[a-zA-Z0-9_-]*\n(.*?)\n```", r"\1", text, flags=re.DOTALL)
    text = text.replace("```", "")

    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        trimmed = line.strip()
        if trimmed.upper() in ["COMPLETE", "FINISHED", "READY", "PROCEED"]:
            continue
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines).strip()

def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        print(f"Error: Directory '{runs_path}' does not exist.")
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
    if not folders:
        return None
    latest_folder = max(folders, key=os.path.getmtime)
    return latest_folder

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

def prepare_gemini_chat_session(page, manifest):
    """Resumes an ongoing chat session if present in DOM or sidebar, avoiding new chat generation when resuming."""
    try:
        last_resp = get_last_response(page)
        if last_resp and ("Option A" in last_resp or "Chapter" in last_resp or "Rules Confirmation" in last_resp):
            print("[CHAT RESUME] Active Gemini chat session detected in current tab. Continuing...")
            return True
    except Exception:
        pass

    try:
        sidebar_selectors = [
            "a[aria-label*='TTS Orchestrator']",
            "a[aria-label*='Al-Daheeh']",
            "a[aria-label*='Daheeh']",
            "a[aria-label*='Script Segmentation']",
            "nav a:has-text('TTS')",
            "nav a:has-text('Daheeh')",
        ]
        for sel in sidebar_selectors:
            recent_btn = page.locator(sel).first
            if recent_btn.is_visible():
                human_click(page, recent_btn)
                time.sleep(2)
                print(f"[CHAT RESUME] Successfully resumed existing chat session from sidebar ('{sel}').")
                return True
    except Exception as e:
        print(f"[CHAT RESUME] Sidebar check note: {e}")

    start_clean_gemini_chat(page)
    return False

def ensure_speech_playground_tab(context, target_tts_model="gemini-2.5-pro-preview-tts"):
    """Finds or opens the Google AI Studio Speech Playground tab and guarantees Playwright is on the correct UI."""
    tab1_speech = None
    
    # 1. Search existing tabs for generate-speech
    for page in context.pages:
        if "generate-speech" in page.url:
            tab1_speech = page
            break

    # 2. If not found, pick a non-Gemini page or open a new tab
    if not tab1_speech:
        for page in context.pages:
            if "gemini.google.com" not in page.url:
                tab1_speech = page
                break
        if not tab1_speech:
            print("Opening Google AI Studio Speech Playground Tab...")
            tab1_speech = context.new_page()

    tab1_speech.bring_to_front()
    
    clean_speech_url = f"https://aistudio.google.com/generate-speech?model={target_tts_model}"
    
    if "generate-speech" not in tab1_speech.url:
        print(f"Navigating to Speech Playground: {clean_speech_url}")
        tab1_speech.goto(clean_speech_url, wait_until="domcontentloaded")
        time.sleep(4)

    # 3. Guardrail: If AI Studio redirected away to /prompts/..., force direct navigation
    if "generate-speech" not in tab1_speech.url:
        print("[WARNING] AI Studio redirected away from Speech Playground. Retrying direct navigation...")
        tab1_speech.goto(clean_speech_url, wait_until="domcontentloaded")
        time.sleep(4)

    return tab1_speech

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

def select_gemini_model(page, model_name):
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
            time.sleep(1)
            return True
        else:
            print(f"[WARNING] Target model '{model_name}' not visible in dropdown menu.")
            
    except Exception as e:
        print(f"[WARNING] Model selection process failed: {e}")
        
    return False

def select_ai_studio_tts_model(page, target_model):
    """Selects the target TTS model (e.g., gemini-2.5-pro-preview-tts) inside Google AI Studio Speech Playground UI."""
    if not target_model:
        return True

    print(f"[SYSTEM] Verifying AI Studio TTS model: '{target_model}'...")
    
    # 1. Check if active model card in sidebar already matches target model
    try:
        model_card = page.locator("ms-run-settings .model-card, ms-run-settings mat-card, ms-run-settings div:has-text('TTS')").first
        if model_card.is_visible():
            card_text = model_card.inner_text().lower()
            short_target = target_model.lower().replace("-preview-tts", "").replace("gemini-", "").strip()
            if short_target in card_text or target_model.lower() in card_text:
                print(f"[SYSTEM] TTS Model '{target_model}' is already active in UI.")
                return True
    except Exception:
        pass

    print(f"[SYSTEM] Switching active TTS Model to '{target_model}' via Model selection modal...")
    
    # 2. Open Model selection modal dialog
    card_clicked = False
    card_selectors = [
        "ms-run-settings .model-card",
        "ms-run-settings mat-card",
        "ms-run-settings button:has-text('TTS')",
        "ms-run-settings [aria-label*='Model' i]",
        "ms-run-settings div:has-text('Gemini')"
    ]
    for sel in card_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                human_click(page, loc)
                card_clicked = True
                time.sleep(1.5)
                break
        except Exception:
            continue

    if not card_clicked:
        print("[WARNING] Could not locate AI Studio model card trigger in sidebar.")
        return False

    # 3. Filter and select target model option in the modal dialog
    try:
        audio_chip = page.locator("mat-dialog-container button:has-text('Audio'), [role='dialog'] button:has-text('Audio')").first
        if audio_chip.is_visible():
            human_click(page, audio_chip)
            time.sleep(0.8)

        # Flexible text matching for target TTS model
        short_target = target_model.lower().replace("-preview-tts", "").replace("gemini-", "").strip()
        
        target_option = None
        dialog_loc = page.locator("mat-dialog-container, [role='dialog']").first
        if dialog_loc.is_visible():
            options = dialog_loc.locator("div, button, mat-card").all()
            for opt in options:
                try:
                    txt = opt.inner_text().lower() if opt.is_visible() else ""
                    if "tts" in txt and (target_model.lower() in txt or short_target in txt):
                        target_option = opt
                        break
                except Exception:
                    continue

        if target_option and target_option.is_visible():
            human_click(page, target_option)
            print(f"[SYSTEM] Successfully assigned TTS Model to '{target_model}'")
            time.sleep(1.2)
            
            close_btn = page.locator("mat-dialog-container button[aria-label*='Close' i], mat-dialog-container button:has-text('Close')").first
            if close_btn.is_visible():
                human_click(page, close_btn)
                time.sleep(0.8)
            return True
        else:
            print(f"[WARNING] Target model option '{target_model}' not found in modal dialog. Escaping...")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"[WARNING] Model selection dialog error: {e}")
        page.keyboard.press("Escape")
        return False

def reapply_speech_settings(page, options):
    """Re-applies preset voice model settings from voice_option_notes.txt directly into the Speech Playground."""
    target_model = options.get("model", "gemini-2.5-pro-preview-tts")
    temp_val = options.get("temperature", "1.1")
    voice_name = options.get("voice", "Achird")
    
    print(f"Re-applying Speech Playground settings (Model {target_model}, Temperature {temp_val}, speaker {voice_name})...")
    
    # 0. Bypass Splash screen
    splash_selector = "text='Turn text into natural-sounding speech...'"
    try:
        if page.locator(splash_selector).is_visible():
            human_click(page, page.locator(splash_selector).first)
            time.sleep(2)
    except Exception:
        pass

    # 1. Ensure Model settings sidebar panel is expanded
    try:
        settings_btn = page.locator("ms-run-settings button[aria-label*='Model settings']").first
        if settings_btn.is_visible():
            human_click(page, settings_btn)
            time.sleep(1.2)
    except Exception as e:
        print(f"Model settings dropdown click: {e}")

    # 2. Select Target TTS Model
    select_ai_studio_tts_model(page, target_model)

    # 3. Ensure Text mode
    try:
        text_btn = page.locator("button:has-text('Text')").first
        if text_btn.is_visible():
            human_click(page, text_btn)
            time.sleep(1.2)
    except Exception as e:
        print(f"Text mode option check: {e}")

    # 4. Temperature slider adjustment
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
            
            voice_option = page.locator(f"mat-dialog-container :text('{voice_name}'), mat-dialog-container button:has-text('{voice_name}'), :text('{voice_name}')").first
            if voice_option.is_visible():
                human_click(page, voice_option)
                print(f"Successfully assigned speaker to: {voice_name}")
                time.sleep(1.2)
                
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
        "text='500 Internal Server Error'",
        "text='Quota Exceeded'",
        "text='quota exceeded'",
        "mat-snack-bar-container",
        ".error-container"
    ]
    for sel in error_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                error_text = loc.inner_text().strip()
                print(f"[ALERT] Detected AI Studio Error Banner: '{error_text}'")
                dismiss_btn = page.locator("button:has-text('Close'), mat-snack-bar-container button").first
                if dismiss_btn.is_visible():
                    dismiss_btn.click()
                return True, error_text
        except Exception:
            continue
    return False, ""

def main():
    print("=============================================")
    print("Starting Voice Generation Automation (Manifest Upgraded)")
    print("=============================================")

    # Parse initial preset configuration choices (voice_option_notes.txt)
    voice_options = read_voice_options()
    
    # Fetch target LLM model for Tab 2
    target_llm_model = get_config_value("VOICE_GENERATOR_MODEL", "Flash-Lite")

    latest_run = get_latest_run_folder()
    if not latest_run:
        print("Error: No active run folders found in 'youtube_runs/'.")
        sys.exit(1)
    
    # File selection logic for transcript input
    refined_primary = os.path.join(latest_run, "refined_script.txt")
    refined_secondary = os.path.join(latest_run, "refine_script.txt")
    raw_final_output = os.path.join(latest_run, "final_output.txt")

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
        sys.exit(1)

    # Dedicated folder for downloaded audio tracks
    voice_folder = os.path.join(latest_run, "voice_chapters")
    os.makedirs(voice_folder, exist_ok=True)
    print(f"[OUTPUT] Voice chapters will be saved inside: '{voice_folder}'")

    # Load or initialize the persistent manifest JSON
    manifest = load_or_create_manifest(latest_run, voice_options)
    voice_config = manifest.get("voice_config", voice_options)
    target_tts_model = voice_config.get("model", "gemini-2.5-pro-preview-tts")

    prompt_path = "TTS_PROMPT.txt"
    if not os.path.exists(prompt_path):
        print(f"Error: '{prompt_path}' not found in root folder.")
        sys.exit(1)

    with open(prompt_path, "r", encoding="utf-8") as f:
        tts_prompt = f.read().strip()

    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript_text = f.read().strip()

    # Smart auto-detection of Gemini completeness from manifest
    is_gemini_ready = check_is_gemini_complete(manifest, transcript_text)
    if is_gemini_ready and not manifest.get("gemini_completed"):
        manifest["gemini_completed"] = True
        save_manifest(latest_run, manifest)

    print(f"Target Video Folder: {latest_run}")
    print("Verified input files. Connecting to Browser debugging session...")

    # Main Playwright Outer Recovery Loop
    while True:
        failover_triggered = False
        
        try:
            with sync_playwright() as p:
                switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").strip().lower()
                accounts_enabled = switch_enabled_str in ('true', '1', 'yes')
                current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                browser_type = get_config_value("BROWSER_TYPE", "chrome")
                
                try:
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")
                    print(f"Successfully connected to existing {browser_type.capitalize()} session.")
                except Exception:
                    print(f"Debugging browser is closed or unreachable. Launching framework...")
                    if not launch_browser_with_profile(browser_type, current_profile_idx):
                        sys.exit(1)
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")

                context = browser.contexts[0]
                context.grant_permissions(["clipboard-read", "clipboard-write"])
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

                # =========================================================
                # PHASE 1: GEMINI APP SCRIPT ORCHESTRATION (ALL TEXT FIRST)
                # =========================================================
                if manifest.get("gemini_completed") and len(manifest.get("chapters", [])) > 0:
                    print("\n=========================================================")
                    print(f"[MANIFEST VERIFIED] Gemini script generation is 100% complete!")
                    print(f"Total stored chapters ready for synthesis: {len(manifest['chapters'])}")
                    print("=========================================================\n")
                else:
                    print("\n=========================================================")
                    print("--- PHASE 1: GENERATING ALL VOICE SCRIPT PROMPTS IN GEMINI ---")
                    print("=========================================================")

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
                    is_resumed = prepare_gemini_chat_session(tab2_chat, manifest)
                    select_gemini_model(tab2_chat, target_llm_model)

                    if not is_resumed:
                        # 1. Send TTS_PROMPT payload
                        chat_box = find_input_box(tab2_chat)
                        if not chat_box:
                            raise Exception("Could not find Gemini Chat prompt input box. Ensure you are signed in.")

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

                        wait_for_gemini_response(tab2_chat, step_name="Rules Confirmation")

                        # 2. Upload transcript script to Chat
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

                        # Capture breakdown structure & voice recommendation options
                        breakdown_response = wait_for_gemini_response(tab2_chat, step_name="Breakdown Structure & Voice Recommendations")
                        manifest["archetype_plan"] = breakdown_response
                        save_manifest(latest_run, manifest)
                        print("[MANIFEST] Saved voice recommendation options and breakdown plan.")

                        # 3. Trigger run flow with Option A selection
                        print("Triggering run flow with 'Choose the Option A and proceed.' command...")
                        chat_box = find_input_box(tab2_chat)
                        chat_box.focus()
                        human_click(tab2_chat, chat_box)
                        set_clipboard_text("Choose the Option A and proceed.")
                        tab2_chat.keyboard.press("Control+v")
                        time.sleep(1.2)
                        
                        submit_btn = find_send_button(tab2_chat)
                        if submit_btn:
                            human_click(tab2_chat, submit_btn)
                        else:
                            tab2_chat.keyboard.press("Control+Enter")

                        wait_for_gemini_response(tab2_chat, step_name="Chapter 1 Text Setup")

                        # 4. Confirmation check
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
                                
                            wait_for_gemini_response(tab2_chat, step_name="Actual Section 1 Script Text")

                    # Harvest remaining script chapters from Gemini
                    existing_chapters_count = len(manifest.get("chapters", []))
                    current_chap_idx = existing_chapters_count + 1
                    
                    while True:
                        print(f"\nHarvesting Chapter {current_chap_idx} script from Gemini...")
                        raw_content = get_last_response(tab2_chat)
                        
                        if not raw_content or len(raw_content.strip()) < 10:
                            print(f"Warning: Response for Chapter {current_chap_idx} empty or loading. Waiting...")
                            time.sleep(3)
                            continue

                        # Check completion signal
                        has_arabic = bool(re.search(r"[\u0600-\u06FF]", raw_content))
                        if not has_arabic or check_is_gemini_complete(manifest, transcript_text):
                            print("[COMPLETED] Detected final completion signal from Gemini.")
                            manifest["gemini_completed"] = True
                            save_manifest(latest_run, manifest)
                            print(f"[MANIFEST] Gemini script extraction complete. Total chapters saved: {len(manifest['chapters'])}")
                            break

                        markdown_content = sanitize_script_text(raw_content)
                        if not markdown_content:
                            print("Warning: Sanitizer output was empty. Retrying...")
                            time.sleep(3)
                            continue

                        audio_dest_path = os.path.join(voice_folder, f"Chapter_{current_chap_idx}.wav")
                        
                        existing_chap_entry = next((c for c in manifest["chapters"] if c["chapter_num"] == current_chap_idx), None)
                        if existing_chap_entry:
                            existing_chap_entry["text"] = markdown_content
                            existing_chap_entry["audio_file"] = audio_dest_path
                        else:
                            manifest["chapters"].append({
                                "chapter_num": current_chap_idx,
                                "text": markdown_content,
                                "audio_file": audio_dest_path,
                                "status": "PENDING"
                            })
                        
                        save_manifest(latest_run, manifest)
                        print(f"[MANIFEST] Saved Chapter {current_chap_idx} text ({len(markdown_content)} chars).")

                        # Re-verify completeness after saving this chapter
                        if check_is_gemini_complete(manifest, transcript_text):
                            print("[COMPLETED] Manifest verification confirmed transcript fully covered.")
                            manifest["gemini_completed"] = True
                            save_manifest(latest_run, manifest)
                            break

                        # Request next chapter from Gemini
                        print(f"Requesting Chapter {current_chap_idx + 1} script...")
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

                        wait_for_gemini_response(tab2_chat, step_name=f"Chapter {current_chap_idx + 1} Text")
                        current_chap_idx += 1

                # =========================================================
                # PHASE 2: GOOGLE AI STUDIO VOICE SYNTHESIS (ALL AUDIO SECOND)
                # =========================================================
                print("\n=========================================================")
                print("--- PHASE 2: GENERATING VOICE AUDIO TRACKS IN GOOGLE AI STUDIO ---")
                print("=========================================================")

                # Guarantee Playwright is focused on the genuine Speech Playground tab with target model URL
                tab1_speech = ensure_speech_playground_tab(context, target_tts_model)
                reapply_speech_settings(tab1_speech, voice_config)

                main.attempt_count = 0
                chapters_since_reload = 0

                # Iterate through all saved chapters from manifest
                for chap_entry in manifest.get("chapters", []):
                    chap_num = chap_entry["chapter_num"]
                    chap_text = chap_entry["text"]
                    target_dest = chap_entry["audio_file"]

                    # Check if audio file is already completed and verified
                    if chap_entry.get("status") == "COMPLETED" and os.path.exists(target_dest) and os.path.getsize(target_dest) > 100:
                        print(f"[SKIP] Chapter {chap_num} audio already generated and verified at '{target_dest}'.")
                        continue

                    while True:
                        print(f"\nSynthesizing Audio for Chapter {chap_num} (Attempt {getattr(main, 'attempt_count', 0) + 1})...")

                        # URL Guardrail check to prevent typing into standard AI Studio prompt tabs
                        if "generate-speech" not in tab1_speech.url:
                            print("[SAFETY CHECK] Correcting tab navigation to Speech Playground...")
                            tab1_speech.goto(f"https://aistudio.google.com/generate-speech?model={target_tts_model}", wait_until="domcontentloaded")
                            time.sleep(3)
                            reapply_speech_settings(tab1_speech, voice_config)

                        reload_limit = int(get_config_value("TTS_PROACTIVE_RELOAD_INTERVAL", "40"))
                        if chapters_since_reload >= reload_limit:
                            print(f"\n[MAINTENANCE] Proactively refreshing Speech Playground session...")
                            tab1_speech.bring_to_front()
                            try:
                                tab1_speech.locator("body").first.click(timeout=1000)
                                time.sleep(0.5)
                            except Exception:
                                pass
                            tab1_speech.reload(wait_until="domcontentloaded")
                            time.sleep(5)
                            reapply_speech_settings(tab1_speech, voice_config)
                            chapters_since_reload = 0

                        # Recovery reload if prior attempt failed
                        if getattr(main, 'attempt_count', 0) > 0:
                            print(f"[RECOVER] Reloading Speech Playground Tab to refresh credentials...")
                            tab1_speech.bring_to_front()
                            try:
                                tab1_speech.locator("body").first.click(timeout=1000)
                                time.sleep(0.5)
                            except Exception:
                                pass
                            tab1_speech.reload(wait_until="domcontentloaded")
                            time.sleep(5)
                            reapply_speech_settings(tab1_speech, voice_config)
                            chapters_since_reload = 0

                        tab1_speech.bring_to_front()
                        try:
                            tab1_speech.locator("body").first.click(timeout=1000)
                            time.sleep(0.5)
                        except Exception:
                            pass

                        speech_input = tab1_speech.locator("textarea[aria-label='Enter a prompt']").first
                        if not speech_input.is_visible():
                            print("Speech Playground input box was hidden. Retrying context...")
                            time.sleep(2)
                            continue

                        print(f"Entering Chapter {chap_num} script text into AI Studio...")
                        humanize_text_input(tab1_speech, speech_input, chap_text)

                        # Dynamic delay scaled to text length
                        text_length = len(chap_text)
                        base_delay = 3.0
                        scaled_delay = (text_length / 500.0) * random.uniform(1.2, 2.8)
                        cooldown_time = base_delay + scaled_delay
                        
                        print(f"Applying dynamic safety cooldown of {cooldown_time:.2f}s for {text_length} characters...")
                        time.sleep(cooldown_time)

                        # Click Run to synthesize audio
                        run_btn = tab1_speech.locator("button[type='submit'], button:has-text('Run')").first
                        try:
                            human_hover_and_click(tab1_speech, run_btn)
                        except Exception:
                            tab1_speech.keyboard.press("Control+Enter")

                        print("Synthesis started. Waiting dynamically for rendering to complete...")
                        started_rendering = False
                        try:
                            tab1_speech.wait_for_selector("button:has-text('Stop')", timeout=8000)
                            print("Synthesis processing confirmed...")
                            started_rendering = True
                        except Exception:
                            has_error, err_msg = check_ai_studio_errors(tab1_speech)
                            if has_error:
                                print(f"Synthesis failed due to AI Studio error: {err_msg}")
                            else:
                                print("Warning: Synthesis 'Stop' button did not appear within 8s.")

                        if not started_rendering:
                            print("[RETRY TRIGGER] Synthesis failed to start. Reloading session...")
                            if os.path.exists(target_dest):
                                try:
                                    os.remove(target_dest)
                                except Exception:
                                    pass
                            main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                            continue

                        synth_timeout_ms = int(get_config_value("TTS_SYNTHESIS_TIMEOUT", "300")) * 1000
                        try:
                            tab1_speech.wait_for_selector("button:has-text('Run')", timeout=synth_timeout_ms)
                            print("Audio synthesis complete!")
                        except Exception as e:
                            print(f"Warning: Timeout or error waiting for synthesis: {e}")

                        time.sleep(2.0)

                        # Download synthesized audio file
                        download_btn = tab1_speech.locator("button[aria-label*='Download' i], button:has-text('Download')").first
                        try:
                            download_btn.wait_for(state="visible", timeout=10000)
                        except Exception:
                            pass

                        download_success = False
                        if download_btn.is_visible():
                            try:
                                with tab1_speech.expect_download(timeout=15000) as download_info:
                                    human_hover_and_click(tab1_speech, download_btn)
                                download = download_info.value
                                download.save_as(target_dest)
                                print(f"Audio file downloaded and saved: {target_dest}")
                                download_success = True
                            except PlaywrightTimeoutError:
                                print("\n[TIMEOUT] Playwright timed out waiting for download event.")
                            except Exception as e:
                                print(f"\n[ERROR] Error downloading audio file: {e}")

                        if download_success:
                            # MD5 verification against previous chapter
                            is_duplicate = False
                            if chap_num > 1:
                                previous_dest = os.path.join(voice_folder, f"Chapter_{chap_num - 1}.wav")
                                if os.path.exists(previous_dest):
                                    current_md5 = get_file_md5(target_dest)
                                    previous_md5 = get_file_md5(previous_dest)
                                    if current_md5 and previous_md5 and current_md5 == previous_md5:
                                        is_duplicate = True
                                        print(f"\n[ALERT] MD5 Match! Stale audio served (Duplicate of Chapter {chap_num - 1}).")

                            if is_duplicate:
                                try:
                                    os.remove(target_dest)
                                except Exception:
                                    pass
                                main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                                continue

                            # Update manifest chapter status to COMPLETED
                            chap_entry["status"] = "COMPLETED"
                            save_manifest(latest_run, manifest)
                            print(f"[MANIFEST] Chapter {chap_num} marked COMPLETED in manifest.")

                            chapters_since_reload += 1
                            main.attempt_count = 0
                            break
                        else:
                            main.attempt_count = getattr(main, 'attempt_count', 0) + 1
                            retry_limit = int(get_config_value("FAILOVER_RETRY_LIMIT", "3"))
                            
                            if getattr(main, 'attempt_count', 0) >= retry_limit:
                                if accounts_enabled:
                                    print(f"\n[FAILOVER ALERT] Chapter {chap_num} failed {retry_limit} times. Rotating Account Profile...")
                                    rotate_profile_index()
                                    kill_cdp_chrome()
                                    failover_triggered = True
                                    break
                                else:
                                    print(f"\n[FATAL ERROR] Chapter {chap_num} failed after {retry_limit} attempts. Halting.")
                                    sys.exit(1)

                            backoff_delay = 5.0 * (2.0 ** (getattr(main, 'attempt_count', 0) - 1))
                            print(f"Applying exponential backoff of {backoff_delay:.2f}s before retry...")
                            time.sleep(backoff_delay)

                if failover_triggered:
                    # Do not break out of the outer while True loop here.
                    # Exiting this block allows the code below to catch failover_triggered and continue.
                    pass
                else:
                    # Exit outer loop when all chapters are successfully synthesized
                    all_done = all(c.get("status") == "COMPLETED" for c in manifest.get("chapters", []))
                    if all_done:
                        print("\n=============================================")
                        print("ALL VOICE CHAPTERS SUCCESSFULLY GENERATED & SAVED!")
                        print("=============================================")
                        break

        except Exception as e:
            print(f"[RECOVERY] Playwright context closed or browser crashed: {e}")

        if failover_triggered:
            print("\n[SYSTEM] Reinitializing Playwright environment with new profile. Fast-forwarding...\n")
            main.attempt_count = 0
            time.sleep(3)
            continue
        else:
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[SYSTEM] Automation execution interrupted by user (Ctrl+C). Progress checkpoint saved.")
        sys.exit(0)