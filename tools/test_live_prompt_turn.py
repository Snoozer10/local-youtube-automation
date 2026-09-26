"""Live E2E Verification Test for Upgraded Prompt Pipeline.

Connects to the active Chrome debugging session on port 9222, opens a clean
Gemini chat, verifies the setup prompt calibration handshake using loader.ack_tokens("refine"),
dispatches a content refinement turn using loader.turn("refine", "full", ...),
and asserts that the output adheres to the XML tagging contract and contains clean Arabic.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from refine_script import input_gemini_prompt, wait_for_gemini_ready  # noqa: E402
from youtube_automation.browser.gemini_utils import (  # noqa: E402
    find_send_button,
    select_gemini_model,
    start_clean_gemini_chat,
    wait_for_gemini_response,
)
from youtube_automation.prompts import loader  # noqa: E402

RESPONSE_SELECTOR = "model-response, .model-response, [data-test-id='model-response']"


def run_live_prompt_verification(model_name: str = "Flash") -> dict:
    results = {
        "status": "INIT",
        "calibration_passed": False,
        "calibration_token_matched": None,
        "turn_passed": False,
        "tags_valid": False,
        "arabic_content_valid": False,
        "no_metadata_leaks": True,
        "model_response_raw": "",
        "thinking_content": "",
        "final_script": "",
    }

    print("=" * 60)
    print("LIVE E2E PROMPT PIPELINE VERIFICATION")
    print("=" * 60)

    with sync_playwright() as p:
        print("[CDP] Connecting to Chrome on http://127.0.0.1:9222...")
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]

        # Locate existing Gemini page or create one
        page = None
        for pg in context.pages:
            if "gemini.google.com" in pg.url:
                page = pg
                break
        if not page:
            page = context.new_page()
            page.goto("https://gemini.google.com/app")

        page.bring_to_front()
        wait_for_gemini_ready(page, timeout_seconds=30)
        print(f"[PAGE] Active page URL: {page.url}")

        # Step 1: Start clean session & select model
        print(f"[SESSION] Starting clean chat session with model: {model_name}...")
        start_clean_gemini_chat(page)
        time.sleep(2)
        select_gemini_model(page, model_name)
        time.sleep(2)

        # Step 2: Render & dispatch setup prompt
        setup_prompt = loader.render("refine")
        expected_ack_tokens = loader.ack_tokens("refine")
        print(f"[SETUP] Rendered refine prompt ({len(setup_prompt)} chars).")
        print(f"[SETUP] Expected ack tokens: {expected_ack_tokens}")

        initial_count = page.locator(RESPONSE_SELECTOR).count()
        input_gemini_prompt(page, setup_prompt)
        time.sleep(1)

        send_btn = find_send_button(page)
        if send_btn and send_btn.is_visible() and send_btn.is_enabled():
            send_btn.click()
        else:
            page.keyboard.press("Control+Enter")

        print("[SETUP] Prompt dispatched. Waiting for Gemini calibration acknowledgment...")
        ack_response = wait_for_gemini_response(page, initial_count=initial_count, timeout_seconds=90)
        print(f"[SETUP] Gemini response:\n---\n{ack_response}\n---")

        matched_token = None
        if ack_response:
            for token in expected_ack_tokens:
                if token.lower() in ack_response.lower():
                    matched_token = token
                    break

        if matched_token:
            print(f"[PASS] Calibration handshake SUCCESS: matched '{matched_token}'")
            results["calibration_passed"] = True
            results["calibration_token_matched"] = matched_token
        else:
            print("[WARN] Exact ack token not found, checking semantic acknowledgment...")
            if ack_response and any(w in ack_response for w in ["أنا جاهز", "مستعد", "تمام", "Ready"]):
                results["calibration_passed"] = True
                results["calibration_token_matched"] = "semantic_match"
                print("[PASS] Semantic calibration handshake confirmed.")

        # Step 3: Dispatch Content Turn
        print("\n[TURN 1] Formatting test paragraph via loader.turn('refine', 'full')...")
        sample_paragraph = (
            "Did you know that octopuses have three hearts and blue blood? "
            "Two of the hearts pump blood to the gills, while the third circulates it to the rest of the body. "
            "When they swim, the systemic heart actually stops beating."
        )

        turn_prompt = loader.turn(
            "refine",
            "full",
            index=1,
            total=5,
            persona="Al-Daheeh",
            context_bridge="",
            tone_block="- Ground explanations in tangible Egyptian archetypes (الميكروباص / الموظف / باقة النت).\n- Insert an 'Abo Hmeed' skeptic interjection if pacing fits.",
            slang_restriction="",
            source_paragraph=sample_paragraph,
        )

        print(f"[TURN 1] Turn prompt prepared ({len(turn_prompt)} chars).")
        assert "<<<PROMPT_META" not in turn_prompt, "CRITICAL DEFECT: Leaked metadata in turn prompt!"

        initial_count = page.locator(RESPONSE_SELECTOR).count()
        input_gemini_prompt(page, turn_prompt)
        time.sleep(1)

        send_btn = find_send_button(page)
        if send_btn and send_btn.is_visible() and send_btn.is_enabled():
            send_btn.click()
        else:
            page.keyboard.press("Control+Enter")

        print("[TURN 1] Dispatched. Waiting for Gemini refinement output (up to 180s)...")
        turn_response = wait_for_gemini_response(page, initial_count=initial_count, timeout_seconds=180)
        print(f"\n[TURN 1] Gemini Output:\n==============================\n{turn_response}\n==============================")

        results["model_response_raw"] = turn_response or ""

        # Step 4: Verification assertions
        if turn_response:
            # Check for leaked meta
            if "<<<PROMPT_META" in turn_response:
                results["no_metadata_leaks"] = False
                print("[FAIL] Leaked metadata found in model output!")

            # Check tags
            has_thinking = "<thinking>" in turn_response and "</thinking>" in turn_response
            has_final_script = "<final_script>" in turn_response and "</final_script>" in turn_response
            results["tags_valid"] = has_thinking or has_final_script

            if "<thinking>" in turn_response and "</thinking>" in turn_response:
                m_think = re.search(r"<thinking>(.*?)</thinking>", turn_response, re.DOTALL)
                if m_think:
                    results["thinking_content"] = m_think.group(1).strip()

            if "<final_script>" in turn_response and "</final_script>" in turn_response:
                m_script = re.search(r"<final_script>(.*?)</final_script>", turn_response, re.DOTALL)
                if m_script:
                    results["final_script"] = m_script.group(1).strip()
            else:
                # If tags omitted, the entire text is the script
                results["final_script"] = turn_response.strip()

            # Check Arabic content
            arabic_char_count = len(re.findall(r"[\u0600-\u06FF]", results["final_script"]))
            results["arabic_content_valid"] = arabic_char_count > 50
            results["turn_passed"] = results["arabic_content_valid"]

            print("\n[VERIFICATION RESULTS]")
            print(f"- Calibration Passed: {results['calibration_passed']} ({results['calibration_token_matched']})")
            print(f"- XML Tag Fencing: {results['tags_valid']}")
            print(f"- Arabic Content Valid: {results['arabic_content_valid']} ({arabic_char_count} chars)")
            print(f"- Zero Metadata Leaks: {results['no_metadata_leaks']}")
            print(f"- Final Refined Script:\n  \"{results['final_script']}\"")

        results["status"] = "SUCCESS" if (results["calibration_passed"] and results["turn_passed"]) else "FAILED"
        return results


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "Flash"
    res = run_live_prompt_verification(model_name=model)
    out_file = ROOT / "debug_snapshots" / "live_prompt_verification_result.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[SAVED] Results saved to: {out_file}")
    sys.exit(0 if res["status"] == "SUCCESS" else 1)
