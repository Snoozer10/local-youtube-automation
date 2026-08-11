import os
import re
import sys
import time
import subprocess
import json
import base64
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from utils import get_config_value, launch_browser_with_profile, rotate_profile_index, kill_cdp_chrome

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def enforce_arabic_in_prompt(prompt_text):
    """Sanitizes prompt text: replaces English layout phrases with Arabic, enforces Arabic typography when text is present, or strictly forbids text when overlay is NONE."""
    replacements = {
        r'(?i)"CHALLENGER\s*(\d+)?:?\s*([^"]*)"': r'"التحدي \1: \2"',
        r'(?i)CHALLENGER\s*(\d+)': r'التحدي \1',
        r'(?i)"COLLECTION BOARD"': r'"لوحة التجميع"',
        r'(?i)COLLECTION BOARD': r'لوحة التجميع',
        r'(?i)"SPEED ROUND"': r'"الجولة السريعة"',
        r'(?i)SPEED ROUND': r'الجولة السريعة',
        r'(?i)"DIAGRAM"': r'"مخطط"',
        r'(?i)"INFOGRAPHIC"': r'"انفوجرافيك"',
        r'(?i)"BLUEPRINT"': r'"مخطط تفصيلي"',
        r'(?i)STEP\s*(\d+)': r'الخطوة \1',
        r'(?i)\bBEFORE\b': r'قبل',
        r'(?i)\bAFTER\b': r'بعد',
        r'(?i)\bVS\.?\b|\bVERSUS\b': r'ضد',
        r'(?i)English text': r'Arabic text',
        r'(?i)English typography': r'Arabic typography',
        r'(?i)English labels': r'Arabic labels',
    }
    
    sanitized = prompt_text
    for pattern, repl in replacements.items():
        sanitized = re.sub(pattern, repl, sanitized)

    # Check if prompt explicitly requests no text overlay ("NONE") or if actual Arabic text is present
    has_explicit_none = '"text_overlay_arabic": "NONE"' in sanitized or '"text_overlay_arabic": "none"' in sanitized.lower()
    has_arabic_script = bool(re.search(r'[\u0600-\u06FF]', sanitized))

    if has_arabic_script and not has_explicit_none:
        directive = (
            "\n\n[MANDATORY TYPOGRAPHY RULE]: All visible on-screen text, titles, labels, "
            "and typography MUST be written in crisp, accurate ARABIC script. "
            "Do NOT render any English/Latin letters. "
            "Negative prompt: English text, English typography, Latin characters, English letters, English words, typos, gibberish."
        )
    else:
        directive = (
            "\n\n[STRICT NO ON-SCREEN TEXT RULE]: Do NOT render any visible text, letters, numbers, labels, captions, or typography anywhere on screen. Keep the image pure visual art with zero text."
            "\nNegative prompt: text, typography, letters, numbers, labels, words, signs, watermark, captions."
        )
    
    return sanitized + directive

def clear_attached_prompt_chips(page):
    """DOM Helper: Clears any existing image chips/attachments in the prompt input area."""
    try:
        chip_remove_btns = page.locator("button[aria-label*='remove' i], button[aria-label*='delete' i], button[aria-label*='clear' i]").all()
        for btn in chip_remove_btns:
            if btn.is_visible():
                btn.click(force=True)
                time.sleep(0.3)
    except Exception:
        pass

def attach_previous_image_to_prompt(page):
    """DOM Helper: Clears old chips, finds the top-left (most recent) workspace image card, opens menu, and clicks 'Add to prompt'."""
    try:
        print("  📷 Attaching previous image to prompt via 'Add to prompt'...")
        
        # 1. Clear previous attachments first
        clear_attached_prompt_chips(page)

        # 2. Search for images inside the main workspace feed (x > 200 excludes left sidebar)
        all_imgs = page.locator("img").all()
        workspace_imgs = []
        
        for img in all_imgs:
            try:
                if img.is_visible():
                    box = img.bounding_box()
                    # Filter out left sidebar icons (x < 200) and small UI badges (width/height < 180x120)
                    if box and box["x"] > 200 and box["width"] > 180 and box["height"] > 120:
                        if img.evaluate("el => el.naturalWidth > 180 || el.clientWidth > 180"):
                            workspace_imgs.append((box["y"], box["x"], img))
            except Exception: pass

        if not workspace_imgs:
            print("  ⚠️ No valid workspace image cards found.")
            return False

        # Sort ascending by (y, x): index 0 = top-most, left-most card (newest image)
        workspace_imgs.sort(key=lambda item: (item[0], item[1]))
        top_left_y, top_left_x, last_img = workspace_imgs[0]

        last_img.scroll_into_view_if_needed()
        time.sleep(0.5)

        # 3. Hover over the top-left workspace image to reveal card controls
        last_img.hover()
        time.sleep(0.5)

        # 4. Find the parent card container and click its 3-dots menu button (⋮)
        menu_clicked = False
        try:
            parent_card = last_img.locator("xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'media') or contains(@class, 'item') or position()=2]").first
            card_btns = parent_card.locator("button").all()
            if card_btns:
                for b in reversed(card_btns):
                    if b.is_visible():
                        b.click(force=True)
                        menu_clicked = True
                        break
        except Exception: pass

        if not menu_clicked:
            try:
                last_img.click(button="right", force=True)
                menu_clicked = True
            except Exception: pass

        time.sleep(1)

        # 5. Click "Add to prompt" from popup context menu
        add_pattern = re.compile(r"(\+?\s*Add to prompt|إضافة إلى)", re.IGNORECASE)
        add_opt = None

        try:
            opts = page.get_by_text(add_pattern).all()
            for opt in reversed(opts):
                if opt.is_visible():
                    add_opt = opt
                    break
        except Exception: pass

        if not add_opt:
            try:
                opts = page.locator("button, div, [role='menuitem'], li").filter(has_text=add_pattern).all()
                for opt in reversed(opts):
                    if opt.is_visible():
                        add_opt = opt
                        break
            except Exception: pass

        if add_opt:
            add_opt.scroll_into_view_if_needed()
            add_opt.click(force=True)
            time.sleep(1.2)
            print("  ✅ Successfully attached previous image card to active prompt!")
            return True
        else:
            print("  ⚠️ Could not find 'Add to prompt' option in menu.")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"  ⚠️ Error attaching image to prompt: {e}")
        page.keyboard.press("Escape")
        return False
    
def scan_batch_folders():
    runs_dir = "youtube_runs"
    batch_queue = []
    if os.path.exists(runs_dir):
        for item in os.listdir(runs_dir):
            subfolder = os.path.join(runs_dir, item)
            if os.path.isdir(subfolder):
                # Check for image_timestamps.txt OR timestamped_transcript.txt
                ts_file = os.path.join(subfolder, "image_timestamps.txt")
                if not os.path.exists(ts_file):
                    ts_file = os.path.join(subfolder, "timestamped_transcript.txt")
                    
                if os.path.exists(ts_file):
                    batch_queue.append(subfolder)
    return batch_queue

def parse_json_prompts(file_path):
    """Parses individual JSON objects from file, bypassing array/bracket tracking errors."""
    if not os.path.exists(file_path):
        return []
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    prompts = []
    
    content_clean = re.sub(r'```json\s*', '', content, flags=re.IGNORECASE)
    content_clean = re.sub(r'```\s*', '', content_clean)

    raw_objects = []
    in_string = False
    escape = False
    brace_depth = 0
    start_pos = -1

    for i, char in enumerate(content_clean):
        if char == '"' and not escape:
            in_string = not in_string
        elif char == '\\' and in_string:
            escape = not escape
            continue
        elif not in_string:
            if char == '{':
                if brace_depth == 0:
                    start_pos = i
                brace_depth += 1
            elif char == '}' and brace_depth > 0:
                brace_depth -= 1
                if brace_depth == 0 and start_pos != -1:
                    raw_objects.append(content_clean[start_pos:i+1])
                    start_pos = -1
        escape = False

    for obj_str in raw_objects:
        if '"index"' not in obj_str and "'index'" not in obj_str:
            continue

        item = None
        try:
            item = json.loads(obj_str, strict=False)
        except json.JSONDecodeError:
            try:
                fixed_str = re.sub(r'(?<=:\s")([^"\\]*?)"([^"\\]*?)"(?=[\s,}])', r'\1\"\2\"', obj_str)
                fixed_str = re.sub(r',\s*([}\]])', r'\1', fixed_str)
                item = json.loads(fixed_str, strict=False)
            except Exception:
                try:
                    idx_m = re.search(r'"index"\s*:\s*(\d+)', obj_str)
                    ts_m = re.search(r'"timestamp"\s*:\s*"([^"]*)"', obj_str)
                    if idx_m:
                        idx_val = int(idx_m.group(1))
                        ts_val = ts_m.group(1) if ts_m else ""
                        # FIX #2: Append full 6-element tuple for fallback regex
                        prompts.append((idx_val, ts_val, obj_str, "STANDALONE", 1, 1))
                        continue
                except Exception:
                    pass
                print(f"Warning: Could not parse object string starting with: {obj_str[:60]}...")
                continue

        if isinstance(item, dict):
            try:
                idx = int(item.get("index", 0))
                ts = str(item.get("timestamp", "")).strip()
                vp = item.get("visual_prompt", "")

                if isinstance(vp, dict):
                    prompt = json.dumps(vp, indent=2)
                else:
                    prompt = str(vp).strip()

                seq_type = str(item.get("sequence_type", "STANDALONE")).strip().upper()
                seq_meta = item.get("sequence_metadata", {})

                frame_idx = 1
                total_frames = 1
                if isinstance(seq_meta, dict):
                    frame_idx = int(seq_meta.get("frame_index", 1))
                    total_frames = int(seq_meta.get("total_frames_in_set", 1))

                if idx > 0 and prompt:
                    prompts.append((idx, ts, prompt, seq_type, frame_idx, total_frames, item))
            except Exception:
                continue

    # Deduplicate and sort by (index, frame_index) tuple to preserve multi-frame set items
    prompts_dict = {}
    for p in prompts:
        idx, frame_idx = p[0], p[4]
        key = (idx, frame_idx)
        # Automatically resolve key collisions to prevent overwriting multi-frame items
        while key in prompts_dict:
            frame_idx += 1
            key = (idx, frame_idx)
            
        p_list = list(p)
        p_list[4] = frame_idx
        prompts_dict[key] = tuple(p_list)

    sorted_keys = sorted(prompts_dict.keys(), key=lambda x: (x[0], x[1]))
    sorted_prompts = [prompts_dict[k] for k in sorted_keys]
    return sorted_prompts

def save_sorted_prompts_file(prompts_list, file_path):
    """Overwrites flow_prompts.json with cleanly formatted, numerically ordered JSON items."""
    try:
        clean_items = []
        for p in prompts_list:
            if len(p) >= 7 and isinstance(p[6], dict):
                clean_items.append(p[6])
            else:
                try:
                    clean_items.append(json.loads(p[2]))
                except Exception: pass

        if clean_items:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(clean_items, ensure_ascii=False, indent=2))
                f.write("\n")
            print(f"  🧹 Successfully cleaned up and sorted {len(clean_items)} items in {os.path.basename(file_path)}.")
    except Exception as e:
        print(f"  ⚠️ Warning saving sorted prompts file: {e}")

def is_gemini_generating(page):
    """Detects if Gemini is actively thinking, analyzing, or streaming."""
    stop_selectors = [
        "button[aria-label*='Stop' i]",
        "button[aria-label*='Cancel' i]",
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

    # Check for thinking/analyzing indicators or spinners
    try:
        if page.locator("mat-progress-spinner, .thinking-indicator, [aria-label*='Thinking' i]").first.is_visible():
            return True
    except Exception:
        pass

    return False

def wait_until_gemini_idle(page, timeout_seconds=180):
    """Ensures Gemini is completely idle before pasting a new prompt."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        if not is_gemini_generating(page):
            time.sleep(2)  # Extra buffer to let DOM settle
            if not is_gemini_generating(page):
                return True
        time.sleep(1)
    return False

def wait_for_gemini_response(page, initial_count, min_length=20, timeout_seconds=180):
    """Waits for Gemini to finish generating a substantial response."""
    start_time = time.time()
    
    print("  ⏳ Waiting for Gemini to begin response stream...")
    generation_started = False
    while time.time() - start_time < 35:
        if is_gemini_generating(page) or page.locator("model-response").count() > initial_count:
            generation_started = True
            break
        time.sleep(1)
        
    if not generation_started:
        print("  ⚠️ Gemini response stream did not trigger.")
        return None

    print("  🟢 Response stream active. Monitoring progress until complete...")
    time.sleep(3)  # Give Gemini time to pass initial "Analyzing" placeholder
    
    last_text = ""
    stable_count = 0
    
    while time.time() - start_time < timeout_seconds:
        still_thinking = is_gemini_generating(page)
        
        try:
            last_response = page.locator("model-response").last
            last_response.scroll_into_view_if_needed(timeout=1000)
            current_text = last_response.evaluate("el => el.innerText", timeout=5000).strip()
            
            if current_text.startswith("Gemini said"):
                cleaned_text = current_text[len("Gemini said"):].strip()
            else:
                cleaned_text = current_text
            
            # Reject transient status text
            if cleaned_text.lower() in ["analyzing", "thinking", "thinking...", "visualizing the scenes"]:
                still_thinking = True

            # Must NOT be thinking AND must exceed minimum character length
            if not still_thinking and len(cleaned_text) >= min_length:
                if cleaned_text == last_text:
                    stable_count += 1
                    if stable_count >= 4:  # Must be stable for 4 consecutive cycles (~6 seconds)
                        print(f"  ✅ Complete response received ({len(cleaned_text)} characters).")
                        return cleaned_text
                else:
                    last_text = cleaned_text
                    stable_count = 0
            else:
                last_text = cleaned_text
                stable_count = 0
                
        except Exception:
            pass
            
        time.sleep(1.5)
        
    print("  ⚠️ Timed out waiting for complete response.")
    return None

def select_gemini_model(page, target_model="Pro"):
    """Robust model selection for Google Gemini's updated UI."""
    print(f"\n[MODEL] Verifying Gemini model selection (Target: {target_model})...")
    
    # 1. Locate the model selector pill button near the prompt input box
    model_btn = None
    btn_candidates = [
        page.locator("button:has-text('Flash'), button:has-text('Pro'), button:has-text('Lite')").first,
        page.locator("button[aria-label*='model' i], button[aria-label*='mode' i]").first,
        page.locator("rich-textarea ~ * button").first
    ]
    
    for loc in btn_candidates:
        try:
            if loc.is_visible() and loc.is_enabled():
                model_btn = loc
                break
        except Exception: pass

    if not model_btn:
        print("Warning: Could not locate Gemini model selector button.")
        return False

    try:
        active_text = model_btn.inner_text().strip().lower()
        target_clean = target_model.strip().lower()

        # Check if target model (e.g. "pro") is already active
        if target_clean in active_text:
            print(f"Success: Correct model '{target_model}' is already active.")
            return True

        print(f"Switching Gemini model to '{target_model}'...")
        model_btn.click(force=True)
        time.sleep(1.5)

        # 2. Regex search for the target model option inside the opened dropdown menu
        # Matches "Pro", "3.1 Pro", "Flash", "3.6 Flash", "3.5 Flash-Lite", etc.
        pattern = re.compile(rf"(\b{re.escape(target_clean)}\b|\d+\.\d+\s*{re.escape(target_clean)})", re.IGNORECASE)
        option_clicked = False

        try:
            opts = page.get_by_text(pattern).all()
            for opt in opts:
                if opt.is_visible():
                    opt.click(force=True)
                    option_clicked = True
                    print(f"Successfully selected model option: '{target_model}'")
                    break
        except Exception: pass

        if not option_clicked:
            try:
                opts = page.locator("div, button, [role='option'], [role='menuitem'], span").filter(has_text=pattern).all()
                for opt in reversed(opts):
                    if opt.is_visible():
                        opt.click(force=True)
                        option_clicked = True
                        print(f"Successfully selected model option: '{target_model}'")
                        break
            except Exception: pass

        if not option_clicked:
            print(f"Warning: Could not find '{target_model}' inside Gemini dropdown.")
            page.keyboard.press("Escape")

        time.sleep(1.5)
        return option_clicked

    except Exception as e:
        print(f"Warning: Model selection failed: {e}")
        page.keyboard.press("Escape")
        return False

def setup_flow_ui(page, target_flow_model="Nano Banana Pro", target_flow_count="1x", project_url=None):
    def wake_up_page():
        try:
            page.mouse.move(100, 100)
            time.sleep(0.2)
            page.mouse.move(500, 500)
            page.mouse.down()
            page.mouse.up()
        except Exception: pass

    # Attempt to load saved project URL if provided
    resumed = False
    if project_url and "project" in project_url:
        print(f"\n[FLOW] Attempting to resume workspace: {project_url}")
        try:
            page.goto(project_url, wait_until="domcontentloaded", timeout=60000)
            wake_up_page() 
            time.sleep(3)
            if "project" in page.url:
                resumed = True
                print("  ✅ Workspace resumed successfully.")
            else:
                print("  ⚠️ Workspace URL not accessible for current profile account. Falling back to new project creation...")
        except Exception as e:
            print(f"  ⚠️ Error loading workspace URL: {e}. Falling back to new project creation...")

    if not resumed:
        print(f"\n[FLOW] Configuring NEW workspace for active profile (Model: {target_flow_model} | Count: {target_flow_count})...")
        workspace_created = False
        
        for attempt in range(1, 4):
            print(f"[FLOW] Attempt {attempt}/3 to load Google Flow and open a new project...", flush=True)
            page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=60000)
            wake_up_page() 
            time.sleep(3) 

            # 1. Splash Screen Bypass
            try:
                splash_btn = page.locator("button:has-text('Create with Google Flow'), a:has-text('Create with Google Flow')").first
                if splash_btn.is_visible():
                    splash_btn.click(force=True)
                    time.sleep(4) 
                    wake_up_page()
            except Exception: pass

            # 2. Robust '+ New project' Waiter & Clicker
            print("[FLOW] Waiting for '+ New project' element to appear on dashboard...", flush=True)
            pattern = re.compile(r"(\+?\s*New project|\+?\s*مشروع جديد)", re.IGNORECASE)
            new_project_target = None
            
            start_wait = time.time()
            while time.time() - start_wait < 25:
                try:
                    loc = page.get_by_text(pattern)
                    cnt = loc.count()
                    for i in reversed(range(cnt)):
                        el = loc.nth(i)
                        if el.is_visible():
                            new_project_target = el
                            break
                    if new_project_target:
                        break
                except Exception: pass

                try:
                    loc = page.locator("button, div, a, span, p").filter(has_text=pattern)
                    cnt = loc.count()
                    for i in reversed(range(cnt)):
                        el = loc.nth(i)
                        if el.is_visible():
                            new_project_target = el
                            break
                    if new_project_target:
                        break
                except Exception: pass

                time.sleep(1)
                wake_up_page()

            if new_project_target:
                print("[FLOW] Found visible '+ New project' element. Attempting click...", flush=True)
                try:
                    new_project_target.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    new_project_target.click(force=True)
                except Exception: pass
                
                time.sleep(2)
                if "project" not in page.url:
                    try:
                        new_project_target.evaluate("el => el.click()")
                    except Exception: pass

                    try:
                        parent_card = new_project_target.locator("xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'project') or position()=1]")
                        if parent_card.is_visible():
                            parent_card.click(force=True)
                    except Exception: pass

                try:
                    page.wait_for_url("**/project/**", timeout=20000)
                    print(f"[FLOW] Successfully redirected to new project workspace: {page.url}", flush=True)
                    workspace_created = True
                    break
                except Exception: pass

            time.sleep(2)

        if not workspace_created and "project" not in page.url:
            raise Exception("Failed to create or enter a Google Flow project workspace after 3 attempts.")


    time.sleep(4)
    current_workspace_url = page.url

    # 3. Turn Agent OFF if FLOW_DISABLE_AGENT is true
    if get_config_value("FLOW_DISABLE_AGENT", "true").lower() in ["true", "1", "yes"]:
        try:
            agent_btn = page.locator("button:has-text('Agent')").first
            if agent_btn.is_visible():
                is_active = agent_btn.evaluate("el => el.getAttribute('aria-pressed') === 'true' || el.classList.contains('active')")
                if is_active:
                    print("[FLOW] Turning Agent OFF...")
                    agent_btn.click(force=True)
                    time.sleep(1)
        except Exception: pass

    # 4. Select Custom Flow Model
    try:
        model_dropdown = page.locator("button:has-text('Nano Banana'), button:has-text('Imagen'), button:has-text('Veo'), button[aria-haspopup='listbox']").first
        if model_dropdown.is_visible():
            if target_flow_model.lower() not in model_dropdown.inner_text().lower():
                print(f"[FLOW] Changing image model to '{target_flow_model}'...")
                model_dropdown.click(force=True)
                time.sleep(1)
                model_option = page.get_by_text(target_flow_model).last
                if model_option.is_visible():
                    model_option.click(force=True)
                    time.sleep(1)
                else:
                    page.keyboard.press("Escape")
    except Exception as e: print(f"[FLOW] Warning setting image model: {e}")

    # 5. Settings Menu: Set Aspect Ratio (16:9) & Generation Count (1x, x2, etc)
    try:
        settings_icon = page.locator("button:has(svg path[d*='M3']), button[aria-label*='Settings' i]").last
        if settings_icon.is_visible():
            settings_icon.click(force=True)
            time.sleep(1)
            
            # Set aspect ratio dynamically from .env
            target_ratio = get_config_value("FLOW_ASPECT_RATIO", "16:9")
            ratio_btn = page.locator(f"button:has-text('{target_ratio}'), div:has-text('{target_ratio}')").first
            if ratio_btn.is_visible():
                ratio_btn.click(force=True)
                time.sleep(0.5)
                
            # Set Count (1x, x2, x3, x4)
            count_btn = page.locator(f"button:has-text('{target_flow_count}'), div:has-text('{target_flow_count}')").first
            if count_btn.is_visible():
                count_btn.click(force=True)
                time.sleep(0.5)
                
            page.keyboard.press("Escape")
    except Exception: pass

    return current_workspace_url

# ==========================================
# MAIN ORCHESTRATOR
# ==========================================
def main():
    batch_queue = scan_batch_folders()
    if not batch_queue:
        print("No active folders found.")
        return

    # Define retry counters HERE at the top of main()
    consecutive_failures = 0
    max_retries_no_switch = 3

    while True:
        failover_triggered = False
        
        switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower()
        accounts_enabled = switch_enabled_str in ['true', '1', 'yes']
        
        try:
            with sync_playwright() as p:
                current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                browser_type = get_config_value("BROWSER_TYPE", "chrome")
                
                try:
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")
                except Exception:
                    if not launch_browser_with_profile(browser_type, current_profile_idx): sys.exit(1)
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")

                context = browser.contexts[0]
                gemini_page = context.new_page()
                flow_page = context.new_page()

                for folder_idx, subfolder in enumerate(batch_queue, 1):
                    print(f"\n==================================================")
                    print(f"PROCESSING TOPIC: {subfolder}")
                    print(f"==================================================")
                    
                    script_path = os.path.join(subfolder, "image_timestamps.txt")
                    if not os.path.exists(script_path):
                        script_path = os.path.join(subfolder, "timestamped_transcript.txt")
                    prompts_file = os.path.join(subfolder, "flow_prompts.json")
                    image_dir = os.path.join(subfolder, "generated_images")
                    dup_dir = os.path.join(subfolder, "generated_images_duplicates") # <-- NEW
                    os.makedirs(image_dir, exist_ok=True)
                    os.makedirs(dup_dir, exist_ok=True) # <-- NEW
                    
                    target_planner_model = get_config_value("IMAGE_PLANNER_MODEL", "Flash-Lite")
                    target_flow_model = get_config_value("FLOW_IMAGE_MODEL", "Nano Banana 2")
                    target_flow_count = get_config_value("FLOW_IMAGE_COUNT", "1x")
                    reset_loop_limit = int(get_config_value("IMAGE_RESET_LOOP_LIMIT", "20"))

                    sentences, timestamps = [], []
                    if os.path.exists(script_path):
                        with open(script_path, "r", encoding="utf-8") as f:
                            for line in f:
                                line_str = line.strip()
                                if not line_str: continue
                                match = re.match(r"^\[(?:(\d{2}):)?(\d{2}):(\d{2})\]\s*(.*)", line_str)
                                if match:
                                    h = match.group(1)
                                    m = match.group(2)
                                    s = match.group(3)
                                    text = match.group(4).strip()
                                    ts_str = f"[{h}:{m}:{s}]" if h else f"[{m}:{s}]"
                                    timestamps.append(ts_str)
                                    sentences.append(text)

                    storyboard_prompts = parse_json_prompts(prompts_file)

                    # Auto-sort flow_prompts.json on disk to clean up out-of-order/duplicate entries
                    if storyboard_prompts:
                        save_sorted_prompts_file(storyboard_prompts, prompts_file)

                    # Set-based index check
                    expected_indices = set(range(1, len(sentences) + 1))
                    existing_indices = {item[0] for item in storyboard_prompts}
                    missing_indices = expected_indices - existing_indices

                    skip_planning = (len(missing_indices) == 0) and (len(sentences) > 0)

                    if skip_planning:
                        print(f"\n[SKIP] All {len(sentences)} prompt indices found in flow_prompts.json. Proceeding to image rendering...")
                    else:
                        print(f"\n[PLANNING] {len(missing_indices)} missing indices detected out of {len(sentences)}. Running Phase 1...")

                    # ---------------------------------------------------------
                    # PHASE 1: TWO-PASS MASTER ROADMAP & JSON PLANNING (CHECKPOINTED)
                    # ---------------------------------------------------------
                    roadmap_file = os.path.join(subfolder, "master_roadmap.txt")
                    
                    if not skip_planning and len(sentences) > 0:
                        gemini_page.bring_to_front()
                        
                        # --- PHASE 1A: MASTER ROADMAP CHECKPOINT ---
                        master_roadmap = ""

                        if os.path.exists(roadmap_file):
                            with open(roadmap_file, "r", encoding="utf-8") as f:
                                cached_roadmap = f.read().strip()
                                if len(cached_roadmap) > 150 and cached_roadmap.lower() not in ["analyzing", "thinking"]:
                                    print("\n[RESUME] Found valid cached Master Roadmap. Loading from disk...")
                                    master_roadmap = cached_roadmap

                        if not master_roadmap:
                            print("\n[PHASE 1A] Analyzing full script to generate Master Continuity Roadmap...")
                            gemini_page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                            time.sleep(3)
                            select_gemini_model(gemini_page, target_planner_model)
                            
                            initial_count = gemini_page.locator("model-response").count()
                            input_box = gemini_page.locator("rich-textarea div[contenteditable='true']").first
                            
                            # 1. SEND THE FULL SCRIPT FOR GLOBAL ANALYSIS
                            full_script_text = " ".join(sentences)
                            roadmap_prompt = f"""# SYSTEM PROMPT: VISUAL CONTINUITY ARCHITECT (ARABIC CREATOR STYLE)
Create a visual roadmap for Google Flow still-image animation.

### CHARACTER TOKENS
1. **HOST (Sparing, <25%)**: 2D faceless character, smooth featureless white circular head (no eyes, no nose, no mouth, no glasses), short wavy black hair, wearing a vibrant red baseball cap, dark charcoal t-shirt, and an open light-grey lab coat / jacket.
2. **USER (Main Actor)**: Minimalist stick figure, white circular head, vertical line eyes (`||`), black t-shirt, line limbs.
3. **MAIN CHARACTER (SINGLE)**: Main character alone.
4. **SECONDARY CHARACTERS (DUO / MULTI)**: Main character interacting with a distinct, 2D secondary character.
5. **CROWD / GROUPS (GROUP)**: An active crowd of stick-figures.
6. **ABSENT**: For standalone diagrams, conceptual diagrams, hardware devices, B-roll, UI HUDs, typography, pure typography scenes, or isolated objects.

### PROGRESSIVE CONCEPT BUILD-UP VARIANTS (SELECT FIT FOR SCRIPT CONTEXT)
Whenever the script explains a process, mechanism, comparison, or breakdown:
- **DO NOT** condense it into 1 frame.
- **BUILD IT PROGRESSIVELY** across extended keyframe chains using one of these visual variants:
  * **Variant A (Flow & Transmission)**: Base Subject -> Vector Arrow -> Active Payload -> Target Node -> Result Inset -> Arabic Callout Badge.
  * **Variant B (Comparison/Split)**: Dual Split Screen -> Left Option A -> Right Option B -> VS/Checkmark Badge.
  * **Variant C (Macro Inset Breakdown)**: Wide Subject -> Circular Magnifying Lens -> Internal Mechanics -> Component Labels.
  * **Variant D (Pipeline & Network Nodes)**: Core Node -> Connector Lines -> Terminal Nodes -> Energy Pulses -> Status Cards.
  * **Variant E (Collection Grid)**: Empty Display Shelf -> Batch 1 Items -> Batch 2 Items -> Summary Badge.
  * **Variant F (Infographic Data HUD)**: Gauge Baseline -> 50% Fill -> 100% Fill + Spotlight -> Metric Callout.

### STORYBOARD BEAT-BY-BEAT PRODUCTION ARC
When designing a scene sequence, map the progression to this structural arc:
- OPENER: Wide establishing shot introducing the environment, the main character, and the core goal/object.
- PREPARATION: Medium shot revealing the tools, steps, or concepts needed.
- FIRST ACTION: Close-up showing the process beginning with visible, clear progress.
- TRANSFORMATION: Extreme close-up of the most visually satisfying, peak moment.
- PROGRESS: Medium close-up showing continuation and improvement.
- FINAL STEP: Dramatic close shot building high anticipation.
- FINAL REVEAL: Wide cinematic shot showing the finished result, character reaction, and a satisfying wrap-up.

### HIGH QUALITY SEQUENCE TYPES & DIRECTIVES
1. **STANDALONE**: Single isolated keyframe concept or visual beat.
2. **PROGRESSIVE_BUILD_SET**: Multi-frame step-by-step element accumulation (Device -> Arrow -> Payload -> Signal -> Output).
3. **THEME_SET_CONTINUITY**: Multi-frame scene holding subject & room background steady across state/pose shifts.
4. **STOP_MOTION_SET**: High-frequency frame sequence simulating fluid animation cuts or physical motion.
5. **CAMERA_ZOOM_SEQUENCE**: Multi-frame push-in (wide establishing shot -> medium detail -> extreme macro close-up) or pull-out.
6. **PANORAMIC_PAN_SET**: Multi-frame seamless horizontal or vertical camera pan across a continuous visual canvas.
7. **CHARACTER_ACTION_ARC**: Multi-frame step-by-step breakdown of dynamic movement, body gesture, or physical action.
8. **CHALLENGER_CARD**: Gamified vs matchup layout, head-to-head comparison, or dual-threat card visual.
9. **COLLECTION_BOARD**: Grid or display shelf gathering multiple collected items, tech icons, badges, or concepts.
10. **SPEED_ROUND_HUD**: Rapid-fire quiz/data HUD layout with glowing timer, live point counters, and status badges.
11. **DIAGRAM_BREAKDOWN**: Technical blueprint or schematic with glowing vector directional arrows, callouts, and component labels.
12. **INFOGRAPHIC_PHOTO_INSET**: Graphic vector layout featuring a realistic photographic or high-tech blueprint inset card.
13. **FLASHBACK_STORY**: Retro monochromatic or sepia-toned historical memory, backstory, or contextual origin scene.
14. **SPLIT_PANEL**: Dual-view screen (vertical or horizontal split) comparing two contrasting states, choices, or perspectives.
15. **BEFORE_AFTER_TRANSFORMATION**: Dramatic transition split or cut showing "Before" state vs "After" state visual impact.
16. **ISOMETRIC_PIPELINE**: 3D-angled isometric vector schema detailing system architectures, workflows, network nodes, or data paths.
17. **COMIC_MULTI_PANEL**: Multi-panel comic strip layout (2-panel or 3-panel grid with crisp black borders) for fast comedic beats.
18. **MACRO_INSET_FOCUS**: Wide scene with a magnified circular vector lens highlight displaying microscopic or technical inner details.
19. **TYPOGRAPHY_SCENE**: Bold Arabic text-centric frame for chapter titles, key statistics, major statements, or punchlines.
20. **POV**: Direct first-person point-of-view perspective framing the scene through the main character's eyes.

### LAYOUT TOKENS (MUST BE USED IN LAYOUT CLASSIFICATION COLUMN)
1. **ISOLATED_WHITE**: Seamless pure white background (`#FFFFFF`) with no floor/wall textures.
2. **ENVIRONMENT_ROOM**: Cartoon room, beige tiled floor, brown wooden table, front orthographic perspective.
3. **CINEMATIC_PACING**: Wide-angle dramatic framing, dynamic depth, cinematic perspective.

### CAMERA & MOOD GUIDELINES FOR VISUAL CONCEPT COLUMN
- Include camera framing cues in the Visual Concept column: Wide Establishing (Fisheye 35mm), Medium Action, Close-Up Macro (120mm), or POV.
- Include lighting mood presets: Playful/Optimistic, Educational/Informative, Serious/Tension, or Melancholy.

--------------------------------------------------------------------------------
### ROADMAP TABLE OUTPUT FORMAT
| Index | Timestamp | Script Line | Sequence Type | Layout Classification | Visual Concept & Composition | Color & Selective Text Overlay |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |

SCRIPT:
{full_script_text}
"""
                            # Submit Roadmap Prompt
                            input_box.fill(roadmap_prompt)
                            input_box.press("Control+Enter")
                            
                            # Require a minimum of 200 characters for a valid Master Roadmap
                            master_roadmap = wait_for_gemini_response(gemini_page, initial_count, min_length=200, timeout_seconds=180)
                            
                            if not master_roadmap or len(master_roadmap) < 150 or master_roadmap.strip().lower() in ["analyzing", "thinking"]:
                                raise Exception("Generated Master Roadmap is invalid or stuck on 'Analyzing'. Retrying run...")
                                
                            with open(roadmap_file, "w", encoding="utf-8") as f:
                                f.write(master_roadmap)
                            print("✅ Master Roadmap successfully generated and saved to checkpoint.")

                        # --- PHASE 1B: JSON CHUNKING CHECKPOINT ---
                        print("\n[PHASE 1B] Checking chunks for missing indices...")
                        
                        existing_prompts = parse_json_prompts(prompts_file)
                        existing_indices = {item[0] for item in existing_prompts}

                        chunk_size = int(get_config_value("FLOW_CHUNK_SIZE", "15"))
                        chunks = [sentences[i:i+chunk_size] for i in range(0, len(sentences), chunk_size)]
                        
                        # Filter chunks to find only those containing missing indices
                        chunks_to_process = []
                        for chunk_idx, chunk in enumerate(chunks, 1):
                            start_idx = (chunk_idx - 1) * chunk_size + 1
                            chunk_indices = set(range(start_idx, start_idx + len(chunk)))
                            if not chunk_indices.issubset(existing_indices):
                                chunks_to_process.append((chunk_idx, start_idx, chunk))

                        if chunks_to_process:
                            print(f"[PHASE 1B] Initializing Gemini setup for {len(chunks_to_process)} missing chunk(s)...")
                            generic_monolithic_template = """# SYSTEM PROMPT: KEYFRAME PROMPT ARCHITECT (ARABIC CREATOR STYLE)

Translate the Master Visual Roadmap into stateless keyframe JSON prompts for Google Flow.

---

### === MASTER VISUAL CONTINUITY ROADMAP ===
[INJECT_ROADMAP_HERE]

---

### MANDATORY TOKENS & DIRECTIVES

1. **VERBATIM CHARACTER TOKENS**:
   - **HOST**: `"HOST: 2D faceless character, smooth featureless white circular head (no eyes, no nose, no mouth, no glasses), short wavy black hair, wearing a vibrant red baseball cap, dark charcoal t-shirt, and an open light-grey lab coat / jacket."` (Use sparingly, <25%).
   - **USER**: `"USER: Minimalist 2D stick figure, white circular head with simple vertical line eyes (||), wearing a plain black t-shirt with thin black line-art limbs."`
   - **MAIN CHARACTER**: `"SINGLE: A simple 2D character. Head is a uniform white circle with no nose or ears. Mouth is a single expressive black vector stroke. Exactly 3 to 5 thin black hair strands curving from the top of the scalp (bald otherwise). Wears an unbranded charcoal-grey hoodie (with a visible hood resting on the shoulders) and dark sweatpants. Arms and legs are simple, uniform black line art.`"
   - **SECONDARY CHARACTERS**: `"DUO / MULTI: Same 2D vector style. To distinguish them, they must have a flat-colored circle head (e.g., pale flat yellow), different hair configurations, or a simple flat-blue or flat-maroon hoodie. They must be drawn interacting directly with the main character (e.g., talking, pointing, handing over an object)."`
   - **CROWD / GROUPS**: `"GROUP: A background collection of multiple minimalist circle-head stick figures interacting naturally."`
   - **ABSENT**: `"ABSENT"`

2. **VERBATIM LAYOUT TOKENS**:
   - **ENVIRONMENT_ROOM**: `"ENVIRONMENT_ROOM: Simple 2D cartoon room set in a flat orthographic front-facing perspective. Off-white plain background wall with a dark horizontal dividing line, light beige square tiled floor with subtle brown grid lines, and a plain rectangular brown wooden four-legged table placed horizontally in the center foreground."`
   - **ISOLATED_WHITE**: `"ISOLATED_WHITE: Isolated subject on a seamless, pure solid white background (#FFFFFF) with no shadows or wall textures."`
   - **CINEMATIC_PACING**: `"CINEMATIC_PACING: Wide-angle cinematic framing for dramatic reveals, emphasizing depth and perspective."`

3. **PROGRESSIVE ELEMENT ACCUMULATION & HIGH QUALITY SEQUENCE TYPES**:
   - **PROGRESSIVE VISUAL BUILD VARIANTS (SELECT THE BEST MATCH FOR SCRIPT CONTEXT)**:
     Build elements additively across consecutive keyframes while keeping camera coordinates and room background 100% FROZEN:

     - **VARIANT A (FLOW & TRANSMISSION - 3 to 6 frames)**:
       * F1: Base Source Object/Subject alone (e.g., Router, Heart, Bank, Brain, Server).
       * F2: Append thick curved directional arrow/vector line originating from source.
       * F3: Append active payload/particles (e.g., signal waves, blood cells, coins, light rays, binary bits, molecules).
       * F4: Append receiving target node/device (e.g., Smartphone, Organ, Customer, Output Screen).
       * F5: Append result thumbnail inset card (e.g., video thumbnail, chart, medical scan).
       * F6: Append bold Arabic concept callout badge with high-contrast accent outline.

     - **VARIANT B (COMPARISON / BEFORE-AFTER - 2 to 4 frames)**:
       * F1: Split canvas into dual equal panels (`SPLIT_PANEL`).
       * F2: Left panel populates with Option A / "Before" state illustration.
       * F3: Right panel populates with Option B / "After" state illustration.
       * F4: Append central "VS" or Checkmark vs Cross comparison callout badge.

     - **VARIANT C (MACRO INSET BREAKDOWN - 3 to 5 frames)**:
       * F1: Wide shot of main subject (e.g., Human Body, Engine, Smartphone, Cell, Planet).
       * F2: Append magnified circular vector lens target over specific sub-component.
       * F3: Reveal micro/internal mechanics inside the circular lens highlight (`MACRO_INSET_FOCUS`).
       * F4: Append labeled directional callout arrows and short Arabic component tags around the lens.

     - **VARIANT D (PIPELINE & NETWORK NODES - 4 to 8 frames)**:
       * F1: Central core node appears (`ISOMETRIC_PIPELINE`).
       * F2: Branching connector lines shoot outward to empty node slots.
       * F3: Terminal node icons populate at line ends.
       * F4: Data packets / energy pulses travel along connecting pathways.
       * F5: Status indicators / result cards pop up at terminal nodes.

     - **VARIANT E (COLLECTION GRID ASSEMBLY - 3 to 5 frames)**:
       * F1: Display empty grid board or shelf layout (`COLLECTION_BOARD`).
       * F2: First batch of collected items/badges pop into initial slots.
       * F3: Remaining slots populate with items.
       * F4: Summary badge or total metric card pops up at the center.

     - **VARIANT F (INFOGRAPHIC DATA HUD RISE - 3 to 5 frames)**:
       * F1: Baseline metric gauge or bar chart layout (`SPEED_ROUND_HUD`).
       * F2: Progress gauge fills to 50% + live numeric counter appears.
       * F3: Progress gauge fills to 100% + glowing accent highlight.
       * F4: Append top Arabic statistical result badge (e.g., `"نمو بنسبة 100%"`)..
   - SPEECH BUBBLES: Render clean 2D white vector speech bubbles with dark outlines containing Arabic dialogue (e.g., `"شغل الفيديو الي بعده"`).
   - TECHNICAL GRAPHICS: Use curved yellow directional arrows, floating neon-green binary digits (`0` and `1`), blue radiating Wi-Fi arcs, and rectangular inset media cards (e.g., funny cat video thumbnail).
   - **STANDALONE**: Single isolated keyframe concept or visual beat.   
   - **THEME_SET_CONTINUITY**: Multi-frame consistency locking room/character baseline while mutating gestures.
   - **STOP_MOTION_SET**: High-frequency frame sequence simulating fluid movement.
   - **CAMERA_ZOOM_SEQUENCE**: Multi-frame camera distance shift (Wide establishing -> Medium -> Extreme Close-Up Macro).
   - **PANORAMIC_PAN_SET**: Multi-frame panning action across an extended scene.
   - **CHARACTER_ACTION_ARC**: Multi-frame movement or reaction arc.
   - **CHALLENGER_CARD**: Versus matchup card or direct comparison frame.
   - **COLLECTION_BOARD**: Multi-item display shelf or visual collection grid.
   - **SPEED_ROUND_HUD**: Rapid data HUD layout with glowing timer and score counters.
   - **DIAGRAM_BREAKDOWN**: Detailed schematic breakdown with vector arrows and callouts.
   - **INFOGRAPHIC_PHOTO_INSET**: Clean graphic with photographic/blueprint inset panel.
   - **FLASHBACK_STORY**: Sepia/monochromatic narrative backstory scene.
   - **SPLIT_PANEL**: Vertical or horizontal dual-view comparison.
   - **BEFORE_AFTER_TRANSFORMATION**: Before vs After state comparison layout.
   - **ISOMETRIC_PIPELINE**: 3D isometric vector schema detailing system components or flow.
   - **COMIC_MULTI_PANEL**: Multi-panel comic strip format (2-panel or 3-panel layout).
   - **MACRO_INSET_FOCUS**: Main wide scene with a magnified circular lens highlight showing micro details.
   - **TYPOGRAPHY_SCENE**: Bold Arabic text-centric frame for chapters or major punchlines.
   - **POV**: First-person point-of-view perspective frame.

4. **CAMERA RECIPES & MOOD PRESETS**:
   - Camera Lenses: Fisheye 35mm at f/8 (Wide/Establishing), Macro 120mm f/4 at f/2.8 (Close-Up/Metaphor), 35mm f/4 (Medium/Standard), POV (First-person).
   - Mood Presets: Playful/Optimistic (Warm pastel yellow/sky blue), Educational/Informative (Crisp neutral light grey), Serious/Tension (Deep charcoal/slate blue), Melancholy (Desaturated cold blue).

5. **RETENTION & COMPOSITION RULES**:
   - **LAYOUT ROTATION**: Max 15 consecutive identical layouts/sequence types. Rotate layout classifications constantly.
   - **LOCKED SET CONTINUITY**: For multi-frame sets (up to 15 frames), lock room/camera coordinates verbatim; mutate ONLY `subject_action_increment`.

6. **SELECTIVE ARABIC TEXT DIRECTIVES (`text_overlay_arabic`)**:
   - `text_overlay_arabic` MUST contain either the **ACTUAL ARABIC WORDS** to be rendered on screen (in clean, correct Arabic script) OR `"NONE"`.
   - **WHEN TO INCLUDE ARABIC TEXT**:
     - **Major Questions / Statements**: Render the actual Arabic question (e.g., `"كيف يعمل الواي فاي؟"`).
     - - **Top Topic Header**: Render a clean 1-2 word Arabic topic category title at top-center when explaining a technical/scientific concept (derived dynamically from current script topic).
     - **Contextual Action/Concept Callout**: Render 1 to 3 bold, accurate Arabic words inside a vibrant callout badge with thick black outline highlighting the specific step, action, key term, or punchline relevant to the current script sentence.
     - **Chapter Headers / Section Titles**: Render clean Arabic section titles (e.g., `"الخطوة الأولى"`).
     - **Typography Punchlines**: Render dramatic glowing Arabic text for major reveals (e.g., `"السر الحقيقي!"`).
   - **WHEN TO SET `"NONE"`**:
     - Set `text_overlay_arabic` to `"NONE"` for routine character actions, B-roll, narrative scenes, or background visuals to prevent visual clutter and rendering artifacts.
   - **CRITICAL FORMAT RULE**: NEVER output meta-label category descriptions such as `"Text/Question Overlay"` or `"Typography Punchline"`. ALWAYS write the literal Arabic text itself in Arabic script or `"NONE"`.

7. **STYLE ANCHOR**: `"2D webcomic vector style, thick clean black outlines, flat base colors, simple clean lighting, high contrast, crisp line art, cool-toned desaturated slate palette with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 aspect ratio."`

8. **JSON SYNTAX**: Output valid JSON array only. Escape inner quotes as `\"`.

---

### JSON SCHEMA CONTRACT

```json
[
  {
    "index": 1,
    "timestamp": "[00:00]",
    "sequence_type": "STANDALONE | PROGRESSIVE_BUILD_SET | THEME_SET_CONTINUITY | STOP_MOTION_SET | CAMERA_ZOOM_SEQUENCE | PANORAMIC_PAN_SET | CHARACTER_ACTION_ARC | CHALLENGER_CARD | COLLECTION_BOARD | SPEED_ROUND_HUD | DIAGRAM_BREAKDOWN | INFOGRAPHIC_PHOTO_INSET | FLASHBACK_STORY | SPLIT_PANEL | BEFORE_AFTER_TRANSFORMATION | ISOMETRIC_PIPELINE | COMIC_MULTI_PANEL | MACRO_INSET_FOCUS | TYPOGRAPHY_SCENE | POV",
    "layout_classification": "ISOLATED_WHITE | ENVIRONMENT_ROOM | CINEMATIC_PACING",
    "sequence_metadata": {
      "set_id": "SET_01",
      "frame_index": 1,
      "total_frames_in_set": 15
    },
    "visual_prompt": {
      "subject_details": "Verbatim character token string from Section 1 (e.g., 'SINGLE: A simple 2D character...', 'USER: ...', or 'ABSENT').",
      "subject_action_increment": "Describe exact new visual delta added in this keyframe index.",
      "motion_delta_description": "Exact motion vector or dynamic movement arrow direction relative to previous keyframe (e.g., 'Curved yellow arrow shoots from left to right at 45 degrees', or 'Static scene with new pop-up inset card').",
      "environment_coordinates": "Verbatim string definition from Section 2 (e.g., 'ENVIRONMENT_ROOM: ...', 'ISOLATED_WHITE: ...', or 'CINEMATIC_PACING: ...').",
      "composition_layout": "Spatial arrangement & rule-of-thirds framing (e.g., 'Orthographic front view, rule of thirds: Subject on left, target on right', 'Centered focal point', or 'Dual split screen layout').",
      "text_overlay_arabic": "Exact Arabic text string in Arabic script (e.g., 'كيف يعمل هذا؟' or 'السر الحقيقي'), OR 'NONE'.",
      "color_palette_mood": "Base color harmony lock (e.g., 'Cool desaturated slate palette (#2B303A), crisp white background (#FFFFFF), neutral grey tones').",
      "lighting_setup": "Flat studio vector lighting, clean high contrast, OR mood preset (e.g., 'Playful / Optimistic', 'Educational / Informative', 'Serious / Tension').",
      "accent_color_hook": "Select exactly ONE context-appropriate vibrant pop accent color matching the topic domain: Sky Blue/Cyan for tech/signals, Neon Green for data/growth, Vibrant Yellow/Gold for arrows/currency/highlights, Crimson Red for medical/heat/warnings, or Electric Violet for AI/quantum.",
      "camera_specifications": "Camera angle/lens specification (e.g., 'Flat 2D front view framing, 16:9 aspect ratio', or 'Vintage 35mm fisheye lens at f/8', or 'Hasselblad H6D-100c with Macro 120mm f/4').",
      "style_anchor": "2D webcomic vector style, thick clean black outlines, flat base colors, simple clean lighting, high contrast, crisp line art, cool-toned desaturated slate palette with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 aspect ratio.",
      "aspect_ratio_and_resolution": "16:9 widescreen format, 4K resolution, ultra-clean vector line art, hyper-sharp focus.",
      "negative": {
        "content": ["English text", "Latin alphabet", "3D shading", "photorealistic textures", "realistic human faces", "real photos", "3D renders", "complex backgrounds", "distracting elements"],
        "style": "No 3D render style, no real photos, no text, no letters, no watermarks, no gibberish, no AI signatures"
      }
    }
  }
]
```

---
Reply EXACTLY with: **"JSON System Ready. Awaiting chunks."**
"""
                        final_system_prompt = generic_monolithic_template.replace("[INJECT_ROADMAP_HERE]", master_roadmap)
                        
                        gemini_page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                        time.sleep(3)
                        select_gemini_model(gemini_page, target_planner_model)
                        
                        initial_count = gemini_page.locator("model-response").count()
                        input_box = gemini_page.locator("rich-textarea div[contenteditable='true']").first
                        input_box.fill(final_system_prompt)
                        input_box.press("Control+Enter")
                        wait_for_gemini_response(gemini_page, initial_count, min_length=20)

                        for chunk_idx, start_idx, chunk in chunks_to_process:
                            print(f"\nVerifying Gemini idle status before Chunk {chunk_idx}...")
                            wait_until_gemini_idle(gemini_page)

                            print(f"Planning Chunk {chunk_idx}/{len(chunks)} (Indices {start_idx}-{start_idx+len(chunk)-1})...")
                            chunk_text = "\n".join([f"Index {start_idx+i} ({timestamps[start_idx+i-1]}): {s}" for i, s in enumerate(chunk)])
                            
                            initial_count = gemini_page.locator("model-response").count()
                            payload = f"Generate the JSON array for this chunk:\n\n{chunk_text}"
                            
                            input_box = gemini_page.locator("rich-textarea div[contenteditable='true']").first
                            input_box.fill(payload)
                            time.sleep(1)
                            input_box.press("Control+Enter")
                            
                            resp = wait_for_gemini_response(gemini_page, initial_count, timeout_seconds=180)
                            if resp:
                                clean_resp = re.sub(r'```json\s*', '', resp, flags=re.IGNORECASE)
                                clean_resp = re.sub(r'```\s*', '', clean_resp).strip()
                                with open(prompts_file, "a", encoding="utf-8") as f:
                                    f.write(clean_resp + "\n\n")
                                print(f"✅ Chunk {chunk_idx} successfully parsed and saved.")
                            else:
                                print(f"❌ Error: Failed to get JSON response for chunk {chunk_idx}")
                            
                    # Refresh parsed prompts after chunk generation
                    storyboard_prompts = parse_json_prompts(prompts_file)
                    save_sorted_prompts_file(storyboard_prompts, prompts_file)

                    # ---------------------------------------------------------
                    # PHASE 2: IMAGE RENDERING (GOOGLE FLOW WITH FREEZE PROTECTION)
                    # ---------------------------------------------------------
                    total_frames = len(storyboard_prompts)
                    if total_frames == 0: continue
                    
                    print(f"\n[PHASE 2] Rendering {total_frames} images via Google Flow...")
                    flow_page.bring_to_front()
                    
                    # Save workspace URL file specific to active Chrome profile index
                    url_checkpoint_file = os.path.join(subfolder, f"flow_workspace_url_profile_{current_profile_idx}.txt")
                    saved_project_url = None
                    if os.path.exists(url_checkpoint_file):
                        with open(url_checkpoint_file, "r") as f:
                            saved_project_url = f.read().strip()
                            
                    active_project_url = setup_flow_ui(flow_page, target_flow_model, target_flow_count, saved_project_url)
                    
                    if "project" in active_project_url:
                        with open(url_checkpoint_file, "w") as f:
                            f.write(active_project_url)

                    executed_generations_count = 0
                    prev_prompt_text = ""
                    prev_idx = None
                    ts_counts = {}  # Tracks occurrence count for duplicate multi-frame timestamps

                    for current_run, prompt_item in enumerate(storyboard_prompts, 1):
                        idx, ts, prompt_text, seq_type, frame_idx, total_frames = prompt_item[:6]
                        # Use timestamp directly from flow_prompts item (ts)
                        ts_source = ts if ts else (timestamps[idx - 1] if 0 <= (idx - 1) < len(timestamps) else "")
                        clean_ts = ts_source.replace("[", "").replace("]", "").replace(":", "_").strip()

                        # Multi-frame suffix logic (e.g. 00_42.png for Frame 1, 00_42_2.png for Frame 2)
                        if clean_ts:
                            occ = ts_counts.get(clean_ts, 0) + 1
                            ts_counts[clean_ts] = occ
                            image_name = f"{clean_ts}.png" if occ == 1 else f"{clean_ts}_{occ}.png"
                        else:
                            occ = 1  # <--- Added initialization
                            image_name = f"sentence_{idx}.png"

                        save_path = os.path.join(image_dir, image_name)

                        # Check if this specific frame image already exists
                        if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                            print(f"[SKIP] Frame {idx} ({image_name}) exists.")
                            prev_prompt_text = prompt_text
                            prev_idx = idx
                            continue

                        executed_generations_count += 1
                        if executed_generations_count > 1 and (executed_generations_count - 1) % reset_loop_limit == 0:
                            print(f"\n[RESET] Refreshing Flow UI (Limit: {reset_loop_limit})...")
                            flow_page.reload()
                            setup_flow_ui(flow_page, target_flow_model, target_flow_count, active_project_url)

                        print(f"Rendering Frame {idx} ({image_name})...")
                        success = False
                        try:
                            for attempt in range(1, 4):
                                try:
                                    # --- CONTINUITY CHAINING PAYLOAD ---
                                    multiframe_seq_types = [
                                        "STOP_MOTION_SET", "THEME_SET_CONTINUITY", "PROGRESSIVE_BUILD_SET",
                                        "CAMERA_ZOOM_SEQUENCE", "PANORAMIC_PAN_SET", "CHARACTER_ACTION_ARC",
                                        "BEFORE_AFTER_TRANSFORMATION", "COMIC_MULTI_PANEL"
                                    ]

                                    is_multiframe_continuity = (
                                        (seq_type in multiframe_seq_types and frame_idx > 1)
                                        or (occ > 1)
                                        or (frame_idx > 1)
                                    )

                                    if is_multiframe_continuity and prev_prompt_text and prev_idx is not None:
                                        payload_text = (
                                            f"[STRICT ANIMATION CONTINUITY DIRECTIVE]\n"
                                            f"This image is Frame Index {idx} (Frame {frame_idx} of set) directly following attached Frame Index {prev_idx}.\n\n"
                                            f"[ATTACHED BASELINE IMAGE - FRAME {prev_idx}]: Refer to attached image chip.\n"
                                            f"[PREVIOUS FRAME PROMPT]: {prev_prompt_text}\n\n"
                                            f"[TARGET FRAME {idx} DELTA ACTION]:\n{prompt_text}\n\n"
                                            f"CRITICAL REQUIREMENT: Maintain 100% visual identity consistency with attached Frame {prev_idx}. "
                                            f"Keep character facial features, hair, charcoal hoodie, background layout, lighting, and camera angle IDENTICAL. "
                                            f"Execute ONLY the new delta movement specified for Frame {idx}."
                                        )
                                    else:
                                        payload_text = f"Please generate a standalone image for this JSON prompt:\n\n{prompt_text}"

                                    # Apply the Arabic sanitizer right before submitting
                                    payload_text = enforce_arabic_in_prompt(payload_text)

                                    flow_page.wait_for_timeout(1000)
                                    pre_image_srcs = set()
                                    for i in range(flow_page.locator("img").count()):
                                        try:
                                            src = flow_page.locator("img").nth(i).get_attribute("src")
                                            if src: pre_image_srcs.add(src)
                                        except: pass
                                    # Multi-frame sequence types that require continuity image anchoring
                                    multiframe_seq_types = [
                                        "STOP_MOTION_SET", "THEME_SET_CONTINUITY", "PROGRESSIVE_BUILD_SET",
                                        "CAMERA_ZOOM_SEQUENCE", "PANORAMIC_PAN_SET", "CHARACTER_ACTION_ARC",
                                        "BEFORE_AFTER_TRANSFORMATION", "COMIC_MULTI_PANEL"
                                    ]

                                    is_multiframe_continuity = (
                                        (seq_type in multiframe_seq_types and frame_idx > 1)
                                        or (occ > 1)
                                        or (frame_idx > 1)
                                    )

                                    if is_multiframe_continuity:
                                        attach_previous_image_to_prompt(flow_page)
                                    else:
                                        clear_attached_prompt_chips(flow_page)

                                    input_box = None
                                    selectors = ["textarea[placeholder*='What do you want' i]", "input[placeholder*='What do you want' i]", "div[contenteditable='true']", "textarea"]
                                    for sel in selectors:
                                        loc = flow_page.locator(sel).first
                                        if loc.is_visible():
                                            input_box = loc
                                            break

                                    if not input_box:
                                        input_box = flow_page.get_by_placeholder(re.compile(r"(what do you want|describe|صف|أنشئ|اكتب)", re.IGNORECASE)).first

                                    if not input_box or not input_box.is_visible():
                                        raise Exception("Could not find Google Flow prompt input box on page.")

                                    input_box.scroll_into_view_if_needed()
                                    input_box.click(force=True)
                                    time.sleep(0.5)

                                    flow_page.keyboard.press("Control+a")
                                    flow_page.keyboard.press("Backspace")
                                    time.sleep(0.5)

                                    flow_page.keyboard.insert_text(payload_text)
                                    time.sleep(1)
                                    flow_page.keyboard.press("Enter")

                                    print(f"  Attempt {attempt}: Prompt submitted. Monitoring generation engine...")
                                    time.sleep(2)

                                    has_started = False
                                    try:
                                        if flow_page.locator("[role='progressbar']").is_visible():
                                            has_started = True
                                        else:
                                            for load_idx in range(flow_page.get_by_text(re.compile(r"\d+%")).count()):
                                                if flow_page.get_by_text(re.compile(r"\d+%")).nth(load_idx).is_visible():
                                                    has_started = True
                                                    break
                                    except Exception: pass

                                    if not has_started:
                                        box_text = ""
                                        try:
                                            box_text = input_box.evaluate("el => el.value || el.innerText || ''").strip()
                                        except Exception: pass

                                        if box_text and "what do you want" not in box_text.lower():
                                            print("  🔄 Submission not detected. Re-triggering Enter...")
                                            flow_page.keyboard.press("Enter")
                                            time.sleep(2)

                                    render_success = False
                                    final_generated_locators = []
                                    start_gen_time = time.time()
                                    max_wait_seconds = 180
                                    generation_has_started = False
                                    last_activity_time = time.time()

                                    while time.time() - start_gen_time < max_wait_seconds:
                                        error_locators = flow_page.get_by_text(re.compile(r"(unusual activity|couldn't generate|failed to generate|policy violation)", re.IGNORECASE))
                                        for err_idx in range(error_locators.count()):
                                            if error_locators.nth(err_idx).is_visible():
                                                error_msg = error_locators.nth(err_idx).inner_text()
                                                print(f"  ⚠️ Google Flow rejected the prompt: {error_msg}")
                                                raise Exception("Generation failed due to API rejection or UI error.")

                                        failed_media_locator = flow_page.get_by_text("Something went wrong loading your media")
                                        if failed_media_locator.is_visible():
                                            print("  ⚠️ Detected: 'Something went wrong loading your media' container.")
                                            card_retry_success = False
                                            for retry_attempt in range(1, 4):
                                                try:
                                                    retry_btn = flow_page.locator("button:has-text('Retry'), button:has(svg)").filter(has=flow_page.locator("path")).last
                                                    if retry_btn.is_visible():
                                                        print(f"  🔄 Clicking Google Flow's card retry button (Attempt {retry_attempt}/3)...")
                                                        retry_btn.click(force=True)
                                                        time.sleep(5)
                                                        if not failed_media_locator.is_visible():
                                                            print("  🟢 Card retry succeeded! Continuing monitoring...")
                                                            card_retry_success = True
                                                            break
                                                except Exception: pass
                                                time.sleep(2)

                                            if not card_retry_success and failed_media_locator.is_visible():
                                                raise Exception("Media loading failed completely on this card.")

                                        is_loading = False
                                        loading_locators = flow_page.get_by_text(re.compile(r"\d+%"))
                                        for load_idx in range(loading_locators.count()):
                                            if loading_locators.nth(load_idx).is_visible():
                                                is_loading = True
                                                break
                                        if flow_page.locator("[role='progressbar']").is_visible():
                                            is_loading = True

                                        if is_loading:
                                            if not generation_has_started:
                                                print("  🟢 Generation activity detected in DOM. Watching progress...")
                                                generation_has_started = True
                                            last_activity_time = time.time()

                                        new_images = []
                                        for i in range(flow_page.locator("img").count()):
                                            try:
                                                loc = flow_page.locator("img").nth(i)
                                                src = loc.get_attribute("src")
                                                if src and src not in pre_image_srcs:
                                                    is_complete = loc.evaluate("el => el.complete && el.naturalWidth > 200")
                                                    if is_complete:
                                                        new_images.append(loc)
                                            except: pass

                                        if len(new_images) > 0 and not is_loading:
                                            print("  ✅ New image render 100% complete! Waiting for overlay to clear...")
                                            time.sleep(5)
                                            final_generated_locators = new_images
                                            render_success = True
                                            break

                                        if not generation_has_started and (time.time() - start_gen_time > 120):
                                            print("  ⚠️ No generation card/progress appeared after 120s. Forcing reload...")
                                            raise Exception("Google Flow initial queue stalled.")

                                        if generation_has_started and (time.time() - last_activity_time > 120):
                                            print("  ⚠️ Progress froze for 120s mid-generation. Forcing reload...")
                                            raise Exception("Google Flow rendering froze mid-progress.")

                                        time.sleep(2)

                                    expected_new = int(re.sub(r'\D', '', target_flow_count))
                                    if expected_new < 1: expected_new = 1

                                    images_to_extract = min(len(final_generated_locators), expected_new)
                                    print(f"  Render 100% Complete! Extracting {images_to_extract} image(s)...")

                                    download_attempt_success = False

                                    for i in range(images_to_extract):
                                        img_locator = final_generated_locators[i]
                                        is_duplicate = (i > 0)
                                        if is_duplicate:
                                            current_save_path = os.path.join(dup_dir, f"{clean_ts}_duplicate_{i}.png")
                                        else:
                                            current_save_path = save_path

                                        img_locator.scroll_into_view_if_needed()
                                        time.sleep(0.5)

                                        try:
                                            js_code = """
                                            async (img) => {
                                                if (img.src && img.src.startsWith('data:image')) {
                                                    return img.src;
                                                }
                                                try {
                                                    const response = await fetch(img.src);
                                                    const blob = await response.blob();
                                                    return new Promise((resolve) => {
                                                        const reader = new FileReader();
                                                        reader.onloadend = () => resolve(reader.result);
                                                        reader.readAsDataURL(blob);
                                                    });
                                                } catch (e) {
                                                    const canvas = document.createElement('canvas');
                                                    canvas.width = img.naturalWidth || img.width;
                                                    canvas.height = img.naturalHeight || img.height;
                                                    const ctx = canvas.getContext('2d');
                                                    ctx.drawImage(img, 0, 0);
                                                    return canvas.toDataURL('image/png');
                                                }
                                            }
                                            """
                                            base64_data_url = img_locator.evaluate(js_code)

                                            if base64_data_url and isinstance(base64_data_url, str) and "," in base64_data_url:
                                                base64_string = base64_data_url.split(",")[1]
                                                img_bytes = base64.b64decode(base64_string)

                                                with open(current_save_path, "wb") as f:
                                                    f.write(img_bytes)

                                                if os.path.exists(current_save_path) and os.path.getsize(current_save_path) > 100:
                                                    print(f"  ✅ Saved: {os.path.basename(current_save_path)}")
                                                    if not is_duplicate:
                                                        download_attempt_success = True
                                            else:
                                                print("  ⚠️ Failed to parse Base64 data from browser.")
                                        except Exception as e:
                                            print(f"  ⚠️ Direct extraction failed: {e}")

                                    if download_attempt_success:
                                        success = True
                                        prev_prompt_text = prompt_text
                                        prev_idx = idx
                                        break

                                except PlaywrightTimeoutError:
                                    print("  ⚠️ Playwright Timeout Error.")
                                except Exception as e:
                                    print(f"  ⚠️ Error: {e}")

                                if not success and attempt < 3:
                                    print("  🔄 Clearing UI error state before retry...")
                                    time.sleep(3)
                                    flow_page.goto(active_project_url, wait_until="domcontentloaded")
                                    time.sleep(3)

                            if not success:
                                if accounts_enabled:
                                    print(f"\n[FAILOVER ALERT] Flow rendering failed 3 times. Rotating account...")
                                    rotate_profile_index()
                                    kill_cdp_chrome()
                                    failover_triggered = True
                                    break
                                else:
                                    print(f"❌ Frame {idx} failed completely. Skipping.")
                        except Exception as e:
                            print(f"[RECOVERY] Framework error: {e}")
                            consecutive_failures += 1
                            if not accounts_enabled and consecutive_failures >= max_retries_no_switch:
                                print(f"[FATAL ERROR] Reached maximum retries ({max_retries_no_switch}) with account switching disabled. Exiting.")
                                sys.exit(1)
                            failover_triggered = True

                        if failover_triggered:
                            print("\n[SYSTEM] Profile rotated. Restarting browser session for current subfolder...\n")
                            time.sleep(3)
                            break  # Break out of subfolder loop so outer while-loop retries current folder with new account

        except Exception as e:
            print(f"[MAIN] Fatal orchestration error: {e}")
            time.sleep(5)
            continue

if __name__ == "__main__":
    main()