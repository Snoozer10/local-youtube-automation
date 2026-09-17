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
from typing import Any

try:
    from youtube_automation.visuals.text_gate import check_text_collision
except ImportError:
    from text_gate import check_text_collision  # type: ignore

try:
    from youtube_automation.visuals.flow_generator import (
        RollingSha256Ledger,
        attach_previous_images_to_prompt,
        build_dual_mode_prompt,
        card_spawn_handshake,
        check_flow_quota_or_errors,
        clear_attached_prompt_chips,
        dismiss_blocking_flow_modals,
        inject_prompt_safely,
        summon_character_chip,
        wait_for_flow_input_box,
    )
    from youtube_automation.visuals.image_extractor import (
        extract_high_res_image,
        validate_image_file,
    )
except ImportError:
    try:
        from image_extractor import extract_high_res_image, validate_image_file  # type: ignore

        from flow_image_generator import (  # type: ignore
            RollingSha256Ledger,
            attach_previous_images_to_prompt,
            build_dual_mode_prompt,
            card_spawn_handshake,
            check_flow_quota_or_errors,
            clear_attached_prompt_chips,
            dismiss_blocking_flow_modals,
            inject_prompt_safely,
            summon_character_chip,
            wait_for_flow_input_box,
        )
    except Exception:
        extract_high_res_image = None
        validate_image_file = None
        wait_for_flow_input_box = None
        inject_prompt_safely = None
        dismiss_blocking_flow_modals = None
        clear_attached_prompt_chips = None
        attach_previous_images_to_prompt = None
        summon_character_chip = None
        RollingSha256Ledger = None
        card_spawn_handshake = None
        check_flow_quota_or_errors = None
        build_dual_mode_prompt = None

try:
    from youtube_automation.prompts.prompt_enhancer import enhance_diffusion_prompt
except ImportError:
    from prompt_enhancer import enhance_diffusion_prompt  # type: ignore

try:
    from tools.viewer_generator import generate_comparison_viewer_html
except ImportError:
    try:
        from viewer_generator import generate_comparison_viewer_html  # type: ignore
    except Exception:
        generate_comparison_viewer_html = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

DEFAULT_CANARY_INDICES = [1, 15, 60, 150, 264]

ARCHETYPE_MAP: dict[int, str] = {
    1: "Host Hook (ISOLATED_WHITE)",
    15: "Debunk Dissection (COMPARATIVE_DIAGRAM_DESK)",
    60: "Pedagogical Analogy (METAPHORICAL_MACHINE)",
    150: "Scientific Rigor (RETRO_BLUEPRINT)",
    264: "Historical Parody (HISTORICAL_MUSEUM)",
}


def parse_frame_spec(spec_str: str, total_count: int = 293) -> list[int]:
    """Parses a flexible frame specification string into a list of sorted, unique integer indices.

    Supports:
      - 'all' -> [1, 2, ..., total_count]
      - '1-50' -> [1, 2, ..., 50]
      - '1,15,60,150,264' -> [1, 15, 60, 150, 264]
      - '1-10, 15, 20-25' -> [1..10, 15, 20..25]
    """
    raw = (spec_str or "").strip().lower()
    if not raw or raw == "all":
        return list(range(1, total_count + 1))

    indices: set[int] = set()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            bounds = part.split("-", 1)
            try:
                start = max(1, int(bounds[0].strip()))
                end = min(total_count, int(bounds[1].strip()))
                if start <= end:
                    indices.update(range(start, end + 1))
            except ValueError:
                pass
        else:
            try:
                val = int(part)
                if 1 <= val <= total_count:
                    indices.add(val)
            except ValueError:
                pass

    return sorted(indices)


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


def resolve_target_character(item: dict[str, Any]) -> str | None:
    """Resolves character preset name if the frame calls for character presence."""
    vp = item.get("visual_prompt", {})
    if not isinstance(vp, dict):
        vp = {}

    text_corpus = " ".join([
        str(item.get("subject", "")),
        str(item.get("continuity_id", "")),
        str(vp.get("subject", "")),
        str(vp.get("subject_details", "")),
        str(vp.get("action", "")),
        str(vp.get("continuity_id", "")),
    ])

    if "CHARACTER_HOST_MAIN" in text_corpus or "SUBJ_HOST" in text_corpus or "al-daheeh host" in text_corpus.lower():
        return "CHARACTER_HOST_MAIN"
    if "CHARACTER_CLERK_BUREAUCRAT" in text_corpus or "SUBJ_CLERK" in text_corpus:
        return "CHARACTER_CLERK_BUREAUCRAT"
    if "CHARACTER_SKEPTIC_ABO_HMEED" in text_corpus or "SUBJ_SKEPTIC" in text_corpus:
        return "CHARACTER_SKEPTIC_ABO_HMEED"

    return None


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
    if "orthographic" in socratic_text.lower():
        features.append("Orthographic 2D projection")
    elif "24mm" in socratic_text:
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


def is_fatal_flow_quota_error(err_msg: Any) -> bool:
    """Checks if an error string or exception indicates fatal account-level quota saturation."""
    if not err_msg:
        return False
    fatal_patterns = [
        "reached your usage limit",
        "you have not been charged",
        "الحدّ الأقصى للاستخدام",
        "لقد بلغت الحدّ الأقصى",
        "quota exceeded",
        "rate limit exceeded",
    ]
    low = str(err_msg).lower()
    return any(p in low for p in fatal_patterns)


def dismiss_blocking_agent_and_modals(page: Any) -> bool:
    """Detects and dismisses standard modals (cookies, dialogs) and Google Flow Agent UI.

    Ensures the UI is in pure Image generation mode (Agent panel closed, Agent pill toggled OFF).
    """
    dismissed = False
    if dismiss_blocking_flow_modals:
        try:
            dismissed = dismiss_blocking_flow_modals(page) or dismissed
        except Exception:
            pass

    # 1. Dismiss any modal with 'OK, got it' or 'Got it' directly
    try:
        ok_btn = page.locator("button:has-text('OK, got it'), button:has-text('Got it')").first
        if ok_btn.is_visible():
            ok_btn.click(force=True)
            dismissed = True
            page.wait_for_timeout(300)
    except Exception:
        pass

    # 2. Reject any pending conversational agent confirmation
    try:
        reject_btn = page.locator("button:has-text('Reject')").first
        if reject_btn.is_visible():
            reject_btn.click(force=True)
            dismissed = True
            page.wait_for_timeout(300)
    except Exception:
        pass

    # 3. Close agent side-panel if open
    try:
        close_btn = page.locator("button:has-text('close'), [aria-label*='Close' i]").first
        if close_btn.is_visible():
            close_btn.click(force=True)
            dismissed = True
            page.wait_for_timeout(300)
    except Exception:
        pass

    # 4. Toggle Agent pill to OFF if active (white background or aria-pressed="true")
    try:
        agent_btn = page.locator("button:has-text('Agent')").first
        if agent_btn.is_visible():
            bg = agent_btn.evaluate("el => window.getComputedStyle(el).backgroundColor")
            is_active = (
                "255, 255, 255" in bg
                or "rgb(255, 255, 255)" in bg
                or agent_btn.get_attribute("aria-pressed") == "true"
                or agent_btn.get_attribute("aria-checked") == "true"
            )
            if is_active:
                agent_btn.click(force=True)
                dismissed = True
                page.wait_for_timeout(400)
    except Exception:
        pass

    return dismissed


def run_canary_benchmark(
    run_dir: str,
    target_indices: list[int] = DEFAULT_CANARY_INDICES,
    output_dir: str | None = None,
    cdp_port: int = 9222,
    dry_run: bool = False,
    force_overwrite: bool = False,
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
    except ImportError as err:
        raise RuntimeError("Playwright is required for live canary benchmark execution.") from err

    try:
        from youtube_automation.core.utils import launch_browser_with_profile
    except ImportError:
        try:
            from utils import launch_browser_with_profile  # type: ignore
        except ImportError:
            launch_browser_with_profile = None

    print(f"[CANARY] Connecting to Chrome DevTools Protocol at 127.0.0.1:{cdp_port}...")
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
        except Exception:
            if launch_browser_with_profile is not None:
                print(f"[CANARY] Port {cdp_port} not reachable. Auto-launching Chrome with Profile 1...")
                if launch_browser_with_profile("chrome", 1, cdp_port):
                    time.sleep(2.0)
                    try:
                        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                    except Exception as err2:
                        raise RuntimeError(f"Launched Chrome but failed to connect over CDP: {err2}") from err2
            if browser is None:
                raise RuntimeError(
                    f"Could not connect to Chrome CDP on port {cdp_port}. Ensure Chrome is launched with --remote-debugging-port={cdp_port}."
                ) from None

        contexts = browser.contexts
        flow_page = None
        if contexts:
            # Strictly search for Google Flow tabs (prevent matching gemini.google.com or aistudio.google.com)
            for page in contexts[0].pages:
                if "flow.google" in page.url or "/flow" in page.url:
                    flow_page = page
                    break

        if not flow_page:
            if contexts and contexts[0].pages:
                for page in contexts[0].pages:
                    if "flow" in page.url:
                        flow_page = page
                        break
            if not flow_page:
                flow_page = browser.new_page()
                flow_page.goto("https://flow.google.com/", wait_until="domcontentloaded")

        if "flow" not in flow_page.url:
            flow_page.goto("https://flow.google.com/", wait_until="domcontentloaded")

        flow_page.bring_to_front()
        time.sleep(1.0)
        print(f"[CANARY] Bound to Google Flow page: {flow_page.url} ('{flow_page.title()}')")

        sha256_ledger = RollingSha256Ledger(window_size=15) if RollingSha256Ledger else None
        if sha256_ledger and os.path.exists(canary_dir):
            for fn in sorted(os.listdir(canary_dir)):
                if fn.endswith(".png"):
                    fp = os.path.join(canary_dir, fn)
                    try:
                        sha256_ledger.register_hash(sha256_ledger.compute_file_hash(fp))
                    except Exception:
                        pass

        for item in canary_items:
            idx = item.get("index", 0)
            ts = item.get("timestamp", "")
            clean_ts = ts.replace("[", "").replace("]", "").replace(":", "_").strip() if ts else f"sentence_{idx}"
            archetype = ARCHETYPE_MAP.get(idx, "Custom Epistemic Frame")

            base_item = baseline_map.get(idx, {})
            base_text = str(base_item.get("visual_prompt", ""))

            save_image_path = os.path.join(canary_dir, f"{clean_ts}.png")
            socratic_text = ""

            if not force_overwrite and os.path.exists(save_image_path) and (validate_image_file is None or validate_image_file(save_image_path, min_size_kb=50)):
                print(f"\n[CANARY] Frame {idx} already exists and verified on disk: {save_image_path}")
                socratic_text = enhance_diffusion_prompt(item)
            else:
                generation_success = False
                fatal_quota_hit = False
                for attempt in range(1, 4):
                    print(f"\n[CANARY] Generating Frame {idx} ({archetype}) [Attempt {attempt}/3] -> {save_image_path}...")
                    try:
                        # ── Lock 2: Continuous Modal & Quota Interceptor ────────
                        dismiss_blocking_agent_and_modals(flow_page)
                        if check_flow_quota_or_errors:
                            q_err = check_flow_quota_or_errors(flow_page)
                            if q_err:
                                raise RuntimeError(f"Google Flow quota or API error: {q_err}")

                        # ── Dual-Mode Selection & Prompt Construction ───────────
                        beat_idx = item.get("beat_index")
                        if beat_idx is None:
                            seq_meta = item.get("sequence_metadata", {})
                            beat_idx = seq_meta.get("frame_index", 1) if isinstance(seq_meta, dict) else 1
                        scene_arch = item.get("scene_archetype") or item.get("sequence_type", "")
                        is_progressive = scene_arch in ("PROGRESSIVE_BUILD", "PROGRESSIVE_BUILD_SET") or (
                            item.get("sequence_metadata", {}).get("total_frames_in_set", 1) > 1
                        )

                        target_char = resolve_target_character(item)
                        if beat_idx == 1 or not is_progressive:
                            # MODE A: Master Anchor Setup (Text-to-Image with chips cleared)
                            if clear_attached_prompt_chips:
                                clear_attached_prompt_chips(flow_page)

                            if target_char and summon_character_chip:
                                print(f"  [CHARACTER PRESET] Summoning '{target_char}' chip for Frame {idx}...")
                                summoned = summon_character_chip(flow_page, target_char)
                                print(f"  [CHARACTER PRESET] Summon {target_char}: {'SUCCESS' if summoned else 'FAILED/SKIPPED'}")

                            mode, prompt_text = (
                                build_dual_mode_prompt(item, attach_success=False)
                                if build_dual_mode_prompt
                                else ("A", "")
                            )
                            if not prompt_text:
                                prompt_text = enhance_diffusion_prompt(item)
                            print(f"  [PROMPT ENGINE] Mode A (Master Setup) for Frame {idx}")
                        else:
                            # MODE B: Progressive Surgical Delta ("Add to Prompt" Active)
                            attached = False
                            if attach_previous_images_to_prompt:
                                attached = attach_previous_images_to_prompt(flow_page, count_to_attach=1)

                            if not attached and target_char and summon_character_chip:
                                print(f"  [CHARACTER PRESET] Mode B fallback: Summoning '{target_char}' chip for Frame {idx}...")
                                summon_character_chip(flow_page, target_char)

                            mode, prompt_text = (
                                build_dual_mode_prompt(item, attach_success=attached)
                                if build_dual_mode_prompt
                                else ("A", "")
                            )
                            if mode == "A" and not prompt_text:
                                prompt_text = enhance_diffusion_prompt(item)
                            print(
                                f"  [PROMPT ENGINE] Mode {mode} ({'Surgical Delta' if mode == 'B' else 'Fallback Master'}) for Frame {idx}: '{prompt_text}'"
                            )

                        socratic_text = prompt_text

                        # ── Lock 1: Pre-submit Card Snapshot & ID Registry ──────
                        input_box = (
                            wait_for_flow_input_box(flow_page, timeout_seconds=15.0)
                            if wait_for_flow_input_box
                            else flow_page.locator("textarea, div[contenteditable='true']").first
                        )
                        pre_card_count = flow_page.locator(
                            "flow-grid-tile-container, div[data-card-index], .generation-card, [role='article']"
                        ).count()
                        if pre_card_count == 0:
                            pre_card_count = flow_page.locator("flow-image-tile, flow-tile-container").count()
                        pre_image_srcs = set()
                        for loc in flow_page.locator("img").all():
                            try:
                                s = loc.get_attribute("src")
                                if s:
                                    pre_image_srcs.add(s)
                            except Exception:
                                pass

                        # Inject prompt safely
                        if inject_prompt_safely and input_box:
                            inject_prompt_safely(flow_page, input_box, prompt_text)
                        elif input_box:
                            input_box.click(force=True)
                            flow_page.wait_for_timeout(200)
                            flow_page.keyboard.press("Control+A")
                            flow_page.keyboard.press("Backspace")
                            flow_page.keyboard.insert_text(prompt_text)
                            flow_page.wait_for_timeout(500)

                        # Submit
                        submit_btn = flow_page.locator(
                            "flow-generate-icon-button button, button[aria-label*='بدء الإنشاء' i], button[aria-label*='Start generation' i], button:has-text('arrow_forward')"
                        ).first
                        if submit_btn.is_visible() and submit_btn.is_enabled():
                            submit_btn.click(force=True)
                        else:
                            flow_page.keyboard.press("Enter")

                        print(f"  [CANARY] Submitted prompt for Frame {idx}. Waiting for card spawn...")

                        # ── Lock 3: Adaptive Handshake with 45s Exponential Backoff ──
                        spawned = (
                            card_spawn_handshake(flow_page, pre_card_count, timeout_seconds=45.0, pre_image_srcs=pre_image_srcs)
                            if card_spawn_handshake
                            else False
                        )
                        if not spawned:
                            flow_page.keyboard.press("Enter")
                            flow_page.wait_for_timeout(2000)
                            if card_spawn_handshake:
                                spawned = card_spawn_handshake(flow_page, pre_card_count, timeout_seconds=15.0, pre_image_srcs=pre_image_srcs)

                        if not spawned:
                            print(f"  ⚠️ Card spawn timed out after 45s on Attempt {attempt}. Reloading...")
                            flow_page.reload()
                            if wait_for_flow_input_box:
                                wait_for_flow_input_box(flow_page, timeout_seconds=15.0)
                            continue

                        # ── Scoped Active-Card Polling ──────────────────────────
                        active_card = flow_page.locator(
                            "flow-grid-tile-container, flow-image-tile, div[data-card-index], .generation-card, [role='article']"
                        ).first
                        start_gen_time = time.time()
                        new_image_loc = None
                        while time.time() - start_gen_time < 120:
                            if check_flow_quota_or_errors:
                                q_err = check_flow_quota_or_errors(flow_page, target_locator=active_card)
                                if q_err:
                                    raise RuntimeError(f"Google Flow error mid-generation: {q_err}")

                            is_loading = False
                            try:
                                if active_card.is_visible():
                                    if active_card.locator("[role='progressbar']").is_visible():
                                        is_loading = True
                                    elif active_card.locator(".animate-pulse, [class*='shimmer'], [class*='skeleton']").first.is_visible():
                                        is_loading = True
                                    elif active_card.get_by_text(re.compile(r'\d+%')).first.is_visible():
                                        is_loading = True
                            except Exception:
                                pass

                            candidates = []
                            card_imgs = flow_page.locator("flow-image-tile img, flow-grid-tile-container img, img").all()
                            for img_loc in card_imgs:
                                try:
                                    src = img_loc.get_attribute("src")
                                    if src and src not in pre_image_srcs and img_loc.is_visible():
                                        box = img_loc.bounding_box()
                                        if box and box["width"] > 180 and box["height"] > 120:
                                            candidates.append((box["y"], box["x"], img_loc))
                                except Exception:
                                    pass

                            if candidates and not is_loading:
                                candidates.sort(key=lambda item: (item[0], item[1]))
                                new_image_loc = candidates[0][2]
                                print(f"  ✅ Frame {idx} render complete!")
                                break
                            flow_page.wait_for_timeout(2000)

                        if not new_image_loc:
                            print(f"  ⚠️ Render timed out on Attempt {attempt}. Reloading...")
                            flow_page.reload()
                            if wait_for_flow_input_box:
                                wait_for_flow_input_box(flow_page, timeout_seconds=15.0)
                            continue

                        # Extract high-res image
                        if new_image_loc and extract_high_res_image:
                            new_image_loc.scroll_into_view_if_needed()
                            flow_page.wait_for_timeout(500)
                            extract_high_res_image(flow_page, new_image_loc, save_image_path, min_size_kb=20)
                        elif new_image_loc:
                            new_image_loc.screenshot(path=save_image_path)

                        # ── Lock 4: 15-frame Rolling SHA-256 Collision Ledger ────
                        if sha256_ledger and os.path.exists(save_image_path):
                            collision, file_hash = sha256_ledger.check_and_register(save_image_path)
                            if collision:
                                print(
                                    f"  ⚠️ [QUADRUPLE-LOCK] Stale scrape collision detected! SHA-256 {file_hash[:12]} matches recent frame. Forcing Hard Reload Recovery..."
                                )
                                try:
                                    os.remove(save_image_path)
                                except OSError:
                                    pass
                                flow_page.reload()
                                if wait_for_flow_input_box:
                                    wait_for_flow_input_box(flow_page, timeout_seconds=15.0)
                                continue

                        generation_success = True
                        break
                    except Exception as exc:
                        print(f"  ⚠️ Attempt {attempt}/3 error: {exc}")
                        if is_fatal_flow_quota_error(exc):
                            fatal_quota_hit = True
                            print(f"\n🛑 [FATAL QUOTA] Google Flow account quota limit reached: {exc}")
                            break
                        if attempt < 3:
                            print(f"  🔄 Recovering: Reloading Flow page before Attempt {attempt + 1}...")
                            try:
                                flow_page.reload()
                                if wait_for_flow_input_box:
                                    wait_for_flow_input_box(flow_page, timeout_seconds=15.0)
                                flow_page.wait_for_timeout(2000)
                            except Exception:
                                pass

                if fatal_quota_hit:
                    print(f"\n🛑 [HALT] Cleanly stopping canary benchmark at Frame {idx} due to account quota saturation.")
                    print("  Existing completed frames are preserved on disk. Switch accounts or retry later.")
                    break

                if not generation_success and not os.path.exists(save_image_path):
                    print(f"  ❌ Failed to generate Frame {idx} after 3 attempts.")

            # OCR Text Gate Evaluation
            has_collision = False
            ocr_text = "NONE"
            upper_clear = False
            file_exists = os.path.exists(save_image_path) and os.path.getsize(save_image_path) > 0
            gate_cfg = {
                "ENABLE_MSER_FALLBACK": os.getenv("FLOW_ENABLE_MSER_FALLBACK", "false").strip().lower() in ("true", "1", "yes")
            }
            seq_type = item.get("sequence_type", "STANDALONE")
            if file_exists:
                has_collision, boxes = check_text_collision(save_image_path, config=gate_cfg, sequence_type=seq_type)
                ocr_text = ", ".join(b.get("text", "") for b in boxes if b.get("text")) or "NONE"
                upper_clear = not has_collision
                status = "PASS" if (not has_collision and upper_clear) else "FAIL"
            else:
                has_collision = True
                upper_clear = False
                status = "FAIL"

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

            # Atomic incremental checkpoint to canary_progress.json
            progress_file = os.path.join(canary_dir, "canary_progress.json")
            prog_data: dict[str, Any] = {"total": len(canary_items), "completed": 0, "frames": {}}
            if os.path.exists(progress_file):
                try:
                    with open(progress_file, encoding="utf-8") as pf:
                        prog_data = json.load(pf)
                except Exception:
                    pass
            prog_frames = prog_data.get("frames", {})
            prog_frames[str(idx)] = {
                "index": idx,
                "timestamp": ts,
                "clean_ts": clean_ts,
                "status": status,
                "ocr_text": ocr_text,
                "size_bytes": os.path.getsize(save_image_path) if file_exists else 0,
            }
            prog_data["frames"] = prog_frames
            prog_data["completed"] = len([f for f in prog_frames.values() if f.get("status") == "PASS" and f.get("size_bytes", 0) > 0])
            try:
                prog_tmp = progress_file + ".tmp"
                with open(prog_tmp, "w", encoding="utf-8") as pf:
                    json.dump(prog_data, pf, indent=2, ensure_ascii=False)
                os.replace(prog_tmp, progress_file)
            except Exception:
                pass

    report_md = (
        "# Socratic Canary Benchmark Live Report\n\n"
        f"Generated and evaluated {len(results)} frames via Google Flow.\n\n"
        + format_comparison_markdown_table(results)
    )
    report_path = os.path.join(run_dir, "canary_benchmark_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    # Compile / update HTML Comparison Viewer Studio
    if generate_comparison_viewer_html:
        try:
            viewer_file = generate_comparison_viewer_html(run_dir, canary_dir)
            print(f"\n[VIEWER] Interactive comparison viewer updated: {viewer_file}")
        except Exception as e:
            print(f"\n[VIEWER] Warning updating comparison viewer: {e}")

    return {"status": "success", "mode": "live", "frames_count": len(results), "report_path": report_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Canary Generation Benchmark Tool")
    parser.add_argument("--run-dir", default=None, help="Path to production run folder")
    parser.add_argument("--output-dir", default=None, help="Output directory for generated canary assets")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of frames to benchmark")
    parser.add_argument("--frames", default="all", help="Frame indices (e.g. 'all', '1-50', '1,15,60,150,264')")
    parser.add_argument("--range", dest="frames", help="Alias for --frames (e.g. '1-50', '51-100')")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome DevTools Protocol port")
    parser.add_argument("--dry-run", action="store_true", help="Run offline without browser automation")
    parser.add_argument("--force-overwrite", action="store_true", help="Bypass disk existence checks and force regeneration of frames")
    args = parser.parse_args()

    run_dir = args.run_dir
    if not run_dir and args.output_dir:
        candidate_parent = os.path.dirname(os.path.abspath(args.output_dir))
        if os.path.exists(os.path.join(candidate_parent, "flow_prompts_socratic.json")) or os.path.exists(
            os.path.join(candidate_parent, "flow_prompts.json")
        ):
            run_dir = candidate_parent
        elif os.path.exists(args.output_dir) and (
            os.path.exists(os.path.join(args.output_dir, "flow_prompts_socratic.json"))
            or os.path.exists(os.path.join(args.output_dir, "flow_prompts.json"))
        ):
            run_dir = args.output_dir

    if not run_dir:
        default_dir = os.path.join(
            "youtube_runs", "Terrence Howard This is The Best Kept SECRET in The ENTIRE WORLD!"
        )
        if os.path.exists(default_dir):
            run_dir = default_dir
        else:
            raise ValueError("No --run-dir provided and could not deduce active run directory.")

    socratic_prompts_file = os.path.join(run_dir, "flow_prompts_socratic.json")
    total_count = 293
    if os.path.exists(socratic_prompts_file):
        try:
            with open(socratic_prompts_file, encoding="utf-8") as f:
                total_count = len(json.load(f))
        except Exception:
            pass

    target_indices = parse_frame_spec(args.frames, total_count=total_count)
    if args.limit and args.limit > 0:
        target_indices = target_indices[: args.limit]

    res = run_canary_benchmark(
        run_dir=run_dir,
        target_indices=target_indices,
        output_dir=args.output_dir,
        cdp_port=args.cdp_port,
        dry_run=args.dry_run,
        force_overwrite=args.force_overwrite,
    )
    print(f"\nCanary Benchmark completed successfully! Mode: {res.get('mode')}")
    print(f"Report saved to: {res.get('report_path')}")


if __name__ == "__main__":
    main()
