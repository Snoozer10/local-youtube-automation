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
def scan_batch_folders():
    runs_dir = "youtube_runs"
    batch_queue = []
    if os.path.exists(runs_dir):
        for item in os.listdir(runs_dir):
            subfolder = os.path.join(runs_dir, item)
            if os.path.isdir(subfolder):
                if os.path.exists(os.path.join(subfolder, "timestamped_transcript.txt")):
                    batch_queue.append(subfolder)
    return batch_queue

def parse_json_prompts(file_path):
    """Parses pure JSON arrays to extract nested deep-JSON prompts and timestamps."""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    prompts = []
    json_blocks = re.findall(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
    
    for block in json_blocks:
        try:
            data = json.loads(block)
            for item in data:
                idx = int(item.get("index", 0))
                ts = str(item.get("timestamp", "")).strip() # <-- NEW: Grab timestamp natively
                vp = item.get("visual_prompt", "")
                
                if isinstance(vp, dict):
                    prompt = json.dumps(vp, indent=2)
                else:
                    prompt = str(vp).strip()
                    
                if idx > 0 and prompt:
                    prompts.append((idx, ts, prompt)) # <-- NEW: Return a 3-part tuple
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse a JSON block: {e}")
   
    # Sort by index to ensure correct sequential order
    prompts.sort(key=lambda x: x[0])
    return prompts

def is_gemini_generating(page):
    stop_selectors = ["button[aria-label*='Stop' i]", "button[aria-label*='Cancel' i]"]
    for sel in stop_selectors:
        try:
            if page.locator(sel).first.is_visible(): return True
        except Exception: pass
    return False

def wait_for_gemini_response(page, initial_count, timeout_seconds=120):
    """Dynamic DOM monitor to prevent premature extraction and UI glitches."""
    start_time = time.time()
    new_response_found = False
    
    while time.time() - start_time < 30:
        try:
            if page.locator("model-response").count() > initial_count:
                new_response_found = True
                break
        except Exception: pass
        time.sleep(0.5)
        
    if not new_response_found: return None
        
    last_text = ""
    stable_count = 0
    
    while time.time() - start_time < timeout_seconds:
        try:
            last_response = page.locator("model-response").last
            last_response.scroll_into_view_if_needed(timeout=500)
            current_text = last_response.evaluate("el => el.innerText", timeout=5000).strip()
            
            if current_text and current_text == last_text:
                if is_gemini_generating(page):
                    stable_count = 0
                else:
                    stable_count += 1
                    if stable_count >= 4:
                        if current_text.startswith("Gemini said"):
                            current_text = current_text[len("Gemini said"):].strip()
                        return current_text
            else:
                last_text = current_text
                stable_count = 0
        except Exception: pass
        time.sleep(1)
    return None

def select_gemini_model(page, target_model="Flash-Lite"):
    """Robust model selection with fuzzy matching for hyphens/spaces."""
    print(f"\n[MODEL] Verifying Gemini model selection (Target: {target_model})...")
    model_btn = None
    
    # Handle Google's UI variations (e.g., "Flash-Lite" vs "Flash Lite")
    target_alt = target_model.replace("-", " ") 
    
    btn_selectors = [
        f"button:has-text('{target_model}')", 
        f"button:has-text('{target_alt}')",
        "button[aria-label*='model' i]", 
        "button[aria-label*='mode' i]"
    ]
    
    for sel in btn_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible() and loc.is_enabled():
                if "setting" in (loc.get_attribute("aria-label") or "").lower():
                    continue
                model_btn = loc
                break
        except Exception: continue
            
    if not model_btn: 
        print("Warning: Could not locate Gemini model selector button.")
        return False
        
    try:
        active_text = model_btn.inner_text().strip().lower()
        if target_model.lower() in active_text or target_alt.lower() in active_text:
            print(f"Success: Correct model '{target_model}' is already active.")
            return True
            
        print(f"Switching to '{target_model}'...")
        model_btn.click()
        time.sleep(2)
        
        dropdown_selectors = [
            f"mat-option:has-text('{target_model}')", f"mat-option:has-text('{target_alt}')",
            f"[role='menuitem']:has-text('{target_model}')", f"[role='menuitem']:has-text('{target_alt}')",
            f":text('{target_model}')", f":text('{target_alt}')"
        ]
        
        option_clicked = False
        for sel in dropdown_selectors:
            try:
                opt = page.locator(sel).first
                if opt.is_visible():
                    opt.click()
                    time.sleep(2)
                    option_clicked = True
                    print(f"Successfully selected model option: '{target_model}'")
                    break
            except Exception: continue
            
        if not option_clicked:
            print(f"Warning: Could not find '{target_model}' inside the dropdown.")
            page.keyboard.press("Escape") 
            
        return option_clicked
    except Exception as e: 
        print(f"Warning: Model selection failed: {e}")
        page.keyboard.press("Escape")
        return False

def setup_flow_ui(page, target_flow_model="Nano Banana Pro", target_flow_count="1x", project_url=None):
    """Navigates to Google Flow. Configures Model, Aspect Ratio, and Generation Count."""
    
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
    else:
        print(f"\n[FLOW] Configuring NEW workspace (Model: {target_flow_model} | Count: {target_flow_count})...")
        page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=60000)
        wake_up_page() 
        time.sleep(5) 

        # 1. Splash Screen Bypass
        try:
            splash_btn = page.locator("button:has-text('Create with Google Flow'), a:has-text('Create with Google Flow')").first
            if splash_btn.is_visible():
                splash_btn.click(force=True)
                time.sleep(5) 
                wake_up_page()
        except Exception: pass

        # 2. Aggressive '+ New project' Clicker
        try:
            print("[FLOW] Locating '+ New project' button...", flush=True)
            clicked = False
            
            # Use direct text matchers focusing only on visible elements
            candidates = [
                page.get_by_text("+ New project"),
                page.get_by_text("New project"),
                page.locator("div").filter(has_text=re.compile(r"\+?\s*New project", re.IGNORECASE))
            ]
            
            for candidate in candidates:
                # Loop backwards (equivalent to .last) to find the grid card
                count = candidate.count()
                for i in reversed(range(count)):
                    element = candidate.nth(i)
                    if element.is_visible():
                        print(f"[FLOW] Found clickable element. Attempting click...", flush=True)
                        element.scroll_into_view_if_needed()
                        element.click(force=True)
                        clicked = True
                        break
                if clicked:
                    break
            
            if not clicked:
                print("[FLOW] Standard selectors missed. Trying fallback locator...", flush=True)
                # Broader fallback to search the page
                fallback = page.locator("*:has-text('New project')").last
                if fallback.is_visible():
                    fallback.scroll_into_view_if_needed()
                    fallback.click(force=True)
                    clicked = True
            
            # Wait to ensure we transition to a project URL
            if clicked:
                print("[FLOW] Clicked. Waiting for project URL redirection...", flush=True)
                try: 
                    page.wait_for_url("**/project/**", timeout=20000)
                    print("[FLOW] Redirection success!", flush=True)
                except Exception: 
                    print("[FLOW] Warning: Redirection to /project/ timed out.", flush=True)
            else:
                print("[FLOW] Error: Could not locate any visible '+ New project' element.", flush=True)
        except Exception as e:
            print(f"[FLOW] Aggressive clicker encountered an exception: {e}", flush=True)

    time.sleep(4)
    current_workspace_url = page.url

    # 3. Turn Agent OFF
    try:
        agent_btn = page.locator("button:has-text('Agent')").first
        if agent_btn.is_visible():
            is_active = agent_btn.evaluate("el => el.getAttribute('aria-pressed') === 'true' || el.classList.contains('active')")
            if is_active:
                agent_btn.click(force=True)
                time.sleep(1)
    except Exception: pass

    # 4. Select Custom Flow Model (More robust selector)
    try:
        model_dropdown = page.locator("button:has-text('Nano Banana'), button:has-text('Imagen'), button[aria-haspopup='listbox']").first
        if model_dropdown.is_visible():
            if target_flow_model.lower() not in model_dropdown.inner_text().lower():
                print(f"[FLOW] Changing image model to '{target_flow_model}'...")
                model_dropdown.click(force=True)
                time.sleep(1)
                # Very broad text matcher to pierce through Google's nested spans
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

    return current_workspace_url # Return the URL so Python can save it

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
                    skip_planning = len(storyboard_prompts) == len(sentences)

                    # ---------------------------------------------------------
                    # PHASE 1: TWO-PASS MASTER ROADMAP & JSON PLANNING
                    # ---------------------------------------------------------
                    if not skip_planning and len(sentences) > 0:
                        print("\n[PHASE 1A] Analyzing full script to generate Master Continuity Roadmap...")
                        gemini_page.bring_to_front()
                        gemini_page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                        time.sleep(3)
                        select_gemini_model(gemini_page, target_planner_model)
                        
                        initial_count = gemini_page.locator("model-response").count()
                        input_box = gemini_page.locator("rich-textarea div[contenteditable='true']").first
                        
                        # 1. SEND THE FULL SCRIPT FOR GLOBAL ANALYSIS
                        full_script_text = " ".join(sentences)
                        roadmap_prompt = f"""You are an elite Video Systems Architect and Creative Director.
Analyze the following video script and construct a "Master Continuity Roadmap" for our image generation pipeline.

---

### SECTION 1: STORYBOARD BEAT-BY-BEAT PRODUCTION PLAN
Divide this entire script into timed, thematic blocks. For each block, define:
1. TIMED SECTION & PACING CUE: (e.g., "[00:00 - 00:05] The Hook"). Describe the visual speed and cut frequency.
2. VIRAL RETENTION PATTERN: Choose a pattern (e.g., "The Open Loop Reveal", "Pattern Interrupt", "The Visual Metaphor Drop", or "The Fast Climax Build").
3. CAMERA DIRECTION & ENERGY NOTE: Establish the movement scale and emotional intensity (e.g., Low Energy/Intimate, Rising Action/Tension, Peak Climax).

---

### SECTION 2: PRODUCTION ARC TEMPLATE
Map out where in the script to transition through these structural cinematic phases:
- OPENER: Wide establishing shot introducing the environment, the main character, and the core goal/object.
- PREPARATION: Medium shot revealing the tools, steps, or concepts needed.
- FIRST ACTION: Close-up showing the process beginning with visible, clear progress.
- TRANSFORMATION: Extreme close-up of the most satisfying, peak visual moment.
- PROGRESS: Medium close-up showing continuation and improvement.
- FINAL STEP: Dramatic close shot building high anticipation.
- FINAL REVEAL: Wide cinematic shot showing the finished result, character reaction, and a satisfying wrap-up.

---

### SECTION 3: EDITORIAL RULES & STOP-MOTION SEQUENCING
1. STOP-MOTION TRIGGER: Scan the timestamps. If consecutive sentences are <= 2 seconds apart, mark them as a "STOP-MOTION SET". Lock down the background, camera, and lighting, and change ONLY the character's micro-actions or moving assets in 2-second increments.
2. THE VIDEO EDITOR'S CUTS: Act like an editor. Plan complex, dynamic panel styles:
   - "Comparative Panel Reveal": Frame 1 shows only the Left Panel active while the Right Panel is blurred/blackout. Frame 2 reveals both active panels side-by-side.
   - "Text Overlay Blur": If there is a dramatic question or vital statement, design a frame with that text in sharp typography set against a heavily blurred version of the previous frame's background.
   - "Point-of-View (POV) Shift": Shift the camera to the main character's actual eyes, showing their hands interacting with objects or looking directly at another character.

---

### SECTION 4: CASTING, TYPOGRAPHY & MOOD DYNAMICS
1. MULTI-CHARACTER DYNAMICS: The main character must not be alone in every frame. Depending on script context, assign:
   - "SINGLE": Main character alone.
   - "DUO / MULTI": Main character interacting with a secondary character (use matching flat 2D style but with different hair, a flat blue hoodie, or distinct flat props).
   - "GROUP": A crowd of simple 2D stick-figures with circle heads.
   - "ABSENT (B-Roll)": Character is removed entirely for metaphor/object emphasis.
2. ARABIC TYPOGRAPHY SCENES: If a sentence features a punchline, new topic, new chapter, or transition, designate it as a "Typography Scene". Use no characters. Place a bold, glowing Arabic word/phrase in exact quotes (e.g., "النجاح") in the center of a moody background.
3. CONTEXTUAL MOOD SHIFTS: Establish mood presets based on script tone:
   - "Playful/Optimistic": Bright pastel backdrops, warm soft lighting.
   - "Serious/Tension": Deep slate and charcoal, stark top-down spotlights, high contrast.
   - "Melancholy/Sad": Heavily desaturated cold blue tones, long cast shadows.

SCRIPT:
{full_script_text}
"""
                        # Submit Roadmap Prompt
                        input_box.fill(roadmap_prompt)
                        input_box.press("Control+Enter")
                        
                        # Wait for Roadmap
                        master_roadmap = wait_for_gemini_response(gemini_page, initial_count, timeout_seconds=150)
                        if not master_roadmap:
                            raise Exception("Failed to generate Master Roadmap.")
                            
                        print("\n✅ Master Roadmap Generated. Initializing JSON chunking system...")
                        
                        # 2. INJECT ROADMAP INTO THE GENERIC MASTER TEMPLATE
                        generic_monolithic_template = """# SYSTEM PROMPT: ELITE JSON MONOLITHIC KEYFRAME ARCHITECT

You are translating a script chunk into visual prompts for a completely STATELESS image generator (Google Flow running Nano Banana Pro) [1].
Below is the MASTER CONTINUITY ROADMAP you just created. You must obey this roadmap strictly.

=== MASTER CONTINUITY ROADMAP ===
[INJECT_ROADMAP_HERE]
=================================

## STRICT FORMATTING & LAYOUT RULES

### 1. CHARACTER CASTING & BIOMETRICS (Based on Reference Images)
If a character is present, they must adhere to these rules:
- MAIN CHARACTER: Oversized white circle head, no nose/ears, simple expressive black vector mouth, exactly 3 thin black hair strands on top of the scalp, thin black line-art limbs, dark charcoal hoodie with kangaroo pocket, dark sweatpants.
- SECONDARY CHARACTERS: Same 2D vector style. To distinguish them, they must have a flat-colored circle head (e.g., pale flat yellow), different hair strands, or a simple flat-blue hoodie.
- GROUP/CROWD: Multiple minimalist circle-head stick figures interacting in the background.
- ABSENT: Completely remove characters if the frame is marked as B-Roll, Diagram, or Typography.

### 2. THE EDITORIAL LAYOUTS
Translate "Video Editor cuts" into physical prompts:
- "Split Screen / Panel Reveal": If marked as a comparative split, use exact terms: "Left side is a sharp 2D panel showing [Subject A]. Right side is a blacked-out panel with soft blurred borders." or "Split panel screen: Left side shows [Subject A], Right side shows [Subject B]."
- "Text Overlay Blur": If generating a statement/question overlay, use: "A heavily blurred, soft, gauzy out-of-focus background of the previous room. In the sharp foreground, bold clean typography displays the text: [Text]."
- "POV Frame": Write the prompt looking directly through the character's eyes: "Point-of-view perspective looking at two hands holding a flat grey map, other characters visible in front."

### 3. ARABIC TYPOGRAPHY RENDERING
When a Typography Scene is triggered for a punchline, chapter, or new topic, write the Arabic text enclosed in exact quotes inside the prompt (e.g., "In the center of the frame is the glowing, sharp, clean Arabic text "الفشل" written in modern flat typography."). Combine this with the absolute text ban for any *other* background elements to prevent gibberish.

### 4. CONTEXTUAL TONES & ACCENT HOOKS
- Match the color scheme to the roadmap's emotional notes (e.g., "cool-toned desaturated slate" for serious; "bright pastel-yellow background" for optimistic).
- Every single frame must contain exactly ONE vibrant, glowing accent element to capture attention (e.g., a glowing yellow lightbulb, a neon-cyan screen, or glowing white Arabic typography).

---

## DEEP JSON SCHEMA MANDATE
Output ONLY a valid JSON array of objects. Do not write any conversational text, explanations, or notes outside the JSON block.

[
  {
    "index": 1,
    "timestamp": "[00:00]",
    "sequence_type": "Choose: 'STANDALONE', 'THEME_SET_CONTINUITY', 'STOP_MOTION_SET', 'TYPOGRAPHY_SCENE', 'POV', 'SPLIT_PANEL'",
    "sequence_metadata": {
      "set_id": "e.g., SMS_01_REVEAL, TS_02_CHAPTER_INTRO",
      "frame_index": 1,
      "total_frames_in_set": 3
    },
    "visual_prompt": {
      "subject_details": "Describe the cast: MAIN, SECONDARY, GROUP, or ABSENT. Specify biometric features and expressions.",
      "subject_action_increment": "Exact pose, hand gesture, or micro-movement for this specific index in the stop-motion/action progression.",
      "environment_coordinates": "Detailed setting. e.g., Flat solid slate-grey background. If a blurred backdrop or split-panel, describe the layout here.",
      "lighting_setup": "Select: top-down narrow spotlight, classic high-contrast three-point lighting, warm golden hour rim-light, or flat even studio lighting.",
      "accent_color_hook": "The single high-contrast glowing element (e.g., glowing white Arabic typography, glowing yellow bulb, orange control button).",
      "camera_specifications": "Flat 2D orthographic perspective, 50mm flat portrait framing, or 35mm fisheye for wide angles.",
      "negative": {
        "content": ["gradients", "3D shadows", "shading", "photorealism", "textures", "extruded edges"],
        "style": "No 3D elements, no gradients, no realistic skin textures, no soft focus filters"
      }
    }
  }
]

Reply EXACTLY with: "JSON System Ready. Awaiting chunks."
"""
                        # Safely insert the roadmap without breaking JSON formatting
                        final_system_prompt = generic_monolithic_template.replace("[INJECT_ROADMAP_HERE]", master_roadmap)
                        
                        # Submit System Prompt
                        initial_count = gemini_page.locator("model-response").count()
                        input_box.fill(final_system_prompt)
                        input_box.press("Control+Enter")
                        wait_for_gemini_response(gemini_page, initial_count)

                        # 3. CHUNK PROCESSING
                        print("\n[PHASE 1B] Generating JSON frames chunk by chunk...")
                        chunk_size = 15
                        chunks = [sentences[i:i+chunk_size] for i in range(0, len(sentences), chunk_size)]
                        
                        open(prompts_file, 'w').close() 
                        
                        for chunk_idx, chunk in enumerate(chunks, 1):
                            print(f"Planning Chunk {chunk_idx}/{len(chunks)}...")
                            start_idx = (chunk_idx - 1) * chunk_size + 1
                            chunk_text = "\n".join([f"Index {start_idx+i} ({timestamps[start_idx+i-1]}): {s}" for i, s in enumerate(chunk)])
                            
                            initial_count = gemini_page.locator("model-response").count()
                            payload = f"Generate the JSON array for this chunk:\n\n{chunk_text}"
                            input_box.fill(payload)
                            input_box.press("Control+Enter")
                            
                            resp = wait_for_gemini_response(gemini_page, initial_count, timeout_seconds=120)
                            if resp:
                                with open(prompts_file, "a", encoding="utf-8") as f:
                                    f.write(resp + "\n\n")
                            else:
                                print(f"Error: Failed to get JSON response for chunk {chunk_idx}")
                                
                        storyboard_prompts = parse_json_prompts(prompts_file)

                    # ---------------------------------------------------------
                    # PHASE 2: IMAGE RENDERING (GOOGLE FLOW)
                    # ---------------------------------------------------------
                    total_frames = len(storyboard_prompts)
                    if total_frames == 0: continue
                    
                    print(f"\n[PHASE 2] Rendering {total_frames} images via Google Flow...")
                    flow_page.bring_to_front()
                    
                    # --- THE URL CHECKPOINT SYSTEM ---
                    url_checkpoint_file = os.path.join(subfolder, "flow_workspace_url.txt")
                    saved_project_url = None
                    if os.path.exists(url_checkpoint_file):
                        with open(url_checkpoint_file, "r") as f:
                            saved_project_url = f.read().strip()
                            
                    # Pass the URL to the setup function. It returns the active URL.
                    active_project_url = setup_flow_ui(flow_page, target_flow_model, target_flow_count, saved_project_url)
                    
                    # Save the active URL so we can resume here if it crashes
                    if "project" in active_project_url:
                        with open(url_checkpoint_file, "w") as f:
                            f.write(active_project_url)

                    executed_generations_count = 0

                    for current_run, (idx, ts, prompt_text) in enumerate(storyboard_prompts, 1):
                        clean_ts = ts.replace("[", "").replace("]", "").replace(":", "_").strip()
                        image_name = f"{clean_ts}.png" if clean_ts else f"sentence_{idx}.png"
                        save_path = os.path.join(image_dir, image_name)

                        if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                            print(f"[SKIP] Frame {idx} ({image_name}) exists.")
                            continue

                        executed_generations_count += 1
                        if executed_generations_count > 1 and (executed_generations_count - 1) % reset_loop_limit == 0:
                            print(f"\n[RESET] Refreshing Flow UI (Limit: {reset_loop_limit})...")
                            flow_page.reload()
                            # Pass the active URL so we don't lose our place on refresh
                            setup_flow_ui(flow_page, target_flow_model, target_flow_count, active_project_url)

                        print(f"Rendering Frame {idx}...")
                        success = False
                        
                        for attempt in range(1, 4):
                            try:
                                payload_text = f"Please generate exactly 1 image for this JSON prompt:\n\n{prompt_text}"

                                # 1. Track ALL existing image SRCs (to ignore avatars & UI icons)
                                flow_page.wait_for_timeout(1000)
                                pre_image_srcs = set()
                                for i in range(flow_page.locator("img").count()):
                                    try:
                                        src = flow_page.locator("img").nth(i).get_attribute("src")
                                        if src: pre_image_srcs.add(src)
                                    except: pass

                                # 2. Paste Monolithic Prompt
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
                                
                                # 3. THE ULTIMATE BACKEND-AWARE MONITOR
                                print(f"  Attempt {attempt}: Prompt submitted. Monitoring generation engine...")
                                time.sleep(2) 
                                
                                render_success = False
                                final_generated_locators = []
                                
                                for tick in range(90):
                                    # 1. Stricter error and restriction detection
                                    error_locators = flow_page.get_by_text(re.compile(r"(unusual activity|couldn't generate|failed to generate|policy violation)", re.IGNORECASE))
                                    error_visible = False
                                    error_msg = ""
                                    for err_idx in range(error_locators.count()):
                                        if error_locators.nth(err_idx).is_visible():
                                            error_visible = True
                                            error_msg = error_locators.nth(err_idx).inner_text()
                                            break
                                            
                                    if error_visible:
                                        print(f"  ⚠️ Google Flow rejected the prompt: {error_msg}")
                                        raise Exception("Generation failed due to API rejection or UI error.")
                                    
                                    # 2. NEW: Detect "Something went wrong loading your media"
                                    failed_media_locator = flow_page.get_by_text("Something went wrong loading your media")
                                    if failed_media_locator.is_visible():
                                        print("  ⚠️ Detected: 'Something went wrong loading your media' error container.")
                                        
                                        # Try to find and click the circular retry/refresh button inside the failed card
                                        try:
                                            # We look for a button containing a refresh SVG or close to the text
                                            retry_btn = flow_page.locator("button:has(svg), button").filter(has=flow_page.locator("path[d*='M'], path[d*='m']")).last
                                            if retry_btn.is_visible():
                                                print("  🔄 Clicked the card's retry button automatically...")
                                                retry_btn.click(force=True)
                                                time.sleep(3)  # Cooldown to let loading start
                                                continue  # Keep ticking and monitor the generation
                                        except Exception as click_err:
                                            print(f"  Warning: Failed to click inline retry button: {click_err}")
                                            
                                        # If retry button didn't resolve it, raise exception to force a clean page reload
                                        raise Exception("Media loading failed completely on this card.")

                                    # 3. Check for active loading indicators
                                    loading_locators = flow_page.get_by_text(re.compile(r"\d+%"))
                                    is_loading = False
                                    for load_idx in range(loading_locators.count()):
                                        if loading_locators.nth(load_idx).is_visible():
                                            is_loading = True
                                            break
                                            
                                    if flow_page.locator("[role='progressbar']").is_visible():
                                        is_loading = True
                                    
                                    # Scan for NEW images that are large enough (Filtering out UI/Avatars)
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
                                        
                                    if not is_loading and tick > 1 and len(new_images) > 0:
                                        print("  Generation 100% reached. Allowing image to fully render in DOM...")
                                        time.sleep(5)
                                        final_generated_locators = new_images
                                        render_success = True
                                        break
                                            
                                    time.sleep(2)
                                
                                # 4. Image Extraction
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
                                        # Bypass UI Menus and extract the raw image data from browser memory
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
                                                print(f"  ✅ Saved (Direct Extraction): {os.path.basename(current_save_path)}")
                                                if not is_duplicate:
                                                    download_attempt_success = True
                                        else:
                                            print("  ⚠️ Failed to parse Base64 data from browser.")
                                    except Exception as e:
                                        print(f"  ⚠️ Direct extraction failed: {e}")

                                if download_attempt_success:
                                    success = True
                                    break
                                    
                            except PlaywrightTimeoutError: 
                                print("  ⚠️ Playwright Timeout Error.")
                            except Exception as e: 
                                print(f"  ⚠️ Error: {e}")
                            
                            # CRITICAL FIX: If the attempt failed, the UI is likely polluted with an error toast.
                            # We must refresh the specific project URL to clear the error state before the next attempt.
                            if not success and attempt < 3:
                                print("  🔄 Clearing UI error state before retry...")
                                time.sleep(3) # Brief cooldown for rate limits
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