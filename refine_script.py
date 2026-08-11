import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from docx import Document
from gemini_utils import (
    RESPONSE_SELECTOR,
    find_input_box,
    find_send_button,
    select_gemini_model,
    start_clean_gemini_chat,
    wait_for_gemini_response,
)
from playwright.sync_api import sync_playwright
from utils import (
    get_config_value,
    kill_cdp_chrome,
    launch_browser_with_profile,
    rotate_profile_index,
    send_telegram_notification,
)

sys.stdout.reconfigure(encoding="utf-8")


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
        json.dump(
            {"refined_paragraphs": refined_paragraphs},
            f,
            ensure_ascii=False,
            indent=2,
        )


def delete_checkpoint(folder):
    path = os.path.join(folder, "refine_checkpoint.json")
    if os.path.exists(path):
        os.remove(path)

def clean_refined_paragraph(text):
    """Clean Gemini response to ensure zero metadata, strip thinking tags, and single-paragraph formatting."""
    if not text:
        return ""

    # 1. CRUCIAL FIX: Remove the <thinking>...</thinking> block and all its contents
    # flags=re.DOTALL allows the regex to match across multiple lines
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 2. TTS SAFETY: Remove markdown bold/italics (TTS engines hate reading asterisks)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)

    lines = text.splitlines()
    filtered_lines = []
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        # 3. Strips headers (🎬), metadata (مستوى الحماس), and (جاهز للمقطع...) transition prompts
        if (
            line_str.startswith("🎬")
            or line_str.startswith("مستوى الحماس")
            or line_str.startswith("الهدف النفسي")
            or (line_str.startswith("(") and line_str.endswith(")"))
        ):
            continue
        filtered_lines.append(line_str)

    # 4. Flattens multi-line output into a single continuous paragraph
    cleaned = " ".join(filtered_lines)

    # 5. Removes English words in parentheses e.g. "(The Hook)", "(John Wheeler)"
    cleaned = re.sub(r"\([A-Za-z0-9\s\-_,\.\'&]+\)", "", cleaned)

    # 6. Cleans up any double spaces left behind
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned

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
        "cannot fulfill",
        "unable to assist",
        "safety guidelines",
        "against my policy",
        "something went wrong",
        "restricted content",
        "i am unable",
        "i apologize, but i cannot",
        "as an ai language model",
    ]
    for word in refusal_keywords:
        if word in lower_text:
            return True
    return False


def ensure_chrome_debug_session(browser_type, profile_index):
    """Verify or launch Chrome debugging session using the specified profile index from config."""
    url = "http://127.0.0.1:9222/json/version"

    # Check if port 9222 is open
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                print(f"Chrome debugging session is already active on port 9222.")
                return True
    except Exception:
        pass

    print(
        f"Launching Chrome debugging session (Browser: {browser_type}, Profile Index: {profile_index})..."
    )
    return launch_browser_with_profile(browser_type, profile_index)


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
    response = wait_for_gemini_response(
        page, initial_count, timeout_seconds=120
    )

    if response and (
        "understood" in response.lower()
        or "جاهز" in response.lower()
        or "مستعد" in response.lower()
    ):
        print("[SETUP] Gemini acknowledged refinement rules.")
        return True
    else:
        print(
            f"[SETUP] Gemini response: {response[:200] if response else '(empty)'}"
        )
        print(
            "[SETUP] Proceeding anyway — Gemini may have acknowledged implicitly."
        )
        return True


def refine_paragraph(page, paragraph_text, index, total):
    """Turn 2: Send a single paragraph for refinement."""
    message = (
        f"Refine paragraph {index} of {total}.\n"
        "SYSTEM OVERRIDE REMINDER:\n"
        '1. Maintain "Cairo Hype-Man" persona.\n'
        "2. MAX 2 slang words per sentence.\n"
        "3. SFW metaphors ONLY (Simping/Aura/Dominance).\n"
        "4. Check your previous <slang_ledger> and do not repeat words.\n\n"
        f"REFINE THIS PARAGRAPH:\n{paragraph_text}"
    )

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
    response = wait_for_gemini_response(
        page, initial_count, timeout_seconds=300
    )

    if is_safety_blocked(response):
        print(
            f"[WARNING] Safety block detected for paragraph {index}. Retrying with fresh chat..."
        )
        return None

    if response:
        # Apply strict cleaning & paragraph flattening
        return clean_refined_paragraph(response)
    return None


def main():
    print("=" * 60)
    print(" refinement: Arabic Script Refinement via Gemini")
    print("=" * 60)

    # 1. Read config variables FIRST
    model_name = get_config_value("REFINE_MODEL", "Pro")
    max_retries = int(get_config_value("FAILOVER_RETRY_LIMIT", "4"))
    switch_accounts = (
        get_config_value("SWITCH_ACCOUNTS_ENABLED", "true").lower() == "true"
    )
    browser_type = get_config_value("BROWSER_TYPE", "chrome")
    profile_index = int(get_config_value("ACTIVE_PROFILE_INDEX", "1"))

    print(
        f"[CONFIG] Active Profile Index: {profile_index} | Browser: {browser_type} | Model: {model_name}"
    )

    # 2. Automatically verify or launch Chrome debug session using the configured profile index
    if not ensure_chrome_debug_session(browser_type, profile_index):
        print("Could not verify or start Chrome debugging session. Exiting.")
        return

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

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            "http://127.0.0.1:9222", timeout=5000
        )
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
            print(
                f"\n[REFINE] Paragraph {current_index + 1}/{len(paragraphs)}..."
            )

            refined = refine_paragraph(
                page, paragraph, current_index + 1, len(paragraphs)
            )

            if refined and not is_safety_blocked(refined):
                refined_paragraphs.append(refined)
                save_checkpoint(folder, refined_paragraphs)
                print(
                    f"[OK] Paragraph {current_index + 1} refined ({len(refined)} chars)."
                )
                current_index += 1
                retries = 0
            else:
                retries += 1
                print(
                    f"[RETRY {retries}/{max_retries}] Paragraph {current_index + 1} failed. Starting fresh chat..."
                )

                if switch_accounts and retries >= max_retries:
                    print("[FAILOVER] Rotating account...")
                    profile_index = rotate_profile_index()
                    kill_cdp_chrome()
                    time.sleep(3)
                    launch_browser_with_profile(browser_type, profile_index)
                    time.sleep(5)
                    browser = p.chromium.connect_over_cdp(
                        "http://127.0.0.1:9222", timeout=5000
                    )
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
        print(
            f"\n[PARTIAL] Refined {current_index}/{len(paragraphs)} paragraphs. Checkpoint saved."
        )
        send_telegram_notification(
            f"⚠️ Script refinement partial: {video_title} ({current_index}/{len(paragraphs)})"
        )


if __name__ == "__main__":
    main()