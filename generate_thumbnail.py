import os
import sys

# Force Python to prioritize the parent project root directory when importing modules
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import re
import time
import json
import base64
import glob
from playwright.sync_api import sync_playwright
from utils import get_config_value, launch_browser_with_profile, kill_cdp_chrome, rotate_profile_index, send_telegram_notification
from gemini_utils import (
    find_input_box, find_send_button,
    start_clean_gemini_chat, select_gemini_model,
    wait_for_gemini_response  # Re-imported standard text wait helper
)

sys.stdout.reconfigure(encoding='utf-8')

THUMBNAIL_COUNT = 5
TOP_N = 2

THUMBNAIL_SETUP_PROMPT = """### CORE DIRECTIVE: YOUTUBE THUMBNAIL CONCEPT EXTRACTOR ###
You are a YouTube thumbnail strategist. Analyze the video script and extract 5 thumbnail concepts that maximize click-through rate.

For each concept, provide:
- EMOTION: The core emotion (fear, wonder, anger, curiosity, excitement, shock, nostalgia)
- SCENE: A single visual moment that captures the video's hook — one frozen frame, not a sequence
- TEXT_OVERLAY: Short Arabic text (3-5 words) for the thumbnail — bold, provocative, curiosity-driven
- STYLE: One of: cinematic, dramatic, mysterious, confrontational, emotional

RULES:
1. Each concept must target a DIFFERENT emotion — no duplicates
2. The scene must be visually describable in one sentence — a photographer could stage it
3. The text overlay must create a curiosity gap — make them NEED to click
4. Avoid cliche stock photo language — no "person thinking at desk"
5. Think: what makes someone stop scrolling?

Return a JSON array of 5 objects with keys: emotion, scene, text_overlay, style.
Return ONLY the JSON array, no commentary."""

CRITIQUE_PROMPT_TEMPLATE = """You generated {count} thumbnail prompts for a YouTube video about "{topic}".

Here are the {count} prompts:
{prompts_json}

Rate each on these criteria (1-10 scale):
- CLICK_APPEAL: Would you stop scrolling for this?
- EMOTIONAL_IMPACT: Does it trigger a visceral reaction?
- VISUAL_CLARITY: Is the composition immediately readable at small size?

You MUST pick EXACTLY the top {top_n} winners (no more, no less). For each winner, suggest ONE specific improvement.

CRITICAL INDEXING RULE: You must use 0-based indexing (0, 1, 2, 3, 4) exactly matching the positions of the prompts above. For example:
- Prompt 1 is index 0.
- Prompt 2 is index 1.
- Prompt 5 is index 4.

Return a JSON object with:
- "scores": array of {{"index": N, "click_appeal": N, "emotional_impact": N, "visual_clarity": N, "total": N}}
- "winners": array of EXACTLY {top_n} winning 0-based indices (e.g. [1, 4])
- "improvements": object mapping the 0-based index to its improvement suggestion (e.g. {{"1": "suggestion for Prompt 2", "4": "suggestion for Prompt 5"}})

Return ONLY the JSON, no commentary."""


def get_latest_run_folder(runs_path="youtube_runs"):
    """Finds the latest run folder by checking both CWD and script-relative paths."""
    # Try resolving relative to generate_thumbnail.py's own directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rel_to_script = os.path.join(script_dir, runs_path)
    
    resolved_path = runs_path
    if os.path.exists(rel_to_script):
        resolved_path = rel_to_script
    elif not os.path.exists(resolved_path):
        return None

    folders = glob.glob(os.path.join(resolved_path, "*/"))
    if not folders:
        return None
    return max(folders, key=os.path.getmtime)


def read_script(folder):
    """Read refined_script.txt, fall back to final_output.txt."""
    refined_path = os.path.join(folder, "refined_script.txt")
    final_path = os.path.join(folder, "final_output.txt")

    for path in [refined_path, final_path]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()

    print("Error: No script found (refined_script.txt or final_output.txt).")
    sys.exit(1)

def send_and_wait(page, message, timeout=180):
    """Generic send-message-wait-for-response helper using standard text selectors."""
    input_box = find_input_box(page)
    if not input_box:
        print("[ERROR] Could not find input box.")
        return None

    input_box.click()
    time.sleep(0.5)
    input_box.fill(message)
    time.sleep(1)

    send_btn = find_send_button(page)
    if send_btn:
        send_btn.click()
    else:
        page.keyboard.press("Enter")

    # Import and use RESPONSE_SELECTOR to track text responses safely
    from gemini_utils import RESPONSE_SELECTOR
    initial_count = page.locator(RESPONSE_SELECTOR).count()
    return wait_for_gemini_response(page, initial_count, timeout_seconds=timeout)

def wait_for_gemini_image_response(page, initial_count, timeout_seconds=120):
    """Wait specifically for Gemini to render a visible image inside the last model-response."""
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
        
    print("Waiting for image to generate and render in DOM...")
    last_log_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        elapsed = time.time() - start_time
        if time.time() - last_log_time >= 15:
            print(f"Still waiting for image generation... (elapsed: {elapsed:.1f}s / {timeout_seconds}s)")
            last_log_time = time.time()
            
        try:
            # Periodically prevent background tab throttling
            if int(elapsed) % 10 == 0:
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                    
            last_response = page.locator("model-response").last
            
            # Automatically scroll the active response block into view to trigger instant rendering
            try:
                last_response.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
                
            # Check if the generated image is attached and visible
            img_locator = last_response.locator("img").first
            if img_locator.is_visible():
                time.sleep(2)  # Soft buffer to ensure the image fully loads its source
                return "image_ready"
                
        except Exception:
            pass
        time.sleep(1)
        
    print(f"Warning: Image response timed out after {timeout_seconds} seconds.")
    return None


def send_image_prompt_and_wait(page, message, timeout=180):
    """Dedicated helper to send image prompts and wait using model-response selectors."""
    input_box = find_input_box(page)
    if not input_box:
        print("[ERROR] Could not find input box.")
        return None

    input_box.click()
    time.sleep(0.5)
    input_box.fill(message)
    time.sleep(1)

    send_btn = find_send_button(page)
    if send_btn:
        send_btn.click()
    else:
        page.keyboard.press("Enter")

    initial_count = page.locator("model-response").count()
    return wait_for_gemini_image_response(page, initial_count, timeout_seconds=timeout)


def extract_json_from_response(text):
    """Extract JSON from a response that may contain markdown code blocks."""
    code_block = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"[WARNING] Could not parse JSON from response: {text[:200]}")
        return None


def build_webcomic_thumbnail_prompt(concept, index):
    """Build a natural-language image prompt based on the visual_style.txt guidelines."""
    emotion = concept.get("emotion", "intense")
    scene = concept.get("scene", "dramatic scene")
    text_overlay = concept.get("text_overlay", "")
    
    character_casting = (
        "Main Character details: A simple 2D character. Head is a uniform white circle with no nose or ears. "
        "Mouth is a single expressive black vector stroke. Exactly 3 to 5 thin black hair strands curving from the top of the scalp. "
        "Wears an unbranded charcoal-grey hoodie (with a visible hood resting on the shoulders) and dark sweatpants. "
        "Arms and legs are simple, uniform black line art."
    )
    
    style_anchor = (
        "Style Anchor: 2D digital webcomic, pristine solid uniform black vector outlines, "
        "flat base colors with dramatic cinematic lighting, cool-toned desaturated slate palette "
        "with exactly one vibrant pop of accent color, hyper-sharp focus, dynamic composition, 16:9 cinematic aspect ratio."
    )
    
    # Compile the prompt into a clean natural-language paragraph
    prompt = (
        f"Generate a cinematic YouTube thumbnail image based on the following specifications:\n\n"
        f"Scene Composition: {scene}\n"
        f"Character Aesthetics: {character_casting}\n"
        f"Emotion and facial expression: {emotion}\n"
        f"Visual Art Style: {style_anchor}\n"
    )
    
    if text_overlay:
        prompt += (
            f"Typography Rule: You must place the exact bold, sharp Arabic text \"{text_overlay}\" "
            f"in the center or bottom third of the frame. Keep the background clean and empty around the text to prevent rendering errors.\n"
        )
        
    prompt += "NEGATIVE: [no extra text, no random letters, no watermarks, no gibberish, no AI signatures, no hyper-saturation, no soft focus filters]"
    return prompt


def generate_images_via_gemini(page, prompts, output_dir):
    """Send each prompt to Gemini and download generated images using robust UI hover/download."""
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    for i, prompt_text in enumerate(prompts):
        print(f"\n[IMAGE] Generating variant {i + 1}/{len(prompts)}...")

        response = send_image_prompt_and_wait(page, prompt_text, timeout=300)

        if not response:
            print(f"[WARNING] No response for variant {i + 1}. Skipping.")
            continue

        filepath = os.path.join(output_dir, f"variant_{i + 1}.png")
        try:
            last_response = page.locator("model-response").last
            img_locator = last_response.locator("img").first
            
            # Wait for image to actually be attached and visible
            img_locator.wait_for(state="visible", timeout=15000)
            
            # Force scroll into view to ensure the hover action is not blocked
            img_locator.scroll_into_view_if_needed()
            time.sleep(1)
            
            # Leverage Playwright's Relative Hover (Forced Center)
            box = img_locator.bounding_box()
            if box:
                # Hover the exact dead-center of the image to trigger the UI overlay safely
                hover_x = box["width"] / 2
                hover_y = box["height"] / 2
                
                # force=True bypasses the "subtree intercepts pointer events" error from hidden Google UI layers
                img_locator.hover(position={"x": hover_x, "y": hover_y}, force=True)
                time.sleep(1.5) # Wait for the overlay animation to reveal the button
                
                # Robust Selector for the Download Button from script_image_generator.py
                dl_btn = last_response.locator(
                    'button[aria-label*="Download full size" i], '
                    'button[aria-label*="Download" i], '
                    'button[aria-label*="تحميل" i], '
                    'button[data-tooltip*="Download" i]'
                ).first
                
                if dl_btn.is_visible():
                    # The Native expect_download Handler
                    with page.expect_download(timeout=30000) as download_info:
                        dl_btn.click(force=True)
                        
                    download = download_info.value
                    download.save_as(filepath)
                    
                    # Post-Download Verification Guard
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        generated.append(filepath)
                        print(f"[OK] Saved variant {i + 1}: {filepath}")
                    else:
                        print(f"[WARNING] Download completed but file is missing or 0 bytes: {filepath}")
                else:
                    print("[WARNING] Hover succeeded but Download button did not appear.")
            else:
                print("[WARNING] Could not calculate image bounding box for hover.")
        except Exception as e:
            # Fallback to base64 extract if UI interaction fails
            b64_match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', response)
            if b64_match:
                try:
                    img_data = base64.b64decode(b64_match.group(1))
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    generated.append(filepath)
                    print(f"[OK] Saved variant {i + 1} (base64): {filepath}")
                except Exception as ex:
                    print(f"[ERROR] Base64 extraction failed: {ex}")
            else:
                print(f"[ERROR] Image extraction failed for variant {i + 1}: {e}")

    return generated


def main():
    print("=" * 60)
    print(" THUMBNAIL: YouTube Thumbnail Generation Pipeline")
    print("=" * 60)

    folder = get_latest_run_folder()
    if not folder:
        print("No youtube_runs folder found.")
        sys.exit(1)

    video_title = os.path.basename(os.path.normpath(folder))
    print(f"Processing: {video_title}")

    output_dir = os.path.join(folder, "thumbnails")
    if os.path.exists(output_dir) and len(os.listdir(output_dir)) >= TOP_N:
        print(f"Thumbnails already generated ({len(os.listdir(output_dir))} files). Skipping.")
        return

    script_text = read_script(folder)
    script_excerpt = script_text[:6000]

    model_name = get_config_value("THUMBNAIL_MODEL", get_config_value("REFINE_MODEL", "Pro"))
    max_retries = int(get_config_value("FAILOVER_RETRY_LIMIT", "4"))
    switch_accounts = get_config_value("SWITCH_ACCOUNTS_ENABLED", "true").lower() == "true"
    browser_type = get_config_value("BROWSER_TYPE", "chrome")
    profile_index = int(get_config_value("ACTIVE_PROFILE_INDEX", "1"))

    prompts_path = os.path.join(folder, "thumbnail_prompts.json")
    critique_path = os.path.join(folder, "thumbnail_critique.json")

    with sync_playwright() as p:
        try:
            # Attempt to connect to an existing running session on the IPv4 loopback
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            print(f"Successfully connected to existing {browser_type.capitalize()} session on port 9222.")
        except Exception:
            print("Debugging browser is closed or unreachable on port 9222. Launching framework...")
            # Automatically launch Chrome using your profile index config
            if not launch_browser_with_profile(browser_type, profile_index):
                sys.exit(1)
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")

        context = browser.contexts[0]
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = context.new_page()

        # Phase 1: Concept extraction
        print("\n[PHASE 1] Extracting thumbnail concepts...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        concept_prompt = f"{THUMBNAIL_SETUP_PROMPT}\n\nSCRIPT EXCERPT:\n{script_excerpt}"
        concept_response = send_and_wait(page, concept_prompt, timeout=180)

        concepts = extract_json_from_response(concept_response)
        if not concepts or not isinstance(concepts, list) or len(concepts) < 3:
            print("[ERROR] Failed to extract valid thumbnail concepts. Retrying...")
            start_clean_gemini_chat(page)
            time.sleep(2)
            select_gemini_model(page, model_name)
            concept_response = send_and_wait(page, concept_prompt, timeout=180)
            concepts = extract_json_from_response(concept_response)

        if not concepts:
            print("[FATAL] Could not extract thumbnail concepts after retry.")
            page.close()
            sys.exit(1)

        concepts = concepts[:THUMBNAIL_COUNT]
        print(f"[OK] Extracted {len(concepts)} concepts.")

        # Phase 2: Build Webcomic Style prompts
        print("\n[PHASE 2] Building Webcomic Style prompts...")
        webcomic_prompts = [build_webcomic_thumbnail_prompt(c, i) for i, c in enumerate(concepts)]

        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(webcomic_prompts, f, ensure_ascii=False, indent=2)
        print(f"[OK] Prompts saved to {prompts_path}")

        # Phase 3: Self-critique
        print("\n[PHASE 3] Running self-critique loop...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        topic = video_title.replace("_", " ").replace("-", " ")
        critique_msg = CRITIQUE_PROMPT_TEMPLATE.format(
            count=len(webcomic_prompts),
            topic=topic,
            prompts_json=json.dumps(webcomic_prompts, ensure_ascii=False, indent=2),
            top_n=TOP_N
        )
        critique_response = send_and_wait(page, critique_msg, timeout=180)

        critique = extract_json_from_response(critique_response)
        if critique:
            with open(critique_path, "w", encoding="utf-8") as f:
                json.dump(critique, f, ensure_ascii=False, indent=2)
            print(f"[OK] Critique saved to {critique_path}")
        else:
            print("[WARNING] Critique failed. Using first 2 prompts as defaults.")
            critique = {"winners": [0, 1], "improvements": {}}

        # Phase 4: Generate images for winners
        print("\n[PHASE 4] Generating thumbnail images...")
        winners = critique.get("winners", list(range(TOP_N)))[:TOP_N]
        improvements = critique.get("improvements", {})

        winning_prompts = []
        for w_idx in winners:
            if w_idx < len(webcomic_prompts):
                prompt_str = webcomic_prompts[w_idx]
                if str(w_idx) in improvements:
                    prompt_str += f"\nRefinement Suggestion: {improvements[str(w_idx)]}"
                winning_prompts.append(prompt_str)

        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        generated = generate_images_via_gemini(page, winning_prompts, output_dir)

        page.close()

    if generated:
        print(f"\n{'=' * 60}")
        print(f" THUMBNAILS COMPLETE: {len(generated)} images for {video_title}")
        print(f"{'=' * 60}")
        send_telegram_notification(f"✅ Thumbnails generated: {video_title} ({len(generated)} variants)")
    else:
        print("\n[WARNING] No thumbnails were generated.")
        send_telegram_notification(f"⚠️ Thumbnail generation failed: {video_title}")


if __name__ == "__main__":
    main()
