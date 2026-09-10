"""Google Flow SPA Automation Coordinator & Image Generation Engine.

Coordinates end-to-end visual generation for the Al-Daheeh YouTube automation pipeline:
- Integrates browser CDP lifecycle via youtube_automation.browser.cdp_client
- Character and scene preset pre-flights via youtube_automation.visuals.asset_studio
- 4-tier high-resolution image extraction via youtube_automation.visuals.image_extractor
- Multi-frame continuity chaining, prompt injection, and turn completion handshakes
- Layer 3 OCR text gate collision detection and debug artifact reporting
- Idempotent checkpointing and state recovery via PipelineManifest
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# Core & Planning DAG imports
try:
    from pipeline_manifest import PhaseStatus, PipelineManifest, compute_script_hash
except ImportError:
    from youtube_automation.core.manifest import (  # type: ignore[no-redef]
        PhaseStatus,
        PipelineManifest,
        compute_script_hash,
    )

try:
    from prompt_planner import build_compact_preamble, plan_all_chunks
except ImportError:
    from youtube_automation.prompts.planner import (  # type: ignore[no-redef]
        build_compact_preamble,
        plan_all_chunks,
    )

try:
    from roadmap_orchestrator import generate_master_roadmap, load_or_migrate_roadmap
except ImportError:
    from youtube_automation.prompts.roadmap import (  # type: ignore[no-redef]
        generate_master_roadmap,
        load_or_migrate_roadmap,
    )

try:
    from text_gate import (
        STRENGTHENED_NEGATIVE_PROMPT,
        check_text_collision,
        dump_text_collision_debug,
    )
except ImportError:
    from youtube_automation.visuals.text_gate import (  # type: ignore[no-redef]
        STRENGTHENED_NEGATIVE_PROMPT,
        check_text_collision,
        dump_text_collision_debug,
    )

try:
    from utils import (
        get_config_value,
        kill_cdp_chrome,
        launch_browser_with_profile,
        rotate_profile_index,
    )
except ImportError:
    from youtube_automation.core.utils import (  # type: ignore[no-redef]
        get_config_value,
        kill_cdp_chrome,
        launch_browser_with_profile,
        rotate_profile_index,
    )

try:
    from validator import (
        enforce_arabic_in_prompt,
        flatten_visual_prompt_to_diffusion_text,
        purge_subtitle_phrases,
        verify_pipeline_integrity,
    )
except ImportError:
    from youtube_automation.prompts.validator import (  # type: ignore[no-redef]
        enforce_arabic_in_prompt,
        flatten_visual_prompt_to_diffusion_text,
        purge_subtitle_phrases,
        verify_pipeline_integrity,
    )

# Modular Browser & Visuals Components
from youtube_automation.browser.cdp_client import (
    capture_debug_state,
    clean_context_tabs,
    connect_cdp,
    ensure_cdp_browser,
    get_or_create_page,
    is_port_in_use,
    prepare_browser_context,
    safe_failover_teardown,
    verify_cdp_port,
)
from youtube_automation.visuals.asset_studio import (
    FLOW_ASSET_PRESETS,
    _rename_workspace_image_card,
    get_profile_assets_manifest_path,
    is_profile_assets_initialized,
    mark_profile_assets_initialized,
    setup_flow_characters_and_scenes,
    summon_asset_in_prompt,
    wait_for_prompt_format_completion,
)
from youtube_automation.visuals.image_extractor import (
    atomic_screenshot_and_verify,
    extract_high_res_image,
    save_binary_image_data,
    validate_image_file,
)

__all__ = [
    "FLOW_ASSET_PRESETS",
    "FlowSelectors",
    "GeminiSelectors",
    "StoryboardFrame",
    "_click_add_to_prompt_on_image",
    "_rename_workspace_image_card",
    "_retry_gemini_call",
    "atomic_screenshot_and_verify",
    "attach_previous_images_to_prompt",
    "capture_debug_state",
    "clean_context_tabs",
    "clear_attached_prompt_chips",
    "connect_cdp",
    "count_attached_prompt_chips",
    "dismiss_blocking_flow_modals",
    "dump_diagnostic_artifact",
    "enforce_arabic_in_prompt",
    "ensure_cdp_browser",
    "extract_high_res_image",
    "flatten_visual_prompt_to_diffusion_text",
    "get_or_create_page",
    "get_profile_assets_manifest_path",
    "inject_prompt_safely",
    "is_flow_page_healthy",
    "is_port_in_use",
    "is_profile_assets_initialized",
    "kill_cdp_chrome",
    "launch_browser_with_profile",
    "log",
    "main",
    "mark_profile_assets_initialized",
    "parse_json_prompts",
    "prepare_browser_context",
    "purge_subtitle_phrases",
    "rotate_profile_index",
    "safe_failover_teardown",
    "save_binary_image_data",
    "save_sorted_prompts_file",
    "scan_batch_folders",
    "setup_flow_characters_and_scenes",
    "setup_flow_ui",
    "summon_asset_in_prompt",
    "validate_image_file",
    "verify_cdp_port",
    "verify_pipeline_integrity",
    "wait_for_flow_app_ready",
    "wait_for_flow_generation_handshake",
    "wait_for_flow_generation_idle",
    "wait_for_flow_input_box",
    "wait_for_predicate",
    "wait_for_prompt_format_completion",
    "write_runtime_telemetry",
]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str) -> None:
    """Outputs real-time timestamped logs with immediate buffer flushing."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def wait_for_flow_app_ready(page: Any, timeout_seconds: int = 60) -> bool:
    """Wait until the Flow SPA is fully interactive (sidebar + content rendered).

    Requires a 3s stability window so React has finished hydrating before any
    click is issued (clicks during hydration are silently swallowed).
    """
    start = time.time()
    first_pass: float | None = None
    while time.time() - start < timeout_seconds:
        try:
            sidebar = page.locator(
                "button:has-text('Characters'), a:has-text('Characters'), [aria-label*='Characters' i]"
            ).first
            if sidebar.is_visible():
                content_ready = (
                    page.locator("img").count() > 0
                    or page.locator("[aria-roledescription='draggable']").count() > 0
                    or page.locator("[contenteditable='true']").count() > 0
                )
                if content_ready:
                    if first_pass is None:
                        first_pass = time.time()
                    elif time.time() - first_pass >= 3.0:
                        return True
                else:
                    first_pass = None
            else:
                first_pass = None
        except Exception:
            first_pass = None  # Tier 1 probe: SPA still booting
        time.sleep(1)
    log("  ⚠️ Flow SPA did not become ready in time.")
    return False


# ==========================================
# TYPED DATA MODEL & SELECTOR REGISTRY
# ==========================================
@dataclass(frozen=True)
class StoryboardFrame:
    """Typed storyboard item replacing the positional 7-tuple."""

    index: int
    timestamp: str
    prompt_text: str
    sequence_type: str = "STANDALONE"
    frame_index: int = 1
    total_frames_in_set: int = 1
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def clean_timestamp(self) -> str:
        return self.timestamp.replace("[", "").replace("]", "").replace(":", "_").strip()


class GeminiSelectors:
    URL = "https://gemini.google.com/app"
    INPUT_BOX = (
        "div[contenteditable='true'], "
        "div[role='textbox'], "
        "rich-textarea div[contenteditable='true'], "
        ".ql-editor, "
        "p[data-placeholder*='Ask' i], "
        "textarea[placeholder*='Ask' i], "
        "textarea"
    )
    RESPONSE_CONTAINER = "model-response, .model-response-text, message-content"
    THINKING_INDICATORS = "mat-progress-spinner, .thinking-indicator, [aria-label='Thinking' i], [aria-label='Thinking...' i], [aria-label='يفكر' i], [aria-label='يفكر...' i]"


class FlowSelectors:
    URL = "https://flow.google.com"
    PROMPT_INPUTS = (
        "textarea[placeholder*='What do you want' i]",
        "input[placeholder*='What do you want' i]",
        "div[contenteditable='true']",
        "textarea",
        "[role='textbox']",
    )
    PROGRESS_INDICATORS = "[role='progressbar'], .animate-spin, mat-progress-spinner"
    AGENT_BUTTON = "button:has-text('Agent')"
    NEW_PROJECT_PATTERN = re.compile(r"(\+?\s*New project|\+?\s*مشروع جديد)", re.IGNORECASE)


def wait_for_predicate(
    predicate_fn: Callable[[], bool],
    timeout: float = 15.0,
    interval: float = 0.5,
    error_msg: str = "Predicate timed out",
) -> bool:
    """Polls a condition until truthy or timeout is reached."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            if predicate_fn():
                return True
        except Exception:
            pass  # Tier 1 probe: predicate may raise while DOM is transient
        time.sleep(interval)
    return False


def write_runtime_telemetry(
    subfolder: str, frame_num: int, total_frames: int, image_name: str
) -> None:
    """Writes non-blocking progress telemetry to disk.

    Catches file-lock exceptions (e.g. Windows WinError 32) so log access
    by external watchers never crashes the rendering pipeline.
    """
    try:
        os.makedirs(subfolder, exist_ok=True)
        log_path = os.path.join(subfolder, "flow_runtime_telemetry.log")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Frame {frame_num}/{total_frames} -> {image_name} (COMPLETE)\n")
    except (OSError, PermissionError):
        pass


def wait_for_flow_generation_handshake(page: Any, timeout_seconds: int = 180) -> bool:
    """2-Phase Handshake:
    Phase 1: Debounce wait (up to 5s) for progressbar/spinner/percentage to MOUNT in DOM.
    Phase 2: Polling wait for all indicators to UNMOUNT and DOM to settle.
    Prevents False-Green race where the DOM is checked before the spinner mounts.
    """
    start_mount = time.time()
    while time.time() - start_mount < 5.0:
        try:
            if page.locator(FlowSelectors.PROGRESS_INDICATORS).first.is_visible():
                break
            if page.get_by_text(re.compile(r"\d+%")).count() > 0:
                break
        except Exception:
            pass
        time.sleep(0.3)

    start_complete = time.time()
    last_heartbeat = time.time()
    while time.time() - start_complete < timeout_seconds:
        is_busy = False
        try:
            if page.locator(FlowSelectors.PROGRESS_INDICATORS).first.is_visible():
                is_busy = True
            elif page.get_by_text(re.compile(r"\d+%")).count() > 0:
                for idx in range(page.get_by_text(re.compile(r"\d+%")).count()):
                    if page.get_by_text(re.compile(r"\d+%")).nth(idx).is_visible():
                        is_busy = True
                        break
        except Exception:
            pass

        if not is_busy:
            time.sleep(1.0)
            return True

        elapsed_complete = int(time.time() - start_complete)
        if time.time() - last_heartbeat >= 5.0:
            log(f"  ⏳ Still generating (Flow) ({elapsed_complete}s/{int(timeout_seconds)}s)...")
            last_heartbeat = time.time()

        time.sleep(1.0)

    log("  ⚠️ Flow generation handshake timed out. Capturing debug state...")
    capture_debug_state(page, "flow_generation_timeout")
    return False


def wait_for_flow_generation_idle(page: Any, timeout_seconds: int = 90) -> bool:
    """Backward-compatible wrapper redirecting to the 2-Phase Handshake."""
    return wait_for_flow_generation_handshake(page, timeout_seconds=timeout_seconds)


def count_attached_prompt_chips(page: Any) -> int:
    """Returns the count of visible reference image chips strictly inside the prompt bar."""
    prompt_container = page.locator(
        "form:has(textarea), div:has(> div[contenteditable='true']), [role='region']:has(textarea)"
    ).last
    if not prompt_container.is_visible():
        prompt_container = page

    chip_selectors = [
        "[role='group']",
        ".attachment-chip",
        "[aria-label*='Remove reference' i]",
        "[aria-label*='Remove chip' i]",
        "img[alt*='reference' i]",
    ]
    total = 0
    for sel in chip_selectors:
        try:
            total += prompt_container.locator(sel).count()
        except Exception:
            pass
    return total


def clear_attached_prompt_chips(page: Any) -> None:
    """DOM Helper: Clears any existing image chips/attachments with closed-loop verification."""
    try:
        for _ in range(3):
            chip_remove_btns = page.locator(
                "button[aria-label*='remove' i], button[aria-label*='delete' i], button[aria-label*='clear' i]"
            ).all()
            if not chip_remove_btns:
                break
            for btn in chip_remove_btns:
                if btn.is_visible():
                    btn.click(force=True)
                    time.sleep(0.2)
        page.keyboard.press("Escape")
        time.sleep(0.2)
    except Exception:
        pass


def _click_add_to_prompt_on_image(page: Any, img_element: Any) -> bool:
    """Internal Helper: Opens context menu on a specific image and clicks 'Add to prompt'."""
    try:
        img_element.scroll_into_view_if_needed()
        time.sleep(0.5)
        img_element.hover()
        time.sleep(0.5)

        menu_clicked = False
        try:
            parent_card = img_element.locator(
                "xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'media') or contains(@class, 'item') or position()=2]"
            ).first
            card_btns = parent_card.locator("button").all()
            if card_btns:
                for b in reversed(card_btns):
                    if b.is_visible():
                        b.click(force=True)
                        menu_clicked = True
                        break
        except Exception:
            pass

        if not menu_clicked:
            try:
                img_element.click(button="right", force=True)
                menu_clicked = True
            except Exception:
                pass

        time.sleep(1)

        add_pattern = re.compile(r"(\+?\s*Add to prompt|إضافة إلى)", re.IGNORECASE)
        add_opt = None

        try:
            opts = page.get_by_text(add_pattern).all()
            for opt in reversed(opts):
                if opt.is_visible():
                    add_opt = opt
                    break
        except Exception:
            pass

        if not add_opt:
            try:
                opts = (
                    page.locator("button, div, [role='menuitem'], li")
                    .filter(has_text=add_pattern)
                    .all()
                )
                for opt in reversed(opts):
                    if opt.is_visible():
                        add_opt = opt
                        break
            except Exception:
                pass

        if add_opt:
            add_opt.scroll_into_view_if_needed()
            add_opt.click(force=True)
            time.sleep(1.2)
            return True
        else:
            page.keyboard.press("Escape")
            return False
    except Exception:
        page.keyboard.press("Escape")
        return False


def attach_previous_images_to_prompt(
    page: Any, count_to_attach: int = 1, batch_count: int = 1
) -> bool:
    """DOM Helper: Clears old chips, finds the target previous primary cards
    (sliding window max 3), and attaches them in CHRONOLOGICAL ORDER (oldest -> newest).
    """
    try:
        count_to_attach = min(count_to_attach, 3)
        clear_attached_prompt_chips(page)

        # Re-verify chips cleared
        for _ in range(5):
            if count_attached_prompt_chips(page) == 0:
                break
            clear_attached_prompt_chips(page)
            time.sleep(0.3)

        if count_to_attach <= 0:
            return True

        feed_imgs = []
        for loc in page.locator("img").all():
            try:
                if loc.is_visible():
                    box = loc.bounding_box()
                    if box and box["x"] > 200 and box["width"] > 180 and box["height"] > 120:
                        if loc.evaluate(
                            "el => el.complete && (el.naturalWidth > 180 || el.clientWidth > 180)"
                        ):
                            feed_imgs.append((box["y"], box["x"], loc))
            except Exception:
                pass

        feed_imgs.sort(key=lambda item: (item[0], item[1]))
        total_found = len(feed_imgs)
        if total_found == 0:
            return False

        stride = max(1, batch_count)
        primary_cards = [feed_imgs[i][2] for i in range(0, total_found, stride)]

        target_subset = primary_cards[:count_to_attach]
        cards_to_attach = list(reversed(target_subset))

        attached_so_far = 0
        for card_elem in cards_to_attach:
            success = _click_add_to_prompt_on_image(page, card_elem)
            if success:
                attached_so_far += 1
                time.sleep(0.8)
            else:
                page.keyboard.press("Escape")
                time.sleep(0.3)

        return attached_so_far > 0
    except Exception:
        page.keyboard.press("Escape")
        return False


def scan_batch_folders() -> list[str]:
    """Scans youtube_runs for folders with image_timestamps.txt or timestamped_transcript.txt."""
    runs_dir = "youtube_runs"
    batch_queue = []
    if os.path.exists(runs_dir):
        for item in os.listdir(runs_dir):
            subfolder = os.path.join(runs_dir, item)
            if os.path.isdir(subfolder):
                ts_file = os.path.join(subfolder, "image_timestamps.txt")
                if not os.path.exists(ts_file):
                    ts_file = os.path.join(subfolder, "timestamped_transcript.txt")

                if os.path.exists(ts_file):
                    batch_queue.append(subfolder)
    return batch_queue


def parse_json_prompts(file_path: str) -> list[StoryboardFrame]:
    """Parses individual JSON objects from file, bypassing array/bracket tracking errors."""
    if not os.path.exists(file_path):
        return []

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    prompts = []
    content_clean = re.sub(r"```json\s*", "", content, flags=re.IGNORECASE)
    content_clean = re.sub(r"```\s*", "", content_clean)

    raw_objects = []
    in_string = False
    escape = False
    brace_depth = 0
    start_pos = -1

    for i, char in enumerate(content_clean):
        if char == '"' and not escape:
            in_string = not in_string
        elif char == "\\" and in_string:
            escape = not escape
            continue
        elif not in_string:
            if char == "{":
                if brace_depth == 0:
                    start_pos = i
                brace_depth += 1
            elif char == "}" and brace_depth > 0:
                brace_depth -= 1
                if brace_depth == 0 and start_pos != -1:
                    raw_objects.append(content_clean[start_pos : i + 1])
                    start_pos = -1
        escape = False

    for obj_str in raw_objects:
        if '"index"' not in obj_str and "'index'" not in obj_str:
            continue

        item = None
        try:
            item = json.loads(obj_str, strict=False)
        except json.JSONDecodeError:
            try:
                fixed_str = re.sub(
                    r'(?<=:\s")([^"\\]*?)"([^"\\]*?)"(?=[\s,}])', r"\1\"\2\"", obj_str
                )
                fixed_str = re.sub(r",\s*([}\]])", r"\1", fixed_str)
                item = json.loads(fixed_str, strict=False)
            except Exception:
                try:
                    idx_m = re.search(r'"index"\s*:\s*(\d+)', obj_str)
                    ts_m = re.search(r'"timestamp"\s*:\s*"([^"]*)"', obj_str)
                    if idx_m:
                        idx_val = int(idx_m.group(1))
                        ts_val = ts_m.group(1) if ts_m else ""
                        mock_item = {
                            "index": idx_val,
                            "timestamp": ts_val,
                            "sequence_type": "STANDALONE",
                            "visual_prompt": obj_str,
                        }
                        prompts.append(
                            StoryboardFrame(
                                index=idx_val,
                                timestamp=ts_val,
                                prompt_text=obj_str,
                                sequence_type="STANDALONE",
                                frame_index=1,
                                total_frames_in_set=1,
                                raw_payload=mock_item,
                            )
                        )
                        continue
                except Exception:
                    pass
                print(f"Warning: Could not parse object string starting with: {obj_str[:60]}...")
                continue

        if isinstance(item, dict):
            try:
                idx = int(item.get("index", 0))
                ts = str(item.get("timestamp", "")).strip()
                vp = item.get("visual_prompt", "")

                if isinstance(vp, dict):
                    prompt = json.dumps(vp, ensure_ascii=False, indent=2)
                else:
                    prompt = str(vp).strip()

                seq_type = str(item.get("sequence_type", "STANDALONE")).strip().upper()
                seq_meta = item.get("sequence_metadata", {})

                frame_idx = 1
                total_frames = 1
                if isinstance(seq_meta, dict):
                    frame_idx = int(seq_meta.get("frame_index", 1))
                    total_frames = int(seq_meta.get("total_frames_in_set", 1))

                if idx > 0 and prompt:
                    prompts.append(
                        StoryboardFrame(
                            index=idx,
                            timestamp=ts,
                            prompt_text=prompt,
                            sequence_type=seq_type,
                            frame_index=frame_idx,
                            total_frames_in_set=total_frames,
                            raw_payload=item,
                        )
                    )
            except Exception:
                continue

    # Deduplicate and sort by (index, frame_index)
    prompts_dict = {}
    for p in prompts:
        idx, frame_idx = p.index, p.frame_index
        key = (idx, frame_idx)
        while key in prompts_dict:
            frame_idx += 1
            key = (idx, frame_idx)

        p = StoryboardFrame(
            index=p.index,
            timestamp=p.timestamp,
            prompt_text=p.prompt_text,
            sequence_type=p.sequence_type,
            frame_index=frame_idx,
            total_frames_in_set=p.total_frames_in_set,
            raw_payload=p.raw_payload,
        )
        prompts_dict[key] = p

    sorted_keys = sorted(prompts_dict.keys(), key=lambda x: (x[0], x[1]))
    return [prompts_dict[k] for k in sorted_keys]


def save_sorted_prompts_file(prompts_list: list[Any], file_path: str) -> None:
    """Overwrites flow_prompts.json with cleanly formatted, numerically ordered JSON items."""
    try:
        clean_items = []
        for p in prompts_list:
            if isinstance(p, StoryboardFrame) and p.raw_payload:
                clean_items.append(p.raw_payload)
            elif isinstance(p, dict):
                clean_items.append(p)
            else:
                try:
                    clean_items.append(json.loads(p.prompt_text))
                except Exception:
                    pass

        if clean_items:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(clean_items, ensure_ascii=False, indent=2))
                f.write("\n")
            print(
                f"  🧹 Successfully cleaned up and sorted {len(clean_items)} items in {os.path.basename(file_path)}."
            )
    except Exception as e:
        print(f"  ⚠️ Warning saving sorted prompts file: {e}")


def wait_for_flow_input_box(page: Any, timeout_seconds: float = 15.0) -> Any:
    """Hydration-Safe Poller: Repeatedly queries the DOM for Google Flow's contenteditable
    prompt bar or fallback inputs, pumping the Playwright CDP event loop via page.wait_for_timeout.
    """
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        # Strategy 1: Visible contenteditable with sufficient width
        try:
            for ce in page.locator("div[contenteditable='true'], [role='textbox'][contenteditable='true']").all():
                if ce.is_visible():
                    box = ce.bounding_box()
                    if box and box["width"] > 250:
                        return ce
        except Exception:
            pass

        # Strategy 2: Textarea / input with prompt placeholder
        for sel in (
            "textarea[placeholder*='What do you want' i]",
            "input[placeholder*='What do you want' i]",
            "div[data-placeholder*='What do you want' i]",
        ):
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    return loc
            except Exception:
                pass

        page.wait_for_timeout(300)

    # Fallback: check any visible contenteditable
    try:
        cand = page.locator("div[contenteditable='true']").first
        if cand.is_visible():
            return cand
    except Exception:
        pass

    return None


def inject_prompt_safely(page: Any, input_locator: Any, prompt_text: str) -> None:
    """Focuses, clears, and dispatches native hardware keyboard events to satisfy
    React/Lexical SyntheticEvent bindings without text dropout or disabled buttons.
    """
    input_locator.click()
    page.wait_for_timeout(200)

    # Clear existing content via hardware keystrokes
    page.keyboard.press("Control+a")
    page.keyboard.press("Backspace")
    page.wait_for_timeout(100)

    # insert_text simulates native typing/paste satisfying React synthetic state
    page.keyboard.insert_text(prompt_text)
    page.wait_for_timeout(300)


def dismiss_blocking_flow_modals(page: Any) -> bool:
    """Detects and dismisses transient backdrop modals/toasts (ToS updates, errors, changelogs)
    without blindly pressing Escape unless a dialog is affirmatively open.
    """
    dismissed = False
    try:
        dialog_selectors = [
            "[role='dialog']",
            "[role='alertdialog']",
            ".modal-backdrop",
            "[class*='dialog-backdrop']",
        ]
        for sel in dialog_selectors:
            modal = page.locator(sel).first
            if modal.is_visible():
                close_btn = modal.locator(
                    "button[aria-label*='close' i], button:has-text('Got it'), button:has-text('Get started'), button:has-text('Dismiss'), button:has-text('Close')"
                ).first
                if close_btn.is_visible():
                    close_btn.click(force=True)
                    dismissed = True
                    page.wait_for_timeout(300)
                else:
                    page.keyboard.press("Escape")
                    dismissed = True
                    page.wait_for_timeout(300)
                break
    except Exception:
        pass
    return dismissed


def dump_diagnostic_artifact(
    page: Any, frame_idx: int, attempt: int, subfolder: str | None = None
) -> None:
    """Atomically dumps paired .png (screenshot) and .html (DOM snapshot) diagnostic artifacts
    on any generation freeze or selector resolution failure.
    """
    try:
        debug_dir = os.path.join(subfolder or ".", "debug_screenshots")
        os.makedirs(debug_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        base_path = os.path.join(debug_dir, f"error_frame_{frame_idx:03d}_att{attempt}_{ts}")

        # 1. Raster image snapshot
        page.screenshot(path=f"{base_path}.png", full_page=False)

        # 2. Complete DOM snapshot for selector / iframe / overlay inspection
        with open(f"{base_path}.html", "w", encoding="utf-8") as f:
            f.write(page.content())

        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}]   📸 [DIAGNOSTIC ARTIFACT] Saved error state to: {base_path}.png/.html", flush=True)
    except Exception as e:
        print(f"  ⚠️ Could not dump diagnostic artifact: {e}", flush=True)


def is_flow_page_healthy(page: Any) -> bool:
    """DOM Health Validator: Detects client-side React/Next.js crashes, blank screens,
    or 500 errors, and verifies that real workspace elements are rendered.
    """
    try:
        crash_patterns = re.compile(
            r"(Application error|client-side exception|Something went wrong|500 Internal Server|404 Not Found)",
            re.IGNORECASE,
        )
        if page.get_by_text(crash_patterns).count() > 0:
            return False

        prompt_bar = wait_for_flow_input_box(page, timeout_seconds=3.0)

        supporting_ui = [
            "button:has-text('All Media')",
            "button:has-text('All media')",
            "button:has-text('Characters')",
            "button:has-text('Scenes')",
            "button:has-text('Agent')",
            "button[aria-label*='Settings' i]",
            ".settings-trigger-button",
            "[aria-label='Settings trigger']",
            "button[aria-label*='Start generation' i]",
            "[role='feed']",
            "[role='toolbar']",
        ]
        has_support = any(page.locator(sel).first.is_visible() for sel in supporting_ui)

        return prompt_bar is not None and has_support
    except Exception:
        return False


def setup_flow_ui(
    page: Any,
    target_flow_model: str = "Nano Banana Pro",
    target_flow_count: str = "1x",
    project_url: str | None = None,
) -> str:
    def wake_up_page() -> None:
        try:
            page.mouse.move(100, 15)
            page.wait_for_timeout(100)
            page.mouse.move(120, 20)
        except Exception:
            pass

    resumed = False
    if project_url and "project" in project_url:
        print(f"\n[FLOW] Attempting to resume workspace: {project_url}", flush=True)
        if page.url == project_url and is_flow_page_healthy(page):
            resumed = True
            print("  ✅ Already active on workspace project and verified healthy.", flush=True)
        else:
            for resume_attempt in range(1, 3):
                try:
                    page.goto(project_url, wait_until="domcontentloaded", timeout=15000)
                    wake_up_page()
                    page.wait_for_timeout(2000)
                    dismiss_blocking_flow_modals(page)

                    if not is_flow_page_healthy(page):
                        print(
                            f"  ⚠️ Application error/crash detected on resume (Attempt {resume_attempt}/2). Forcing reload...",
                            flush=True,
                        )
                        page.reload(wait_until="domcontentloaded", timeout=15000)
                        wake_up_page()
                        page.wait_for_timeout(3000)
                        dismiss_blocking_flow_modals(page)

                    if is_flow_page_healthy(page) and "project" in page.url:
                        resumed = True
                        print("  ✅ Workspace resumed successfully and verified healthy.", flush=True)
                        break
                except Exception as e:
                    print(f"  ⚠️ Workspace resume attempt {resume_attempt} failed: {e}", flush=True)
                    page.wait_for_timeout(1000)

    if not resumed:
        print("\n[FLOW] Workspace resume unavailable. Initializing via Google Flow Homepage...", flush=True)
        try:
            page.goto(FlowSelectors.URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as nav_e:
            print(f"  ⚠️ Primary homepage navigation warning: {nav_e}. Retrying...", flush=True)
            page.goto("https://flow.google.com/", wait_until="domcontentloaded", timeout=30000)

        wake_up_page()
        page.wait_for_timeout(2000)
        dismiss_blocking_flow_modals(page)

        # Check for '+ New project' button
        print("  Looking for '+ New project' button...", flush=True)
        new_project_btn = None
        for _attempt in range(4):
            try:
                cand = page.get_by_text(FlowSelectors.NEW_PROJECT_PATTERN).first
                if cand.is_visible():
                    new_project_btn = cand
                    break
            except Exception:
                pass
            page.wait_for_timeout(1000)

        if not new_project_btn:
            try:
                cand = page.locator("button:has-text('New project'), a:has-text('New project')").first
                if cand.is_visible():
                    new_project_btn = cand
            except Exception:
                pass

        if new_project_btn and new_project_btn.is_visible():
            print("  Found 'New project' button. Clicking...", flush=True)
            new_project_btn.scroll_into_view_if_needed()
            new_project_btn.click(force=True)
            page.wait_for_timeout(4000)
        else:
            print("  Already inside a workspace project or direct UI ready.", flush=True)

    dismiss_blocking_flow_modals(page)

    # Configure Model & Output Count Settings
    print(f"  Configuring Flow Model: {target_flow_model} | Count: {target_flow_count}...")
    try:
        st = page.locator("[aria-label='Settings trigger'], .settings-trigger-button").first
        if st.is_visible():
            st_text = st.inner_text().strip()
            # Check if model or aspect ratio or count needs updating
            needs_config = (
                target_flow_model.lower() not in st_text.lower()
                or ("16_9" not in st_text and "16:9" not in st_text)
                or f"x{target_flow_count}" not in st_text
            )
            if needs_config:
                st.click(force=True)
                page.wait_for_timeout(600)

                # 1. Ensure Image tab is selected
                img_tab = page.locator("button, div, span").filter(has_text=re.compile(r"^Image$", re.I)).first
                if img_tab.is_visible():
                    img_tab.click(force=True)
                    page.wait_for_timeout(300)

                # 2. Aspect Ratio: 16:9
                ar_btn = page.locator("button, div, span").filter(has_text=re.compile(r"^16:9$", re.I)).first
                if ar_btn.is_visible():
                    ar_btn.click(force=True)
                    page.wait_for_timeout(300)

                # 3. Model family dropdown inside settings popup
                model_btn = page.locator("button[aria-label='Select model family'], button:has(.model-select-trigger-content)").first
                if model_btn.is_visible():
                    curr_model_txt = model_btn.inner_text().strip()
                    if target_flow_model.lower() not in curr_model_txt.lower():
                        model_btn.click(force=True)
                        page.wait_for_timeout(500)
                        # Target model option in root cdk-overlay-container
                        model_opt = page.locator(
                            "div.cdk-overlay-container [role='menuitem'], div.cdk-overlay-container button"
                        ).filter(has_text=re.compile(rf"{re.escape(target_flow_model)}", re.I)).first
                        if model_opt.is_visible():
                            print(f"  Selecting target model option: {target_flow_model}")
                            model_opt.click(force=True)
                            page.wait_for_timeout(400)
                        else:
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(200)

                # 4. Count toggle
                count_btn = page.locator("button, div, span").filter(has_text=re.compile(rf"^x?{target_flow_count}$", re.I)).first
                if count_btn.is_visible():
                    count_btn.click(force=True)
                    page.wait_for_timeout(300)

                # Close settings popup
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
    except Exception as e:
        print(f"  ⚠️ Model selection warning: {e}")

    # Return validated URL
    return page.url


def _retry_gemini_call(
    gemini_page: Any, fn: Callable[..., Any], label: str, retries: int = 3
) -> Any:
    """Run a Gemini planning operation with bounded retries."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_exc = e
            err_msg = str(e).lower()
            is_validation = any(
                k in err_msg
                for k in [
                    "missing",
                    "exhausted",
                    "validation",
                    "schema violation",
                    "forbidden term",
                    "chunkplanningerror",
                ]
            )
            if is_validation:
                print(
                    f"  [RETRY VALIDATION] {label} failed (attempt {attempt}/{retries}): {e}. "
                    "Retrying in same chat (no new chat, preserves context)..."
                )
                try:
                    gemini_page.bring_to_front()
                    time.sleep(2)
                except Exception:
                    pass
            else:
                print(
                    f"  [RETRY BROWSER] {label} failed (attempt {attempt}/{retries}): {e}. "
                    "Reloading Gemini page and retrying..."
                )
                try:
                    gemini_page.bring_to_front()
                    gemini_page.reload(wait_until="domcontentloaded", timeout=45000)
                    gemini_page.bring_to_front()
                    time.sleep(3)
                except Exception as reload_err:
                    print(f"  Gemini page reload during retry failed: {reload_err}")
    raise RuntimeError(f"{label} failed after {retries} attempts: {last_exc}")


# ==========================================
# MAIN ORCHESTRATOR
# ==========================================
def main() -> None:
    """Main CLI execution loop for Google Flow visual generation."""
    batch_queue = scan_batch_folders()
    if not batch_queue:
        print("No active folders found.")
        return

    consecutive_failures = 0
    max_retries_no_switch = 3
    browser_handle = None
    outer_loops = 0
    max_outer_loops = 10

    while True:
        outer_loops += 1
        if outer_loops > max_outer_loops:
            print(
                f"[FATAL ERROR] Outer recovery loop exceeded {max_outer_loops} "
                "iterations (likely unrecoverable browser state). Exiting."
            )
            sys.exit(1)
        failover_triggered = False

        switch_enabled_str = get_config_value("SWITCH_ACCOUNTS_ENABLED", "false").strip().lower()
        accounts_enabled = switch_enabled_str in ("true", "1", "yes")

        try:
            with sync_playwright() as p:
                current_profile_idx = get_config_value("ACTIVE_PROFILE_INDEX", "1")
                browser_type = get_config_value("BROWSER_TYPE", "chrome")
                cdp_port = int(get_config_value("CDP_PORT", "9222"))

                browser = ensure_cdp_browser(
                    p,
                    port=cdp_port,
                    profile_index=current_profile_idx,
                    browser_type=browser_type,
                )
                browser_handle = browser

                context = prepare_browser_context(browser)
                clean_context_tabs(context)

                gemini_page = None
                flow_page = None
                for page in context.pages:
                    if "gemini.google.com" in page.url:
                        gemini_page = page
                    elif "labs.google" in page.url or "fx/tools/flow" in page.url or "flow.google.com" in page.url:
                        flow_page = page

                if not gemini_page:
                    gemini_page = context.new_page()
                    log("Navigating to Gemini Web App...")
                    try:
                        gemini_page.goto(
                            GeminiSelectors.URL,
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                    except Exception as e:
                        log(f"Warning: Gemini initial load: {e}")

                if not flow_page:
                    flow_page = context.new_page()

                gemini_page.bring_to_front()

                for _folder_idx, subfolder in enumerate(batch_queue, 1):
                    print("\n==================================================")
                    print(f"PROCESSING TOPIC: {subfolder}")
                    print("==================================================")

                    script_path = os.path.join(subfolder, "image_timestamps.txt")
                    if not os.path.exists(script_path):
                        script_path = os.path.join(subfolder, "timestamped_transcript.txt")
                    prompts_file = os.path.join(subfolder, "flow_prompts.json")
                    image_dir = os.path.join(subfolder, "generated_images")
                    dup_dir = os.path.join(subfolder, "generated_images_duplicates")
                    os.makedirs(image_dir, exist_ok=True)
                    os.makedirs(dup_dir, exist_ok=True)

                    target_planner_model = get_config_value("IMAGE_PLANNER_MODEL", "Flash-Lite")
                    target_flow_model = get_config_value("FLOW_IMAGE_MODEL", "Nano Banana 2")
                    target_flow_count = get_config_value("FLOW_IMAGE_COUNT", "1x")
                    reset_loop_limit = int(get_config_value("IMAGE_RESET_LOOP_LIMIT", "20"))

                    cumulative_chaining_enabled = get_config_value(
                        "FLOW_CUMULATIVE_CHAINING_ENABLED", "true"
                    ).strip().lower() in ("true", "1", "yes")
                    max_chain_limit = int(get_config_value("FLOW_MAX_CHAIN_IMAGES", "3"))

                    sentences, timestamps = [], []
                    if os.path.exists(script_path):
                        with open(script_path, encoding="utf-8") as f:
                            for line in f:
                                line_str = line.strip()
                                if not line_str:
                                    continue
                                match = re.match(
                                    r"^\[(?:(\d{2}):)?(\d{2}):(\d{2})\]\s*(.*)", line_str
                                )
                                if match:
                                    h = match.group(1)
                                    m = match.group(2)
                                    s = match.group(3)
                                    text = match.group(4).strip()
                                    ts_str = f"[{h}:{m}:{s}]" if h else f"[{m}:{s}]"
                                    timestamps.append(ts_str)
                                    sentences.append(text)

                    storyboard_prompts = []

                    if sentences:
                        transcript_text = "\n".join(
                            f"[{ts}] {s}" for ts, s in zip(timestamps, sentences, strict=False)
                        )
                        presets_text = json.dumps(
                            FLOW_ASSET_PRESETS, ensure_ascii=False, sort_keys=True
                        )
                        script_hash = compute_script_hash(
                            transcript_text, build_compact_preamble(None), presets_text
                        )
                        manifest = PipelineManifest.load_or_create(subfolder, script_hash)
                        if manifest.was_reset:
                            log(
                                "[MANIFEST] Script changed since last run - invalidating cached "
                                "roadmap/planning state."
                            )
                        manifest.set_roadmap_status(PhaseStatus.IN_PROGRESS)
                        window_size = int(get_config_value("ROADMAP_WINDOW_SIZE", "25") or 25)
                        chunk_size = int(get_config_value("FLOW_CHUNK_SIZE", "15"))
                        roadmap_rows = load_or_migrate_roadmap(subfolder, sentences, manifest)
                        if roadmap_rows is None:
                            gemini_page.bring_to_front()
                            roadmap_rows = _retry_gemini_call(
                                gemini_page,
                                lambda gp=gemini_page, s=sentences, sub=subfolder, m=manifest, ws=window_size, pm=target_planner_model: (
                                    generate_master_roadmap(
                                        gp,
                                        s,
                                        sub,
                                        m,
                                        window_size=ws,
                                        planner_model=pm,
                                    )
                                ),
                                label="Master roadmap generation",
                            )
                        expected_total = len(sentences)
                        prompts_complete = False
                        if manifest.all_chunks_done() or os.path.exists(prompts_file):
                            try:
                                if os.path.exists(prompts_file):
                                    with open(prompts_file, encoding="utf-8") as f:
                                        existing = json.load(f)
                                else:
                                    existing = []
                                prompts_complete = {
                                    int(p["index"])
                                    for p in existing
                                    if isinstance(p, dict) and "index" in p
                                } == set(range(1, expected_total + 1))
                                if prompts_complete:
                                    if hasattr(manifest, "set_planning_status"):
                                        manifest.set_planning_status(PhaseStatus.COMPLETED)
                                    else:
                                        manifest._data["planning_phase"]["status"] = PhaseStatus.COMPLETED.value
                                    manifest.save()
                                    log(f"[planner] reusing complete flow_prompts.json ({expected_total} frames).")
                            except Exception as prompt_reuse_err:
                                log(f"[planner] prompt reuse check error: {prompt_reuse_err}")
                                prompts_complete = False
                        if not prompts_complete:
                            gemini_page.bring_to_front()
                            _retry_gemini_call(
                                gemini_page,
                                lambda gp=gemini_page, s=sentences, ts=timestamps, rr=roadmap_rows, sub=subfolder, m=manifest, cs=chunk_size, pm=target_planner_model: (
                                    plan_all_chunks(
                                        gp,
                                        s,
                                        ts,
                                        rr,
                                        sub,
                                        m,
                                        chunk_size=cs,
                                        planner_model=pm,
                                        presets=FLOW_ASSET_PRESETS,
                                    )
                                ),
                                label="Chunk planning",
                            )
                        storyboard_prompts = parse_json_prompts(prompts_file)
                        verify_pipeline_integrity(
                            [frame.raw_payload for frame in storyboard_prompts], expected_total
                        )

                    # ---------------------------------------------------------
                    # PHASE 2: IMAGE RENDERING (GOOGLE FLOW WITH FREEZE PROTECTION)
                    # ---------------------------------------------------------
                    total_storyboard_frames = len(storyboard_prompts)
                    if total_storyboard_frames == 0:
                        continue

                    print(
                        f"\n[PHASE 2] Rendering {total_storyboard_frames} images via Google Flow..."
                    )
                    flow_page.bring_to_front()

                    url_checkpoint_file = os.path.join(
                        subfolder, f"flow_workspace_url_profile_{current_profile_idx}.txt"
                    )
                    saved_project_url = None
                    if os.path.exists(url_checkpoint_file):
                        with open(url_checkpoint_file, encoding="utf-8") as f:
                            saved_project_url = f.read().strip()

                    active_project_url = setup_flow_ui(
                        flow_page, target_flow_model, target_flow_count, saved_project_url
                    )

                    if "project" in active_project_url:
                        with open(url_checkpoint_file, "w", encoding="utf-8") as f:
                            f.write(active_project_url)

                    # Pre-flight character and scene builder
                    try:
                        setup_flow_characters_and_scenes(
                            flow_page,
                            subfolder=subfolder,
                            profile_index=str(current_profile_idx),
                        )
                    except Exception as preset_err:
                        print(
                            f"  ⚠️ Character/Scene preset setup failed (continuing without "
                            f"presets): {preset_err}"
                        )
                        try:
                            capture_debug_state(flow_page, "char_preset_setup_fail", subfolder)
                        except Exception:
                            pass
                        try:
                            flow_page.goto(active_project_url, wait_until="domcontentloaded")
                        except Exception:
                            pass

                    executed_generations_count = 0
                    prev_prompt_text = ""
                    prev_idx = None
                    ts_counts: dict[str, int] = {}

                    for current_run, prompt_item in enumerate(storyboard_prompts, 1):
                        idx = prompt_item.index
                        ts = prompt_item.timestamp
                        prompt_text = prompt_item.prompt_text
                        seq_type = prompt_item.sequence_type
                        frame_idx = prompt_item.frame_index
                        total_frames_in_set = prompt_item.total_frames_in_set
                        ts_source = (
                            ts
                            if ts
                            else (timestamps[idx - 1] if 0 <= (idx - 1) < len(timestamps) else "")
                        )
                        clean_ts = (
                            ts_source.replace("[", "").replace("]", "").replace(":", "_").strip()
                        )

                        if clean_ts:
                            occ = ts_counts.get(clean_ts, 0) + 1
                            ts_counts[clean_ts] = occ
                            image_name = f"{clean_ts}.png" if occ == 1 else f"{clean_ts}_{occ}.png"
                        else:
                            occ = 1
                            image_name = f"sentence_{idx}.png"

                        save_path = os.path.join(image_dir, image_name)

                        if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
                            print(f"[SKIP] Frame {idx} ({image_name}) exists.")
                            prev_prompt_text = prompt_text
                            prev_idx = idx
                            continue

                        executed_generations_count += 1
                        if (
                            executed_generations_count > 1
                            and (executed_generations_count - 1) % reset_loop_limit == 0
                        ):
                            print(f"\n[RESET] Refreshing Flow UI (Limit: {reset_loop_limit})...")
                            flow_page.reload()
                            setup_flow_ui(
                                flow_page, target_flow_model, target_flow_count, active_project_url
                            )

                        print(f"Rendering Frame {idx} ({image_name})...")
                        success = False
                        try:
                            for attempt in range(1, 4):
                                try:
                                    multiframe_seq_types = [
                                        "PROGRESSIVE_BUILD_SET",
                                        "HISTORICAL_PARODY",
                                        "SCIENTIFIC_BLUEPRINT",
                                        "SKEPTIC_SPLIT",
                                        "THEME_SET_CONTINUITY",
                                        "CAMERA_ZOOM_SEQUENCE",
                                    ]

                                    is_multiframe_continuity = (
                                        (seq_type in multiframe_seq_types and frame_idx > 1)
                                        or (occ > 1)
                                        or (frame_idx > 1)
                                    )

                                    if (
                                        is_multiframe_continuity
                                        and prev_prompt_text
                                        and prev_idx is not None
                                    ):
                                        if cumulative_chaining_enabled:
                                            num_prev = frame_idx - 1 if frame_idx > 1 else occ - 1
                                            attach_count = min(max(0, num_prev), max_chain_limit)
                                        else:
                                            attach_count = 1
                                    else:
                                        attach_count = 0

                                    natural_prompt = flatten_visual_prompt_to_diffusion_text(
                                        prompt_text, sequence_type=seq_type
                                    )

                                    if attach_count > 0:
                                        subj_lower = (
                                            str(
                                                prompt_item.raw_payload.get(
                                                    "visual_prompt", {}
                                                ).get("subject_details", "")
                                            ).lower()
                                            if isinstance(prompt_item.raw_payload, dict)
                                            else ""
                                        )

                                        if "clerk" in subj_lower or "bureaucrat" in subj_lower:
                                            char_lock = "the Science Bureaucrat (beige suit, receding hair, thick glasses)"
                                        elif "skeptic" in subj_lower or "abo hmeed" in subj_lower:
                                            char_lock = "Abo Hmeed (navy jacket, questioning facial expression)"
                                        elif "absent" in subj_lower:
                                            char_lock = "the environment, prop materials, and studio lighting setup"
                                        else:
                                            char_lock = "the Host (Al-Daheeh: wire glasses, curly afro hair, charcoal hoodie)"

                                        continuity_directive = (
                                            f" Sequential Continuity Lock (Frame {frame_idx}/{total_frames_in_set}): "
                                            f"Lock 100% visual consistency with the attached reference frame for {char_lock}, background architecture, and warm studio lighting. "
                                            "Preserve the exact 2D vector cel-shaded art style and render only the new subject action described."
                                        )
                                        payload_text = f"{natural_prompt} {continuity_directive}"
                                    else:
                                        payload_text = natural_prompt

                                    payload_text = enforce_arabic_in_prompt(payload_text)
                                    payload_text = purge_subtitle_phrases(payload_text)

                                    flow_page.wait_for_timeout(1000)
                                    pre_image_srcs = set()
                                    for loc in flow_page.locator("img").all():
                                        try:
                                            src = loc.get_attribute("src")
                                            if src:
                                                pre_image_srcs.add(src)
                                        except Exception:
                                            pass

                                    if attach_count > 0:
                                        raw_count_str = re.sub(r"\D", "", target_flow_count)
                                        batch_num = int(raw_count_str) if raw_count_str else 1
                                        attach_previous_images_to_prompt(
                                            flow_page,
                                            count_to_attach=attach_count,
                                            batch_count=batch_num,
                                        )
                                    else:
                                        clear_attached_prompt_chips(flow_page)

                                        presets_master = get_config_value(
                                            "FLOW_ENABLE_ASSET_PRESETS", "true"
                                        ).strip().lower() in ("true", "1", "yes")
                                        chars_enabled = get_config_value(
                                            "FLOW_ENABLE_CHARACTER_PRESETS", "true"
                                        ).strip().lower() in ("true", "1", "yes")
                                        scenes_enabled = get_config_value(
                                            "FLOW_ENABLE_SCENE_PRESETS", "true"
                                        ).strip().lower() in ("true", "1", "yes")

                                        if presets_master and (chars_enabled or scenes_enabled):
                                            raw_item = (
                                                prompt_item.raw_payload
                                                if isinstance(prompt_item.raw_payload, dict)
                                                else {}
                                            )
                                            subject_details = ""
                                            layout_class = ""
                                            env_coords = ""
                                            if isinstance(raw_item, dict):
                                                layout_class = str(
                                                    raw_item.get("layout_classification", "")
                                                )
                                                vp = raw_item.get("visual_prompt", {})
                                                if isinstance(vp, dict):
                                                    subject_details = str(
                                                        vp.get("subject_details", "")
                                                    )
                                                    env_coords = str(
                                                        vp.get("environment_coordinates", "")
                                                    )

                                            is_absent_subject = subject_details.upper().startswith(
                                                "ABSENT"
                                            )
                                            if chars_enabled and not is_absent_subject:
                                                is_skeptic = (
                                                    "skeptic" in subject_details.lower()
                                                    or "abo hmeed" in subject_details.lower()
                                                )

                                                for char_k, char_v in FLOW_ASSET_PRESETS.get(
                                                    "CHARACTERS", {}
                                                ).items():
                                                    if is_skeptic and char_k == "HOST":
                                                        continue
                                                    if char_k.lower() in subject_details.lower():
                                                        summon_asset_in_prompt(
                                                            flow_page,
                                                            char_v["name"],
                                                            category="Characters",
                                                        )
                                                        flow_page.wait_for_timeout(1000)
                                                        break

                                            if scenes_enabled:
                                                for scene_k, scene_v in FLOW_ASSET_PRESETS.get(
                                                    "SCENES", {}
                                                ).items():
                                                    if (
                                                        scene_k.lower() in layout_class.lower()
                                                        or scene_k.lower() in env_coords.lower()
                                                    ):
                                                        summon_asset_in_prompt(
                                                            flow_page,
                                                            scene_v["name"],
                                                            category="Scenes",
                                                        )
                                                        flow_page.wait_for_timeout(1000)
                                                        break

                                    dismiss_blocking_flow_modals(flow_page)
                                    input_box = wait_for_flow_input_box(flow_page, timeout_seconds=15.0)

                                    if not input_box or not input_box.is_visible():
                                        dump_diagnostic_artifact(flow_page, idx, attempt, subfolder)
                                        raise Exception(
                                            "Could not find Google Flow prompt input box on page."
                                        )

                                    input_box.scroll_into_view_if_needed()
                                    chips_count = count_attached_prompt_chips(flow_page)
                                    if chips_count == 0 and attach_count == 0:
                                        inject_prompt_safely(flow_page, input_box, payload_text)
                                    else:
                                        input_box.click(force=True)
                                        flow_page.wait_for_timeout(200)
                                        flow_page.keyboard.press("End")
                                        flow_page.wait_for_timeout(100)
                                        flow_page.keyboard.insert_text(f" {payload_text}")
                                        flow_page.wait_for_timeout(300)

                                    submit_btn = flow_page.locator("button[aria-label*='Start generation' i], button:has-text('arrow_forward')").first
                                    if submit_btn.is_visible() and submit_btn.is_enabled():
                                        submit_btn.click(force=True)
                                    else:
                                        flow_page.keyboard.press("Enter")

                                    print(
                                        f"  Attempt {attempt}: Prompt submitted. Monitoring generation engine..."
                                    )
                                    flow_page.wait_for_timeout(2000)

                                    # ── Card-Spawn Handshake ──────────────────────────────────────
                                    # Record card count before submit and wait up to 20s for a new
                                    # card to appear. This distinguishes "stalled before generation"
                                    # from "generation in progress but no % yet".
                                    pre_card_count = 0
                                    try:
                                        pre_card_count = flow_page.locator(
                                            "div[data-card-index], .generation-card, [role='article']"
                                        ).count()
                                    except Exception:
                                        pass

                                    card_spawned = False
                                    for _cw in range(20):  # 20 × 1s = 20s max
                                        try:
                                            curr_count = flow_page.locator(
                                                "div[data-card-index], .generation-card, [role='article']"
                                            ).count()
                                            if curr_count > pre_card_count:
                                                card_spawned = True
                                                break
                                            # Also accept a progressbar appearing even without new card
                                            if flow_page.locator("[role='progressbar']").is_visible():
                                                card_spawned = True
                                                break
                                        except Exception:
                                            pass
                                        flow_page.wait_for_timeout(1000)

                                    if not card_spawned:
                                        # Re-check input box still has content (submission may have cleared)
                                        box_text = ""
                                        try:
                                            box_text = input_box.evaluate(
                                                "el => el.value || el.innerText || ''"
                                            ).strip()
                                        except Exception:
                                            pass

                                        if box_text and "what do you want" not in box_text.lower():
                                            print(
                                                "  🔄 Submission not detected. Re-triggering Enter..."
                                            )
                                            flow_page.keyboard.press("Enter")
                                            flow_page.wait_for_timeout(2000)
                                    # ── End Card-Spawn Handshake ──────────────────────────────────

                                    final_generated_locators = []
                                    start_gen_time = time.time()
                                    max_wait_seconds = 180
                                    generation_has_started = False
                                    last_activity_time = time.time()
                                    active_card = flow_page.locator(
                                        "div[data-card-index]:last-child, .generation-card:last-child, [role='article']:last-child"
                                    ).first
                                    hard_ceiling_time = start_gen_time + 360  # 6-minute absolute ceiling

                                    while time.time() - start_gen_time < max_wait_seconds:
                                        error_locators = flow_page.get_by_text(
                                            re.compile(
                                                r"(unusual activity|couldn't generate|failed to generate|policy violation|reached your usage limit|you have not been charged)",
                                                re.IGNORECASE,
                                            )
                                        )
                                        for err_idx in range(error_locators.count()):
                                            if error_locators.nth(err_idx).is_visible():
                                                error_msg = error_locators.nth(err_idx).inner_text()
                                                print(
                                                    f"  ⚠️ Google Flow rejected the prompt: {error_msg}"
                                                )
                                                dump_diagnostic_artifact(flow_page, idx, attempt, subfolder)
                                                raise Exception(
                                                    "Generation failed due to API rejection or UI error."
                                                )

                                        failed_media_locator = flow_page.get_by_text(
                                            "Something went wrong loading your media"
                                        )
                                        if failed_media_locator.is_visible():
                                            print(
                                                "  ⚠️ Detected: 'Something went wrong loading your media' container."
                                            )
                                            card_retry_success = False
                                            for retry_attempt in range(1, 4):
                                                try:
                                                    retry_btn = (
                                                        flow_page.locator(
                                                            "button:has-text('Retry'), button:has(svg)"
                                                        )
                                                        .filter(has=flow_page.locator("path"))
                                                        .last
                                                    )
                                                    if retry_btn.is_visible():
                                                        print(
                                                            f"  🔄 Clicking Google Flow's card retry button (Attempt {retry_attempt}/3)..."
                                                        )
                                                        retry_btn.click(force=True)
                                                        flow_page.wait_for_timeout(5000)
                                                        if not failed_media_locator.is_visible():
                                                            print(
                                                                "  🟢 Card retry succeeded! Continuing monitoring..."
                                                            )
                                                            card_retry_success = True
                                                            break
                                                except Exception:
                                                    pass
                                                flow_page.wait_for_timeout(2000)

                                            if (
                                                not card_retry_success
                                                and failed_media_locator.is_visible()
                                            ):
                                                raise Exception(
                                                    "Media loading failed completely on this card."
                                                )

                                        is_loading = False
                                        try:
                                            ac = active_card
                                            if ac.is_visible():
                                                if ac.locator("[role='progressbar']").is_visible():
                                                    is_loading = True
                                                elif ac.get_by_text(re.compile(r'\d+%')).first.is_visible():
                                                    is_loading = True
                                                elif ac.locator(".animate-pulse, [class*='shimmer'], [class*='skeleton']").first.is_visible():
                                                    is_loading = True
                                        except Exception:
                                            pass
                                        if not is_loading:
                                            loading_locators = flow_page.get_by_text(
                                                re.compile(r"\d+%")
                                            )
                                            for load_idx in range(loading_locators.count()):
                                                if loading_locators.nth(load_idx).is_visible():
                                                    is_loading = True
                                                    break
                                            if flow_page.locator("[role='progressbar']").is_visible():
                                                is_loading = True

                                        if is_loading:
                                            if not generation_has_started:
                                                print(
                                                    "  🟢 Generation activity detected in DOM. Watching progress..."
                                                )
                                                generation_has_started = True
                                            last_activity_time = time.time()

                                        new_workspace_imgs = []
                                        for loc in flow_page.locator("img").all():
                                            try:
                                                src = loc.get_attribute("src")
                                                if src and src not in pre_image_srcs:
                                                    if loc.is_visible():
                                                        box = loc.bounding_box()
                                                        if (
                                                            box
                                                            and box["x"] > 200
                                                            and box["width"] > 180
                                                            and box["height"] > 120
                                                        ):
                                                            if loc.evaluate(
                                                                "el => el.complete && (el.naturalWidth > 180 || el.clientWidth > 180)"
                                                            ):
                                                                new_workspace_imgs.append(
                                                                    (box["y"], box["x"], loc)
                                                                )
                                            except Exception:
                                                pass

                                        new_workspace_imgs.sort(key=lambda item: (item[0], item[1]))
                                        new_images = [item[2] for item in new_workspace_imgs]

                                        if len(new_images) > 0 and not is_loading:
                                            print(
                                                "  ✅ New image render 100% complete! Waiting for overlay to clear..."
                                            )
                                            flow_page.wait_for_timeout(5000)
                                            final_generated_locators = new_images
                                            break

                                        if not generation_has_started and (
                                            time.time() - start_gen_time > 120
                                        ):
                                            print(
                                                "  ⚠️ No generation card/progress appeared after 120s. Forcing reload..."
                                            )
                                            raise Exception("Google Flow initial queue stalled.")

                                        if generation_has_started and (
                                            time.time() - last_activity_time > 120
                                        ):
                                            print(
                                                "  ⚠️ Progress froze for 120s mid-generation. Forcing reload..."
                                            )
                                            raise Exception(
                                                "Google Flow rendering froze mid-progress."
                                            )

                                        if time.time() > hard_ceiling_time:
                                            dump_diagnostic_artifact(flow_page, idx, attempt, subfolder)
                                            raise Exception("Google Flow exceeded 360s hard ceiling. Reloading.")

                                        flow_page.wait_for_timeout(2000)

                                    raw_exp_str = re.sub(r"\D", "", str(target_flow_count))
                                    expected_new = int(raw_exp_str) if raw_exp_str else 1
                                    if expected_new < 1:
                                        expected_new = 1

                                    images_to_extract = min(
                                        len(final_generated_locators), expected_new
                                    )
                                    print(
                                        f"  Render 100% Complete! Extracting {images_to_extract} image(s)..."
                                    )

                                    download_attempt_success = False
                                    current_image_stem = os.path.splitext(image_name)[0]

                                    for i in range(images_to_extract):
                                        img_locator = final_generated_locators[i]
                                        is_duplicate = i > 0
                                        if is_duplicate:
                                            current_save_path = os.path.join(
                                                dup_dir, f"{current_image_stem}_duplicate_{i}.png"
                                            )
                                        else:
                                            current_save_path = save_path

                                        img_locator.scroll_into_view_if_needed()
                                        time.sleep(0.3)

                                        saved = extract_high_res_image(
                                            flow_page,
                                            img_locator,
                                            current_save_path,
                                            min_size_kb=20,
                                        )
                                        if saved:
                                            gate_cfg = {
                                                "ENABLE_MSER_FALLBACK": get_config_value(
                                                    "FLOW_ENABLE_MSER_FALLBACK", "false"
                                                ).strip().lower() in ("true", "1", "yes")
                                            }
                                            has_collision, ocr_boxes = check_text_collision(
                                                current_save_path, config=gate_cfg, sequence_type=prompt_item.sequence_type
                                            )
                                            if has_collision:
                                                print(
                                                    f"  ⚠️ [TEXT COLLISION] Detected rendered text in {os.path.basename(current_save_path)}: {ocr_boxes}"
                                                )

                                                def _cleanup_collision_file(fpath: str) -> None:
                                                    if os.path.exists(fpath):
                                                        try:
                                                            os.remove(fpath)
                                                        except OSError:
                                                            pass

                                                if attempt == 1:
                                                    print(
                                                        "  🔄 Retrying once with strengthened negative prompt..."
                                                    )
                                                    payload_text = f"{payload_text}, {STRENGTHENED_NEGATIVE_PROMPT}"
                                                    _cleanup_collision_file(current_save_path)
                                                    continue
                                                else:
                                                    dump_path = os.path.join(
                                                        subfolder,
                                                        "debug",
                                                        f"malformed_chunk_{idx}.json",
                                                    )
                                                    dump_text_collision_debug(
                                                        dump_path,
                                                        idx,
                                                        current_save_path,
                                                        ocr_boxes,
                                                        payload_text,
                                                    )
                                                    print(
                                                        f"  ❌ [TEXT COLLISION] Persistent collision after retry. Debug dump: {dump_path}"
                                                    )
                                                    _cleanup_collision_file(current_save_path)
                                            else:
                                                if not is_duplicate:
                                                    download_attempt_success = True
                                        else:
                                            print(
                                                f"  ⚠️ All extraction attempts failed for {os.path.basename(current_save_path)}"
                                            )

                                    if download_attempt_success:
                                        success = True
                                        prev_prompt_text = prompt_text
                                        prev_idx = idx
                                        consecutive_failures = 0
                                        write_runtime_telemetry(
                                            subfolder,
                                            current_run,
                                            total_storyboard_frames,
                                            image_name,
                                        )
                                        manifest.record_rendered(idx)
                                        manifest.save()
                                        break

                                except PlaywrightTimeoutError:
                                    print("  ⚠️ Playwright Timeout Error.")
                                except Exception as e:
                                    print(f"  ⚠️ Error: {e}")

                                if not success and attempt < 3:
                                    print("  🔄 Clearing UI error state before retry...")
                                    flow_page.wait_for_timeout(2000)
                                    try:
                                        flow_page.goto(
                                            active_project_url, wait_until="domcontentloaded", timeout=15000
                                        )
                                    except Exception:
                                        pass
                                    # Wait for SPA hydration before next attempt
                                    dismiss_blocking_flow_modals(flow_page)
                                    wait_for_flow_input_box(flow_page, timeout_seconds=15.0)
                                    flow_page.wait_for_timeout(1000)

                            if not success:
                                if accounts_enabled:
                                    print(
                                        "\n[FAILOVER ALERT] Flow rendering failed 3 times. Rotating account..."
                                    )
                                    safe_failover_teardown(browser, context)
                                    failover_triggered = True
                                    break
                                else:
                                    print(f"❌ Frame {idx} failed completely. Skipping.")
                        except Exception as e:
                            print(f"[RECOVERY] Framework error: {e}")
                            consecutive_failures += 1
                            if (
                                not accounts_enabled
                                and consecutive_failures >= max_retries_no_switch
                            ):
                                print(
                                    f"[FATAL ERROR] Reached maximum retries ({max_retries_no_switch}) with account switching disabled. Exiting."
                                )
                                sys.exit(1)
                            failover_triggered = True

                        if failover_triggered:
                            print(
                                "\n[SYSTEM] Profile rotated. Restarting browser session for current subfolder...\n"
                            )
                            time.sleep(3)
                            break

                if not failover_triggered:
                    print("\n✅ All topics processed successfully. Exiting.")
                    break

        except KeyboardInterrupt:
            print("\n[MAIN] Interrupted by user. Shutting down gracefully...")
            sys.exit(130)
        except Exception as e:
            print(f"[MAIN] Fatal orchestration error: {e}")
            consecutive_failures += 1
            if not accounts_enabled and consecutive_failures >= max_retries_no_switch:
                print(
                    f"[FATAL ERROR] Reached maximum retries ({max_retries_no_switch}) without account switching. Terminating."
                )
                sys.exit(1)
            time.sleep(5)
            continue
        finally:
            if browser_handle is not None:
                try:
                    browser_handle.close()
                except Exception:
                    pass
                browser_handle = None


if __name__ == "__main__":
    main()
