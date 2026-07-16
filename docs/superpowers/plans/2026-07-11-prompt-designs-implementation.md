# Prompt Designs + Thumbnail Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Arabic script refinement (`refine_script.py`) and thumbnail generation (`generate_thumbnail.py`) to the YouTube automation pipeline, with shared Gemini utilities extracted into `gemini_utils.py`.

**Architecture:** Two-turn refinement prompt (setup + paragraph performance) matches existing `prompt_phase3.txt` pattern. Thumbnail pipeline uses Nano Banana Pro camera architecture with a self-critique loop. Five Gemini UI helpers extracted from copy-pasted code across 5+ files into a single shared module.

**Tech Stack:** Python 3.10+, Playwright CDP, Gemini Web UI, `python-docx`, `json`, `re`, `time`, `os`, `sys`

## Global Constraints

- Windows-only: hardcoded Chrome/Opera paths, `ctypes.windll`, `subprocess.CREATE_NEW_CONSOLE`
- UTF-8 stdout reconfigure: `sys.stdout.reconfigure(encoding='utf-8')` for Arabic text
- Browser must be manually signed into Gemini (`gemini.google.com`) before running
- `RESPONSE_SELECTOR = "model-response div.markdown"` — fragile, may need updating on Google UI changes
- All Gemini UI interactions use Playwright CDP against `localhost:9222`
- Config reads from `gemini_model.txt` via `utils.py:get_config_value()`
- `ensure_ascii=False` required for JSON outputs containing Arabic
- Checkpoint files delete on successful completion; if present, script resumes from last saved state

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `gemini_utils.py` | Create | 5 shared Gemini UI helpers extracted from duplicated code |
| `refine_prompt.txt` | Create | Two-turn refinement prompt (setup + performance) |
| `refine_script.py` | Create | Paragraph-level Arabic refinement via CDP |
| `generate_thumbnail.py` | Create | 3-5 thumbnail variant pipeline with self-critique |
| `run_agency.py` | Modify | Add `refine` step as 1b, add `refine` to default state |
| `gemini_model.txt` | Modify | Add `THUMBNAIL_MODEL=Pro` |

---

### Task 1: Extract Shared Gemini Helpers into `gemini_utils.py`

**Files:**
- Create: `gemini_utils.py`
- Reference: `automate_all.py:84-453` (source of extracted functions)

**Interfaces:**
- Consumes: Playwright `page` object, `RESPONSE_SELECTOR` constant
- Produces: `find_input_box(page)`, `find_send_button(page)`, `wait_for_gemini_response(page, initial_count, timeout)`, `start_clean_gemini_chat(page)`, `select_gemini_model(page, model_name)`, `get_last_response(page)`, `RESPONSE_SELECTOR`

**Rationale for which version to extract:**
- `find_input_box`: `automate_all.py:222-249` — 5 fallback selectors + fallback wait, most robust
- `find_send_button`: `automate_all.py:251-270` — 6 fallback selectors, reverse iteration
- `wait_for_gemini_response`: `automate_all.py:289-351` — growth monitoring + send button state + safety detection, most sophisticated
- `start_clean_gemini_chat`: `automate_all.py:84-135` — keyboard shortcut fallback, response count zeroing
- `select_gemini_model`: `automate_all.py:406-453` — model dropdown detection, active check
- `get_last_response`: `automate_all.py:272-284` — needed by `wait_for_gemini_response`

- [ ] **Step 1: Create `gemini_utils.py` with extracted functions**

```python
import re
import time

# Unified response selector to prevent tracking mismatches
RESPONSE_SELECTOR = "model-response div.markdown"


def find_input_box(page):
    """Locates the Gemini text input box using cascading selectors."""
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
    """Locates the Gemini send/submit button using cascading selectors."""
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
    """Reads the text content of the last Gemini response element."""
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


def wait_for_gemini_response(page, initial_count, timeout_seconds=180):
    """Waits for Gemini response to complete using growth monitoring and send button state."""
    start_time = time.time()

    print(f"Waiting for response to start rendering (initial_count={initial_count})...")
    response_started = False
    while time.time() - start_time < 90:
        try:
            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > initial_count:
                last_text = page.locator(RESPONSE_SELECTOR).nth(current_count - 1).inner_text().strip()
                if last_text:
                    response_started = True
                    print(f"Response rendering started: current_count={current_count}, text length={len(last_text)}")
                    break
        except Exception:
            pass
        time.sleep(0.5)

    if not response_started:
        print(f"Warning: Timeout waiting for response text to start rendering. (initial_count was {initial_count}, current_count is {page.locator(RESPONSE_SELECTOR).count()})")
        return get_last_response(page)

    print("Waiting for response to complete (monitoring text growth and stability)...")
    last_length = 0
    stable_cycles = 0

    while time.time() - start_time < timeout_seconds:
        try:
            send_btn = find_send_button(page)
            btn_ready = send_btn and send_btn.is_visible() and send_btn.is_enabled()

            current_count = page.locator(RESPONSE_SELECTOR).count()
            if current_count > initial_count:
                current_text = page.locator(RESPONSE_SELECTOR).nth(current_count - 1).inner_text().strip()
                current_length = len(current_text)

                if current_length > 0 and current_length == last_length:
                    stable_cycles += 1
                else:
                    stable_cycles = 0

                last_length = current_length

            if (btn_ready and stable_cycles >= 2) or stable_cycles >= 5:
                break
        except Exception:
            pass
        time.sleep(1.5)

    last_val = get_last_response(page)

    if "something went wrong" in last_val.lower() or "try reloading" in last_val.lower():
        print("\n[WARNING] Gemini flagged the content or encountered an active network crash.")

    return last_val


def start_clean_gemini_chat(page):
    """Navigates to Gemini and starts a fresh chat session."""
    print("Navigating to Gemini...")
    try:
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        print(f"Navigation warning (continuing): {e}")
    time.sleep(3)

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
                btn.click()
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


def select_gemini_model(page, model_name):
    """Selects a specific Gemini model from the dropdown."""
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
            time.sleep(1.5)
            return True
        else:
            print(f"[WARNING] Model option '{model_name}' not found in dropdown menu.")
            return False
    except Exception as e:
        print(f"[ERROR] Exception while selecting model: {e}")
        return False
```

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from gemini_utils import find_input_box, find_send_button, wait_for_gemini_response, start_clean_gemini_chat, select_gemini_model, RESPONSE_SELECTOR; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Commit**

```bash
git add gemini_utils.py
git commit -m "feat: extract shared Gemini UI helpers into gemini_utils.py"
```

---

### Task 2: Create the Refinement Prompt (`refine_prompt.txt`)

**Files:**
- Create: `refine_prompt.txt`

**Interfaces:**
- Consumes: N/A (static text file)
- Produces: Read by `refine_script.py` as setup turn content

- [ ] **Step 1: Create `refine_prompt.txt`**

```text
### CORE DIRECTIVE: THE KHALEEJI WHITE DIALECT SCRIPT EDITOR ###
You are an elite Arabic script editor specializing in Khaleeji White Dialect YouTube narration. Your job: refine an already-translated Arabic script for natural fluency, dialect consistency, and audience engagement.

You are NOT translating. You are POLISHING Arabic text that is already in Arabic.

### 1. THE REFINEMENT RULES (STRICT ENFORCEMENT)

* DIALECT ENFORCEMENT: Saudi Khaleeji "White" dialect (اللهجة الخليجية البيضاء). Use "مو" (not "مش"), "كذا" (not "كده"), "يعني" freely. Avoid Egyptian, Levantine, or Gulf-internal variations.
* FLUENCY PASS: Fix literal translation artifacts. Arabic should read as if originally written in Arabic, not translated. Short sentences, natural rhythm. Kill any phrasing that sounds like English structure forced into Arabic words.
* RHYTHM MANDATE: Short, Short, Long, Short, rhetorical Question every 4-6 sentences. Vary sentence length for TTS prosody. The ear must never get bored.
* PRESERVE MEANING: Do NOT add, remove, or alter factual content. You are polishing, not rewriting. Every fact in the original must survive.
* TTS-FRIENDLY: Use Arabic commas (،) for breath pauses. Sparse tashkeel only on genuinely ambiguous words. No excessive diacritics. Example: write "مُو كذا" not "مُوَ كِذَا". Leave standard words bare.

### 2. THE STRUCTURAL BOOKENDS

* FIRST PARAGRAPH = HOOK: The opening must grab attention in the first 15 seconds. Start mid-action, with a provocative question, or a bold claim. No slow buildups. The listener must be hooked before the second sentence.
* LAST PARAGRAPH = OUTRO CTA: End with a compelling call-to-action — subscribe, comment their opinion, or tease the next video. Make it feel natural, not corporate. The CTA must feel like a friend asking, not a brand demanding.

### 3. OUTPUT FORMAT

Output ONLY the refined Arabic text. No headers, no commentary, no translation, no explanation, no bullet points, no stage directions. Pure narration only.

---
Before we begin, reply with 'UNDERSTOOD' to confirm you have absorbed these rules.
```

- [ ] **Step 2: Verify file exists and is readable**

Run: `python -c "with open('refine_prompt.txt', 'r', encoding='utf-8') as f: print(f.read()[:100])"`
Expected: First 100 characters of the prompt text

- [ ] **Step 3: Commit**

```bash
git add refine_prompt.txt
git commit -m "feat: add two-turn refinement prompt for Arabic script polishing"
```

---

### Task 3: Implement `refine_script.py`

**Files:**
- Create: `refine_script.py`
- Reference: `automate_all.py:406-520` (model selection + paragraph processing pattern)
- Reference: `prompt_phase3.txt` (3-part interaction pattern to adapt)

**Interfaces:**
- Consumes: `final_output.txt` (from `youtube_runs/<Title>/`), `refine_prompt.txt`, `gemini_utils.py` helpers, `utils.py:get_config_value()`, `utils.py:launch_browser_with_profile()`, `utils.py:rotate_profile_index()`
- Produces: `refined_script.txt`, `refined_script.docx`, `refine_checkpoint.json` (deleted on completion)

- [ ] **Step 1: Create `refine_script.py`**

```python
import os
import sys
import re
import time
import json
import glob
from docx import Document
from playwright.sync_api import sync_playwright
from utils import get_config_value, launch_browser_with_profile, kill_cdp_chrome, rotate_profile_index, send_telegram_notification
from gemini_utils import (
    RESPONSE_SELECTOR, find_input_box, find_send_button,
    wait_for_gemini_response, start_clean_gemini_chat, select_gemini_model
)

sys.stdout.reconfigure(encoding='utf-8')


def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
    if not folders:
        return None
    return max(folders, key=os.path.getmtime)


def read_refine_prompt():
    try:
        with open("refine_prompt.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print("Error: 'refine_prompt.txt' not found.")
        sys.exit(1)


def read_final_output(folder):
    path = os.path.join(folder, "final_output.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: 'final_output.txt' not found in {folder}")
        sys.exit(1)


def split_paragraphs(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) < 2:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs


def load_checkpoint(folder):
    path = os.path.join(folder, "refine_checkpoint.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("refined_paragraphs", [])
        except Exception:
            pass
    return []


def save_checkpoint(folder, refined_paragraphs):
    path = os.path.join(folder, "refine_checkpoint.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"refined_paragraphs": refined_paragraphs}, f, ensure_ascii=False, indent=2)


def delete_checkpoint(folder):
    path = os.path.join(folder, "refine_checkpoint.json")
    if os.path.exists(path):
        os.remove(path)


def save_refined_script(folder, refined_paragraphs):
    text_path = os.path.join(folder, "refined_script.txt")
    docx_path = os.path.join(folder, "refined_script.docx")
    full_text = "\n\n".join(refined_paragraphs)

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    doc = Document()
    doc.add_heading("Refined Script", level=1)
    for p in refined_paragraphs:
        doc.add_paragraph(p)
    doc.save(docx_path)

    print(f"Refined script saved: {text_path}")


def is_safety_blocked(text):
    if not text or len(text.strip()) < 15:
        return True
    lower_text = text.lower()
    refusal_keywords = [
        "cannot fulfill", "unable to assist", "safety guidelines",
        "against my policy", "something went wrong", "restricted content",
        "i am unable", "i apologize, but i cannot", "as an ai language model"
    ]
    for word in refusal_keywords:
        if word in lower_text:
            return True
    return False


def setup_refinement_session(page, model_name):
    """Turn 1: Send the refinement style guide and wait for acknowledgment."""
    print("[SETUP] Starting refinement session...")
    start_clean_gemini_chat(page)
    time.sleep(2)

    select_gemini_model(page, model_name)
    time.sleep(2)

    prompt_text = read_refine_prompt()

    print("[SETUP] Sending refinement style guide...")
    input_box = find_input_box(page)
    if not input_box:
        print("[FATAL] Could not find input box for setup turn.")
        return False

    input_box.click()
    time.sleep(0.5)
    input_box.fill(prompt_text)
    time.sleep(1)

    send_btn = find_send_button(page)
    if send_btn:
        send_btn.click()
    else:
        page.keyboard.press("Enter")

    print("[SETUP] Waiting for Gemini acknowledgment...")
    initial_count = page.locator(RESPONSE_SELECTOR).count()
    response = wait_for_gemini_response(page, initial_count, timeout_seconds=120)

    if response and ("understood" in response.lower() or "جاهز" in response.lower() or "مستعد" in response.lower()):
        print("[SETUP] Gemini acknowledged refinement rules.")
        return True
    else:
        print(f"[SETUP] Gemini response: {response[:200] if response else '(empty)'}")
        print("[SETUP] Proceeding anyway — Gemini may have acknowledged implicitly.")
        return True


def refine_paragraph(page, paragraph_text, index, total):
    """Turn 2: Send a single paragraph for refinement."""
    message = f"Refine paragraph {index} of {total}. Return ONLY the refined Arabic text, no commentary, no translation, no explanation.\n\n{paragraph_text}"

    input_box = find_input_box(page)
    if not input_box:
        print(f"[ERROR] Could not find input box for paragraph {index}.")
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

    initial_count = page.locator(RESPONSE_SELECTOR).count()
    response = wait_for_gemini_response(page, initial_count, timeout_seconds=300)

    if is_safety_blocked(response):
        print(f"[WARNING] Safety block detected for paragraph {index}. Retrying with fresh chat...")
        return None

    return response.strip() if response else None


def main():
    print("=" * 60)
    print(" refinement: Arabic Script Refinement via Gemini")
    print("=" * 60)

    folder = get_latest_run_folder()
    if not folder:
        print("No youtube_runs folder found.")
        sys.exit(1)

    video_title = os.path.basename(os.path.normpath(folder))
    print(f"Processing: {video_title}")

    final_output = read_final_output(folder)
    paragraphs = split_paragraphs(final_output)
    print(f"Found {len(paragraphs)} paragraphs to refine.")

    refined_paragraphs = load_checkpoint(folder)
    start_index = len(refined_paragraphs)
    print(f"Resuming from paragraph {start_index + 1}.")

    if start_index >= len(paragraphs):
        print("All paragraphs already refined.")
        delete_checkpoint(folder)
        return

    model_name = get_config_value("REFINE_MODEL", "Pro")
    max_retries = int(get_config_value("FAILOVER_RETRY_LIMIT", "4"))
    switch_accounts = get_config_value("SWITCH_ACCOUNTS_ENABLED", "true").lower() == "true"
    browser_type = get_config_value("BROWSER_TYPE", "chrome")
    profile_index = int(get_config_value("ACTIVE_PROFILE_INDEX", "1"))

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=5000)
        context = browser.contexts[0]
        page = context.new_page()

        retries = 0
        current_index = start_index

        while current_index < len(paragraphs) and retries < max_retries:
            if current_index == start_index:
                if not setup_refinement_session(page, model_name):
                    print("[FATAL] Setup failed. Retrying with new chat...")
                    retries += 1
                    continue

            paragraph = paragraphs[current_index]
            print(f"\n[REFINE] Paragraph {current_index + 1}/{len(paragraphs)}...")

            refined = refine_paragraph(page, paragraph, current_index + 1, len(paragraphs))

            if refined and not is_safety_blocked(refined):
                refined_paragraphs.append(refined)
                save_checkpoint(folder, refined_paragraphs)
                print(f"[OK] Paragraph {current_index + 1} refined ({len(refined)} chars).")
                current_index += 1
                retries = 0
            else:
                retries += 1
                print(f"[RETRY {retries}/{max_retries}] Paragraph {current_index + 1} failed. Starting fresh chat...")

                if switch_accounts and retries >= max_retries:
                    print("[FAILOVER] Rotating account...")
                    profile_index = rotate_profile_index()
                    kill_cdp_chrome()
                    time.sleep(3)
                    launch_browser_with_profile(browser_type, profile_index)
                    time.sleep(5)
                    browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=5000)
                    context = browser.contexts[0]
                    page = context.new_page()
                    retries = 0

                start_clean_gemini_chat(page)
                time.sleep(2)
                select_gemini_model(page, model_name)
                time.sleep(2)

        page.close()

    if current_index >= len(paragraphs):
        save_refined_script(folder, refined_paragraphs)
        delete_checkpoint(folder)
        print(f"\n{'=' * 60}")
        print(f" REFINEMENT COMPLETE: {video_title}")
        print(f"{'=' * 60}")
        send_telegram_notification(f"✅ Script refined: {video_title}")
    else:
        print(f"\n[PARTIAL] Refined {current_index}/{len(paragraphs)} paragraphs. Checkpoint saved.")
        send_telegram_notification(f"⚠️ Script refinement partial: {video_title} ({current_index}/{len(paragraphs)})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script syntax**

Run: `python -c "import py_compile; py_compile.compile('refine_script.py', doraise=True); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add refine_script.py
git commit -m "feat: add refine_script.py for Arabic script refinement via Gemini CDP"
```

---

### Task 4: Implement `generate_thumbnail.py`

**Files:**
- Create: `generate_thumbnail.py`
- Reference: `nano-banana-pro-prompting` skill (camera architecture, negative prompts, aspect ratios)

**Interfaces:**
- Consumes: `refined_script.txt` (or `final_output.txt` fallback) from `youtube_runs/<Title>/`, `gemini_utils.py` helpers, `utils.py` config functions
- Produces: `youtube_runs/<Title>/thumbnails/variant_1.png` through `variant_N.png`, `thumbnail_prompts.json`, `thumbnail_critique.json`

- [ ] **Step 1: Create `generate_thumbnail.py`**

```python
import os
import sys
import re
import time
import json
import base64
import glob
from playwright.sync_api import sync_playwright
from utils import get_config_value, launch_browser_with_profile, kill_cdp_chrome, rotate_profile_index, send_telegram_notification
from gemini_utils import (
    RESPONSE_SELECTOR, find_input_box, find_send_button,
    wait_for_gemini_response, start_clean_gemini_chat, select_gemini_model
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

Pick the TOP {top_n} winners. For each winner, suggest ONE specific improvement.

Return a JSON object with:
- "scores": array of {{"index": N, "click_appeal": N, "emotional_impact": N, "visual_clarity": N, "total": N}}
- "winners": array of winning indices
- "improvements": object mapping index to improvement suggestion

Return ONLY the JSON, no commentary."""


def get_latest_run_folder(runs_path="youtube_runs"):
    if not os.path.exists(runs_path):
        return None
    folders = glob.glob(os.path.join(runs_path, "*/"))
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
    """Generic send-message-wait-for-response helper."""
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

    initial_count = page.locator(RESPONSE_SELECTOR).count()
    return wait_for_gemini_response(page, initial_count, timeout_seconds=timeout)


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


def build_nano_banana_prompt(concept, index):
    """Build a Nano Banana Pro structured prompt from a thumbnail concept."""
    style_camera_map = {
        "cinematic": {
            "body": "Sony A7III",
            "lens": "85mm f/1.4",
            "lighting": "golden hour sunlight with warm rim light wrapping around the subject, cinematic color grading with amber tones",
            "mood": "epic, immersive, story-driven"
        },
        "dramatic": {
            "body": "Canon EOS R5",
            "lens": "50mm f/1.2",
            "lighting": "narrow beam spotlight focused on the subject's face, sharp dramatic edges, high falloff shadow, areas outside fall into deep darkness",
            "mood": "intense, confrontational, urgent"
        },
        "mysterious": {
            "body": "Hasselblad X1D-50c",
            "lens": "45mm f/3.5",
            "lighting": "low-key lighting with deep shadows, single soft light source from above, heavy vignette, muted cool tones",
            "mood": "enigmatic, haunting, curiosity-inducing"
        },
        "confrontational": {
            "body": "Sony A7III",
            "lens": "35mm f/2.8",
            "lighting": "harsh direct on-camera flash, bright blown-out highlights, hard shadows, high contrast, raw and unpolished",
            "mood": "provocative, bold, impossible to ignore"
        },
        "emotional": {
            "body": "Kodak Portra 400 film emulation",
            "lens": "50mm f/1.4",
            "lighting": "soft diffused natural light, warm golden tones, gentle catchlight in eyes, subtle film grain",
            "mood": "intimate, vulnerable, deeply human"
        }
    }

    style = concept.get("style", "cinematic")
    cam = style_camera_map.get(style, style_camera_map["cinematic"])

    return {
        "subject": concept.get("scene", "dramatic scene"),
        "subject_details": f"emotional expression: {concept.get('emotion', 'intense')}, high detail facial features, photorealistic skin texture, sharp focus",
        "camera_specifications": f"Shot on {cam['body']} with a {cam['lens']} lens at f/1.4, ISO 200, 1/200s shutter. {cam['lighting']}",
        "environment": "contextually appropriate to video topic, complementary background that directs attention to subject",
        "mood": cam['mood'],
        "text_overlay": {
            "text": concept.get("text_overlay", ""),
            "position": "bottom third or top left corner",
            "style": "bold white Arabic text with subtle drop shadow, or gold accent for emphasis"
        },
        "negative": {
            "content": ["Multiple characters", "blurry", "low resolution", "distorted text", "watermark"],
            "style": "No AI artifacts, no extra limbs, no text errors, no hyper-saturation, no soft focus filters"
        },
        "aspect_ratio": "16:9",
        "resolution": "8K, ultra-detailed, photorealistic"
    }


def generate_images_via_gemini(page, prompts, output_dir):
    """Send each prompt to Gemini and download generated images."""
    os.makedirs(output_dir, exist_ok=True)
    generated = []

    for i, prompt_obj in enumerate(prompts):
        prompt_text = json.dumps(prompt_obj, ensure_ascii=False, indent=2)
        print(f"\n[IMAGE] Generating variant {i + 1}/{len(prompts)}...")

        response = send_and_wait(page, prompt_text, timeout=300)

        if not response:
            print(f"[WARNING] No response for variant {i + 1}. Skipping.")
            continue

        # Try to find image elements in the response
        try:
            img_elements = page.locator(f"{RESPONSE_SELECTOR} img, model-response img").all()
            if img_elements:
                last_img = img_elements[-1]
                last_img.hover()
                time.sleep(2)

                # Look for download button
                download_selectors = [
                    "button[aria-label*='Download' i]",
                    "button[aria-label*='download' i]",
                    "a[aria-label*='Download' i]",
                    "button.mat-mdc-icon-button:has(svg)"
                ]

                for sel in download_selectors:
                    try:
                        dl_btn = page.locator(sel).last
                        if dl_btn.is_visible():
                            with page.expect_download(timeout=15000) as download_info:
                                dl_btn.click()
                            download = download_info.value
                            ext = os.path.splitext(download.suggested_filename)[1] or ".png"
                            filepath = os.path.join(output_dir, f"variant_{i + 1}{ext}")
                            download.save_as(filepath)
                            generated.append(filepath)
                            print(f"[OK] Saved variant {i + 1}: {filepath}")
                            break
                    except Exception:
                        continue
            else:
                # Fallback: try to extract from base64 in response
                b64_match = re.search(r'data:image/[^;]+;base64,([A-Za-z0-9+/=]+)', response)
                if b64_match:
                    img_data = base64.b64decode(b64_match.group(1))
                    filepath = os.path.join(output_dir, f"variant_{i + 1}.png")
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    generated.append(filepath)
                    print(f"[OK] Saved variant {i + 1} (base64): {filepath}")
                else:
                    print(f"[WARNING] No image found in response for variant {i + 1}.")
        except Exception as e:
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
    # Use first 3000 chars for concept extraction (avoid token limits)
    script_excerpt = script_text[:3000]

    model_name = get_config_value("THUMBNAIL_MODEL", get_config_value("REFINE_MODEL", "Pro"))
    max_retries = int(get_config_value("FAILOVER_RETRY_LIMIT", "4"))
    switch_accounts = get_config_value("SWITCH_ACCOUNTS_ENABLED", "true").lower() == "true"
    browser_type = get_config_value("BROWSER_TYPE", "chrome")
    profile_index = int(get_config_value("ACTIVE_PROFILE_INDEX", "1"))

    prompts_path = os.path.join(folder, "thumbnail_prompts.json")
    critique_path = os.path.join(folder, "thumbnail_critique.json")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222", timeout=5000)
        context = browser.contexts[0]
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

        # Phase 2: Build Nano Banana Pro prompts
        print("\n[PHASE 2] Building Nano Banana Pro prompts...")
        nano_prompts = [build_nano_banana_prompt(c, i) for i, c in enumerate(concepts)]

        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(nano_prompts, f, ensure_ascii=False, indent=2)
        print(f"[OK] Prompts saved to {prompts_path}")

        # Phase 3: Self-critique
        print("\n[PHASE 3] Running self-critique loop...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        topic = video_title.replace("_", " ").replace("-", " ")
        critique_msg = CRITIQUE_PROMPT_TEMPLATE.format(
            count=len(nano_prompts),
            topic=topic,
            prompts_json=json.dumps(nano_prompts, ensure_ascii=False, indent=2),
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
            if w_idx < len(nano_prompts):
                prompt = nano_prompts[w_idx].copy()
                if str(w_idx) in improvements:
                    prompt["refinement_note"] = improvements[str(w_idx)]
                winning_prompts.append(prompt)

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
```

- [ ] **Step 2: Verify script syntax**

Run: `python -c "import py_compile; py_compile.compile('generate_thumbnail.py', doraise=True); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add generate_thumbnail.py
git commit -m "feat: add generate_thumbnail.py with Nano Banana Pro prompts and self-critique loop"
```

---

### Task 5: Wire `refine_script.py` into `run_agency.py`

**Files:**
- Modify: `run_agency.py:58-72` (default state)
- Modify: `run_agency.py:136-143` (folder_steps)
- Modify: `run_agency.py:106-107` (valid_folders filter)

**Interfaces:**
- Consumes: `refine_script.py` (subprocess), `pipeline.json` state
- Produces: Updated pipeline state with `refine` key

- [ ] **Step 1: Add `refine` to default pipeline state**

In `run_agency.py`, modify `get_pipeline_state()` function at line 58-72:

Change the `default_state` dict from:
```python
default_state = {
    "voice": False, "audacity": False, "stitch": False,
    "transcribe": False, "spellcheck": False, "images": False,
    "fixtimes": False, "video": False
}
```

To:
```python
default_state = {
    "refine": False,
    "voice": False, "audacity": False, "stitch": False,
    "transcribe": False, "spellcheck": False, "images": False,
    "fixtimes": False, "video": False
}
```

- [ ] **Step 2: Add refine step to folder_steps**

In `run_agency.py`, modify the `folder_steps` list at line 136-143. Insert the refine step BEFORE the voice step:

Change from:
```python
folder_steps = [
    {"key": "voice", "script": "generate_voice.py", "desc": "Phase 2: AI Voice Synthesis"},
    {"key": "audacity", "script": "automate_audacity.py", "desc": "Phase 3: Studio Audio Polish"},
    ...
]
```

To:
```python
folder_steps = [
    {"key": "refine", "script": "refine_script.py", "desc": "Phase 1b: Arabic Script Refinement"},
    {"key": "voice", "script": "generate_voice.py", "desc": "Phase 2: AI Voice Synthesis"},
    {"key": "audacity", "script": "automate_audacity.py", "desc": "Phase 3: Studio Audio Polish"},
    {"key": "stitch", "script": "stitch_chapters.py", "desc": "Phase 4: Audio Stitching"},
    {"key": "transcribe", "script": "transcribe_audio.py", "desc": "Phase 5: Whisper Timestamping"},
    {"key": "spellcheck", "script": "correct_transcript_spelling.py", "desc": "Phase 6: Transcript Spelling"},
    {"key": "images", "script": img_script, "desc": f"Phase 7: Image Generation ({img_gen_type.upper()})"}
]
```

- [ ] **Step 3: Add backward-compatible skip for existing runs**

The existing skip logic at line 147-149 already handles this:
```python
if state.get(step["key"], False):
    print(f"⏭️  [SKIP] {step['desc']} already completed.")
    continue
```

Since `get_pipeline_state()` defaults `refine` to `False`, and existing `pipeline.json` files won't have a `refine` key, the `.get("refine", False)` returns `False` — meaning the refine step WILL run on existing runs. This is the desired behavior per spec (existing runs get refinement applied).

However, if you want existing runs to SKIP refinement (since they already have `final_output.txt`), add this check after state load:

In `run_agency.py`, after `state = get_pipeline_state(folder)` at line 124, add:
```python
# Backward compat: if refine key missing from existing pipeline.json, treat as skipped
if "refine" not in state:
    state["refine"] = True
```

- [ ] **Step 4: Verify syntax**

Run: `python -c "import py_compile; py_compile.compile('run_agency.py', doraise=True); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 5: Commit**

```bash
git add run_agency.py
git commit -m "feat: wire refine_script.py as step 1b in run_agency.py pipeline"
```

---

### Task 6: Add `THUMBNAIL_MODEL` to Config

**Files:**
- Modify: `gemini_model.txt`

**Interfaces:**
- Consumes: N/A
- Produces: `THUMBNAIL_MODEL` config key readable by `generate_thumbnail.py`

- [ ] **Step 1: Add THUMBNAIL_MODEL to gemini_model.txt**

Add the following line after the `REFINE_MODEL=Pro` line:

```
THUMBNAIL_MODEL=Pro
```

- [ ] **Step 2: Verify config is readable**

Run: `python -c "from utils import get_config_value; print('THUMBNAIL_MODEL:', get_config_value('THUMBNAIL_MODEL', 'Pro'))"`
Expected: `THUMBNAIL_MODEL: Pro`

- [ ] **Step 3: Commit**

```bash
git add gemini_model.txt
git commit -m "config: add THUMBNAIL_MODEL=Pro to gemini_model.txt"
```

---

## Summary

| Task | Deliverable | Dependencies |
|------|-------------|-------------|
| 1 | `gemini_utils.py` (5 shared helpers) | None |
| 2 | `refine_prompt.txt` (two-turn prompt) | None |
| 3 | `refine_script.py` (paragraph refinement) | Task 1, Task 2 |
| 4 | `generate_thumbnail.py` (thumbnail pipeline) | Task 1 |
| 5 | `run_agency.py` wiring | Task 3 |
| 6 | `gemini_model.txt` config | None |

Tasks 1, 2, and 6 are independent and can run in parallel. Tasks 3 and 4 depend on Task 1. Task 5 depends on Task 3.

## Validation Checklist

- [ ] `gemini_utils.py` imports without error
- [ ] `refine_script.py` syntax check passes
- [ ] `generate_thumbnail.py` syntax check passes
- [ ] `run_agency.py` syntax check passes
- [ ] `THUMBNAIL_MODEL` config readable
- [ ] `refine_prompt.txt` contains "UNDERSTOOD" acknowledgment trigger
- [ ] `refine_checkpoint.json` created during run, deleted on completion
- [ ] `refined_script.txt` + `.docx` output on completion
- [ ] `thumbnails/` directory created with variant images
- [ ] `thumbnail_prompts.json` saved with Nano Banana Pro prompts
- [ ] `thumbnail_critique.json` saved with scores and winners
- [ ] Pipeline backward-compatible: existing runs without `refine` key auto-skip
