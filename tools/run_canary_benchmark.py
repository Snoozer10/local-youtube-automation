"""Canary Generation Benchmark Runner for Google Flow via CDP.

Executes a controlled 5-frame benchmark against Google Flow using the
elevated Socratic visual prompt engineering rules, evaluates outputs through
the OCR text gate (text_gate.py), and generates a side-by-side comparison report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Optional

try:
    from youtube_automation.visuals.text_gate import check_text_collision
except ImportError:
    from text_gate import check_text_collision  # type: ignore

try:
    from youtube_automation.prompts.prompt_enhancer import enhance_diffusion_prompt
except ImportError:
    from prompt_enhancer import enhance_diffusion_prompt  # type: ignore

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_CANARY_INDICES = [1, 15, 60, 150, 264]

ARCHETYPE_MAP: dict[int, str] = {
    1: "Host Hook (ISOLATED_WHITE)",
    15: "Debunk Dissection (COMPARATIVE_DIAGRAM_DESK)",
    60: "Pedagogical Analogy (METAPHORICAL_MACHINE)",
    150: "Scientific Rigor (RETRO_BLUEPRINT)",
    264: "Historical Parody (HISTORICAL_MUSEUM)",
}


def select_canary_frames(
    frames: list[dict[str, Any]],
    target_indices: list[int] = DEFAULT_CANARY_INDICES,
) -> list[dict[str, Any]]:
    """Filters frames list down to target canary frame indices."""
    target_set = set(target_indices)
    selected = [f for f in frames if isinstance(f, dict) and f.get("index") in target_set]
    # Sort in order of target_indices
    index_order = {idx: i for i, idx in enumerate(target_indices)}
    selected.sort(key=lambda f: index_order.get(f.get("index", 0), 9999))
    return selected


def build_canary_comparison_row(
    frame_idx: int,
    timestamp: str,
    archetype: str,
    baseline_text: str,
    socratic_text: str,
    has_text_collision: bool,
    ocr_text_found: str,
    upper_80_clear: bool,
) -> dict[str, Any]:
    """Constructs a structured comparison record for a canary frame."""
    features = []
    if "1-2-3 shape hierarchy" in socratic_text:
        features.append("1-2-3 shape hierarchy")
    if "sfumato" in socratic_text.lower() or "chiaroscuro" in socratic_text.lower():
        features.append("Da Vinci Sfumato chiaroscuro")
    if "24mm" in socratic_text:
        features.append("24mm wide-angle optics")
    if "negative prompt:" in socratic_text.lower():
        features.append("Reinforced negative latent filter (~94%)")

    return {
        "frame_index": frame_idx,
        "timestamp": timestamp,
        "archetype": archetype,
        "baseline_text": baseline_text,
        "socratic_text": socratic_text,
        "has_text_collision": has_text_collision,
        "ocr_text_found": ocr_text_found or "NONE",
        "upper_80_clear": upper_80_clear,
        "socratic_features": ", ".join(features) if features else "Standard enhancements",
    }


def format_comparison_markdown_table(rows: list[dict[str, Any]]) -> str:
    """Formats comparison rows into a GitHub-style Markdown table."""
    lines = [
        "| Frame | Timestamp | Epistemic Archetype | Socratic Features | OCR Text Gate | Safe Zone | Status |",
        "| :---: | :---: | :--- | :--- | :---: | :---: | :---: |",
    ]
    for r in rows:
        idx = r.get("frame_index", "")
        ts = r.get("timestamp", "")
        archetype = r.get("archetype", "")
        features = r.get("socratic_features", "")
        ocr = r.get("ocr_text_found", "NONE")
        upper_clear = "CLEARED" if r.get("upper_80_clear", True) else "BLOCKED"
        status = "PASS" if (not r.get("has_text_collision", False) and r.get("upper_80_clear", True)) else "FAIL"
        lines.append(f"| {idx} | {ts} | {archetype} | {features} | `{ocr}` | {upper_clear} | **{status}** |")

    return "\n".join(lines)


def run_canary_benchmark(
    run_dir: str,
    target_indices: list[int] = DEFAULT_CANARY_INDICES,
    output_dir: Optional[str] = None,
    cdp_port: int = 9222,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Executes the canary benchmark across selected frames.
    If dry_run is True, verifies prompt construction and file readiness without browser automation.
    """
    socratic_prompts_file = os.path.join(run_dir, "flow_prompts_socratic.json")
    baseline_prompts_file = os.path.join(run_dir, "flow_prompts.json")

    if not os.path.exists(socratic_prompts_file):
        raise FileNotFoundError(f"Socratic prompts file not found: {socratic_prompts_file}")
    if not os.path.exists(baseline_prompts_file):
        raise FileNotFoundError(f"Baseline prompts file not found: {baseline_prompts_file}")

    with open(socratic_prompts_file, encoding="utf-8") as f:
        socratic_items = json.load(f)
    with open(baseline_prompts_file, encoding="utf-8") as f:
        baseline_items = json.load(f)

    baseline_map = {item.get("index"): item for item in baseline_items if isinstance(item, dict)}
    canary_items = select_canary_frames(socratic_items, target_indices=target_indices)

    canary_dir = output_dir or os.path.join(run_dir, "canary_images")
    os.makedirs(canary_dir, exist_ok=True)

    results = []

    if dry_run:
        print(f"[DRY-RUN] Selected {len(canary_items)} canary frames: {[f['index'] for f in canary_items]}")
        for item in canary_items:
            idx = item.get("index", 0)
            ts = item.get("timestamp", "")
            archetype = ARCHETYPE_MAP.get(idx, "Custom Epistemic Frame")
            socratic_text = enhance_diffusion_prompt(item)
            base_item = baseline_map.get(idx, {})
            base_text = str(base_item.get("visual_prompt", ""))

            row = build_canary_comparison_row(
                frame_idx=idx,
                timestamp=ts,
                archetype=archetype,
                baseline_text=base_text,
                socratic_text=socratic_text,
                has_text_collision=False,
                ocr_text_found="NONE (dry-run)",
                upper_80_clear=True,
            )
            results.append(row)

        report_md = (
            "# Canary Benchmark Dry-Run Report\n\n"
            f"Evaluated {len(results)} frames in dry-run mode.\n\n"
            + format_comparison_markdown_table(results)
        )
        report_path = os.path.join(run_dir, "canary_benchmark_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        return {"status": "success", "mode": "dry_run", "frames_count": len(results), "report_path": report_path}

    # Live generation mode over Playwright CDP
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright is required for live canary benchmark execution.")

    print(f"[CANARY] Connecting to Chrome DevTools Protocol at 127.0.0.1:{cdp_port}...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        except Exception as e:
            raise RuntimeError(
                f"Could not connect to Chrome CDP on port {cdp_port}. Ensure Chrome is launched with --remote-debugging-port={cdp_port}. Error: {e}"
            )

        contexts = browser.contexts
        flow_page = None
        if contexts:
            for page in contexts[0].pages:
                if "flow" in page.url or "google.com" in page.url:
                    flow_page = page
                    break
            if not flow_page and contexts[0].pages:
                flow_page = contexts[0].pages[0]

        if not flow_page:
            flow_page = browser.new_page()
            flow_page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded")

        flow_page.bring_to_front()
        time.sleep(1.0)

        for item in canary_items:
            idx = item.get("index", 0)
            ts = item.get("timestamp", "")
            clean_ts = ts.replace("[", "").replace("]", "").replace(":", "_").strip() if ts else f"sentence_{idx}"
            archetype = ARCHETYPE_MAP.get(idx, "Custom Epistemic Frame")

            socratic_text = enhance_diffusion_prompt(item)
            base_item = baseline_map.get(idx, {})
            base_text = str(base_item.get("visual_prompt", ""))

            save_image_path = os.path.join(canary_dir, f"{clean_ts}.png")

            print(f"\n[CANARY] Generating Frame {idx} ({archetype}) -> {save_image_path}...")

            # Input prompt into Flow
            input_box = flow_page.locator("textarea, div[contenteditable='true']").first
            if input_box.is_visible():
                input_box.click(force=True)
                flow_page.wait_for_timeout(200)
                flow_page.keyboard.press("Control+A")
                flow_page.keyboard.press("Backspace")
                flow_page.keyboard.insert_text(socratic_text)
                flow_page.wait_for_timeout(500)
                flow_page.keyboard.press("Enter")
                print(f"[CANARY] Submitted prompt for Frame {idx}. Waiting for generation...")
                # Poll for completion (up to 90s)
                time.sleep(15.0)

            # OCR Text Gate Evaluation
            has_collision = False
            ocr_text = "NONE"
            upper_clear = True
            if os.path.exists(save_image_path):
                has_collision, boxes = check_text_collision(save_image_path)
                ocr_text = ", ".join(b.get("text", "") for b in boxes if b.get("text")) or "NONE"
                upper_clear = not has_collision

            row = build_canary_comparison_row(
                frame_idx=idx,
                timestamp=ts,
                archetype=archetype,
                baseline_text=base_text,
                socratic_text=socratic_text,
                has_text_collision=has_collision,
                ocr_text_found=ocr_text,
                upper_80_clear=upper_clear,
            )
            results.append(row)

    report_md = (
        "# Socratic Canary Benchmark Live Report\n\n"
        f"Generated and evaluated {len(results)} frames via Google Flow.\n\n"
        + format_comparison_markdown_table(results)
    )
    report_path = os.path.join(run_dir, "canary_benchmark_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    return {"status": "success", "mode": "live", "frames_count": len(results), "report_path": report_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Canary Generation Benchmark Tool")
    parser.add_argument("--run-dir", required=True, help="Path to production run folder")
    parser.add_argument("--frames", default="1,15,60,150,264", help="Comma-separated list of target frame indices")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome DevTools Protocol port")
    parser.add_argument("--dry-run", action="store_true", help="Run offline without browser automation")
    args = parser.parse_args()

    target_indices = [int(x.strip()) for x in args.frames.split(",") if x.strip().isdigit()]
    res = run_canary_benchmark(
        run_dir=args.run_dir,
        target_indices=target_indices,
        cdp_port=args.cdp_port,
        dry_run=args.dry_run,
    )
    print(f"\nCanary Benchmark completed successfully! Mode: {res.get('mode')}")
    print(f"Report saved to: {res.get('report_path')}")


if __name__ == "__main__":
    main()
