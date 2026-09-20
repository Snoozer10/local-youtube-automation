import os
import sys

# Force Python to prioritize the parent project root directory when importing modules
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import base64  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from contextlib import nullcontext  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

from gemini_utils import (  # noqa: E402
    find_input_box,
    find_send_button,
    select_gemini_model,
    start_clean_gemini_chat,
    wait_for_gemini_response,  # Re-imported standard text wait helper
)
from text_gate import (  # noqa: E402
    STRENGTHENED_NEGATIVE_PROMPT,
    check_text_collision,
    dump_text_collision_debug,
)
from utils import (  # noqa: E402
    get_config_value,
    launch_browser_with_profile,
    send_telegram_notification,
)
from validator import STRICT_NEGATIVE_PROMPT  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

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
    cleaned = re.sub(r"\(.*?\)", "", title_text)
    return cleaned.strip()


def read_titles(folder):
    """Reads titles.txt, extracts numbered titles, and cleans parenthetical tags."""
    titles_path = os.path.join(folder, "titles.txt")
    if not os.path.exists(titles_path):
        return []

    with open(titles_path, encoding="utf-8") as f:
        content = f.read()

    # Match lines starting with "1.", "2.", "1-", etc.
    raw_matches = re.findall(r"^(\d+)[\.\-]\s*(.+)$", content, re.MULTILINE)
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
            with open(path, encoding="utf-8") as f:
                return f.read().strip()

    print("Error: No script found (refined_script.txt or final_output.txt).")
    sys.exit(1)


def send_and_wait(page, message, timeout=180):
    """Generic send-message-wait-for-response helper using standard text selectors."""
    input_box = find_input_box(page)
    if not input_box:
        print("[ERROR] Could not find input box.")
        return None

    # Import and use RESPONSE_SELECTOR to track text responses safely
    from gemini_utils import RESPONSE_SELECTOR

    initial_count = page.locator(RESPONSE_SELECTOR).count()

    input_box.click()
    time.sleep(0.5)
    input_box.fill(message)
    time.sleep(1)

    send_btn = find_send_button(page)
    if send_btn:
        send_btn.click()
    else:
        page.keyboard.press("Enter")

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
            print(
                f"Still waiting for image generation... (elapsed: {elapsed:.1f}s / {timeout_seconds}s)"
            )
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

    initial_count = page.locator("model-response").count()

    input_box.click()
    time.sleep(0.5)
    input_box.fill(message)
    time.sleep(1)

    send_btn = find_send_button(page)
    if send_btn:
        send_btn.click()
    else:
        page.keyboard.press("Enter")

    return wait_for_gemini_image_response(page, initial_count, timeout_seconds=timeout)


def extract_json_from_response(text):
    """Extract JSON from a response that may contain markdown code blocks."""
    if not text or not isinstance(text, str):
        return None

    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_block:
        text = code_block.group(1)
    text = text.strip()

    # Trim surrounding prose to outermost bracket/brace
    start_idx = -1
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            start_idx = i
            break
    end_idx = -1
    for i in range(len(text) - 1, -1, -1):
        if text[i] in ("}", "]"):
            end_idx = i + 1
            break

    candidate = text[start_idx:end_idx] if (start_idx != -1 and end_idx != -1 and start_idx < end_idx) else text

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
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
    palette = visual_recipe.get(
        "color_palette", "dark desaturated slate with vivid glowing accents"
    )
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
            "Composition Note: Ensure clean, uncluttered high-contrast negative space is reserved for title overlay; "
            "do not paint or render any letters, words, or typography directly onto the raw image bitmap.\n"
        )

    prompt += f"NEGATIVE PROMPT: [{STRICT_NEGATIVE_PROMPT}]"
    return prompt


def parse_critique_json(response_text, concepts=None, top_n=TOP_N):
    """Parses critique ranking JSON from Gemini response, with fallback on malformed response."""
    critique = extract_json_from_response(response_text) if response_text else None
    if isinstance(critique, dict) and "winners" in critique and isinstance(critique["winners"], list):
        return critique

    print("[WARNING] Critique failed or malformed. Defaulting to fallback title indices.")
    concepts = concepts or []
    fallback_winners = [
        c.get("title_index", i + 1) for i, c in enumerate(concepts[:top_n])
    ]
    if not fallback_winners:
        fallback_winners = list(range(1, top_n + 1))
    return {
        "winners": fallback_winners,
        "improvements": {},
    }


def _save_image_from_response(page, response, filepath):
    """Downloads image via Playwright UI hover/click or falls back to base64 data extraction."""
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
            hover_x = box["width"] / 2
            hover_y = box["height"] / 2

            # force=True bypasses the "subtree intercepts pointer events" error from hidden Google UI layers
            img_locator.hover(position={"x": hover_x, "y": hover_y}, force=True)
            time.sleep(1.5)  # Wait for the overlay animation to reveal the button

            # Robust Selector for the Download Button from script_image_generator.py
            dl_btn = last_response.locator(
                'button[aria-label*="Download full size" i], '
                'button[aria-label*="Download" i], '
                'button[aria-label*="تحميل" i], '
                'button[data-tooltip*="Download" i]'
            ).first

            if dl_btn.is_visible():
                with page.expect_download(timeout=30000) as download_info:
                    dl_btn.click(force=True)

                download = download_info.value
                download.save_as(filepath)

                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    return True
                else:
                    print(
                        f"[WARNING] Download completed but file is missing or 0 bytes: {filepath}"
                    )
            else:
                print("[WARNING] Hover succeeded but Download button did not appear.")
        else:
            print("[WARNING] Could not calculate image bounding box for hover.")
    except Exception as e:
        print(f"[WARNING] Download interaction error: {e}")

    # Fallback to direct src inspection / screenshot / base64
    try:
        last_response = page.locator("model-response").last
        img_locator = last_response.locator("img").first
        if img_locator.is_visible():
            src = img_locator.get_attribute("src") or ""
            if src.startswith("data:image/"):
                b64_data = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", src)
                if b64_data:
                    img_data = base64.b64decode(b64_data.group(1))
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        return True
            img_locator.screenshot(path=filepath)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print(f"[INFO] Saved image via element screenshot: {filepath}")
                return True
    except Exception as ex:
        print(f"[ERROR] Direct image fallback extraction failed: {ex}")

    return False


def generate_images_via_gemini(page, items, output_dir):
    """Send each prompt to Gemini and download generated images using robust UI hover/download."""
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    for i, item in enumerate(items):
        if isinstance(item, dict):
            base_prompt = item["prompt"]
            filename = item["filename"]
            chunk_idx = item.get("title_index", i + 1)
        else:
            base_prompt = item
            filename = f"variant_{i + 1}.png"
            chunk_idx = i + 1

        filepath = os.path.join(output_dir, filename)

        for attempt in (1, 2):
            if attempt == 1:
                prompt_to_send = base_prompt
                print(f"\n[IMAGE] Generating {filename} ({i + 1}/{len(items)})...")
            else:
                prompt_to_send = f"{base_prompt}\n{STRENGTHENED_NEGATIVE_PROMPT}"
                print(f"\n[IMAGE] Retrying {filename} with strengthened negative prompt (attempt 2)...")

            response = send_image_prompt_and_wait(page, prompt_to_send, timeout=300)
            if not response:
                print(f"[WARNING] No response for {filename} on attempt {attempt}.")
                continue

            saved = _save_image_from_response(page, response, filepath)
            if not saved or not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                print(
                    f"[WARNING] Download completed but file is missing or 0 bytes: {filepath}"
                )
                continue

            # Immediately after the downloaded PNG image is written to disk:
            has_collision, ocr_boxes = check_text_collision(filepath)
            if has_collision:
                if attempt == 1:
                    print(f"⚠️ [THUMBNAIL TEXT COLLISION] Detected text: {ocr_boxes}")
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except OSError:
                            pass
                    # Retry once appending STRENGTHENED_NEGATIVE_PROMPT
                    continue
                else:
                    # Attempt 2 also fails: dump debug and purge corrupt image
                    print(
                        f"⚠️ [THUMBNAIL TEXT COLLISION] Attempt 2 failed for {filename}. Purging image."
                    )
                    dump_path = os.path.join(
                        output_dir,
                        f"collision_debug_{os.path.splitext(filename)[0]}.json",
                    )
                    dump_text_collision_debug(
                        dump_path=dump_path,
                        chunk_index=chunk_idx,
                        image_path=filepath,
                        ocr_boxes=ocr_boxes,
                        prompt_text=prompt_to_send,
                    )
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except OSError:
                            pass
                    break
            else:
                generated.append(filepath)
                print(f"[OK] Saved variant {i + 1}: {filepath}")
                break

    return generated


def main():
    from youtube_automation.production.contracts import load_brief
    from youtube_automation.production.ledger import leased_resource, resource_database
    from youtube_automation.production.thumbnails import (
        concept_prompt as adaptive_concept_prompt,
    )
    from youtube_automation.production.thumbnails import critique_prompt as adaptive_critique_prompt
    from youtube_automation.production.thumbnails import (
        image_prompt as adaptive_image_prompt,
    )
    from youtube_automation.production.thumbnails import (
        publish as publish_adaptive_thumbnails,
    )
    from youtube_automation.production.thumbnails import recipe as adaptive_thumbnail_recipe
    from youtube_automation.production.thumbnails import (
        validate_concepts,
        validate_critique,
        validate_receipt,
    )
    from youtube_automation.production.writing import verify_written_episode

    print("=" * 60)
    print(" THUMBNAIL: YouTube Thumbnail Generation Pipeline")
    print("=" * 60)

    if len(sys.argv) > 1:
        if not os.path.isdir(sys.argv[1]):
            raise FileNotFoundError(f"Selected thumbnail run does not exist: {sys.argv[1]}")
        folder = os.path.abspath(sys.argv[1])
    else:
        folder = get_latest_run_folder()
    if not folder:
        print("No youtube_runs folder found.")
        sys.exit(1)

    video_title = os.path.basename(os.path.normpath(folder))
    print(f"Processing: {video_title}")

    adaptive_brief = None
    if os.path.isfile(os.path.join(folder, "episode_brief.json")):
        verify_written_episode(folder)
        adaptive_brief = load_brief(folder)

    output_dir = os.path.join(folder, "thumbnails")
    if not adaptive_brief and os.path.exists(output_dir) and len(os.listdir(output_dir)) >= TOP_N:
        print(f"Thumbnails already generated ({len(os.listdir(output_dir))} files). Skipping.")
        return

    script_text = read_script(folder)
    script_excerpt = script_text[:6000]

    model_name = get_config_value("THUMBNAIL_MODEL", get_config_value("REFINE_MODEL", "Pro"))
    source_titles = read_titles(folder)
    titles = source_titles or [{"index": 1, "text": video_title.replace("_", " ").replace("-", " ")}]
    if adaptive_brief:
        current_recipe = adaptive_thumbnail_recipe(adaptive_brief, script_text, titles, model_name)
        accepted = validate_receipt(folder, current_recipe)
        if accepted is not None:
            print(f"Verified {len(accepted)} accepted adaptive thumbnails. Skipping generation.")
            return
    browser_type = get_config_value("BROWSER_TYPE", "chrome")
    raw_profile = get_config_value("ACTIVE_PROFILE_INDEX", "1")
    match = re.search(r"\d+", str(raw_profile))
    profile_index = int(match.group(0)) if match else 1
    cdp_port = int(get_config_value("CDP_PORT", "9222"))

    suffix = f"_adaptive_{current_recipe[:16]}" if adaptive_brief else ""
    prompts_path = os.path.join(folder, f"thumbnail_prompts{suffix}.json")
    critique_path = os.path.join(folder, f"thumbnail_critique{suffix}.json")

    browser_lease = leased_resource(resource_database(), "browser") if adaptive_brief else nullcontext()
    with browser_lease, sync_playwright() as p:
        try:
            # Attempt to connect to an existing running session on the IPv4 loopback
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            print(
                f"Successfully connected to existing {browser_type.capitalize()} session on port {cdp_port}."
            )
        except Exception:
            print(
                f"Debugging browser is closed or unreachable on port {cdp_port}. Launching framework..."
            )
            # Automatically launch Chrome using your profile index config
            if not launch_browser_with_profile(browser_type, profile_index):
                sys.exit(1)
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")

        context = browser.contexts[0]
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = context.new_page()

        # Phase 1 & 3: Single Chat Session for Strategy & Critique
        print("\n[PHASE 1 & 3] Extracting and Critiquing Title-Matched Concepts in single chat...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        titles_formatted = "\n".join([f"{t['index']}. {t['text']}" for t in titles])

        concept_prompt = adaptive_concept_prompt(adaptive_brief, titles, script_text) if adaptive_brief else (
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
        if adaptive_brief:
            concepts = validate_concepts(concepts, titles)

        print(f"[OK] Generated {len(concepts)} title-matched concepts.")

        # Save generated prompts/concepts JSON for reference
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(concepts, f, ensure_ascii=False, indent=2)

        # Step 2: Send Critique Prompt directly in the SAME chat session!
        critique_msg = (
            adaptive_critique_prompt(adaptive_brief, min(TOP_N, len(titles)))
            if adaptive_brief
            else CRITIQUE_PROMPT_TEMPLATE.format(top_n=TOP_N)
        )
        critique_response = send_and_wait(page, critique_msg, timeout=180)
        critique = (
            validate_critique(extract_json_from_response(critique_response), titles, TOP_N)
            if adaptive_brief
            else parse_critique_json(critique_response, concepts, top_n=TOP_N)
        )

        if critique_response and extract_json_from_response(critique_response):
            with open(critique_path, "w", encoding="utf-8") as f:
                json.dump(critique, f, ensure_ascii=False, indent=2)
            print(f"[OK] Critique saved to {critique_path}")
        else:
            print("[WARNING] Critique failed. Using fallback winners.")

        winners = critique.get("winners", [1, 2])[:TOP_N]
        improvements = critique.get("improvements", {})

        # Phase 2 & 4: Build prompts and Generate Images (saved as title_X_thumbnail.png)
        winning_items = []
        for concept in concepts:
            t_idx = concept.get("title_index", 1)
            if t_idx in winners:
                prompt_str = (
                    adaptive_image_prompt(adaptive_brief, concept, STRICT_NEGATIVE_PROMPT)
                    if adaptive_brief
                    else build_webcomic_thumbnail_prompt(concept, t_idx)
                )
                if not adaptive_brief and str(t_idx) in improvements:
                    prompt_str += f"\nVisual Refinement: {improvements[str(t_idx)]}"

                winning_items.append(
                    {
                        "title_index": t_idx,
                        "filename": f"title_{t_idx}_thumbnail.png",
                        "prompt": prompt_str,
                    }
                )

        print("\n[PHASE 4] Opening clean session for image generation...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        if adaptive_brief:
            if len(winning_items) != min(TOP_N, len(titles)):
                raise ValueError("Adaptive thumbnail critique did not select the required title concepts")
            with tempfile.TemporaryDirectory(prefix="adaptive-thumbnail-", dir=folder) as scratch:
                generated = generate_images_via_gemini(page, winning_items, scratch)
                if len(generated) != len(winning_items):
                    raise ValueError("Adaptive thumbnail generation is incomplete; no receipt published")
                if read_titles(folder) != source_titles:
                    raise ValueError("Thumbnail titles changed during generation")
                generated = publish_adaptive_thumbnails(
                    folder, adaptive_brief, script_text, titles, model_name, generated
                )
        else:
            generated = generate_images_via_gemini(page, winning_items, output_dir)

        page.close()

    if generated:
        print(f"\n{'=' * 60}")
        print(f" THUMBNAILS COMPLETE: {len(generated)} images for {video_title}")
        print(f"{'=' * 60}")
        if not adaptive_brief:
            send_telegram_notification(
                f"✅ Thumbnails generated: {video_title} ({len(generated)} variants)"
            )
    else:
        print("\n[WARNING] No thumbnails were generated.")
        if not adaptive_brief:
            send_telegram_notification(f"⚠️ Thumbnail generation failed: {video_title}")


if __name__ == "__main__":
    main()
