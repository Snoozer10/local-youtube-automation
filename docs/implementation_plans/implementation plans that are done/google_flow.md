Here is the complete, master-class implementation plan and the standalone script for **`flow_image_generator.py`**.

### Architectural Blueprint: The "Dual-Tab" System
To solve the memory problem, this script acts as a highly coordinated orchestrator between two entirely different Google AI platforms:
1.  **Tab 1 (The Director - Gemini Web App):** Playwright opens Gemini, feeds it your transcript, and forces it to generate **Monolithic Prompts**. These prompts contain the complete aesthetic DNA (anatomy, clothing, colors, style) repeated in every single string so no context is lost.
2.  **Tab 2 (The Renderer - Google Flow):** Playwright navigates to `labs.google/fx/tools/flow`. It turns off the "Agent" (so Flow doesn't alter our perfect prompts), sets the aspect ratio to `16:9`, and acts as an automated factory worker—pasting the prompt, waiting for the render, hovering the center of the image, and extracting the download.

If either tab fails or crashes, the script uses our `utils.py` Failover Framework to rotate profiles, reboot the browser, and resume from the exact checkpoint.

---

### Phase 1: Create `flow_image_generator.py`
Create a new file in your project folder named `flow_image_generator.py`. Paste the entire code block below. 

*(Note: Ensure your `utils.py` file is in the same folder, as this script relies heavily on the Factory pattern we built earlier).*

```python
import os
import re
import sys
import time
import subprocess
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Import our Unified Automation Framework
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

def parse_pre_planned_prompts(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().replace("\ufeff", "").replace("*", "")
    
    prompts, current_idx, current_prompt, is_reading = [], None, [], False
    for line in content.splitlines():
        line_str = line.strip()
        if not line_str: continue
            
        index_match = re.search(r"\bIndex:\s*(\d+)", line_str, re.IGNORECASE)
        if index_match:
            if current_idx is not None and current_prompt:
                prompts.append((current_idx, " ".join(current_prompt).strip()))
            current_idx = int(index_match.group(1))
            current_prompt, is_reading = [], False
            continue
            
        prompt_match = re.search(r"\bVisual\s+Prompt:\s*(.*)", line_str, re.IGNORECASE)
        if prompt_match:
            is_reading = True
            if prompt_match.group(1).strip(): current_prompt.append(prompt_match.group(1).strip())
            continue
            
        if is_reading and not line_str.startswith("==="):
            current_prompt.append(line_str)
            
    if current_idx is not None and current_prompt:
        prompts.append((current_idx, " ".join(current_prompt).strip()))
    return prompts

def select_gemini_model(page, target_model="Pro"):
    print(f"[MODEL] Selecting Gemini Planner Model: {target_model}...")
    try:
        model_btn = page.locator("button[aria-label*='model' i], button[aria-haspopup='menu']").first
        if model_btn.is_visible():
            if target_model.lower() not in model_btn.inner_text().lower():
                model_btn.click()
                time.sleep(1)
                page.locator(f"mat-option:has-text('{target_model}'), [role='menuitem']:has-text('{target_model}')").first.click()
                time.sleep(1)
        return True
    except Exception:
        return False

def setup_flow_ui(page):
    """Navigates to Google Flow and configures the UI (16:9, Agent OFF)."""
    print("\n[FLOW] Navigating to Google Flow and configuring workspace...")
    page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)

    # 1. Click '+ New project'
    try:
        new_proj_btn = page.locator("button:has-text('New project'), text='+ New project', .new-project-button").first
        if new_proj_btn.is_visible():
            new_proj_btn.click()
            time.sleep(3)
    except Exception:
        pass # Might already be in a workspace

    # 2. Disable Agent Toggle (We want pure prompting)
    try:
        agent_btn = page.locator("button:has-text('Agent')").first
        if agent_btn.is_visible():
            # Check if it's active (usually indicated by class or aria-pressed)
            is_active = agent_btn.evaluate("el => el.getAttribute('aria-pressed') === 'true' || el.classList.contains('active') || el.style.backgroundColor !== ''")
            if is_active:
                print("[FLOW] Turning Agent OFF to protect monolithic prompts.")
                agent_btn.click()
                time.sleep(1)
            else:
                print("[FLOW] Agent is already OFF.")
    except Exception as e:
        print(f"[FLOW] Warning finding Agent toggle: {e}")

    # 3. Set Aspect Ratio to 16:9
    try:
        # Click settings slider icon near the input box
        settings_icon = page.locator("button:has(svg path[d*='M3']), button[aria-label*='Settings' i]").last
        if settings_icon.is_visible():
            settings_icon.click()
            time.sleep(1)
            
        ratio_btn = page.locator("button:has-text('16:9'), div:has-text('16:9')").first
        if ratio_btn.is_visible():
            ratio_btn.click()
            print("[FLOW] Aspect Ratio set to 16:9.")
            time.sleep(1)
            
        # Close settings popup if needed
        page.keyboard.press("Escape")
    except Exception as e:
        print(f"[FLOW] Warning setting aspect ratio: {e}")

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
        try:
            with sync_playwright() as p:
                switch_enabled = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").lower() in ['true', '1', 'yes']
                current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                browser_type = get_config_value("BROWSER_TYPE", "chrome")
                
                try:
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")
                except Exception:
                    if not launch_browser_with_profile(browser_type, current_profile_idx): sys.exit(1)
                    browser = p.chromium.connect_over_cdp("http://localhost:9222")

                context = browser.contexts[0]
                
                # Tab Management: Gemini for Planning, Flow for Rendering
                gemini_page = context.new_page()
                flow_page = context.new_page()

                for folder_idx, subfolder in enumerate(batch_queue, 1):
                    print(f"\n==================================================")
                    print(f"PROCESSING TOPIC: {subfolder}")
                    print(f"==================================================")
                    
                    script_path = os.path.join(subfolder, "timestamped_transcript.txt")
                    prompts_file = os.path.join(subfolder, "pre_planned_prompts.txt")
                    image_dir = os.path.join(subfolder, "generated_images")
                    os.makedirs(image_dir, exist_ok=True)
                    
                    target_planner_model = get_config_value("IMAGE_PLANNER_MODEL", "Pro")
                    reset_loop_limit = int(get_config_value("IMAGE_RESET_LOOP_LIMIT", "20"))
                    
                    # Parse Transcript
                    sentences, timestamps = [], []
                    if os.path.exists(script_path):
                        with open(script_path, "r", encoding="utf-8") as f:
                            for line in f:
                                match = re.match(r"^\[([\d:]+)\]\s*(.*)", line.strip())
                                if match:
                                    timestamps.append(f"[{match.group(1)}]")
                                    sentences.append(match.group(2).strip())

                    storyboard_prompts = parse_pre_planned_prompts(prompts_file)
                    skip_planning = len(storyboard_prompts) == len(sentences)

                    # ---------------------------------------------------------
                    # PHASE 1: STORYBOARD PLANNING (GEMINI)
                    # ---------------------------------------------------------
                    if not skip_planning and len(sentences) > 0:
                        print("\n[PHASE 1] Generating Monolithic Storyboard in Gemini...")
                        gemini_page.bring_to_front()
                        gemini_page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                        time.sleep(3)
                        select_gemini_model(gemini_page, target_planner_model)
                        
                        # THE MONOLITHIC TEMPLATE
                        monolithic_template = """# SYSTEM PROMPT: MONOLITHIC KEYFRAME ARCHITECT FOR GOOGLE FLOW

You are translating an Arabic script chunk into English visual prompts for a stateless image generator. The generator HAS NO MEMORY. Therefore, EVERY SINGLE PROMPT must be a "Monolithic Prompt" containing the full aesthetic blueprint.

## CRITICAL RUNTIME RULES
1. TIMESTAMP: Extract the exact timestamp from the input line. Output it in `Calculated Timestamp:` AND prepend it to the `Visual Prompt:`.
2. CAMERA & COMPOSITION: Begin the prompt with a camera tag (e.g., [EXTREME WIDE SHOT], [EXTREME CLOSE-UP], [DUTCH ANGLE], [SPLIT SCREEN], or [B-ROLL MACRO]). Rotate angles constantly. Never use two wide shots in a row.
3. THE MONOLITHIC CHARACTER: If the character is in the frame, you MUST include this exact description: "A bald character with a perfectly round white head, no nose, 3-5 sparse thin black hair strands, thin black line-art limbs, wearing an unbranded charcoal-grey hoodie and dark sweatpants".
4. B-ROLL MACRO: For 1 out of every 4 prompts, use [B-ROLL MACRO]. The character MUST be absent. Describe a close-up metaphorical object instead.
5. NO TEXT MANDATE: Include exactly "[NO TEXT, NO LETTERS, NO GIBBERISH]" in every prompt unless the script requires a specific Arabic sign (put Arabic inside "quotes").

## OUTPUT FORMAT (STRICT)
Index: [Index]
Sentence: [Arabic Sentence]
Calculated Timestamp: [Timestamp]
Visual Prompt: [Timestamp] [CAMERA TAG] [Lighting]. [Monolithic Character Description & Action OR B-Roll description]. [Environment]. [NO TEXT, NO LETTERS, NO GIBBERISH]. Style Anchor: 2D digital webcomic, pristine solid uniform black vector outlines, flat base colors, cinematic lighting, cool-toned slate palette with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 aspect ratio.
"""
                        
                        chunk_size = 5
                        chunks = [sentences[i:i+chunk_size] for i in range(0, len(sentences), chunk_size)]
                        chunk_responses = []
                        
                        for chunk_idx, chunk in enumerate(chunks, 1):
                            print(f"Planning Chunk {chunk_idx}/{len(chunks)}...")
                            start_idx = (chunk_idx - 1) * chunk_size + 1
                            chunk_text = "\n".join([f"Index {start_idx+i} ({timestamps[start_idx+i-1]}): {s}" for i, s in enumerate(chunk)])
                            
                            gemini_page.locator("a[aria-label='New chat']").first.click()
                            time.sleep(2)
                            
                            payload = monolithic_template + "\n\nSCRIPT CHUNK:\n" + chunk_text
                            gemini_page.locator("rich-textarea div[contenteditable='true']").first.fill(payload)
                            gemini_page.keyboard.press("Control+Enter")
                            
                            # Wait for generation
                            time.sleep(15) # Wait for text to finish
                            resp = gemini_page.locator("model-response").last.evaluate("el => el.innerText")
                            chunk_responses.append(resp)
                            
                        with open(prompts_file, "w", encoding="utf-8") as f:
                            f.write("\n\n=== CHUNK ===\n\n".join(chunk_responses))
                        storyboard_prompts = parse_pre_planned_prompts(prompts_file)

                    # ---------------------------------------------------------
                    # PHASE 2: IMAGE RENDERING (GOOGLE FLOW)
                    # ---------------------------------------------------------
                    total_frames = len(storyboard_prompts)
                    if total_frames == 0: continue
                    
                    print(f"\n[PHASE 2] Rendering {total_frames} images via Google Flow...")
                    flow_page.bring_to_front()
                    setup_flow_ui(flow_page)

                    executed_generations_count = 0

                    for current_run, (idx, prompt_text) in enumerate(storyboard_prompts, 1):
                        ts_match = re.match(r"^\[([\d:]+)\]", prompt_text.strip())
                        image_name = f"{ts_match.group(1).replace(':', '_')}.png" if ts_match else f"sentence_{idx}.png"
                        save_path = os.path.join(image_dir, image_name)

                        if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                            print(f"[SKIP] Frame {idx} ({image_name}) exists.")
                            continue

                        executed_generations_count += 1
                        if executed_generations_count > 1 and (executed_generations_count - 1) % reset_loop_limit == 0:
                            print(f"\n[RESET] Refreshing Flow UI (Limit: {reset_loop_limit})...")
                            flow_page.reload()
                            setup_flow_ui(flow_page)

                        print(f"Rendering Frame {idx}...")
                        success = False
                        
                        for attempt in range(1, 4):
                            try:
                                # 1. Paste Monolithic Prompt
                                input_box = flow_page.locator("textarea[placeholder*='What do you want to create' i], textarea").first
                                input_box.click()
                                input_box.fill(prompt_text)
                                time.sleep(0.5)
                                input_box.press("Enter") # Submit to Flow
                                
                                # 2. Wait for rendering (DOM monitor)
                                print(f"  Attempt {attempt}: Waiting for Flow generation...")
                                time.sleep(5) # Let the loading spinner appear
                                
                                # Wait for the new image to render in the workspace
                                img_locator = flow_page.locator("img").last
                                img_locator.wait_for(state="visible", timeout=45000)
                                time.sleep(2) # Stabilize DOM
                                
                                # 3. Forced-Center Hover Extraction
                                box = img_locator.bounding_box()
                                if box:
                                    hover_x, hover_y = box["width"] / 2, box["height"] / 2
                                    img_locator.hover(position={"x": hover_x, "y": hover_y}, force=True)
                                    time.sleep(1)
                                    
                                    # Locate Flow's specific download button
                                    dl_btn = flow_page.locator('button[aria-label*="Download" i], button[title*="Download" i]').last
                                    if dl_btn.is_visible():
                                        with flow_page.expect_download(timeout=15000) as download_info:
                                            dl_btn.click(force=True)
                                        
                                        download = download_info.value
                                        download.save_as(save_path)
                                        
                                        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                                            print(f"  ✅ Saved: {image_name}")
                                            success = True
                                            break
                                    else:
                                        print("  ⚠️ Download button not visible after hover.")
                                else:
                                    print("  ⚠️ Could not calculate bounding box.")
                                    
                            except PlaywrightTimeoutError:
                                print("  ⚠️ Timeout waiting for rendering or download.")
                            except Exception as e:
                                print(f"  ⚠️ Error: {e}")
                                
                            # If failed, refresh page and retry
                            flow_page.reload()
                            setup_flow_ui(flow_page)
                            
                        if not success:
                            if accounts_enabled:
                                print(f"\n[FAILOVER ALERT] Flow rendering failed 3 times. Rotating account...")
                                rotate_profile_index()
                                kill_cdp_chrome()
                                failover_triggered = True
                                break
                            else:
                                print(f"❌ Frame {idx} failed completely. Skipping.")

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
```

### Key Upgrades in this Implementation:
1. **The Monolithic Template:** Look closely at the `prompt_template` string in the code. Because Flow doesn't remember previous messages, the script forces Gemini to inject the character's *entire physical description* ("A bald character with a perfectly round white head...") into every single prompt automatically.
2. **Dual-Tab Orchestration:** The script cleanly separates logic. Gemini (Tab 1) generates the text file. Flow (Tab 2) reads the text file and generates the images. 
3. **Flow UI Automation (`setup_flow_ui`):** The script clicks `+ New project`, toggles the `Agent` off (so Google doesn't ruin our strict prompts), and sets the aspect ratio to 16:9, just like your screenshots requested. 

Save this file as `flow_image_generator.py`. 