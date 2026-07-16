import os
import re
import sys
import time
import subprocess
import base64
from playwright.sync_api import sync_playwright
from utils import get_config_value, launch_browser_with_profile, rotate_profile_index, kill_cdp_chrome

# Force standard streams to use UTF-8 to prevent Windows terminal encoding errors with Arabic text
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


# 1. Parse Pre-Planned Storyboard Prompts
def parse_pre_planned_prompts_string(content):
    # Clean up common markdown bold markers, system BOMs, and brackets
    content = content.replace("\ufeff", "").replace("*", "")
    lines = content.splitlines()
    
    prompts = []
    current_idx = None
    current_prompt = []
    is_reading_prompt = False
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        index_match = re.search(r"\bIndex:\s*(\d+)", line_str, re.IGNORECASE)
        if index_match:
            # Save the accumulated prompt before moving to the next index
            if current_idx is not None and current_prompt:
                prompts.append((current_idx, " ".join(current_prompt).strip()))
            current_idx = int(index_match.group(1))
            current_prompt = []
            is_reading_prompt = False
            continue
            
        prompt_match = re.search(r"\bVisual\s+Prompt:\s*(.*)", line_str, re.IGNORECASE)
        if prompt_match:
            is_reading_prompt = True
            prompt_content = prompt_match.group(1).strip()
            if prompt_content:
                current_prompt.append(prompt_content)
            continue
            
        if is_reading_prompt:
            if line_str.startswith("===") or "gemini said" in line_str.lower() or "creating your image" in line_str.lower():
                continue
            current_prompt.append(line_str)
            
    # Append the final parsed prompt
    if current_idx is not None and current_prompt:
        prompts.append((current_idx, " ".join(current_prompt).strip()))
        
    return prompts


def parse_pre_planned_prompts(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return parse_pre_planned_prompts_string(content)


# Playwright Web Helpers
def find_input_box(page):
    selectors = [
        "rich-textarea div[contenteditable='true']",
        "rich-textarea [contenteditable='true']",
        "div[contenteditable='true'][role='textbox']"
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
            for i in range(count):
                el = loc.nth(i)
                if el.is_enabled():
                    return el
        except Exception:
            continue
    return None


def find_send_button(page):
    """Locate the send button by visibility only — Playwright's auto-wait handles the
    enabled state transition that occurs after text is pasted into the prompt box."""
    selectors = [
        "button[aria-label*='Send' i]",
        "button[aria-label*='Submit' i]",
        "button.send-button",
        "div[class*='send-button-container'] button",
        "button[id*='send']",
        "button:has(svg)",
        "rich-textarea + div button"
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                # Safety check: Skip button if it is in an active "Stop" state
                aria_label = loc.get_attribute("aria-label") or ""
                btn_text = loc.evaluate("el => el.innerText") or ""
                combined_check = (aria_label + btn_text).lower()
                if "stop" in combined_check or "cancel" in combined_check or "interrupt" in combined_check:
                    continue
                return loc
        except Exception:
            continue
    return None

def is_gemini_generating(page):
    """Returns True if Gemini is actively generating text (Stop/Interrupt button is visible)."""
    stop_selectors = [
        "button[aria-label*='Stop' i]",
        "button[aria-label*='Cancel' i]",
        "button[aria-label*='Interrupt' i]"
    ]
    for sel in stop_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                return True
        except Exception:
            pass
    return False


def fill_textbox(page, textbox, text):
    try:
        textbox.click()
        # Native Playwright fill preserves newlines and handles rich-text fields
        textbox.fill(text)
        return True
    except Exception as e:
        print(f"Warning: Standard fill failed. Attempting keyboard fallback: {e}")
        try:
            textbox.focus()
            page.keyboard.press("Control+a")
            page.keyboard.press("Backspace")
            page.keyboard.type(text)
            return True
        except Exception as ex:
            print(f"Error filling textbox: {ex}")
            return False


def select_gemini_model(page, target_model="Flash-Lite"):
    print(f"[SYSTEM] Attempting to select Gemini model: {target_model}")
    
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
        if target_model.lower() in current_text.lower():
            print(f"[SYSTEM] Model '{target_model}' is already active.")
            return True
            
        # 3. Click to open the menu
        btn.click()
        time.sleep(1.5) # Wait for Material UI menu animation to render
        
        # 4. Find the option in the dropdown using a flexible regex filter
        import re
        opt = page.locator("[role='menuitem'], [role='option'], li").filter(has_text=re.compile(target_model, re.IGNORECASE)).first
        
        if not opt.is_visible():
            # Fallback to any visible element containing the text
            opt = page.locator(f'text="{target_model}"').filter(visible=True).last
            
        if opt.is_visible():
            opt.click()
            print(f"[SYSTEM] Successfully switched model to {target_model}")
            time.sleep(1)
            return True
        else:
            print(f"[WARNING] Target model '{target_model}' not visible in dropdown menu.")
            
    except Exception as e:
        print(f"[WARNING] Model selection process failed: {e}")
        
    return False


def wait_for_gemini_response(page, initial_count, timeout_seconds=90):
    start_time = time.time()
    new_response_found = False
    
    while time.time() - start_time < 30:
        try:
            if page.locator("model-response").count() > initial_count:
                new_response_found = True
                break
        except Exception:
            pass
        time.sleep(0.5)
        
    if not new_response_found:
        print("Warning: Timeout waiting for response to start.")
        return None
        
    print("Waiting for response text to settle...")
    last_text = ""
    stable_count = 0
    last_log_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        elapsed = time.time() - start_time
        if time.time() - last_log_time >= 15:
            print(f"Still waiting for text stability... (elapsed: {elapsed:.1f}s / {timeout_seconds}s)")
            last_log_time = time.time()
            
        try:
            # Periodically bring page to front to prevent background throttling
            if int(elapsed) % 10 == 0:
                try:
                    page.bring_to_front()
                except Exception:
                    pass
            
            last_response = page.locator("model-response").last
            current_text = last_response.evaluate("el => el.innerText", timeout=5000).strip()
            
            if current_text and current_text == last_text:
                if is_gemini_generating(page):
                    # Gemini is still active (generating slowly) — do not stabilize yet
                    stable_count = 0
                else:
                    stable_count += 1
                    
                if stable_count >= 4:  # Stable for 4 consecutive seconds
                    # === ISSUE 3: ONE-TIME SMOOTH SCROLL EXECUTION ===
                    page.evaluate("""
                        (() => {
                            // 1. Locate and scroll the main chat container
                            const mainContainer = Array.from(document.querySelectorAll('*')).find(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.left > 200 && el.scrollHeight > el.clientHeight && 
                                       getComputedStyle(el).overflowY !== 'hidden';
                            });
                            if (mainContainer) {
                                mainContainer.scrollTo({ top: mainContainer.scrollHeight, behavior: 'smooth' });
                            } else {
                                // Fallback: Scroll the main window viewport
                                window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                            }

                            // 2. Locate and scroll the left sidebar UP
                            const leftSidebar = Array.from(document.querySelectorAll('*')).find(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.left >= 0 && rect.left < 200 && rect.width > 50 &&
                                       el.scrollHeight > el.clientHeight && 
                                       getComputedStyle(el).overflowY !== 'hidden';
                            });
                            if (leftSidebar) {
                                leftSidebar.scrollTo({ top: 0, behavior: 'smooth' });
                            }
                        })()
                    """)
                    time.sleep(1) # Allow 1 second for the smooth scroll animation to finish visually
                    
                    if current_text.startswith("Gemini said"):
                        current_text = current_text[len("Gemini said"):].strip()
                    return current_text
            else:
                last_text = current_text
                stable_count = 0
        except Exception:
            pass
        time.sleep(1)
        
    print(f"Warning: Response timed out after {timeout_seconds} seconds.")
    return None


def send_handover_alignment(page, visual_style, visuals_plan, carryover_anchor=""):
    print("\n[ALIGNMENT] Aligning style system configuration...")
    
    payload = (
        "We are generating a series of consecutive images for an animation sequence. "
        "You must maintain strict consistency across all frames. "
        f"Design Rules:\n{visual_style}\n\n"
        f"Storyboard Blueprint:\n{visuals_plan}\n"
        f"{carryover_anchor}\n"
        "Confirm your readiness by replying exactly: 'STYLE SYSTEM ALIGNED. READY TO EXECUTE SYSTEM.'"
    )

    initial_count = page.locator("model-response").count()
    textbox = find_input_box(page)
    if not textbox:
        print("Error: Input box missing during style alignment.")
        return False

    fill_textbox(page, textbox, payload)
    time.sleep(1)

    send_btn = find_send_button(page)
    if send_btn:
        try:
            send_btn.click(timeout=5000)
        except Exception:
            textbox.press("Control+Enter")
    else:
        textbox.press("Control+Enter")

    wait_for_gemini_response(page, initial_count, timeout_seconds=60)
    print("[ALIGNMENT] Style parameters successfully registered.")
    return True


def get_chrome_path():
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            return path
    print("Error: Google Chrome binary not detected.")
    sys.exit(1)


def scan_batch_folders():
    runs_dir = "youtube_runs"
    batch_queue = []
    if not os.path.exists(runs_dir):
        print(f"Error: '{runs_dir}' folder not found in workspace.")
        sys.exit(1)
        
    for item in os.listdir(runs_dir):
        subfolder = os.path.join(runs_dir, item)
        if os.path.isdir(subfolder):
            script_file = os.path.join(subfolder, "timestamped_transcript.txt")
            if os.path.exists(script_file) and os.path.getsize(script_file) > 0:
                batch_queue.append(subfolder)
                
    return batch_queue


def load_local_or_global_config(subfolder, config_filename, default_text=""):
    # Split filename to check both extension variants (hidden extensions)
    base_name, ext = os.path.splitext(config_filename)
    filenames_to_try = [config_filename]
    if ext == ".txt":
        filenames_to_try.append(base_name)
    else:
        filenames_to_try.append(config_filename + ".txt")

    for fname in filenames_to_try:
        local_path = os.path.join(subfolder, fname)
        if os.path.exists(local_path):
            print(f"  Using local config: {local_path}")
            with open(local_path, "r", encoding="utf-8") as f:
                return f.read().strip()
                
    for fname in filenames_to_try:
        if os.path.exists(fname):
            print(f"  Using global config: {fname}")
            with open(fname, "r", encoding="utf-8") as f:
                return f.read().strip()
                
    print(f"  Warning: '{config_filename}' not found. Utilizing default fallback.")
    return default_text


def run_storyboard_planning_phase(page, script_path, prompts_file, sentences, timestamps, visual_style, visuals_plan, target_model="Flash-Lite"):
    print("\n" + "="*50)
    print("PHASE 1: STORYBOARD PLANNING PHASE")
    print("="*50)
    
    total_sentences = len(sentences)
    print(f"Storyboard planning for {total_sentences} sentences...")

    chunk_size = 5
    chunks = [sentences[i:i + chunk_size] for i in range(0, len(sentences), chunk_size)]
    
    # Checkpoint Configuration
    planning_checkpoint = os.path.join(os.path.dirname(prompts_file), "planning_checkpoint.json")
    completed_chunks = 0
    chunk_responses = []
    all_parsed_prompts = []

    # Load existing checkpoint if available
    import json
    if os.path.exists(planning_checkpoint):
        try:
            with open(planning_checkpoint, "r", encoding="utf-8") as cp:
                data = json.load(cp)
                completed_chunks = data.get("completed_chunks", 0)
                chunk_responses = data.get("chunk_responses", [])
                all_parsed_prompts = [tuple(item) for item in data.get("all_parsed_prompts", [])]
                print(f"[RESUME] Resuming storyboard planning from Chunk {completed_chunks + 1}...")
        except Exception as e:
            print(f"Warning: Failed to load planning checkpoint ({e}). Starting fresh.")

    # Helper to open a clean chat and align visual directives
    def initialize_clean_planning_chat(carryover_anchor=""):
        print("\nOpening/Resetting clean chat session for planning batch...")
        new_chat_btn = page.locator("a[aria-label='New chat']").first
        new_chat_btn.click()
        time.sleep(3)
        
        # Verify and set target model
        select_gemini_model(page, target_model)
        
        style_payload = f"""You are the lead visual director for a YouTube animation.
We are using the following style guidelines:

{visual_style}

Here is our overarching Visual Plan:
{visuals_plan}
{carryover_anchor}
Do not generate any images yet. Simply respond with: "SYSTEM READY. Awaiting script chunks to plan."
"""
        initial_count = page.locator("model-response").count()
        textbox = find_input_box(page)
        fill_textbox(page, textbox, style_payload)
        time.sleep(1)
        
        send_btn = find_send_button(page)
        if send_btn:
            try:
                send_btn.click(timeout=5000)
            except Exception:
                textbox.press("Control+Enter")
        else:
            textbox.press("Control+Enter")
            
        wait_for_gemini_response(page, initial_count, timeout_seconds=60)
        print("Style parameters successfully aligned in new planning session.")

    # Initialize first session or resume with carryover context anchors
    if completed_chunks == 0:
        initialize_clean_planning_chat()
    else:
        continuity_anchor = ""
        if len(all_parsed_prompts) >= 2:
            last_two = all_parsed_prompts[-2:]
            continuity_anchor = (
                f"\nTo maintain strict visual consistency with the previous scenes, "
                f"here are the last 2 generated visual prompts you must reference as your baseline:\n"
                f"- Index {last_two[0][0]}: {last_two[0][1]}\n"
                f"- Index {last_two[1][0]}: {last_two[1][1]}\n"
            )
        initialize_clean_planning_chat(carryover_anchor=continuity_anchor)
    
    for chunk_idx, chunk in enumerate(chunks, 1):
        # Skip chunks completed in previous runs
        if chunk_idx <= completed_chunks:
            continue
            
        print(f"\nPlanning Chunk {chunk_idx} of {len(chunks)}...")
        
        # Reset standard UI and carry over the last 2 frames every 8 chunks (40 sentences)
        if chunk_idx > 1 and (chunk_idx - 1) % 8 == 0:
            continuity_anchor = ""
            if len(all_parsed_prompts) >= 2:
                last_two = all_parsed_prompts[-2:]
                continuity_anchor = (
                    f"\nTo maintain strict visual consistency with the previous scenes, "
                    f"here are the last 2 generated visual prompts you must reference as your baseline:\n"
                    f"- Index {last_two[0][0]}: {last_two[0][1]}\n"
                    f"- Index {last_two[1][0]}: {last_two[1][1]}\n"
                )
            
            initialize_clean_planning_chat(carryover_anchor=continuity_anchor)
        
        start_idx = (chunk_idx - 1) * chunk_size + 1
        chunk_text_list = []
        for i, s in enumerate(chunk):
            idx = start_idx + i
            timestamp = timestamps[idx - 1]
            chunk_text_list.append(f"Index {idx} ({timestamp}): {s}")
        chunk_text = "\n".join(chunk_text_list)
        
        # Comprehensive visual framing guidelines focusing on keyframing & timestamp prepending
        prompt_template = """# SYSTEM PROMPT: MASTER HYBRID PROMPT GENERATOR

You are an elite Visual Keyframe Director. Your job is to translate a raw Arabic script chunk into highly descriptive, dynamic, and cinematic English text-to-image prompts. Your singular goal is to maximize viewer retention through camera precision, stop-motion consistency, casting variety, and strict B-Roll integration.

## INPUT DATA
SCRIPT CHUNK:
{chunk_text}

---

## CRITICAL EXECUTION RULES

### 1. TIMESTAMP ANCHORING (MANDATORY)
* Extract the exact timestamp (e.g., `[11:05]`) from the script chunk.
* You MUST output it in the `Calculated Timestamp:` field AND prepend it to the beginning of the `Visual Prompt:` field.

### 2. STOP-MOTION TRIGGER (<= 2 SECONDS)
* If the timestamps of 3 or more consecutive sentences are 2 seconds or less apart, you must designate them as a "STOP-MOTION SET".
* In a STOP-MOTION SET, you must write the exact same Camera Body, Lens, f-stop, Lighting, and Background coordinates for all frames in that set. Modify ONLY the micro-actions, facial details, or object position from frame to frame to simulate incremental stop-motion animation.

### 3. CASTING & INTERACTION RULES
* Do not keep the character alone in every frame.
* Differentiate between SINGLE (character alone), DUO/MULTI (main character interacting with a secondary character in blue/maroon hoodies), GROUP (active stick-figure crowd), or ABSENT (pure typography, diagram, or B-roll).

### 4. ARABIC TEXT & TYPOGRAPHY SCENES
* When a sentence marks a punchline, new chapter, or transition, write a "TYPOGRAPHY_SCENE" prompt. Place a clean, bold, glowing Arabic phrase (enclosed in exact quotes, e.g., "الخطر") on a moody, desaturated background with NO characters present.
* When demonstrating a concept in a scene, write a prompt showing clear Arabic text integrated into the environment (e.g., text on a billboard, screen, or chalkboard).

### 5. VIDEO-EDITOR FRAMES & POVs
* Comparative Panels: Design split-screen prompts (e.g., "Split panel: Left side is active showing [Scene A], Right side is a blacked-out panel with soft blurred borders").
* Text Blur Overlays: For major questions, use a blurred version of the previous room as the background with sharp, prominent foreground typography.
* POV Shifts: Write first-person camera perspectives looking at objects or other characters.

### 6. MOOD PRESETS
Select a mood based on the context of the sentence:
* Playful/Optimistic: Pastel backgrounds, soft diffused lighting.
* Serious/Tension: Slate-blue backgrounds, high-contrast, top-down spotlights.
* Sad/Melancholy: Cold grey/blue desaturated tones, long cast shadows.

### 7. HYBRID PROMPT STRUCTURE
The "Visual Prompt" must be formatted as a highly descriptive hybrid sequence. Follow this exact structural layout:
`[Timestamp] [CAMERA TAG] Shot on [CAMERA BODY] with a [LENS] at f/[APERTURE], ISO [ISO]. Mood: [CONEXTUAL MOOD PRESET]. Lighting: [LIGHTING Setup]. Subject: [Casting Type (SINGLE/DUO/GROUP/ABSENT) with biometric and micro-action details]. Layout: [Standard, Split-Screen, POV, or Blurred Text Overlay]. Environment: [Background coordinates and atmosphere]. Accent: [Exactly one vibrant, glowing accent element]. SUPPRESSION: [NO TEXT, NO LETTERS, NO GIBBERISH (unless authorized Arabic text is specified in quotes)]. Style Anchor: 2D digital webcomic, pristine solid uniform black vector outlines, flat base colors with dramatic cinematic lighting, cool-toned desaturated slate palette with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 cinematic aspect ratio.`

---

## OUTPUT FORMAT FOR EACH SENTENCE
You must output exactly in this format. No conversational filler.

Index: [Sentence Index]
Sentence: [Original Arabic Sentence]
Calculated Timestamp: [Timestamp]
Visual Prompt: [Timestamp] [CAMERA TAG] Shot on [CAMERA BODY] with a [LENS] at f/[APERTURE], ISO [ISO]. Mood: [CONEXTUAL MOOD PRESET]. Lighting: [LIGHTING Setup]. Subject: [Casting Type with biometric and micro-action details]. Layout: [Standard, Split-Screen, POV, or Blurred Text Overlay]. Environment: [Background coordinates]. Accent: [One vibrant, glowing accent element]. SUPPRESSION: [NO TEXT, NO LETTERS, NO GIBBERISH (unless authorized Arabic text is specified in quotes)]. Style Anchor: 2D digital webcomic, pristine solid uniform black vector outlines, flat base colors with dramatic cinematic lighting, cool-toned desaturated slate palette with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 cinematic aspect ratio.
"""
        
        prompt = prompt_template.format(chunk_text=chunk_text)
        initial_count = page.locator("model-response").count()
        textbox = find_input_box(page)
        fill_textbox(page, textbox, prompt)
        time.sleep(1)
        
        send_btn = find_send_button(page)
        if send_btn:
            try:
                send_btn.click(timeout=5000)
            except Exception:
                textbox.press("Control+Enter")
        else:
            textbox.press("Control+Enter")
            
        resp = wait_for_gemini_response(page, initial_count, timeout_seconds=240)
        if not resp:
            print("Error: Storyboard response failed to return.")
            sys.exit(1)
            
        if f"Index: {start_idx}" not in resp:
            followup = f"Please output the storyboard prompts for Chunk {chunk_idx} (Index {start_idx}-{start_idx+len(chunk)-1}) that I just sent. Follow the output format exactly. No conversational filler."
            print("Sending follow-up query to force translation...")
            initial_count = page.locator("model-response").count()
            textbox = find_input_box(page)
            fill_textbox(page, textbox, followup)
            time.sleep(1)
            
            send_btn = find_send_button(page)
            if send_btn:
                try:
                    send_btn.click(timeout=5000)
                except Exception:
                    textbox.press("Control+Enter")
            else:
                textbox.press("Control+Enter")
                
            resp = wait_for_gemini_response(page, initial_count, timeout_seconds=240)
            if not resp:
                print("Error: Storyboard response failed to return on retry.")
                sys.exit(1)
                
        chunk_responses.append(resp)
        
        parsed_chunk = parse_pre_planned_prompts_string(resp)
        all_parsed_prompts.extend(parsed_chunk)
        
        # Save planning checkpoint progress
        try:
            with open(planning_checkpoint, "w", encoding="utf-8") as cp:
                json.dump({
                    "completed_chunks": chunk_idx,
                    "chunk_responses": chunk_responses,
                    "all_parsed_prompts": all_parsed_prompts
                }, cp, ensure_ascii=False, indent=4)
        except Exception as ec:
            print(f"Warning: Failed to save planning checkpoint ({ec})")
            
        print(f"Successfully planned Chunk {chunk_idx}!")
        
    final_storyboard = "\n\n=== CHUNK PLAN ===\n\n".join(chunk_responses)
    with open(prompts_file, "w", encoding="utf-8") as f:
        f.write(final_storyboard)
        
    # Clear planning checkpoint on full success
    if os.path.exists(planning_checkpoint):
        try:
            os.remove(planning_checkpoint)
        except Exception as ec:
            print(f"Warning: Failed to clear planning checkpoint file ({ec})")
            
    print(f"\nStoryboard planning phase complete! Storyboard saved to: {prompts_file}")


def main():
    batch_queue = scan_batch_folders()
    if not batch_queue:
        print("No active topic directories with 'timestamped_transcript.txt' scripts detected in 'youtube_runs/'.")
        return
        
    print(f"Detected {len(batch_queue)} batch folder(s) to process:")
    for subfolder in batch_queue:
        print(f" - {subfolder}")

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

                gemini_page = None
                for page in context.pages:
                    if "gemini.google.com" in page.url:
                        gemini_page = page
                        break
                if not gemini_page:
                    gemini_page = context.new_page()
                    print("Navigating to Gemini Web App...")
                    try:
                        # Wait only for DOM ready state, increase timeout, and handle slow loads gracefully
                        gemini_page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=60000)
                    except Exception as e:
                        print(f"Warning: Gemini initial load timed out or had a slow resource warning, proceeding: {e}")
                    time.sleep(3)

                gemini_page.bring_to_front()

                # Batch process each folder
                for folder_idx, subfolder in enumerate(batch_queue, 1):
                    print("\n" + "="*70)
                    print(f"PROCESSING TOPIC FOLDER {folder_idx} OF {len(batch_queue)}")
                    print(f"Target: {subfolder}")
                    print("="*70)
                    
                    script_path = os.path.join(subfolder, "timestamped_transcript.txt")
                    prompts_file = os.path.join(subfolder, "pre_planned_prompts.txt")
                    image_dir = os.path.join(subfolder, "generated_images")
                    os.makedirs(image_dir, exist_ok=True)
                    
                    # Load local or global configurations
                    print("Loading style directives...")
                    visuals_plan = load_local_or_global_config(subfolder, "visuals_plan.txt")
                    visual_style = load_local_or_global_config(subfolder, "visual_style.txt", "2D digital webcomic style.")
                    target_model = get_config_value("IMAGE_PLANNER_MODEL", "Pro")

                    # Parse lines from timestamped_transcript.txt
                    sentences = []
                    timestamps = []
                    
                    if not os.path.exists(script_path):
                        print(f"Warning: '{script_path}' not found in subfolder. Skipping.")
                        continue

                    with open(script_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line_str = line.strip()
                            if not line_str:
                                continue
                            # Match standard format: [MM:SS] Text...
                            match = re.match(r"^\[(\d{2}:\d{2})\]\s*(.*)", line_str)
                            if match:
                                ts = f"[{match.group(1)}]"
                                text = match.group(2).strip()
                                timestamps.append(ts)
                                sentences.append(text)
                            else:
                                # Fallback for [HH:MM:SS] or similar format
                                match_long = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)", line_str)
                                if match_long:
                                    time_parts = match_long.group(1).split(":")
                                    ts = f"[{time_parts[1]}:{time_parts[2]}]"
                                    text = match_long.group(2).strip()
                                    timestamps.append(ts)
                                    sentences.append(text)
                                else:
                                    # Fallback if no timestamp prefix is found
                                    timestamps.append("[00:00]")
                                    sentences.append(line_str)
                    
                    # Check storyboard caching
                    storyboard_prompts = []
                    if os.path.exists(prompts_file):
                        try:
                            storyboard_prompts = parse_pre_planned_prompts(prompts_file)
                        except Exception:
                            pass
                    
                    # ---> THIS RESTORES THE MISSING VARIABLE <---
                    skip_planning = len(storyboard_prompts) == len(sentences)
                        
                        # PHASE 1: STORYBOARD PLANNING
                    if not skip_planning:
                        run_storyboard_planning_phase(gemini_page, script_path, prompts_file, sentences, timestamps, visual_style, visuals_plan, target_model)
                        storyboard_prompts = parse_pre_planned_prompts(prompts_file)
                    else:
                        print(f"[SKIP] Detected valid cached storyboard file '{prompts_file}' ({len(storyboard_prompts)} prompts). Skipping Storyboard Planning Phase.")

                    total_frames = len(storyboard_prompts)
                    if total_frames == 0:
                        print(f"Warning: Storyboard prompts empty for {subfolder}. Skipping to next directory.")
                        continue

                    # PHASE 2: IMAGE RENDERING
                    print("\n" + "="*50)
                    print("PHASE 2: IMAGE RENDERING PHASE")
                    print("="*50)
                    print(f"Loaded {total_frames} pre-planned prompts for image rendering.")

                    # NEW: Dynamic Runtime Session Reset fetching
                    raw_limit = get_config_value("IMAGE_RESET_LOOP_LIMIT", "20")
                    try:
                        reset_loop_limit = int(raw_limit.strip())
                    except ValueError:
                        print(f"Warning: Invalid limit '{raw_limit}' in config. Defaulting to 20.")
                        reset_loop_limit = 20

                    # Open a fresh chat session for rendering to clear memory of previous topic runs
                    print("\nClicking New Chat to start clean rendering tab...")
                    new_chat_btn = gemini_page.locator("a[aria-label='New chat']").first
                    new_chat_btn.click()
                    time.sleep(3)

                    # Set/Verify the target model
                    select_gemini_model(gemini_page, target_model)

                    # Initialize style alignment configuration
                    send_handover_alignment(gemini_page, visual_style, visuals_plan)

                    # Track actual generated sessions to prevent redundant reloads
                    executed_generations_count = 0

                    for current_run, (idx, prompt_text) in enumerate(storyboard_prompts, 1):
                        # 1. Pre-calculate targets to check if file already exists
                        if 0 <= (idx - 1) < len(timestamps):
                            # timestamps[idx - 1] looks like "[00:28]"
                            timestamp_raw = timestamps[idx - 1]
                            timestamp_clean = timestamp_raw.replace("[", "").replace("]", "").replace(":", "_")
                            image_name = f"{timestamp_clean}.png"
                        else:
                            # Safe fallback if index is out of bounds
                            image_name = f"sentence_{idx}.png"

                        save_path = os.path.join(image_dir, image_name)

                        # --- STATELESS CHECKPOINT CHECK ---
                        # Skip generation entirely if the valid output file is already on disk
                        if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                            print(f"[SKIP] Frame {current_run} of {total_frames} ({image_name}) already exists. Skipping.")
                            continue

                        # Run window optimization reset block based on config limit
                        executed_generations_count += 1
                        if executed_generations_count > 1 and (executed_generations_count - 1) % reset_loop_limit == 0:
                            print(f"\n[RESET] Running window optimization block (Frame Index {idx} / Limit: {reset_loop_limit})...")
                            gemini_page.bring_to_front()
                            try:
                                gemini_page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=30000)
                            except Exception:
                                try:
                                    gemini_page.keyboard.press("Control+Shift+O")
                                except Exception:
                                    pass
                            time.sleep(5)
                            # Re-verify and set the model after reload
                            select_gemini_model(gemini_page, target_model)
                            # Re-align style directives inside the clean tab session
                            send_handover_alignment(gemini_page, visual_style, visuals_plan)

                        print(f"\nProcessing Frame {current_run} of {total_frames} (Target Index: {idx})")
                        
                        full_command = (
                            f"Refer to the Style Guidelines. "
                            f"Execute image generation for target index {idx} based on this instruction:\n\n"
                            f"{prompt_text}"
                        )

                        success = False
                        for attempt in range(1, 4):
                            print(f"Attempt {attempt} for Frame {idx}...")
                            gemini_page.bring_to_front()
                            initial_count = gemini_page.locator("model-response").count()

                            textbox = find_input_box(gemini_page)
                            if not textbox:
                                print("Error: Input box missing.")
                                return

                            fill_textbox(gemini_page, textbox, full_command)
                            time.sleep(1)

                            send_btn = find_send_button(gemini_page)
                            if send_btn:
                                try:
                                    send_btn.click(timeout=5000)
                                except Exception:
                                    textbox.press("Control+Enter")
                            else:
                                textbox.press("Control+Enter")

                            time.sleep(2)
                            
                            # Wait for response text to settle
                            if wait_for_gemini_response(gemini_page, initial_count, timeout_seconds=90) is not None:
                                # Locate and download image using UI Hover Automation
                                download_attempt_success = False
                                last_response = gemini_page.locator("model-response").last
                                
                                # 1. Locate the generated image
                                img_locator = last_response.locator("img").first
                                
                                try:
                                    # Wait for image to actually be attached and visible
                                    img_locator.wait_for(state="visible", timeout=15000)
                                    
                                    # Force scroll into view to ensure the hover action is not blocked
                                    img_locator.scroll_into_view_if_needed()
                                    time.sleep(1)
                                    
                                    # 2. Leverage Playwright's Relative Hover (Forced Center)
                                    box = img_locator.bounding_box()
                                    if box:
                                        # Hover the exact dead-center of the image to trigger the UI overlay safely
                                        hover_x = box["width"] / 2
                                        hover_y = box["height"] / 2
                                        
                                        # force=True bypasses the "subtree intercepts pointer events" error from hidden Google UI layers
                                        img_locator.hover(position={"x": hover_x, "y": hover_y}, force=True)
                                        time.sleep(1.5) # Wait for the overlay animation to reveal the button
                                        
                                        # 3. Robust Selector for the Download Button
                                        dl_btn = last_response.locator(
                                            'button[aria-label*="Download full size" i], '
                                            'button[aria-label*="Download" i], '
                                            'button[aria-label*="تحميل" i], '
                                            'button[data-tooltip*="Download" i]'
                                        ).first
                                        
                                        if dl_btn.is_visible():
                                            # 4. The Native expect_download Handler
                                            with gemini_page.expect_download(timeout=30000) as download_info:
                                                # Force the click just in case the UI overlay shifts
                                                dl_btn.click(force=True)
                                                
                                            download = download_info.value
                                            
                                            # Blocking save operation ensures the file writes completely to disk
                                            download.save_as(save_path)
                                            
                                            # 5. Post-Download Verification Guard
                                            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                                                print(f"Successfully downloaded high-quality image: {save_path}")
                                                download_attempt_success = True
                                            else:
                                                print(f"Warning: Download completed but file is missing or 0 bytes: {save_path}")
                                        else:
                                            print("Warning: Hover succeeded but Download button did not appear.")
                                    else:
                                        print("Warning: Could not calculate image bounding box for hover.")
                                        
                                except Exception as e:
                                    print(f"Warning: UI Hover/Download extraction failed: {e}")

                                if download_attempt_success:
                                    success = True
                                    break # Break out of the 3-attempt loop safely
                                        
                            # If we get here, this attempt failed — reload and retry
                            print(f"Warning: Frame {idx} attempt {attempt} failed or timed out. Reloading Gemini tab and retrying...")
                            try:
                                gemini_page.reload(wait_until="domcontentloaded")
                            except Exception as e:
                                print(f"Reload error: {e}")
                            time.sleep(10)
                            # Re-align style guidelines
                            send_handover_alignment(gemini_page, visual_style, visuals_plan)
                            
                        if not success:
                            if accounts_enabled:
                                print(f"\n[FAILOVER ALERT] Frame {idx} failed completely. Triggering Account Rotation...")
                                rotate_profile_index()
                                kill_cdp_chrome()
                                failover_triggered = True
                                break # Break out of the image generation loop
                            else:
                                print(f"Error: Frame {idx} failed completely after 3 attempts. Skipping to next frame.")
                    
                    if failover_triggered:
                        break # Break out of the folder loop
                    
                    print(f"\nAll pre-planned images generated and saved successfully for: {subfolder}")

                # If failover was triggered, we must break the folder loop to restart Playwright
                if failover_triggered:
                    break

        except Exception as e:
            print(f"[RECOVERY] Playwright context closed or browser crashed: {e}")

        if failover_triggered:
            print("\n[SYSTEM] Reinitializing Playwright environment with new profile. Fast-forwarding...\n")
            time.sleep(3)
            continue # Restart the 'while True' outer loop
        else:
            break # Exit loop


if __name__ == "__main__":
    main()
