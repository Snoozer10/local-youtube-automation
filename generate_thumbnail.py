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

THUMBNAIL_SETUP_PROMPT = """### CORE DIRECTIVE: YOUTUBE THUMBNAIL STRATEGIST (2D WEBCOMIC STYLE) — CTR MAXIMIZATION ENGINE ###
You are an elite YouTube thumbnail strategist specializing in high-CTR 2D animated webcomic channels. You create thumbnail concepts that complement specific video titles to maximize CTR.

═══════════════════════════════════════════════════════════════
GOLDEN RULES FOR HIGH CTR (TITLE + THUMBNAIL SYNERGY)
═══════════════════════════════════════════════════════════════
1. SYNERGY > REPETITION: Thumbnail text (1-3 words MAX) must NEVER repeat words from the title. 
   - Title = Driving Question / Premise.
   - Thumbnail Visual = Dramatic Reaction / Mysterious Catalyst / Missing Puzzle Piece.
   - Thumbnail Text = Emotional Trigger ("صدمة!", "السر", "احذر", "قبل/بعد").
2. 1-SECOND MOBILE SCAN: 1 dominant focal point (2D webcomic character with white circular head), 40%+ dark negative space, ultra-high contrast.
3. CURIOSITY GAP ARCHETYPE: Each concept must deploy 1 specific curiosity gap (Moment, Story, Result, Transformation, or Novelty).
4. ARABIC TYPOGRAPHY: 1-3 Arabic words MAX, ultra-simple vocabulary (7-year-old reading level), high-contrast stroke.

═══════════════════════════════════════════════════════════════
TASK: GENERATE 1 THUMBNAIL CONCEPT FOR EACH PROVIDED TITLE
═══════════════════════════════════════════════════════════════
For each title provided, design a tailored 2D webcomic thumbnail concept that perfectly complements that title's specific angle without repeating its text.

FOR EACH TITLE, PROVIDE:
- title_index: Integer (1, 2, 3...) matching the title number
- title_text: Cleaned title text
- curiosity_archetype: One of [moment, story, result, transformation, novelty]
- scene: ONE visually specific 2D webcomic frame featuring the main character (simple 2D character with white circular head, charcoal hoodie) interacting with dynamic props/environment.
- text_overlay: 1-2 Arabic words (MAX 3) that ADD curiosity without repeating the title.
- visual_recipe:
  * lighting: (e.g., "glowing neon cyan rim light, dark shadow background")
  * color_palette: (e.g., "slate background with glowing golden accents")
  * composition: (e.g., "character on left 1/3, glowing object center, clean right negative space")

OUTPUT FORMAT: JSON ARRAY ONLY — NO MARKDOWN, NO COMMENTARY
[
  {
    "title_index": 1,
    "title_text": "...",
    "curiosity_archetype": "moment",
    "scene": "...",
    "text_overlay": "...",
    "visual_recipe": {
      "lighting": "...",
      "color_palette": "...",
      "composition": "..."
    }
  }
]"""

CRITIQUE_PROMPT_TEMPLATE = """Now evaluate the thumbnail concepts you just generated above against their paired titles.

RATE EACH Title + Thumbnail Pair on a 1-10 scale (be harsh — average ~5):
- TITLE_THUMBNAIL_SYNERGY: Does thumbnail complement title without repeating words?
- CURIOSITY_GAP_STRENGTH: Does the pair create an irresistible "itch to click"?
- 1_SECOND_MOBILE_CLARITY: Is composition readable instantly on a phone screen?
- EMOTIONAL_IMPACT: Visceral reaction pose/scene?

YOU MUST PICK EXACTLY THE TOP {top_n} BEST TITLE + THUMBNAIL COMBINATIONS.

CRITICAL INDEXING RULE:
- Refer to concepts by their "title_index" from the generated JSON array above.

For each winning pair, suggest ONE specific visual tweak to maximize CTR.

Return ONLY this JSON object:
{{
  "scores": [
    {{"title_index": 1, "total_score": 35}},
    {{"title_index": 2, "total_score": 28}}
  ],
  "winners": [1, 3],  // array of {top_n} title_index numbers
  "improvements": {{
    "1": "Specific visual tweak for title_index 1",
    "3": "Specific visual tweak for title_index 3"
  }}
}}"""

# ============================================================
# USAGE IN YOUR GENERATE_THUMBNAIL.PY:
# ============================================================
# 1. Keep THUMBNAIL_COUNT = 5, TOP_N = 2 at top
# 2. Replace THUMBNAIL_SETUP_PROMPT with the enhanced version above
# 3. Replace CRITIQUE_PROMPT_TEMPLATE with the enhanced version above
# 4. When calling the LLM, inject these variables into the prompt:
#    - {topic}: video title/main topic from script
#    - {niche}: detected niche (you add this detection step)
#    - {audience}: e.g., "Saudi youth 18-30", "MENA tech enthusiasts"
#    - {count}: THUMBNAIL_COUNT
#    - {top_n}: TOP_N
#    - {prompts_json}: JSON string of the 5 generated concepts
#
# NICHE DETECTION HELPER (add before calling setup prompt):
# def detect_niche_and_auditor(script: str) -> tuple[str, str]:
#     # Simple keyword-based or LLM-based classification
#     # Returns (niche, audience_profile)
#     # Example niches: "arabic_tech_reviews", "mena_gaming", "islamic_finance",
#     #                 "saudi_lifestyle", "egyptian_comedy", "arabic_storytelling",
#     #                 "arabic_education", "mena_crypto", "saudi_travel"
#     pass
#
# Then format the setup prompt with niche/audience context before sending to LLM.

def clean_title(title_text):
    """Removes parenthetical text like (تحليل عصبي) and extra spaces."""
    cleaned = re.sub(r'\(.*?\)', '', title_text)
    return cleaned.strip()


def read_titles(folder):
    """Reads titles.txt, extracts numbered titles, and cleans parenthetical tags."""
    titles_path = os.path.join(folder, "titles.txt")
    if not os.path.exists(titles_path):
        return []
    
    with open(titles_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Match lines starting with "1.", "2.", "1-", etc.
    raw_matches = re.findall(r'^(\d+)[\.\-]\s*(.+)$', content, re.MULTILINE)
    cleaned_titles = []
    for idx, text in raw_matches:
        cleaned_text = clean_title(text)
        if cleaned_text:
            cleaned_titles.append({"index": int(idx), "text": cleaned_text})
            
    return cleaned_titles


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
    """Build a natural-language image prompt based on concept and webcomic art guidelines."""
    emotion = concept.get("emotion", "intense")
    scene = concept.get("scene", "dramatic scene")
    text_overlay = concept.get("text_overlay", "")
    visual_recipe = concept.get("visual_recipe", {})
    
    lighting = visual_recipe.get("lighting", "cinematic accent lighting")
    palette = visual_recipe.get("color_palette", "dark desaturated slate with vivid glowing accents")
    composition = visual_recipe.get("composition", "dynamic focal point with clean negative space")

    character_casting = (
        "Main Character specs: A simple 2D webcomic character. Head is a uniform white circle with no nose or ears. "
        "Mouth is a single expressive black vector stroke. Exactly 3 to 5 thin black hair strands curving from the top of the scalp. "
        "Wears an unbranded charcoal-grey hoodie (with a visible hood resting on the shoulders) and dark sweatpants. "
        "Arms and legs are simple, uniform black line art."
    )
    
    style_anchor = (
        "Visual Art Style: 2D digital webcomic, pristine solid uniform black vector outlines, "
        "flat base colors with dramatic cinematic lighting effects, hyper-sharp focus, dynamic composition, 16:9 cinematic aspect ratio."
    )
    
    prompt = (
        f"Generate a cinematic YouTube thumbnail image based on the following specifications:\n\n"
        f"Scene & Action: {scene}\n"
        f"Character Aesthetics: {character_casting}\n"
        f"Emotion & Posing: Expressing {emotion}\n"
        f"Lighting & Atmosphere: {lighting}\n"
        f"Color Palette: {palette}\n"
        f"Composition Strategy: {composition}\n"
        f"Art Style: {style_anchor}\n"
    )
    
    if text_overlay:
        prompt += (
            f"Typography Rule: Render the exact bold Arabic text \"{text_overlay}\" in large, clean Arabic typography "
            f"integrated into an uncluttered high-contrast area of the image.\n"
        )
        
    prompt += "NEGATIVE PROMPT: [no extra text, no random letters, no photorealism, no watermarks, no gibberish, no soft focus blur]"
    return prompt


def generate_images_via_gemini(page, items, output_dir):
    """Send each prompt to Gemini and download generated images using robust UI hover/download."""
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    for i, item in enumerate(items):
        if isinstance(item, dict):
            prompt_text = item["prompt"]
            filename = item["filename"]
        else:
            prompt_text = item
            filename = f"variant_{i + 1}.png"

        print(f"\n[IMAGE] Generating {filename} ({i + 1}/{len(items)})...")

        response = send_image_prompt_and_wait(page, prompt_text, timeout=300)

        if not response:
            print(f"[WARNING] No response for {filename}. Skipping.")
            continue

        filepath = os.path.join(output_dir, filename)
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
    switch_accounts = (
        get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").strip().lower()
        in ("true", "1", "yes")
    )
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

        # Phase 1 & 3: Single Chat Session for Strategy & Critique
        print("\n[PHASE 1 & 3] Extracting and Critiquing Title-Matched Concepts in single chat...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        titles = read_titles(folder)
        if titles:
            titles_formatted = "\n".join([f"{t['index']}. {t['text']}" for t in titles])
        else:
            titles_formatted = f"1. {video_title.replace('_', ' ').replace('-', ' ')}"

        concept_prompt = (
            f"{THUMBNAIL_SETUP_PROMPT}\n\n"
            f"TITLES FROM titles.txt:\n{titles_formatted}\n\n"
            f"SCRIPT EXCERPT:\n{script_excerpt}"
        )
        
        # Step 1: Send setup prompt
        concept_response = send_and_wait(page, concept_prompt, timeout=180)
        concepts = extract_json_from_response(concept_response)

        if not concepts or not isinstance(concepts, list):
            print("[ERROR] Failed to extract valid thumbnail concepts. Retrying...")
            start_clean_gemini_chat(page)
            time.sleep(2)
            select_gemini_model(page, model_name)
            concept_response = send_and_wait(page, concept_prompt, timeout=180)
            concepts = extract_json_from_response(concept_response)

        if not concepts:
            print("[FATAL] Could not extract concepts.")
            page.close()
            sys.exit(1)

        print(f"[OK] Generated {len(concepts)} title-matched concepts.")

        # Save generated prompts/concepts JSON for reference
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(concepts, f, ensure_ascii=False, indent=2)

        # Step 2: Send Critique Prompt directly in the SAME chat session!
        critique_msg = CRITIQUE_PROMPT_TEMPLATE.format(top_n=TOP_N)
        critique_response = send_and_wait(page, critique_msg, timeout=180)
        critique = extract_json_from_response(critique_response)

        if critique:
            with open(critique_path, "w", encoding="utf-8") as f:
                json.dump(critique, f, ensure_ascii=False, indent=2)
            print(f"[OK] Critique saved to {critique_path}")
        else:
            print("[WARNING] Critique failed. Defaulting to first 2 title indices.")
            critique = {"winners": [c.get("title_index", i + 1) for i, c in enumerate(concepts[:TOP_N])], "improvements": {}}

        winners = critique.get("winners", [1, 2])[:TOP_N]
        improvements = critique.get("improvements", {})

        # Phase 2 & 4: Build prompts and Generate Images (saved as title_X_thumbnail.png)
        winning_items = []
        for concept in concepts:
            t_idx = concept.get("title_index", 1)
            if t_idx in winners:
                prompt_str = build_webcomic_thumbnail_prompt(concept, t_idx)
                if str(t_idx) in improvements:
                    prompt_str += f"\nVisual Refinement: {improvements[str(t_idx)]}"
                
                winning_items.append({
                    "title_index": t_idx,
                    "filename": f"title_{t_idx}_thumbnail.png",
                    "prompt": prompt_str
                })

        print("\n[PHASE 4] Opening clean session for image generation...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        generated = generate_images_via_gemini(page, winning_items, output_dir)

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
