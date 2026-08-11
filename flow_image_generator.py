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
    """Sanitizes prompt text: replaces common English layout phrases with Arabic and appends English negative directives."""
    replacements = {
        r'(?i)"CHALLENGER\s*(\d+)?:?\s*([^"]*)"': r'"التحدي \1: \2"',
        r'(?i)CHALLENGER\s*(\d+)': r'التحدي \1',
        r'(?i)"COLLECTION BOARD"': r'"لوحة التجميع"',
        r'(?i)COLLECTION BOARD': r'لوحة التجميع',
        r'(?i)"SPEED ROUND"': r'"الجولة السريعة"',
        r'(?i)SPEED ROUND': r'الجولة السريعة',
        r'(?i)"DIAGRAM"': r'"مخطط"',
        r'(?i)English text': r'Arabic text',
        r'(?i)English typography': r'Arabic typography',
        r'(?i)English labels': r'Arabic labels',
    }
    
    sanitized = prompt_text
    for pattern, repl in replacements.items():
        sanitized = re.sub(pattern, repl, sanitized)
        
    # Append explicit Arabic font directive and English negative directive
    arabic_directive = (
        "\n\n[MANDATORY TYPOGRAPHY RULE]: All visible on-screen text, titles, labels, "
        "and typography MUST be written in crisp ARABIC script. "
        "Do NOT render any English/Latin letters. "
        "Negative prompt: English text, English typography, Latin characters, English letters, English words."
    )
    
    return sanitized + arabic_directive

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
                    prompts.append((idx, ts, prompt, seq_type, frame_idx, total_frames))
            except Exception:
                continue

    # Deduplicate and sort by index
    prompts_dict = {}
    for p in prompts:
        idx = p[0]  # FIX #1: Access index by tuple position
        prompts_dict[idx] = p

    sorted_prompts = [prompts_dict[k] for k in sorted(prompts_dict.keys())]
    return sorted_prompts

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

    if project_url and "project" in project_url:
        print(f"\n[FLOW] Resuming existing workspace: {project_url}")
        page.goto(project_url, wait_until="domcontentloaded", timeout=60000)
        wake_up_page() 
        time.sleep(3)
    else:
        print(f"\n[FLOW] Configuring NEW workspace (Model: {target_flow_model} | Count: {target_flow_count})...")
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

    # 3. Turn Agent OFF
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
                model_option = page.locator(f"text='{target_flow_model}'").last
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
            
            # Set 16:9
            ratio_btn = page.locator("button:has-text('16:9'), div:has-text('16:9')").first
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

    while True:
        failover_triggered = False
        
        # Define variable OUTSIDE the try block to satisfy Pylance scope rules
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
                                match = re.match(r"^\[([\d:]+)\]\s*(.*)", line.strip())
                                if match:
                                    timestamps.append(f"[{match.group(1)}]")
                                    sentences.append(match.group(2).strip())

                    storyboard_prompts = parse_json_prompts(prompts_file)

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
1. **HOST (Sparing, <25%)**: 2D faceless white head with thick black round glasses, wearing a red-and-white Shemagh (Keffiyeh) neck scarf and a dark charcoal hoodie over a white shirt.
2. **USER (Main Actor)**: Minimalist stick figure, white circular head, vertical line eyes (`||`), black t-shirt, line limbs.
3. **MAIN CHARACTER (SINGLE)**: Main character alone.
4. **SECONDARY CHARACTERS (DUO / MULTI)**: Main character interacting with a distinct, 2D secondary character.
5. **CROWD / GROUPS (GROUP)**: An active crowd of stick-figures.
6. **ABSENT**: For standalone diagrams, conceptual diagrams, hardware devices, B-roll, UI HUDs, typography, pure typography scenes, or isolated objects.

### PROGRESSIVE CONCEPT BUILD-UP RULE (CRITICAL FOR TECHNICAL EXPLANATIONS)
Whenever the script explains a process, mechanism, or flow (e.g., how Wi-Fi transmits data, signal pathways, data conversion):
- **DO NOT** condense it into 1 frame.
- **BUILD IT PROGRESSIVELY** across an extended chain of consecutive keyframes (`PROGRESSIVE_BUILD_SET` or `STOP_MOTION_SET`).
- - Accumulate visual elements step-by-step (e.g., Base device -> Arrow -> Data payload -> Signal wave -> Receiving device -> Result card):
  - *Step 1:* Base device appears (e.g., Router).
  - *Step 2:* Directional arrow shoots out.
  - *Step 3:* Floating data payload appears (Binary 0 and 1).
  - *Step 4:* Signal waves burst outward.
  - *Step 5:* Receiving device catches signal (e.g., Smartphone).
  - *Step 6:* Final output/result card pops up (e.g., Cat video thumbnail).

### STORYBOARD BEAT-BY-BEAT PRODUCTION ARC
When designing a scene sequence, map the progression to this structural arc:
- OPENER: Wide establishing shot introducing the environment, the main character, and the core goal/object.
- PREPARATION: Medium shot revealing the tools, steps, or concepts needed.
- FIRST ACTION: Close-up showing the process beginning with visible, clear progress.
- TRANSFORMATION: Extreme close-up of the most visually satisfying, peak moment.
- PROGRESS: Medium close-up showing continuation and improvement.
- FINAL STEP: Dramatic close shot building high anticipation.
- FINAL REVEAL: Wide cinematic shot showing the finished result, character reaction, and a satisfying wrap-up.

### SEQUENCE TYPES
STANDALONE | PROGRESSIVE_BUILD_SET | THEME_SET_CONTINUITY | STOP_MOTION_SET | CHALLENGER_CARD | COLLECTION_BOARD | SPEED_ROUND_HUD | DIAGRAM_BREAKDOWN | INFOGRAPHIC_PHOTO_INSET | FLASHBACK_STORY | SPLIT_PANEL | TYPOGRAPHY_SCENE | POV

### LAYOUT TOKENS
- **ISOLATED_WHITE**: Seamless pure white background (`#FFFFFF`).
- **ENVIRONMENT_ROOM**: Cartoon room, beige tiled floor, brown wooden table.
- **CINEMATIC_PACING**: Use wide-angle, cinematic framing for dramatic reveals.

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

                        chunk_size = 15
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
   - **HOST**: `"HOST: 2D faceless character, smooth featureless white head with prominent thick black round glasses, wearing a traditional red-and-white patterned Shemagh (Keffiyeh) draped around the neck like a scarf, wearing a dark charcoal hoodie over a plain white t-shirt."` (Use sparingly, <25%).
   - **USER**: `"USER: Minimalist 2D stick figure, white circular head with simple vertical line eyes (||), wearing a plain black t-shirt with thin black line-art limbs."`
   - **MAIN CHARACTER**: `"SINGLE: A simple 2D character. Head is a uniform white circle with no nose or ears. Mouth is a single expressive black vector stroke. Exactly 3 to 5 thin black hair strands curving from the top of the scalp (bald otherwise). Wears an unbranded charcoal-grey hoodie (with a visible hood resting on the shoulders) and dark sweatpants. Arms and legs are simple, uniform black line art.`"
   - **SECONDARY CHARACTERS**: `"DUO / MULTI: Same 2D vector style. To distinguish them, they must have a flat-colored circle head (e.g., pale flat yellow), different hair configurations, or a simple flat-blue or flat-maroon hoodie. They must be drawn interacting directly with the main character (e.g., talking, pointing, handing over an object)."`
   - **CROWD / GROUPS**: `"GROUP: A background collection of multiple minimalist circle-head stick figures interacting naturally."`
   - **ABSENT**: `"ABSENT"`

2. **VERBATIM LAYOUT TOKENS**:
   - **ENVIRONMENT_ROOM**: `"ENVIRONMENT_ROOM: Simple 2D cartoon room set in a flat orthographic front-facing perspective. Off-white plain background wall with a dark horizontal dividing line, light beige square tiled floor with subtle brown grid lines, and a plain rectangular brown wooden four-legged table placed horizontally in the center foreground."`
   - **ISOLATED_WHITE**: `"ISOLATED_WHITE: Isolated subject on a seamless, pure solid white background (#FFFFFF) with no shadows or wall textures."`
   - **CINEMATIC_PACING**: `"CINEMATIC_PACING: Wide-angle cinematic framing for dramatic reveals, emphasizing depth and perspective."`

3. **PROGRESSIVE ELEMENT ACCUMULATION**:
   - For `PROGRESSIVE_BUILD_SET` or `STOP_MOTION_SET` sequences:
     - **RETAIN** all visual elements from Frame N-1 (device position, background, previous arrows).
     - **APPEND** ONLY the new visual delta for Frame N (e.g., adding binary numbers `0` and `1`, signal arcs, or an inset video card).
     - Keep canvas scale, camera angle, and object coordinates 100% IDENTICAL across the chain.
    - For `CINEMATIC_PACING` VERBATIM LAYOUT TOKENS Settings:
    1. **CAMERA RECIPES & PERSPECTIVES**
       Even though this is a 2D webcomic style, simulate physical camera properties to create depth:
     - Extreme Wide / Establishing: Simulated on a "Vintage 35mm fisheye lens at f/8" to create heavy barrel distortion and dramatic scale.
     - Close-Ups / Emotional Metaphors: Simulated on a "Hasselblad H6D-100c with a Macro 120mm f/4 lens at f/2.8, ISO 100" to create a shallow depth of field, sharp subject textures, and a soft-focus background.
     - High/Low Angles: Simulated on a "Sony A7III with a 35mm lens, f/4, ISO 400" for crisp, clean framing.
     - Point-of-View (POV): Frame looking through the character's eyes (e.g., showing their 2D hands holding a map or device in the foreground, with other characters visible ahead).
     2. **MOOD PRESETS**
       You must dynamically shift the color palette and lighting to match the emotional tone of the script:
     - Playful / Optimistic: Warm pastel-yellow or light sky-blue flat background, soft diffused lighting, bright tones.
     - Educational / Informative: Crisp, neutral light-grey flat background, clear even studio lighting.
     - Serious / Tension: Deep charcoal or slate-blue background, stark top-down spotlights, high contrast.
     - Sad / Melancholy: Desaturated dark grey or cold blue tones, cast shadows, dim lighting.
     - Hopeful: Gentle lavender or soft cream background, warm volumetric rim-light.
     
4. **RETENTION & COMPOSITION RULES**:
   - **LAYOUT ROTATION**: Max 15 consecutive identical layouts/sequence types. Rotate constantly.
   - **LOCKED SET CONTINUITY**: For multi-frame sets (up to 15 frames), lock room/camera coordinates verbatim; mutate ONLY `subject_action_increment`.

5. **SELECTIVE ARABIC TEXT**:
   - Render bold rounded Arabic text ONLY on major emphasis frames; set to `"NONE"` otherwise.
   - Render Arabic text ONLY on essential keyframes (key concepts, headers, main terms).
   - Set `text_overlay_arabic` to `"NONE"` for routine action/narrative frames.
   - Set `text_overlay_arabic` to `"Text/Question Overlay"` When a major question or statement is posed, instantly cut to a "Text Overlay Blur" frame to break the visual pattern and emphasize the words.
   - Set `text_overlay_arabic` to `"Typography Punchline"` When the script hits a punchline, transitional section, or a new chapter, drop all characters. Create a pure typography frame featuring bold, glowing Arabic text on a dark, atmospheric background.
   - Set `text_overlay_arabic` to `"Explanations/Typography"` When demonstrating a concept, displaying a question/statement, or showing a transitional chapter/punchline, place bold, sharp Arabic text in exact quotes (e.g., "النجاح") in the center of the scene. Keep the background clean and empty around the text to prevent rendering errors.

6. **STYLE ANCHOR**: `"2D webcomic vector style, thick clean black outlines, flat base colors, simple clean lighting, high contrast, crisp line art, cool-toned desaturated slate palette with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 aspect ratio."`

7. **JSON SYNTAX**: Output valid JSON array only. Escape quotes as `\"`.

---

### JSON SCHEMA CONTRACT

```json
[
  {
    "index": 1,
    "timestamp": "[00:00]",
    "sequence_type": "STANDALONE | PROGRESSIVE_BUILD_SET | THEME_SET_CONTINUITY | STOP_MOTION_SET | CHALLENGER_CARD | COLLECTION_BOARD | SPEED_ROUND_HUD | DIAGRAM_BREAKDOWN | INFOGRAPHIC_PHOTO_INSET | FLASHBACK_STORY | SPLIT_PANEL | TYPOGRAPHY_SCENE | POV",
    "layout_classification": "ISOLATED_WHITE | ENVIRONMENT_ROOM | CINEMATIC_PACING",
    "sequence_metadata": {
      "set_id": "SET_01",
      "frame_index": 1,
      "total_frames_in_set": 15
    },
    "visual_prompt": {
      "subject_details": "Verbatim character token (HOST, USER, MAIN CHARACTER 'SINGLE', SECONDARY CHARACTERS 'DUO / MULTI', CROWD / GROUPS 'GROUP', or ABSENT).",
      "subject_action_increment": "Describe exact new visual delta added in this keyframe index.",
      "environment_coordinates": "Verbatim LAYOUT TOKEN.",
      "text_overlay_arabic": "Arabic text string, 'Text/Question', 'Typography Punchline', 'Explanations/Typography', OR 'NONE'.",
      "lighting_setup": "Flat studio vector lighting, clean high contrast, OR 'MOOD PRESETS'.",
      "accent_color_hook": "Single high-contrast glowing neon/vibrant pop element.",
      "camera_specifications": "Flat 2D front view framing, 16:9 aspect ratio, OR 'CAMERA RECIPES & PERSPECTIVES' OR '[CAMERA TAG] Shot on [CAMERA BODY] with a [LENS] at f/[APERTURE], ISO [ISO]'.",
      "Style Anchor": "2D webcomic vector style, thick clean black outlines, flat base colors, simple clean lighting, high contrast, crisp line art, cool-toned desaturated slate palette with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 aspect ratio.",
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
                                with open(prompts_file, "a", encoding="utf-8") as f:
                                    f.write(resp + "\n\n")
                                print(f"✅ Chunk {chunk_idx} successfully parsed and saved.")
                            else:
                                print(f"❌ Error: Failed to get JSON response for chunk {chunk_idx}")
                            
                    # Refresh parsed prompts after chunk generation
                    storyboard_prompts = parse_json_prompts(prompts_file)

                    # ---------------------------------------------------------
                    # PHASE 2: IMAGE RENDERING (GOOGLE FLOW WITH FREEZE PROTECTION)
                    # ---------------------------------------------------------
                    total_frames = len(storyboard_prompts)
                    if total_frames == 0: continue
                    
                    print(f"\n[PHASE 2] Rendering {total_frames} images via Google Flow...")
                    flow_page.bring_to_front()
                    
                    url_checkpoint_file = os.path.join(subfolder, "flow_workspace_url.txt")
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
                        idx, ts, prompt_text, seq_type, frame_idx, total_frames = prompt_item
                        # Use timestamp directly from flow_prompts item (ts)
                        ts_source = ts if ts else (timestamps[idx - 1] if 0 <= (idx - 1) < len(timestamps) else "")
                        clean_ts = ts_source.replace("[", "").replace("]", "").replace(":", "_").strip()

                        # Multi-frame suffix logic (e.g. 00_42.png for Frame 1, 00_42_2.png for Frame 2)
                        if clean_ts:
                            occ = ts_counts.get(clean_ts, 0) + 1
                            ts_counts[clean_ts] = occ
                            image_name = f"{clean_ts}.png" if occ == 1 else f"{clean_ts}_{occ}.png"
                        else:
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
                        for attempt in range(1, 4):
                            try:
                                # --- CONTINUITY CHAINING PAYLOAD ---
                                if prev_prompt_text and prev_idx is not None:
                                    payload_text = (
                                        f"[STRICT ANIMATION CONTINUITY DIRECTIVE]\n"
                                        f"This image is Frame Index {idx} in a continuous sequence directly after Frame Index {prev_idx}.\n\n"
                                        f"[PREVIOUS FRAME {prev_idx} BASELINE VISUAL]:\n{prev_prompt_text}\n\n"
                                        f"[TARGET FRAME {idx} DELTA ACTION INSTRUCTION]:\n{prompt_text}\n\n"
                                        f"CRITICAL REQUIREMENT: Maintain 100% visual identity consistency with Frame {prev_idx}. "
                                        f"Keep the character face, hair, charcoal hoodie, background environment, lighting setup, and camera angle EXACTLY IDENTICAL to Frame {prev_idx}. "
                                        f"Execute ONLY the new pose or movement specified in Frame {idx}."
                                    )
                                else:
                                    payload_text = f"Please generate exactly 1 image for this JSON prompt:\n\n{prompt_text}"

                                # Apply the Arabic sanitizer right before submitting
                                payload_text = enforce_arabic_in_prompt(payload_text)

                                flow_page.wait_for_timeout(1000)
                                pre_image_srcs = set()
                                for i in range(flow_page.locator("img").count()):
                                    try:
                                        src = flow_page.locator("img").nth(i).get_attribute("src")
                                        if src: pre_image_srcs.add(src)
                                    except: pass
                                # Check if this frame is frame #2 or #3 of a multi-frame set
                                # NEW CODE:
                                is_multiframe_continuity = (
                                    (seq_type in ["STOP_MOTION_SET", "THEME_SET_CONTINUITY"] and frame_idx > 1)
                                    or (occ > 1)
                                    or (frame_idx > 1)
                                )

                                if is_multiframe_continuity:
                                    # Attaches Frame N-1 image card and clears older attachments
                                    attach_previous_image_to_prompt(flow_page)
                                else:
                                    # Standalone frames stay clean
                                    clear_attached_prompt_chips(flow_page)
                                input_box = None
                                selectors = ["textarea[placeholder*='What do you want' i]", "input[placeholder*='What do you want' i]", "div[contenteditable='true']", "textarea"]
                                for sel in selectors:
                                    loc = flow_page.locator(sel).first
                                    if loc.is_visible():
                                        input_box = loc
                                        break
                                        
                                if not input_box:
                                    input_box = flow_page.get_by_placeholder(re.compile(r"what do you want", re.IGNORECASE)).first
                                
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

                                # --- Smart Submission Re-verification ---
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
                                
                                # Reduced max timeout loop with Freeze Protection
                                # --- DYNAMIC GENERATION WATCHER ---
                                render_success = False
                                final_generated_locators = []
                                start_gen_time = time.time()
                                max_wait_seconds = 180  # Total timeout for slow queue/server
                                generation_has_started = False
                                last_activity_time = time.time()
                                
                                while time.time() - start_gen_time < max_wait_seconds:
                                    # 1a. Rejection/Policy error checks
                                    error_locators = flow_page.get_by_text(re.compile(r"(unusual activity|couldn't generate|failed to generate|policy violation)", re.IGNORECASE))
                                    for err_idx in range(error_locators.count()):
                                        if error_locators.nth(err_idx).is_visible():
                                            error_msg = error_locators.nth(err_idx).inner_text()
                                            print(f"  ⚠️ Google Flow rejected the prompt: {error_msg}")
                                            raise Exception("Generation failed due to API rejection or UI error.")

                                    # 1b. Handle temporary "Something went wrong loading your media" glitch inline
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
                                                    time.sleep(5)  # Allow Google Flow 5 seconds to recover the media inline
                                                    if not failed_media_locator.is_visible():
                                                        print("  🟢 Card retry succeeded! Continuing monitoring...")
                                                        card_retry_success = True
                                                        break
                                            except Exception: pass
                                            time.sleep(2)
                                            
                                        if not card_retry_success and failed_media_locator.is_visible():
                                            raise Exception("Media loading failed completely on this card.")

                                    # 2. Check loading indicators (\d+% or progressbar)
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

                                    # 3. Check for completed new images
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

                                    # 4. Completion condition
                                    if len(new_images) > 0 and not is_loading:
                                        print("  ✅ New image render 100% complete! Waiting for overlay to clear...")
                                        time.sleep(5)  # <--- This 5-second sleep allows the grey overlay to vanish!
                                        final_generated_locators = new_images
                                        render_success = True
                                        break

                                    # 5. True Stall Protection: Only reload if 60s pass with zero DOM activity
                                    if not generation_has_started and (time.time() - start_gen_time > 60):
                                        print("  ⚠️ No generation card/progress appeared after 60s. Forcing reload...")
                                        raise Exception("Google Flow initial queue stalled.")

                                    if generation_has_started and (time.time() - last_activity_time > 60):
                                        print("  ⚠️ Progress froze for 60s mid-generation. Forcing reload...")
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
                                        base_name, ext = os.path.splitext(image_name)
                                        current_save_path = os.path.join(dup_dir, f"{base_name}_duplicate_{i}{ext}")
                                    else:
                                        current_save_path = save_path

                                    img_locator.scroll_into_view_if_needed()
                                    time.sleep(0.5)

                                    try:
                                        js_code = """
                                        async (img) => {
                                            const response = await fetch(img.src);
                                            const blob = await response.blob();
                                            return new Promise((resolve) => {
                                                const reader = new FileReader();
                                                reader.onloadend = () => resolve(reader.result);
                                                reader.readAsDataURL(blob);
                                            });
                                        }
                                        """
                                        base64_data_url = img_locator.evaluate(js_code)
                                        
                                        if "," in base64_data_url:
                                            base64_string = base64_data_url.split(",")[1]
                                            import base64
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
                            else: print(f"❌ Frame {idx} failed completely. Skipping.")

                    if failover_triggered: break
                if failover_triggered: break
                
        except Exception as e:
            print(f"[RECOVERY] Framework error: {e}")
            failover_triggered = True

        if failover_triggered:
            print("\n[SYSTEM] Reinitializing with new profile...\n")
            time.sleep(3)
            continue
        break

if __name__ == "__main__":
    main()