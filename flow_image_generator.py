import base64
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from pipeline_manifest import PhaseStatus, PipelineManifest, compute_script_hash
from prompt_planner import build_compact_preamble, plan_all_chunks
from roadmap_orchestrator import generate_master_roadmap, load_or_migrate_roadmap
from utils import (
    get_config_value,
    kill_cdp_chrome,
    launch_browser_with_profile,
    rotate_profile_index,
)
from validator import (
    enforce_arabic_in_prompt,
    flatten_visual_prompt_to_diffusion_text,
    verify_pipeline_integrity,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


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
                    # else: keep polling until the 3s window closes
                else:
                    first_pass = None
            else:
                first_pass = None
        except Exception:
            first_pass = None  # Tier 1 probe: SPA still booting
        time.sleep(1)
    log("  ⚠️ Flow SPA did not become ready in time.")
    return False


def capture_debug_state(page: Any, step_name: str, subfolder: str | None = None) -> None:
    """Takes a debug screenshot and logs the current URL/title when a step stalls."""
    try:
        debug_dir = os.path.join(subfolder or ".", "debug_snapshots")
        os.makedirs(debug_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(debug_dir, f"{step_name}_{ts}.png")

        page.screenshot(path=screenshot_path)
        log(f"  📸 [DEBUG SNAPSHOT] Saved visual state to: {screenshot_path}")
        log(f"  🌐 [DEBUG URL]: {page.url}")
        try:
            log(f"  🏷️ [DEBUG TITLE]: {page.title()}")
        except Exception:
            pass
    except Exception as e:
        log(f"  ⚠️ Could not take debug snapshot: {e}")


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
    THINKING_INDICATORS = "mat-progress-spinner, .thinking-indicator, [aria-label*='Thinking' i]"


class FlowSelectors:
    URL = "https://labs.google/fx/tools/flow"
    PROMPT_INPUTS = (
        "textarea[placeholder*='What do you want' i]",
        "input[placeholder*='What do you want' i]",
        "div[contenteditable='true']",
        "textarea",
        "[role='textbox']",
    )
    # Comma-joined string: Playwright locator() accepts one string, NOT a tuple
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


# ==========================================
# ATOMIC IMAGE VALIDATION & PIXEL INTEGRITY
# ==========================================
def validate_image_file(file_path: str, min_size_kb: int = 20) -> bool:
    """
    Validates that an image exists on disk, exceeds the minimum byte threshold,
    and contains valid image headers (PNG, JPEG, or WebP) without corruption.
    """
    if not os.path.exists(file_path):
        return False

    file_size = os.path.getsize(file_path)
    if file_size < (min_size_kb * 1024):
        return False

    # Fast Pillow integrity check (verifies file is not truncated/corrupted)
    try:
        from PIL import Image

        with Image.open(file_path) as img:
            w, h = img.size  # Read dimensions BEFORE verify() (verify() consumes the stream)
            img.verify()
            return w > 100 and h > 100
    except Exception:
        pass  # Tier 2 file op: corrupt/truncated file returns False, falls to header check

    # Fallback header check (PNG magic bytes: \x89PNG\r\n\x1a\n or JPEG: \xff\xd8\xff)
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)
            if header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff"):
                return True
    except Exception:
        return False

    return False


def atomic_screenshot_and_verify(
    locator: Any, final_save_path: str, page: Any, min_size_kb: int = 50
) -> bool:
    """
    Executes a de-hovered screenshot to a temporary file, validates binary integrity,
    and atomically moves it to final_save_path to prevent corrupted partial files.
    """
    os.makedirs(os.path.dirname(os.path.abspath(final_save_path)), exist_ok=True)
    temp_path = final_save_path + ".tmp"
    try:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

        # Move mouse to safe neutral coordinate to clear active CSS :hover styles
        page.mouse.move(100, 15)
        page.evaluate("() => new Promise(requestAnimationFrame)")
        time.sleep(0.35)

        locator.scroll_into_view_if_needed()
        locator.screenshot(path=temp_path, type="png")

        if validate_image_file(temp_path, min_size_kb=min_size_kb):
            os.replace(temp_path, final_save_path)
            return True
        else:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
    except Exception as e:
        print(f"  ⚠️ Atomic screenshot failed: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def extract_high_res_image(
    page: Any, img_locator: Any, save_path: str, min_size_kb: int = 20
) -> bool:
    """
    Tiered full-resolution image extraction that avoids CORS canvas tainting.

    Tier 1: Inline base64 data URL (no network needed).
    Tier 2: Authenticated network stream via page.request.get() (bypasses CORS,
            inherits the browser session's cookies/auth, no canvas involved).
    Tier 2B: Local blob: URL fetched in-page (same-origin, no CORS issue).
    Tier 3: De-hovered atomic Playwright screenshot fallback.
    """
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    temp_path = save_path + ".tmp"
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass

    try:
        src = img_locator.get_attribute("src") or ""
    except Exception:
        src = ""

    # --- TIER 1: Inlined Base64 ---
    if src.startswith("data:image"):
        try:
            base64_data = src.split(",", 1)[1]
            with open(temp_path, "wb") as f:
                f.write(base64.b64decode(base64_data))
            if validate_image_file(temp_path, min_size_kb=min_size_kb):
                os.replace(temp_path, save_path)
                print(f"  ✅ Saved (Inline Base64): {os.path.basename(save_path)}")
                return True
        except Exception as e:
            print(f"  ℹ️ Base64 extraction failed ({e}), falling back to network stream...")

    # --- TIER 2: Local Blob URL (fetchable in browser context without CORS) ---
    # Directive override: prioritize Blob/FileReader over page.request.get to bypass CDN cookie restrictions
    if src.startswith("blob:"):
        try:
            js_blob = """
            async (img) => {
                const response = await fetch(img.src);
                const blob = await response.blob();
                return new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result);
                    reader.readAsDataURL(blob);
                });
            }
            """
            data_url = img_locator.evaluate(js_blob)
            if data_url and isinstance(data_url, str) and "," in data_url:
                base64_data = data_url.split(",", 1)[1]
                with open(temp_path, "wb") as f:
                    f.write(base64.b64decode(base64_data))
                if validate_image_file(temp_path, min_size_kb=min_size_kb):
                    os.replace(temp_path, save_path)
                    print(f"  ✅ Saved (Blob Fetch): {os.path.basename(save_path)}")
                    return True
        except Exception as e:
            print(f"  ℹ️ Blob fetch extraction failed ({e}), falling back to screenshot...")

        # --- TIER 2B: In-Page Canvas / Fetch Extraction (bypasses CDN cookie restrictions) ---
    # For http/https images, prefer in-page fetch + FileReader (inherits browser auth) over page.request.get
    if src.startswith(("http://", "https://", "/")):
        try:
            js_fetch = """
            async (img) => {
                try {
                    const response = await fetch(img.src, {credentials: 'include'});
                    if (!response.ok) throw new Error('fetch not ok');
                    const blob = await response.blob();
                    return await new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onloadend = () => resolve(reader.result);
                        reader.onerror = () => resolve(null);
                        reader.readAsDataURL(blob);
                    });
                } catch (e) {
                    try {
                        const canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth || img.width;
                        canvas.height = img.naturalHeight || img.height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0);
                        return canvas.toDataURL('image/png');
                    } catch (e2) {
                        return null;
                    }
                }
            }
            """
            data_url = img_locator.evaluate(js_fetch)
            if data_url and isinstance(data_url, str) and "," in data_url:
                base64_data = data_url.split(",", 1)[1]
                with open(temp_path, "wb") as f:
                    f.write(base64.b64decode(base64_data))
                if validate_image_file(temp_path, min_size_kb=min_size_kb):
                    os.replace(temp_path, save_path)
                    print(f"  Saved (In-Page Fetch/Canvas): {os.path.basename(save_path)}")
                    return True
        except Exception as e:
            print(f"  In-page fetch/canvas failed ({e}), falling back to network stream...")

        # --- TIER 2C: Network Stream via Playwright (fallback, may lack CDN cookies) ---
        try:
            absolute_src = urljoin(page.url, src)
            response = page.request.get(absolute_src)
            if response.ok:
                with open(temp_path, "wb") as f:
                    f.write(response.body())
                if validate_image_file(temp_path, min_size_kb=min_size_kb):
                    os.replace(temp_path, save_path)
                    print(f"  Saved (Network Stream): {os.path.basename(save_path)}")
                    return True
        except Exception as e:
            print(f"  Network stream extraction failed ({e}), falling back to screenshot...")

    # --- TIER 3: Atomic De-Hovered Screenshot Fallback ---
    return atomic_screenshot_and_verify(img_locator, save_path, page, min_size_kb=min_size_kb)


def safe_failover_teardown(browser: Any, context: Any) -> None:
    """
    Gracefully detaches Playwright CDP handles BEFORE killing the browser PID,
    preventing TargetClosedError / orphaned port bindings on 9222 during failover.
    """
    print("  🔌 Detaching CDP handles gracefully...")
    try:
        if context:
            context.close()
    except Exception as e:
        print(f"  ⚠️ CDP context close failed (non-fatal): {e}")

    try:
        if browser:
            browser.close()
    except Exception as e:
        print(f"  ⚠️ CDP browser close failed (non-fatal): {e}")

    time.sleep(1.0)
    # Now safe to kill process at OS level
    rotate_profile_index()
    kill_cdp_chrome()
    time.sleep(2.0)


# ==========================================
# NON-BLOCKING RUNTIME TELEMETRY
# ==========================================
def write_runtime_telemetry(
    subfolder: str, frame_num: int, total_frames: int, image_name: str
) -> None:
    """
    Writes non-blocking progress telemetry to disk.
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


# ==========================================
# ASSET PRESETS (CHARACTERS & SCENES)
# ==========================================
FLOW_ASSET_PRESETS = {
    "CHARACTERS": {
        "HOST": {
            "name": "CHARACTER_HOST_MAIN",
            "info": (
                "Character Visual DNA: Ahmed El-Ghandour (Al-Daheeh). "
                "Anatomy: Voluminous dark curly afro hair, thin round wire-rim glasses, animated hazel eyes, expressive comedic eyebrows, light stubble. "
                "Outfit: Matte charcoal-grey pullover hoodie (#2B2D42), black relaxed joggers, clean white minimal sneakers. "
                "Rendering Invariant: 2D graphic vector animation style, uniform 3px black contour outlines, flat 2-step cel-shading."
            ),
            "portrait_prompt": (
                "Studio character visual development bust portrait of Ahmed El-Ghandour (Al-Daheeh) in a 2D graphic vector animation explainer style. "
                "Chest-up framing with 15% upper headroom: thin circular wire-rim glasses, wide energetic comic eyes, wild voluminous curly black afro hair, expressive eyebrows, light comedic stubble. "
                "Wearing an unbranded matte charcoal-grey pullover hoodie (#2B2D42). "
                "Rendering: Crisp 3px black vector contour outlines, vibrant flat 2-step cel-shading, high-contrast studio illumination, pure solid seamless white background (#FFFFFF). "
                "Visual rule: Clean 2D animation art only. Zero 3D CGI, zero photorealism, zero gradients, zero shadows on backdrop."
            ),
            "body_prompt": (
                "Professional animation character turnaround model sheet. "
                "Horizontal 3-view orthographic lineup: full-body front view, 3/4 dynamic perspective view, and side profile view. "
                "Character: Ahmed El-Ghandour (Al-Daheeh) in 2D graphic vector animated style. "
                "Biometrics & Wardrobe: Circular wireframe glasses, voluminous dark curly afro hair, matte charcoal-grey pullover hoodie (#2B2D42), relaxed black joggers, minimal white canvas sneakers. "
                "Technical constraints: Aligned eye-lines and identical proportions across all 3 views, crisp 3px black vector contour lines, flat 2-step cel-shading, pure solid seamless white background (#FFFFFF). "
                "Visual rule: Studio model turnaround sheet only. Zero 3D render, zero photorealism, zero floor shadows, zero background props."
            ),
        },
        "GOVERNMENT_CLERK": {
            "name": "CHARACTER_CLERK_BUREAUCRAT",
            "info": (
                "Character Visual DNA: The Science Bureaucrat. "
                "Anatomy: Slouching posture, receding messy dark hair, oversized thick black square glasses, bored droopy eyes. "
                "Outfit: Oversized vintage 1980s beige suit jacket (#D4C5A9), wrinkled white collared shirt, crooked striped tie, laminated chest ID badge. "
                "Rendering Invariant: 2D graphic vector animation style, crisp 3px black linework, flat cel-shading."
            ),
            "portrait_prompt": (
                "Studio character visual development bust portrait of the Science Bureaucrat in a 2D graphic vector animation style. "
                "Chest-up framing with 15% upper headroom: exhausted deadpan expression, bored droopy eyes, oversized thick black-rimmed square reading glasses, receding messy dark hair strands. "
                "Wearing an oversized vintage beige suit jacket (#D4C5A9), wrinkled white collared shirt, crooked striped tie, and laminated government chest ID badge. "
                "Rendering: Uniform 3px black vector contour linework, vibrant flat 2-step cel-shading, pure solid seamless white background (#FFFFFF). "
                "Visual rule: Clean 2D graphic vector art only. Zero 3D render, zero realistic skin textures, zero background shadows."
            ),
            "body_prompt": (
                "Professional animation character turnaround model sheet. "
                "Horizontal 3-view orthographic lineup: full-body front view, 3/4 dynamic perspective view, and side profile view. "
                "Character: The Science Bureaucrat (Egyptian government clerk) in 2D graphic vector animated style. "
                "Biometrics & Wardrobe: Slouching tired posture, receding dark hair, oversized thick black square glasses, loose crooked striped tie, baggy vintage 1980s beige suit (#D4C5A9), brown dress shoes, laminated chest ID card. "
                "Technical constraints: Aligned character height and scale across all 3 views, crisp 3px black vector linework, flat 2-step cel-shading, pure solid white background (#FFFFFF). "
                "Visual rule: Clean 2D production model sheet. Zero 3D CGI, zero realistic textures, zero background noise."
            ),
        },
        "SKEPTIC": {
            "name": "CHARACTER_SKEPTIC_ABO_HMEED",
            "info": (
                "Character Visual DNA: Abo Hmeed (The Everyday Skeptic). "
                "Anatomy: Short wavy dark hair, thick questioning eyebrows, animated comedic facial expression. "
                "Outfit: Casual navy zip jacket (#1D3557) over heather-grey crewneck t-shirt, relaxed dark jeans. "
                "Rendering Invariant: 2D graphic vector animation style, sharp 3px black outlines, vibrant flat cel-shading."
            ),
            "portrait_prompt": (
                "Studio character visual development bust portrait of Abo Hmeed (The Skeptic) in a 2D graphic vector animation style. "
                "Chest-up framing with 15% upper headroom: animated bewildered expression, one raised questioning eyebrow, direct engaged gaze, short wavy dark hair. "
                "Wearing a casual navy zip jacket (#1D3557) over a clean heather-grey crewneck t-shirt. "
                "Rendering: Sharp 3px black vector contour outlines, vibrant saturated 2-step cel-shading, pure solid seamless white background (#FFFFFF). "
                "Visual rule: Clean 2D animation art only. Zero 3D CGI, zero photorealism, zero backdrop shadows."
            ),
            "body_prompt": (
                "Professional animation character turnaround model sheet. "
                "Horizontal 3-view orthographic lineup: full-body front view, 3/4 dynamic perspective view, and side profile view. "
                "Character: Abo Hmeed (The Skeptic) in 2D graphic vector animated style. "
                "Biometrics & Wardrobe: Animated questioning expression, thick expressive eyebrows, short wavy dark hair, navy blue casual zip jacket over a heather-grey t-shirt, relaxed dark denim jeans, casual slip-on shoes. "
                "Technical constraints: Aligned eye-lines and uniform proportions across all 3 views, crisp 3px black vector contours, flat vibrant cel-shading, pure solid seamless white background (#FFFFFF). "
                "Visual rule: Studio turnaround lineup only. Zero 3D modeling, zero realistic skin, zero floor shadow."
            ),
        },
    },
    "SCENES": {
        "AHWA_STUDIO": {
            "name": "SCENE_AHWA_STUDIO_ENV",
            "scene_prompt": (
                "2D animation layout background plate of a cozy Cairo studio. "
                "Wooden desk, stacked encyclopedias, retro CRT monitor, Egyptian glass teacup with mint, warm 3200K tungsten lighting. "
                "Crisp 3px black vector outlines, flat cel-shading, open central staging area, 16:9 widescreen. "
                "Visual rule: Empty background plate only. Zero characters, zero 3D CGI."
            ),
        },
        "ARCHIVAL_DOSSIER": {
            "name": "SCENE_ARCHIVAL_DOSSIER_ENV",
            "scene_prompt": (
                "Mixed-media scientific evidence scrapbook dossier background plate. "
                "Scenography: Warm parchment paper background (#F4EBD9) with faint watermark anatomical skeleton sketches and handwritten notes. "
                "Staging props: Layered manila folder tabs, transparent plastic protector sleeves, metal paperclips, brass binder clips, and Polaroid photo card frames. "
                "Lighting & Style: High-contrast documentary editorial layout, crisp graphic paper shadows, top-down flat-lay perspective, 16:9 widescreen. "
                "Visual rule: Archival flat-lay dossier plate only. Zero human characters, zero 3D CGI."
            ),
        },
        "COMPARATIVE_DIAGRAM_DESK": {
            "name": "SCENE_COMPARATIVE_DIAGRAM_ENV",
            "scene_prompt": (
                "Scientific anatomical casefile clipboard layout plate. "
                "Scenography: Cream paper board secured by a heavy brass bulldog clip at the top, clear plastic document sleeve, soft cream textured backdrop with Da Vinci anatomical sketch watermarks. "
                "Center staging: Clean flat 2D vector comparison chart layout, red dashed indicator lines, clean white placard labels for Arabic typography. "
                "Lighting & Style: Clean scientific editorial aesthetic, flat cel-shaded elements, 16:9 widescreen framing. "
                "Visual rule: Anatomical chart layout plate only. Zero full human figures, zero clutter."
            ),
        },
        "RETRO_BLUEPRINT": {
            "name": "SCENE_RETRO_BLUEPRINT_ENV",
            "scene_prompt": (
                "2D animation layout background plate of a high-tech retro scientific blueprint canvas. "
                "Midnight navy background (#0A1128), glowing cyan (#00F0FF) vector HUD schematics, coordinate grid lines, mathematical formulas. "
                "High-contrast vector illumination, sharp clean linework, 16:9 widescreen. "
                "Visual rule: Technical blueprint background only. Zero human characters."
            ),
        },
        "HISTORICAL_MUSEUM": {
            "name": "SCENE_HISTORICAL_MUSEUM_ENV",
            "scene_prompt": (
                "2D animation layout background plate of a grand Baroque museum gallery. "
                "Deep crimson damask wallpaper (#540B0E), carved gold gilded picture frames, parquet floor, top-down spotlighting. "
                "Rich 2D cel-shaded animation art, sharp black vector contours, 16:9 widescreen. "
                "Visual rule: Museum gallery background plate only. Zero characters, zero 3D CGI."
            ),
        },
        "ISOLATED_WHITE": {
            "name": "SCENE_ISOLATED_WHITE_ENV",
            "scene_prompt": (
                "2D animation layout minimalist clean studio cyclorama background plate. "
                "Pure solid seamless white canvas (#FFFFFF), high-key balanced studio lighting, zero clutter. "
                "Visual rule: Empty solid white background only. Zero characters, zero props, zero gradients."
            ),
        },
    },
}


# ==========================================
# HELPER FUNCTIONS
# ==========================================
def wait_for_flow_generation_handshake(page: Any, timeout_seconds: int = 180) -> bool:
    """
    2-Phase Handshake:
    Phase 1: Debounce wait (up to 5s) for progressbar/spinner/percentage to MOUNT in DOM.
    Phase 2: Polling wait for all indicators to UNMOUNT and DOM to settle.
    Prevents False-Green race where the DOM is checked before the spinner mounts.
    """
    # Phase 1: Wait for generation to start (debounce so Phase 2 can't false-green)
    start_mount = time.time()
    while time.time() - start_mount < 5.0:
        try:
            if page.locator(FlowSelectors.PROGRESS_INDICATORS).first.is_visible():
                break
            if page.get_by_text(re.compile(r"\d+%")).count() > 0:
                break
        except Exception:
            pass  # Tier 1 probe: optional DOM element not present yet
        time.sleep(0.3)

    # Phase 2: Wait until generation finishes (indicators disappear)
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
            pass  # Tier 1 probe: transient DOM state

        if not is_busy:
            # Settle buffer: ensure image elements finish rendering
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


def summon_asset_in_prompt(page: Any, asset_name: str, category: str = "Characters") -> bool:
    """
    DOM Helper: Focuses the prompt bar, clicks '+', searches the unique character name,
    selects the character card, and clicks 'Add to Prompt'.
    """
    try:
        print(f"  🏷️ Summoning asset '@{asset_name}' into prompt...")

        # 1. Focus the bottom prompt input bar first to activate toolbar buttons
        prompt_box = page.locator(
            "div[contenteditable='true'], textarea[placeholder*='What do you want' i], textarea, input"
        ).last
        if prompt_box.is_visible():
            prompt_box.scroll_into_view_if_needed()
            prompt_box.click(force=True)
            time.sleep(0.8)

        # 2. Click the '+' button directly to the left of 'Agent'
        modal_opened = False
        for _attempt in range(1, 4):
            # Check if modal is already open
            search_box = page.locator(
                "input[placeholder*='Search assets' i], input[placeholder*='Search' i]"
            ).first
            if search_box.is_visible():
                modal_opened = True
                break

            plus_btn = None
            try:
                agent_btn = page.locator("button:has-text('Agent')").first
                if agent_btn.is_visible():
                    cand = agent_btn.locator("xpath=preceding-sibling::button").last
                    if cand.is_visible():
                        plus_btn = cand
            except Exception:
                pass

            if not plus_btn or not plus_btn.is_visible():
                plus_candidates = page.locator(
                    "button:has(svg path[d*='M19 13']), button:has(svg path[d*='M12 5']), button:has-text('+')"
                ).all()
                for b in plus_candidates:
                    if b.is_visible():
                        plus_btn = b
                        break

            if plus_btn:
                plus_btn.scroll_into_view_if_needed()
                plus_btn.click(force=True)
                time.sleep(1.5)

            try:
                page.wait_for_selector(
                    "input[placeholder*='Search assets' i], input[placeholder*='Search' i]",
                    timeout=3000,
                )
                modal_opened = True
                break
            except Exception:
                pass

        if not modal_opened:
            print("  ⚠️ Could not open asset drawer modal.")
            return False

        # 3. Type unique asset name into 'Search assets' input
        search_input = page.locator(
            "input[placeholder*='Search assets' i], input[placeholder*='Search' i], input[type='search']"
        ).first
        if search_input.is_visible():
            search_input.click(force=True)
            page.keyboard.press("Control+a")
            page.keyboard.press("Backspace")
            search_input.fill(asset_name)
            time.sleep(1.5)
        else:
            print("  ⚠️ Search assets input box not found.")
            page.keyboard.press("Escape")
            return False

        # 4. Select the matching Character result card
        char_card = (
            page.locator("div[role='listitem'], div[role='option'], div:has(> img)")
            .filter(has_text=re.compile(rf"{re.escape(asset_name)}|Character", re.IGNORECASE))
            .first
        )
        if not char_card.is_visible():
            char_card = page.locator("div:has(> img)").first

        if char_card.is_visible():
            char_card.scroll_into_view_if_needed()
            char_card.click(force=True)
            time.sleep(1)
        else:
            print(f"  ⚠️ Character card '{asset_name}' not found in search results.")
            page.keyboard.press("Escape")
            return False

        # 5. Click 'Add to Prompt' button
        add_btn = page.locator(
            "button:has-text('Add to Prompt'), button:has-text('Add to prompt'), button:has-text('إضافة إلى')"
        ).first
        if add_btn.is_visible():
            add_btn.scroll_into_view_if_needed()
            add_btn.click(force=True)
            time.sleep(1.5)
            print(f"  ➕ Successfully added '@{asset_name}' asset chip to prompt!")
            return True
        else:
            print("  ✖ 'Add to Prompt' button not found in asset dialog.")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"  ⚠️ Error summoning asset '{asset_name}': {e}")
        page.keyboard.press("Escape")
        return False


def get_profile_assets_manifest_path(subfolder: str, profile_index: str) -> str:
    """Returns the persistent asset manifest path scoped to the active topic subfolder and browser profile."""
    return os.path.join(subfolder, f"flow_assets_profile_{profile_index}.json")


def is_profile_assets_initialized(subfolder: str, profile_index: str) -> bool:
    manifest_path = get_profile_assets_manifest_path(subfolder, profile_index)
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("assets_initialized", False) is True
        except Exception:
            return False
    return False


def mark_profile_assets_initialized(subfolder: str, profile_index: str, project_url: str) -> None:
    os.makedirs(subfolder, exist_ok=True)
    manifest_path = get_profile_assets_manifest_path(subfolder, profile_index)
    payload = {
        "assets_initialized": True,
        "profile_index": profile_index,
        "project_url": project_url,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        # Atomic commit prevents a half-written memoization flag from being
        # misread as initialized on the next resume.
        tmp_path = manifest_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, manifest_path)
    except Exception as e:
        print(f"  ⚠️ Warning saving asset manifest: {e}")


def wait_for_prompt_format_completion(
    page: Any, input_locator: Any, timeout_seconds: int = 12
) -> bool:
    """
    Waits for Google Flow's AI prompt format / rewrite operation to complete
    by detecting loading spinners and ensuring the input text has stabilized.
    """
    start_time = time.time()
    time.sleep(1.0)  # Initial buffer for spinner to mount

    while time.time() - start_time < timeout_seconds:
        is_formatting = False
        try:
            # Check for active spinners or disabled buttons in prompt bar
            if (
                page.locator(
                    ".animate-spin, mat-progress-spinner, [aria-label*='Formatting' i]"
                ).count()
                > 0
            ):
                is_formatting = True

            # Check if format button itself has disabled/loading state
            format_btn = page.locator(
                "button:has-text('Format'), button[aria-label*='Format' i]"
            ).first
            if format_btn.is_visible():
                is_btn_disabled = format_btn.evaluate(
                    "el => el.disabled || el.getAttribute('aria-disabled') === 'true'"
                )
                if is_btn_disabled:
                    is_formatting = True
        except Exception:
            pass  # Tier 1 probe: optional Format button not present

        current_text = input_locator.evaluate("el => el.value || el.innerText || ''").strip()

        # If not formatting and text is non-empty and stabilized
        if not is_formatting and len(current_text) > 10:
            time.sleep(0.5)
            return True

        time.sleep(0.8)

    log("  ⚠️ Format operation timed out. Capturing debug state...")
    capture_debug_state(page, "format_timeout")
    return False


def setup_flow_characters_and_scenes(page: Any, subfolder: str, profile_index: str = "1") -> None:
    """
    Pre-flight Routine: Checks and creates registered Characters and Scenes
    in Google Flow before the main rendering loop begins.
    Performs live DOM verification and memoizes per topic subfolder.
    """
    master_enabled = get_config_value("FLOW_ENABLE_ASSET_PRESETS", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    enable_characters = get_config_value(
        "FLOW_ENABLE_CHARACTER_PRESETS", "true"
    ).strip().lower() in (
        "true",
        "1",
        "yes",
    )
    enable_scenes = get_config_value("FLOW_ENABLE_SCENE_PRESETS", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )

    # Exit early if master switch is off OR both sub-categories are disabled
    if not master_enabled or (not enable_characters and not enable_scenes):
        return

    # Check if assets for this topic and profile were already completed
    if is_profile_assets_initialized(subfolder, profile_index):
        print(
            f"  ⚡ [PRE-FLIGHT] Presets for Profile {profile_index} already verified in {os.path.basename(subfolder)}. Skipping creation."
        )
        return

    # Robust boolean parser for FLOW_FORMAT_CHARACTER_PROMPT (defaults to False)
    raw_format_cfg = (
        str(get_config_value("FLOW_FORMAT_CHARACTER_PROMPT", "false"))
        .strip()
        .strip('"')
        .strip("'")
        .lower()
    )
    format_prompt_enabled = raw_format_cfg in ("true", "1", "yes")

    print("\n[PRE-FLIGHT] Checking Character & Scene Presets in Google Flow...")
    project_url = page.url
    all_presets_successful = True

    # Ensure the SPA finished booting before interacting with it
    wait_for_flow_app_ready(page, timeout_seconds=60)

    # -------------------------------------------------------------
    # 1. CHARACTER CREATION (PORTRAIT -> RENAME -> INFO -> CREATE BODY -> DONE)
    # -------------------------------------------------------------
    try:
        char_presets = FLOW_ASSET_PRESETS.get("CHARACTERS", {}) if enable_characters else {}
        for _char_key, char_info in char_presets.items():
            char_name = char_info["name"]

            # Step 1: Ensure we are STRICTLY on the Characters tab. The sidebar
            # click can be swallowed during hydration, leaving us on 'All Media'
            # where the workspace prompt bar ('What do you want to create?')
            # would swallow the portrait prompt and render it as a regular image.
            log(f"\n[PRE-FLIGHT] Checking Character Preset: '{char_name}'...")
            nav_to_chars_success = False
            for _nav_attempt in range(1, 4):
                chars_btn = page.locator(
                    "button:has-text('Characters'), a:has-text('Characters'), [role='tab']:has-text('Characters')"
                ).first
                if chars_btn.is_visible():
                    chars_btn.click(force=True)
                    time.sleep(2)

                # Verify the Characters view is active (URL or dedicated DOM)
                if (
                    "/characters" in page.url
                    or page.locator(
                        "button:has-text('New character'), div:has-text('New Character'), [placeholder*='Describe your character' i]"
                    ).first.is_visible()
                ):
                    nav_to_chars_success = True
                    break
                time.sleep(1)

            if not nav_to_chars_success:
                capture_debug_state(page, f"char_nav_fail_{char_name}", subfolder)
                raise Exception(
                    f"Could not navigate to Characters tab for '{char_name}'. Current URL: {page.url}"
                )

            # Step 2: Check if unique character name already exists
            existing_char = (
                page.locator("[role='listitem'], [role='article'], .character-card, div:has(> img)")
                .filter(has_text=re.compile(rf"\b{re.escape(char_name)}\b", re.IGNORECASE))
                .first
            )
            if existing_char.is_visible():
                log(f"  ✅ Character '{char_name}' already exists. Skipping creation.")
                continue

            log(f"  🚀 Creating Character Preset: '{char_name}'...")

            # Step 3: Click '+ New Character' card and GUARANTEE transition to the
            # 'Describe your character' view. Never type into the workspace
            # prompt bar ('What do you want to create?' / Agent pill).
            char_input = None
            for card_attempt in range(1, 4):
                # Look if we are already on the 'Describe your character' screen
                cand_input = page.locator(
                    "textarea[placeholder*='Describe your character' i], input[placeholder*='Describe your character' i]"
                ).first
                if not cand_input.is_visible():
                    # Fallback: contenteditable whose visible text is the
                    # character prompt label (NOT the workspace bar).
                    for ce in page.locator("div[contenteditable='true']").all():
                        try:
                            if (
                                ce.is_visible()
                                and "describe your character" in (ce.inner_text() or "").lower()
                            ):
                                cand_input = ce
                                break
                        except Exception:
                            continue  # Tier 1 probe: element detached mid-scan

                if cand_input.is_visible():
                    char_input = cand_input
                    log("  ✅ Already on 'Describe your character' view.")
                    break

                # Otherwise, locate and click the '+ New Character' card
                log(f"  🗂️ Clicking 'New Character' card (Attempt {card_attempt}/3)...")
                new_char_label = page.get_by_text(
                    re.compile(r"^(\+?\s*New Character|\+?\s*شخصية جديدة)$", re.I)
                ).first

                if new_char_label.is_visible():
                    try:
                        parent_card = new_char_label.locator(
                            "xpath=ancestor::div[contains(@class, 'card') or position()=1]"
                        ).first
                        parent_card.click(force=True)
                    except Exception:
                        new_char_label.click(force=True)
                else:
                    plus_card = (
                        page.locator("div:has(> svg)")
                        .filter(has_text=re.compile(r"New Character", re.I))
                        .first
                    )
                    if plus_card.is_visible():
                        plus_card.click(force=True)

                time.sleep(2)

                # Verify transition: 'Describe your character' input MUST be visible
                cand_input = page.locator(
                    "textarea[placeholder*='Describe your character' i], input[placeholder*='Describe your character' i]"
                ).first
                if not cand_input.is_visible():
                    for ce in page.locator("div[contenteditable='true']").all():
                        try:
                            if (
                                ce.is_visible()
                                and "describe your character" in (ce.inner_text() or "").lower()
                            ):
                                cand_input = ce
                                break
                        except Exception:
                            continue  # Tier 1 probe: element detached mid-scan

                if cand_input.is_visible():
                    char_input = cand_input
                    log("  ✅ Transitioned to 'Describe your character' view!")
                    break

            if not char_input or not char_input.is_visible():
                capture_debug_state(page, f"char_card_click_fail_{char_name}", subfolder)
                raise Exception(
                    "Failed to open 'Describe your character' screen after clicking New Character card."
                )

            # Step 4: Fill Portrait Prompt strictly in the character box (NO Agent pill)
            log(f"  📝 Filling portrait prompt for '{char_name}'...")
            char_input.scroll_into_view_if_needed()
            char_input.click(force=True)
            time.sleep(0.3)
            char_input.fill(char_info["portrait_prompt"])
            time.sleep(0.8)

            # 1. Apply 'Format' button ONLY if enabled in .env
            if format_prompt_enabled:
                format_btn = page.locator(
                    "button:has-text('Format'), button[aria-label*='Format' i]"
                ).first
                if format_btn.is_visible():
                    print("  ✨ Applying AI prompt formatting to character portrait...")
                    format_btn.click(force=True)
                    wait_for_prompt_format_completion(page, char_input, timeout_seconds=10)

            # 2. Re-focus input box (FIXED: was scene_input)
            char_input.click(force=True)
            time.sleep(0.3)

            # Submit character prompt
            log("  🚀 Submitting Character portrait prompt...")

            # Strategy A: Click submit button. Google Flow uses Material Symbols
            # (<i class="google-symbols">arrow_forward</i>), NOT inline SVGs.
            submit_clicked = False
            submit_selectors = [
                "button:has(i.google-symbols:text-is('arrow_forward'))",
                "button:has-text('arrow_forward')",
                "button:has(svg path[d*='M5'])",
                "button:has(svg path[d*='M2'])",
                "div:has(> textarea) ~ button",
                "button[aria-label*='Submit' i]",
                "button[aria-label*='Create' i]",
                "button[aria-label*='Generate' i]",
                "button:has(svg)",
            ]
            for sel in submit_selectors:
                try:
                    candidates = page.locator(sel).all()
                    for btn in reversed(candidates):
                        if btn.is_visible():
                            btn.click(force=True)
                            submit_clicked = True
                            break
                except Exception:
                    continue  # Tier 1 probe: selector not present in this DOM state
                if submit_clicked:
                    break

            # Strategy B: Keyboard Enter fallback
            page.keyboard.press("Enter")
            page.keyboard.press("Control+Enter")

            # 3. Editor Mount Handshake: after submitting, Flow automatically
            # transitions into the Character Editor (Untitled Character) once
            # the portrait render completes. Do NOT click the sidebar or re-open
            # the gallery — that navigates AWAY from the editor. Just wait for
            # the editor's own DOM ('Done' button or the acts textarea).
            log("  ⏳ Waiting for Character Editor to mount (portrait rendering)...")
            editor_mounted = False
            start_editor = time.time()
            while time.time() - start_editor < 120:
                done_btn = page.locator("button:has-text('Done')").first
                acts_box = page.locator(
                    "textarea[placeholder*='Describe how your character acts' i]"
                ).first
                try:
                    name_field = page.locator(
                        "input[placeholder*='Character Name' i], input[value*='Character Name' i]"
                    ).first
                    if (
                        (
                            re.search(r"/character/[a-zA-Z0-9_-]+", page.url)
                            and "/characters" not in page.url
                        )
                        or done_btn.is_visible()
                        or acts_box.is_visible()
                        or name_field.is_visible()
                    ):
                        editor_mounted = True
                        log("  ✅ Character Editor mounted.")
                        break
                except Exception:
                    pass  # Tier 1 probe: DOM mid-transition
                time.sleep(1)

            if not editor_mounted:
                capture_debug_state(page, f"char_editor_fail_{char_name}", subfolder)
                raise Exception(
                    f"Character Editor did not mount for '{char_name}'. Current URL: {page.url}"
                )

            time.sleep(2)

            # -------------------------------------------------------------
            # Step B: Rename Character & Fill Character Info (while portrait renders)
            # -------------------------------------------------------------
            print(f"  🏷️ Setting character name to '{char_name}'...")
            try:
                name_input = page.locator(
                    "input[placeholder*='Character Name' i], input[value*='Character Name' i]"
                ).first
                if not name_input.is_visible():
                    pencil_btn = (
                        page.locator("button:has(svg)")
                        .filter(has=page.locator("path[d*='M3 17'], path[d*='M14.06']"))
                        .first
                    )
                    if pencil_btn.is_visible():
                        pencil_btn.click(force=True)
                        time.sleep(0.5)
                    name_input = (
                        page.locator("h1, h2, div, span")
                        .filter(has_text=re.compile(r"^Character Name", re.I))
                        .first
                    )

                # Fallback: click the 'Untitled Character' title to reveal the input
                if not name_input.is_visible():
                    untitled_el = (
                        page.locator("h1, h2, div, span")
                        .filter(has_text=re.compile(r"Untitled Character", re.I))
                        .first
                    )
                    if untitled_el.is_visible():
                        untitled_el.click(force=True)
                        time.sleep(0.5)
                    name_input = page.locator(
                        "input[value*='Untitled' i], input[placeholder*='Character' i], h1[contenteditable='true']"
                    ).first

                if name_input.is_visible():
                    name_input.click(force=True)
                    name_input.fill(char_name)
                    page.keyboard.press("Enter")
                    name_input.evaluate("el => el.blur()")
                    time.sleep(0.8)
                    print(f"  ✅ Character name set to '{char_name}'.")
            except Exception as rename_err:
                print(f"  ⚠️ Warning setting character name: {rename_err}")

            # Fill Character Info (optional) textarea
            try:
                info_box = page.locator(
                    "textarea[placeholder*='Describe how your character acts' i], textarea[placeholder*='Character Info' i]"
                ).first
                if info_box.is_visible():
                    print("  📝 Filling Character Info (personality & acting context)...")
                    info_box.click(force=True)
                    time.sleep(0.3)
                    page.keyboard.press("Control+a")
                    page.keyboard.press("Backspace")
                    info_box.fill(char_info.get("info", char_info["portrait_prompt"]))
                    time.sleep(1)
                    print("  ✅ Character Info filled successfully.")
            except Exception as info_err:
                print(f"  ⚠️ Warning setting character info: {info_err}")

            # -------------------------------------------------------------
            # Step C: Wait for Portrait Image to Fully Render and Unlock 'Create Body'
            # -------------------------------------------------------------
            print(
                "  ⏳ Generating Character Portrait (Waiting for image render and 'Create Body' unlock)..."
            )
            start_portrait_wait = time.time()

            while time.time() - start_portrait_wait < 60:
                # 1. Check if 'Create Body' button is visible and UNLOCKED (enabled)
                create_body_btn = page.locator("button:has-text('Create Body')").first
                is_btn_unlocked = False
                if create_body_btn.is_visible():
                    is_disabled = create_body_btn.evaluate(
                        "el => el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled')"
                    )
                    is_btn_unlocked = not is_disabled

                # 2. Check if the center portrait image has loaded (dynamic pixel/naturalWidth stability up to 60s)
                has_rendered_image = False
                try:
                    for img in page.locator("img").all():
                        if not img.is_visible():
                            continue
                        box = img.bounding_box()
                        # Dynamic pixel check: bounding_box width >180 and naturalWidth >180
                        if box and box["width"] > 180 and box["height"] > 180:
                            if img.evaluate(
                                "el => el.complete && el.naturalWidth > 180 && el.naturalHeight > 100 && el.naturalWidth < 5000"
                            ):
                                has_rendered_image = True
                                break
                        elif img.evaluate("el => el.complete && el.naturalWidth > 180"):
                            # Fallback without bounding box (older DOM)
                            has_rendered_image = True
                            break
                except Exception:
                    has_rendered_image = False

                # 3. Check if bottom submit button spinner is finished
                is_spinner_active = (
                    page.locator("button .animate-spin, svg.animate-spin").count() > 0
                )

                if is_btn_unlocked and has_rendered_image and not is_spinner_active:
                    print("  ✅ Character Portrait 100% rendered and 'Create Body' is unlocked!")
                    break

                time.sleep(2)

            time.sleep(2)

            # -------------------------------------------------------------
            # Step D: Click 'Create Body' Button & Generate Body Triptych
            # -------------------------------------------------------------
            create_body_btn = page.locator("button:has-text('Create Body')").first
            if create_body_btn.is_visible():
                print("  🧍 Clicking 'Create Body' button...")
                create_body_btn.scroll_into_view_if_needed()
                create_body_btn.click(force=True)
                time.sleep(3)

                # Locate the floating 'Describe body and outfit' input (rendered as
                # div[contenteditable='true'] / custom textbox, not always a
                # placeholder-bearing textarea).
                body_input = None
                input_candidates = [
                    page.locator("div[contenteditable='true']").last,
                    page.get_by_placeholder(re.compile(r"(body|outfit|صف)", re.IGNORECASE)).first,
                    page.locator(
                        "textarea[placeholder*='body' i], textarea[placeholder*='outfit' i]"
                    ).first,
                    page.locator("[role='textbox']").last,
                    page.locator("textarea").last,
                ]

                for cand in input_candidates:
                    try:
                        if cand.is_visible():
                            body_input = cand
                            break
                    except Exception:
                        continue  # Tier 1 probe: candidate detached

                if body_input:
                    print("  📝 Inserting Body Triptych prompt into popup bar...")
                    body_input.scroll_into_view_if_needed()
                    body_input.click(force=True)
                    time.sleep(0.5)

                    # Fill prompt text (fill() for inputs, innerText for contenteditable)
                    try:
                        body_input.fill(char_info["body_prompt"])
                    except Exception:
                        body_input.evaluate(
                            f"el => {{ el.innerText = `{char_info['body_prompt']}`; el.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
                        )
                    time.sleep(1)

                    # 1. Apply Format to Body prompt if enabled in .env
                    if format_prompt_enabled:
                        body_dialog = page.locator(
                            "mat-dialog-container, [role='dialog'], .cdk-overlay-pane"
                        ).last
                        body_format_btn = body_dialog.locator(
                            "button:has-text('Format'), button[aria-label*='Format' i]"
                        ).first
                        if body_format_btn.is_visible():
                            print("  ✨ Applying AI prompt formatting to body triptych...")
                            body_format_btn.click(force=True)
                            wait_for_prompt_format_completion(page, body_input, timeout_seconds=10)

                    # 2. Re-focus popup input and click submit arrow (->)
                    body_input.click(force=True)
                    time.sleep(0.5)

                    body_submitted = False
                    try:
                        model_dd = page.locator(
                            "button:has-text('Nano Banana'), button:has-text('Imagen')"
                        ).last
                        if model_dd.is_visible():
                            arrow_btn = model_dd.locator("xpath=following-sibling::button[1]")
                            if arrow_btn.is_visible():
                                arrow_btn.click(force=True)
                                body_submitted = True
                    except Exception:
                        pass

                    if not body_submitted:
                        try:
                            arrow_btns = page.locator(
                                "button:has(svg path[d*='M5']), button:has(svg path[d*='M2']), button:has(svg)"
                            ).all()
                            if arrow_btns:
                                arrow_btns[-1].click(force=True)
                                body_submitted = True
                        except Exception:
                            pass

                    if not body_submitted:
                        page.keyboard.press("Enter")

                    print("  ⏳ Generating Character Body Triptych (Monitoring DOM render)...")

                    # -------------------------------------------------------------
                    # Strict DOM Verification for 3-View Body Render
                    # -------------------------------------------------------------
                    start_body_wait = time.time()
                    stable_rendered_cycles = 0

                    # Phase 1: Wait up to 15s to confirm generation has initiated
                    while time.time() - start_body_wait < 15:
                        is_loading = False
                        try:
                            if page.locator("[role='progressbar']").is_visible():
                                is_loading = True
                            if (
                                page.locator(
                                    "button .animate-spin, svg.animate-spin, mat-progress-spinner"
                                ).count()
                                > 0
                            ):
                                is_loading = True
                            pct = page.get_by_text(re.compile(r"\d+%"))
                            if pct.count() > 0 and pct.first.is_visible():
                                is_loading = True
                        except Exception:
                            pass

                        if is_loading:
                            break
                        time.sleep(1)

                    # Phase 2: Wait until render finishes AND canvas image is fully visible (dynamic pixel/naturalWidth stability up to 60s)
                    while time.time() - start_body_wait < 60:
                        is_loading = False
                        try:
                            if page.locator("[role='progressbar']").is_visible():
                                is_loading = True
                            if (
                                page.locator(
                                    "button .animate-spin, svg.animate-spin, mat-progress-spinner"
                                ).count()
                                > 0
                            ):
                                is_loading = True
                            pct = page.get_by_text(re.compile(r"\d+%"))
                            if pct.count() > 0 and pct.first.is_visible():
                                is_loading = True
                        except Exception:
                            pass

                        # Check that the main center canvas has a loaded wide triptych image (naturalWidth > 300)
                        has_loaded_triptych = False
                        try:
                            imgs = page.locator("img").all()
                            for img in imgs:
                                if img.is_visible():
                                    box = img.bounding_box()
                                    # Center stage canvas image (x > 250, width > 280)
                                    if box and box["x"] > 250 and box["width"] > 280:
                                        is_complete = img.evaluate(
                                            "el => el.complete && el.naturalWidth > 300 && el.naturalHeight > 100"
                                        )
                                        if is_complete:
                                            has_loaded_triptych = True
                                            break
                        except Exception:
                            pass

                        if not is_loading and has_loaded_triptych:
                            stable_rendered_cycles += 1
                            if (
                                stable_rendered_cycles >= 4
                            ):  # Stable for ~6 seconds (dynamic naturalWidth/bounding_box stability up to 60s)
                                print(
                                    "  ✅ Character Body Triptych 100% rendered and confirmed in DOM!"
                                )
                                break
                        else:
                            stable_rendered_cycles = 0

                        time.sleep(1.5)

                    time.sleep(2)
                else:
                    print("  ⚠️ Could not locate Body prompt popup box.")

            # -------------------------------------------------------------
            # Step E: Click 'Done' to Save Character
            # -------------------------------------------------------------
            done_btn = page.locator(
                "button:has-text('Done'), button:has-text('تم'), button:has-text('حفظ')"
            ).first
            if done_btn.is_visible():
                print("  💾 Clicking 'Done' button to save character preset...")
                done_btn.click(force=True)
                time.sleep(3)

    except Exception as e:
        print(f"  ❌ Character setup encountered an error: {e}")
        all_presets_successful = False

    # -------------------------------------------------------------
    # 2. SCENE CREATION (SCENES TAB -> SUBMIT -> RENDER -> 3-DOTS RENAME)
    # -------------------------------------------------------------
    try:
        scene_presets = FLOW_ASSET_PRESETS.get("SCENES", {}) if enable_scenes else {}

        # Guard: if a character editor page is still open, return to workspace
        if (
            scene_presets
            and re.search(r"/character/[a-zA-Z0-9_-]+", page.url)
            and "/characters" not in page.url
        ):
            log("  🧭 In Character Editor — navigating back to workspace root before scenes...")
            page.goto(
                page.url.split("/character/")[0], wait_until="domcontentloaded", timeout=60000
            )
            time.sleep(3)

        for _scene_key, scene_info in scene_presets.items():
            scene_name = scene_info["name"]

            # Check if unique scene name already exists in project assets (scoped to cards)
            existing_scene = (
                page.locator("[role='listitem'], [role='article'], .scene-card, div:has(> img)")
                .filter(has_text=re.compile(rf"\b{re.escape(scene_name)}\b", re.IGNORECASE))
                .first
            )
            if existing_scene.is_visible():
                print(f"  ✅ Scene '{scene_name}' already exists. Skipping creation.")
                continue

            print(f"\n[PRE-FLIGHT] Creating Scene Preset: '{scene_name}'...")

            # Step A: Click 'Scenes' tab in left sidebar
            scenes_sidebar_btn = page.locator(
                "button:has-text('Scenes'), a:has-text('Scenes'), [aria-label*='Scenes' i]"
            ).first
            if scenes_sidebar_btn.is_visible():
                scenes_sidebar_btn.click(force=True)
                time.sleep(2.5)

            # Record pre-existing image sources on workspace
            pre_scene_srcs = set()
            for loc in page.locator("img").all():
                try:
                    src = loc.get_attribute("src")
                    if src:
                        pre_scene_srcs.add(src)
                except Exception:
                    pass

            # Step B: Enter Scene Prompt in bottom input box (Robust Multi-Selector)
            scene_input = None
            for sel in [
                "textarea[placeholder*='What do you want' i]",
                "input[placeholder*='What do you want' i]",
                "div[contenteditable='true']",
                "textarea",
                "input[type='text']",
                "[role='textbox']",
            ]:
                candidates = page.locator(sel).all()
                for cand in candidates:
                    if cand.is_visible():
                        scene_input = cand
                        break
                if scene_input:
                    break

            if not scene_input:
                try:
                    scene_input = page.get_by_placeholder(
                        re.compile(
                            r"(what do you want|describe|create|صف|أنشئ|اكتب)", re.IGNORECASE
                        )
                    ).first
                except Exception:
                    pass

            if scene_input and scene_input.is_visible():
                scene_input.scroll_into_view_if_needed()
                scene_input.click(force=True)
                scene_input.fill(scene_info["scene_prompt"])
                time.sleep(0.8)

                if format_prompt_enabled:
                    scene_format_btn = page.locator(
                        "button:has-text('Format'), button[aria-label*='Format' i]"
                    ).first
                    if scene_format_btn.is_visible():
                        print("  ✨ Applying AI prompt formatting to scene...")
                        scene_format_btn.click(force=True)
                        wait_for_prompt_format_completion(page, scene_input, timeout_seconds=10)

                # Submit Scene prompt via circular arrow button (->) or Enter
                submit_clicked = False
                try:
                    model_dd = page.locator(
                        "button:has-text('Nano Banana'), button:has-text('Imagen')"
                    ).last
                    if model_dd.is_visible():
                        arrow_btn = model_dd.locator("xpath=following-sibling::button[1]")
                        if arrow_btn.is_visible():
                            arrow_btn.click(force=True)
                            submit_clicked = True
                except Exception:
                    pass

                if not submit_clicked:
                    try:
                        arrow_btns = page.locator(
                            "button:has(svg path[d*='M5']), button:has(svg path[d*='M2']), button:has(svg)"
                        ).all()
                        if arrow_btns:
                            arrow_btns[-1].click(force=True)
                            submit_clicked = True
                    except Exception:
                        pass

                if not submit_clicked:
                    page.keyboard.press("Enter")

                time.sleep(2)

                print(f"  ⏳ Generating Scene '{scene_name}' (Waiting for render on feed)...")

                # Step C: Wait until Scene Generation finishes
                wait_for_flow_generation_idle(page, timeout_seconds=120)
                time.sleep(4)

                # Step D: Locate the newest Top-Left Scene Card (Guaranteed index 0)
                workspace_imgs = []
                for img in page.locator("img").all():
                    try:
                        if img.is_visible():
                            box = img.bounding_box()
                            if (
                                box
                                and box["x"] > 200
                                and box["width"] > 180
                                and box["height"] > 120
                            ):
                                if img.evaluate(
                                    "el => el.naturalWidth > 180 || el.clientWidth > 180"
                                ):
                                    workspace_imgs.append((box["y"], box["x"], img))
                    except Exception:
                        pass

                # Sort ascending by (y, x): index 0 = newest card at top-left
                workspace_imgs.sort(key=lambda item: (item[0], item[1]))

                if workspace_imgs:
                    top_scene_img = workspace_imgs[0][2]
                    print(f"  🏷️ Renaming newest scene card to '{scene_name}' via 3-dots menu...")
                    _rename_workspace_image_card(page, top_scene_img, scene_name)
                else:
                    print("  ⚠️ No scene image card found on workspace feed.")
            else:
                print(f"  ❌ Could not locate prompt input box for scene '{scene_name}'.")
                all_presets_successful = False

            time.sleep(2)

    except Exception as e:
        print(f"  ❌ Scene setup encountered an error: {e}")
        all_presets_successful = False

    # Step E: Explicitly return to 'All Media' main workspace
    try:
        all_media_btn = page.locator(
            "button:has-text('All Media'), a:has-text('All Media'), [aria-label*='All Media' i]"
        ).first
        if all_media_btn.is_visible():
            print("  🏠 Navigating back to 'All Media' main workspace...")
            all_media_btn.click(force=True)
            time.sleep(3)
    except Exception:
        pass

    # Ensure page URL matches base project URL
    if project_url and "/project/" in project_url and page.url != project_url:
        try:
            page.goto(project_url, wait_until="domcontentloaded")
            time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ Warning returning to workspace: {e}")

    # --- MARK ASSETS INITIALIZED ONLY ON COMPLETE SUCCESS ---
    if all_presets_successful:
        mark_profile_assets_initialized(subfolder, profile_index, project_url)
        print(
            f"  💾 [PRE-FLIGHT] Successfully saved preset manifest in '{os.path.basename(subfolder)}' for Profile {profile_index}."
        )
    else:
        print(
            "  ⚠️ [PRE-FLIGHT] Preset creation completed with warnings/errors. Manifest will retry on next run."
        )


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
            pass  # Tier 1 probe: optional chip container not present
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
        # Ensure focus returns to clean state
        page.keyboard.press("Escape")
        time.sleep(0.2)
    except Exception:
        pass  # Tier 1 probe: chip removal is best-effort cleanup


def _rename_workspace_image_card(page: Any, img_element: Any, new_name: str) -> bool:
    """Internal Helper: Opens context menu via 3-dots on card, clicks 'Rename', and types the new name."""
    try:
        img_element.scroll_into_view_if_needed()
        time.sleep(0.5)

        rename_success = False

        for _attempt in range(1, 4):
            # 1. Hover specifically on the TOP-RIGHT corner of the card to reveal [Favorite, Reuse, ⋮] buttons
            box = img_element.bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"] - 25, box["y"] + 25)
                time.sleep(0.6)

            # 2. Click the 3-dots button (⋮) on the card
            menu_clicked = False
            try:
                parent_card = img_element.locator(
                    "xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'media') or position()=2]"
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
                    dots_btn = page.locator(
                        "button:has(svg path[d*='M12 8']), button:has(svg path[d*='M12 10']), button[aria-label*='more' i]"
                    ).last
                    if dots_btn.is_visible():
                        dots_btn.click(force=True)
                        menu_clicked = True
                except Exception:
                    pass

            time.sleep(1.2)

            # 3. Locate & Click 'Rename' option in the open menu
            rename_opt = None

            # Strategy A: Role menuitem
            try:
                item = page.get_by_role(
                    "menuitem", name=re.compile(r"Rename|إعادة تسمية", re.I)
                ).first
                if item.is_visible():
                    rename_opt = item
            except Exception:
                pass

            # Strategy B: Exact text filter on interactive elements (reversed)
            if not rename_opt:
                try:
                    for sel in ["button", "div", "li", "span", "[role='menuitem']"]:
                        for loc in reversed(
                            page.locator(sel).filter(has_text=re.compile(r"^Rename$", re.I)).all()
                        ):
                            if loc.is_visible():
                                rename_opt = loc
                                break
                        if rename_opt:
                            break
                except Exception:
                    pass

            # Strategy C: Regex text match
            if not rename_opt:
                try:
                    for loc in reversed(
                        page.get_by_text(re.compile(r"(\bRename\b|إعادة تسمية)", re.I)).all()
                    ):
                        if loc.is_visible():
                            rename_opt = loc
                            break
                except Exception:
                    pass

            if rename_opt:
                rename_opt.scroll_into_view_if_needed()
                rename_opt.click(force=True)
                time.sleep(1.2)
                rename_success = True
                break
            else:
                page.keyboard.press("Escape")
                time.sleep(1)

        if not rename_success:
            print("  ⚠️ 'Rename' option could not be opened for scene card.")
            return False

        # 4. Fill the inline rename popup on the card (strictly exclude top header y < 120)
        time.sleep(1)
        rename_input = None
        for inp in page.locator("input[type='text'], input").all():
            try:
                if inp.is_visible():
                    box = inp.bounding_box()
                    # Must be inside workspace feed (y > 120 excludes top header, x > 180 excludes sidebar)
                    if box and box["y"] > 120 and box["x"] > 180:
                        rename_input = inp
                        break
            except Exception:
                pass

        if rename_input:
            rename_input.scroll_into_view_if_needed()
            rename_input.click(force=True)
            time.sleep(0.3)
            page.keyboard.press("Control+a")
            page.keyboard.press("Backspace")
            page.keyboard.type(new_name, delay=30)
            time.sleep(0.5)

            # Click the checkmark ✓ button directly adjacent to the rename input
            check_clicked = False
            try:
                check_btn = rename_input.locator("xpath=following-sibling::button[1]")
                if check_btn.is_visible():
                    check_btn.click(force=True)
                    check_clicked = True
            except Exception:
                pass

            if not check_clicked:
                try:
                    check_btn = page.locator(
                        "button:has(svg path[d*='M9 16']), button:has(svg path[d*='M5'])"
                    ).last
                    if check_btn.is_visible():
                        box = check_btn.bounding_box()
                        if box and box["y"] > 120:
                            check_btn.click(force=True)
                            check_clicked = True
                except Exception:
                    pass

            page.keyboard.press("Enter")
            time.sleep(1.5)
            print(f"  ✅ Successfully renamed scene card to '{new_name}'!")
            return True
        else:
            print("  ⚠️ Could not locate inline rename input popup on the card.")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"  ⚠️ Error renaming card: {e}")
        page.keyboard.press("Escape")
        return False


def _click_add_to_prompt_on_image(page: Any, img_element: Any) -> bool:
    """Internal Helper: Opens context menu on a specific image and clicks 'Add to prompt'."""
    try:
        img_element.scroll_into_view_if_needed()
        time.sleep(0.5)
        img_element.hover()
        time.sleep(0.5)

        # Attempt clicking card 3-dots button
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

        # Fallback to right click
        if not menu_clicked:
            try:
                img_element.click(button="right", force=True)
                menu_clicked = True
            except Exception:
                pass

        time.sleep(1)

        # Click "Add to prompt"
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
    """
    DOM Helper: Clears old chips, finds the target previous primary cards
    (sliding window max 3), and attaches them in CHRONOLOGICAL ORDER (oldest -> newest)
    with strict coordinate filtering and context-menu state resets.
    """
    try:
        # Enforce max 3 sliding window limit
        count_to_attach = min(count_to_attach, 3)
        if count_to_attach <= 0:
            clear_attached_prompt_chips(page)
            return True

        print(
            f"  📷 Attaching {count_to_attach} previous image(s) to prompt (Chronological order)..."
        )

        # 1. Clear previous attachments first
        clear_attached_prompt_chips(page)

        # 2. Search for images inside the main workspace feed (x > 200 excludes left sidebar)
        all_imgs = page.locator("img").all()
        workspace_imgs = []

        for img in all_imgs:
            try:
                if img.is_visible():
                    box = img.bounding_box()
                    if box and box["x"] > 200 and box["width"] > 180 and box["height"] > 120:
                        if img.evaluate(
                            "el => el.complete && (el.naturalWidth > 180 || el.clientWidth > 180)"
                        ):
                            workspace_imgs.append((box["y"], box["x"], img))
            except Exception:
                pass  # Tier 1 probe: individual img element transient/detached

        if not workspace_imgs:
            print("  ⚠️ No valid workspace image cards found.")
            return False

        # Sort ascending by (y, x): index 0 = newest batch primary card
        workspace_imgs.sort(key=lambda item: (item[0], item[1]))

        # 3. Identify target primary cards (skipping multi-count duplicates like 2x, 4x)
        targets = []
        for g in reversed(range(count_to_attach)):  # reversed -> oldest first (e.g. 2, 1, 0)
            target_idx = g * batch_count
            if target_idx < len(workspace_imgs):
                targets.append((g + 1, workspace_imgs[target_idx][2]))

        # 4. Attach each in chronological order
        attached_count = 0
        for _step_num, img_el in targets:
            if _click_add_to_prompt_on_image(page, img_el):
                attached_count += 1
                time.sleep(0.5)

        # 5. Safety overlay reset: clear active portals/hover menus
        page.keyboard.press("Escape")
        page.mouse.move(100, 15)
        time.sleep(0.3)

        # 6. Verification
        chips_present = count_attached_prompt_chips(page)
        if attached_count > 0 and chips_present > 0:
            print(f"  ✅ Confirmed {chips_present} reference frame chip(s) attached to prompt bar!")
            return True
        elif attached_count > 0:
            print(
                f"  💢 Attached {attached_count} frame(s), but DOM chip count check was inconclusive (proceeding)."
            )
            return True
        else:
            print("  ⚠️ Failed to attach previous images.")
            return False

    except Exception as e:
        print(f"  ⚠️ Error attaching images to prompt: {e}")
        page.keyboard.press("Escape")
        return False


def scan_batch_folders() -> list[str]:
    runs_dir = "youtube_runs"
    batch_queue = []
    if os.path.exists(runs_dir):
        for item in os.listdir(runs_dir):
            subfolder = os.path.join(runs_dir, item)
            if os.path.isdir(subfolder):
                # Check for image_timestamps.txt OR timestamped_transcript.txt
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
                        # FIX #2: Fallback regex frame for unparseable objects
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
                    pass  # Tier 1 fallback: object string too malformed, warn below
                print(f"Warning: Could not parse object string starting with: {obj_str[:60]}...")
                continue

        if isinstance(item, dict):
            try:
                idx = int(item.get("index", 0))
                ts = str(item.get("timestamp", "")).strip()
                vp = item.get("visual_prompt", "")

                if isinstance(vp, dict):
                    prompt = json.dumps(vp, indent=2)
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

    # Deduplicate and sort by (index, frame_index) tuple to preserve multi-frame set items
    prompts_dict = {}
    for p in prompts:
        idx, frame_idx = p.index, p.frame_index
        key = (idx, frame_idx)
        # Automatically resolve key collisions to prevent overwriting multi-frame items
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
    sorted_prompts = [prompts_dict[k] for k in sorted_keys]
    return sorted_prompts


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


def is_flow_page_healthy(page: Any) -> bool:
    """
    DOM Health Validator: Detects client-side React/Next.js crashes, blank screens,
    or 500 errors, and verifies that real workspace elements are rendered.
    """
    try:
        # 1. Detect fatal crash error screens
        crash_patterns = re.compile(
            r"(Application error|client-side exception|Something went wrong|500 Internal Server|404 Not Found)",
            re.IGNORECASE,
        )
        if page.get_by_text(crash_patterns).count() > 0:
            return False

        # 2. Require the workspace prompt bar to be present AND interactive
        prompt_bar = None
        for sel in (
            "textarea[placeholder*='What do you want' i]",
            "input[placeholder*='What do you want' i]",
        ):
            loc = page.locator(sel).first
            if loc.is_visible():
                prompt_bar = loc
                break
        if prompt_bar is None and "project" in page.url:
            # Fallback: contenteditable prompt bar (character body popups excluded)
            for ce in page.locator("div[contenteditable='true']").all():
                try:
                    if ce.is_visible() and ce.bounding_box() is not None:
                        box = ce.bounding_box()
                        if box and box["width"] > 300:
                            prompt_bar = ce
                            break
                except Exception:
                    continue

        # 3. Workspace must also expose supporting UI (sidebar / toolbar / feed)
        supporting_ui = [
            "button:has-text('All Media')",
            "button:has-text('Characters')",
            "button:has-text('Scenes')",
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
            page.mouse.move(100, 100)
            time.sleep(0.2)
            page.mouse.move(500, 500)
            page.mouse.down()
            page.mouse.up()
        except Exception:
            pass

    # Attempt to load and validate saved project URL
    resumed = False
    if project_url and "project" in project_url:
        print(f"\n[FLOW] Attempting to resume workspace: {project_url}")
        for resume_attempt in range(1, 3):
            try:
                page.goto(project_url, wait_until="domcontentloaded", timeout=45000)
                wake_up_page()
                time.sleep(3)

                # Check for client-side crash error screen
                if not is_flow_page_healthy(page):
                    print(
                        f"  ⚠️ Application error/crash detected on resume (Attempt {resume_attempt}/2). Forcing reload..."
                    )
                    page.reload(wait_until="domcontentloaded")
                    wake_up_page()
                    time.sleep(4)

                # Confirm DOM health before declaring success
                if is_flow_page_healthy(page) and "project" in page.url:
                    resumed = True
                    print("  ✅ Workspace resumed successfully and verified healthy.")
                    break
                else:
                    print(f"  ⚠️ Workspace failed DOM health check (Attempt {resume_attempt}/2).")
            except Exception as e:
                print(f"  ⚠️ Error loading workspace URL (Attempt {resume_attempt}/2): {e}")

        if not resumed:
            print(
                "  ⚠️ Workspace URL crashed or is inaccessible. Falling back to fresh project creation..."
            )

    if not resumed:
        print(
            f"\n[FLOW] Configuring NEW workspace for active profile (Model: {target_flow_model} | Count: {target_flow_count})..."
        )
        workspace_created = False

        for attempt in range(1, 4):
            print(
                f"[FLOW] Attempt {attempt}/3 to load Google Flow and open a new project...",
                flush=True,
            )
            page.goto(FlowSelectors.URL, wait_until="domcontentloaded", timeout=60000)
            wake_up_page()
            time.sleep(3)

            # 1. Splash Screen Bypass
            try:
                splash_btn = page.locator(
                    "button:has-text('Create with Google Flow'), a:has-text('Create with Google Flow')"
                ).first
                if splash_btn.is_visible():
                    splash_btn.click(force=True)
                    time.sleep(4)
                    wake_up_page()
            except Exception:
                pass

            # 2. Robust '+ New project' Waiter & Clicker
            print(
                "[FLOW] Waiting for '+ New project' element to appear on dashboard...", flush=True
            )
            pattern = FlowSelectors.NEW_PROJECT_PATTERN
            new_project_target = None

            start_wait = time.time()
            while time.time() - start_wait < 25:
                try:
                    loc = page.get_by_text(pattern)
                    cnt = loc.count()
                    for i in reversed(range(cnt)):
                        el = loc.nth(i)
                        if el.is_visible():
                            new_project_target = el
                            break
                    if new_project_target:
                        break
                except Exception:
                    pass

                try:
                    loc = page.locator("button, div, a, span, p").filter(has_text=pattern)
                    cnt = loc.count()
                    for i in reversed(range(cnt)):
                        el = loc.nth(i)
                        if el.is_visible():
                            new_project_target = el
                            break
                    if new_project_target:
                        break
                except Exception:
                    pass

                time.sleep(1)
                wake_up_page()

            if new_project_target:
                print(
                    "[FLOW] Found visible '+ New project' element. Attempting click...", flush=True
                )
                try:
                    new_project_target.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    new_project_target.click(force=True)
                except Exception:
                    pass

                time.sleep(2)
                if "project" not in page.url:
                    try:
                        new_project_target.evaluate("el => el.click()")
                    except Exception:
                        pass

                    try:
                        parent_card = new_project_target.locator(
                            "xpath=ancestor::div[contains(@class, 'card') or contains(@class, 'project') or position()=1]"
                        )
                        if parent_card.is_visible():
                            parent_card.click(force=True)
                    except Exception:
                        pass

                try:
                    page.wait_for_url("**/project/**", timeout=20000)
                    print(
                        f"[FLOW] Successfully redirected to new project workspace: {page.url}",
                        flush=True,
                    )
                    workspace_created = True
                    break
                except Exception:
                    pass

            time.sleep(2)

        if not workspace_created and "project" not in page.url:
            raise Exception(
                "Failed to create or enter a Google Flow project workspace after 3 attempts."
            )

    time.sleep(4)
    current_workspace_url = page.url

    # 3. Turn Agent OFF if FLOW_DISABLE_AGENT is true
    if get_config_value("FLOW_DISABLE_AGENT", "true").lower() in ["true", "1", "yes"]:
        try:
            agent_btn = page.locator("button:has-text('Agent')").first
            if agent_btn.is_visible():
                is_active = agent_btn.evaluate(
                    "el => el.getAttribute('aria-pressed') === 'true' || el.classList.contains('active')"
                )
                if is_active:
                    print("[FLOW] Turning Agent OFF...")
                    agent_btn.click(force=True)
                    time.sleep(1)
        except Exception:
            pass

    # 4. Select Custom Flow Model
    try:
        model_dropdown = page.locator(
            "button:has-text('Nano Banana'), button:has-text('Imagen'), button:has-text('Veo'), button[aria-haspopup='listbox']"
        ).first
        if model_dropdown.is_visible():
            if target_flow_model.lower() not in model_dropdown.inner_text().lower():
                print(f"[FLOW] Changing image model to '{target_flow_model}'...")
                model_dropdown.click(force=True)
                time.sleep(1)
                model_option = page.get_by_text(target_flow_model).last
                if model_option.is_visible():
                    model_option.click(force=True)
                    time.sleep(1)
                else:
                    page.keyboard.press("Escape")
    except Exception as e:
        print(f"[FLOW] Warning setting image model: {e}")

    # 5. Settings Menu: Set Aspect Ratio (16:9) & Generation Count (1x, x2, etc)
    try:
        settings_icon = page.locator(
            "button:has(svg path[d*='M3']), button[aria-label*='Settings' i]"
        ).last
        if settings_icon.is_visible():
            settings_icon.click(force=True)
            time.sleep(1)

            # Set aspect ratio dynamically from .env
            target_ratio = get_config_value("FLOW_ASPECT_RATIO", "16:9")
            ratio_btn = page.locator(
                f"button:has-text('{target_ratio}'), div:has-text('{target_ratio}')"
            ).first
            if ratio_btn.is_visible():
                ratio_btn.click(force=True)
                time.sleep(0.5)

            # Set Count (1x, x2, x3, x4)
            count_btn = page.locator(
                f"button:has-text('{target_flow_count}'), div:has-text('{target_flow_count}')"
            ).first
            if count_btn.is_visible():
                count_btn.click(force=True)
                time.sleep(0.5)

            page.keyboard.press("Escape")
    except Exception:
        pass

    return str(current_workspace_url)


# ==========================================
# MAIN ORCHESTRATOR
# ==========================================
def _retry_gemini_call(
    gemini_page: Any, fn: Callable[..., Any], label: str, retries: int = 3
) -> Any:
    """Run a Gemini planning operation with bounded retries.

    Retries recover a lost browser turn (e.g. TargetClosedError during planning)
    without reconnecting the whole CDP browser: reload the Gemini page, wake it,
    and re-invoke the callable. Keeps planning idempotent via the manifest.
    """
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_exc = e
            print(
                f"  ⚠️ {label} failed (attempt {attempt}/{retries}): {e}. "
                "Reloading Gemini page and retrying..."
            )
            try:
                gemini_page.bring_to_front()
                gemini_page.reload(wait_until="domcontentloaded", timeout=45000)
                gemini_page.bring_to_front()
                time.sleep(3)
            except Exception as reload_err:
                print(f"  ⚠️ Gemini page reload during retry failed: {reload_err}")
    raise RuntimeError(f"{label} failed after {retries} attempts: {last_exc}")


def main() -> None:
    batch_queue = scan_batch_folders()
    if not batch_queue:
        print("No active folders found.")
        return

    # Define retry counters HERE at the top of main()
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

                try:
                    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                except Exception:
                    if not launch_browser_with_profile(browser_type, current_profile_idx):
                        sys.exit(1)
                    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
                browser_handle = browser

                context = browser.contexts[0]
                context.grant_permissions(["clipboard-read", "clipboard-write"])

                for existing_p in list(context.pages):
                    if existing_p.url in ("about:blank", ""):
                        try:
                            existing_p.close()
                        except Exception:
                            pass

                gemini_page = None
                flow_page = None
                for page in context.pages:
                    if "gemini.google.com" in page.url:
                        gemini_page = page
                    elif "labs.google" in page.url or "fx/tools/flow" in page.url:
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
                    dup_dir = os.path.join(subfolder, "generated_images_duplicates")  # <-- NEW
                    os.makedirs(image_dir, exist_ok=True)
                    os.makedirs(dup_dir, exist_ok=True)  # <-- NEW

                    target_planner_model = get_config_value("IMAGE_PLANNER_MODEL", "Flash-Lite")
                    target_flow_model = get_config_value("FLOW_IMAGE_MODEL", "Nano Banana 2")
                    target_flow_count = get_config_value("FLOW_IMAGE_COUNT", "1x")
                    reset_loop_limit = int(get_config_value("IMAGE_RESET_LOOP_LIMIT", "20"))

                    # Cumulative Chaining Toggle & Limit
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
                        if manifest.all_chunks_done():
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
                            except Exception:
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

                    # Save workspace URL file specific to active Chrome profile index
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

                    # --- RUN PRE-FLIGHT CHARACTER & SCENE BUILDER (Saved per Subfolder) ---
                    # Non-fatal: a character/scene setup failure must not kill the whole
                    # topic batch. Asset presets simply go unused for this subfolder.
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
                    ts_counts: dict[
                        str, int
                    ] = {}  # Tracks occurrence count for duplicate multi-frame timestamps

                    for current_run, prompt_item in enumerate(storyboard_prompts, 1):
                        idx = prompt_item.index
                        ts = prompt_item.timestamp
                        prompt_text = prompt_item.prompt_text
                        seq_type = prompt_item.sequence_type
                        frame_idx = prompt_item.frame_index
                        total_frames_in_set = prompt_item.total_frames_in_set
                        # Use timestamp directly from flow_prompts item (ts)
                        ts_source = (
                            ts
                            if ts
                            else (timestamps[idx - 1] if 0 <= (idx - 1) < len(timestamps) else "")
                        )
                        clean_ts = (
                            ts_source.replace("[", "").replace("]", "").replace(":", "_").strip()
                        )

                        # Multi-frame suffix logic (e.g. 00_42.png for Frame 1, 00_42_2.png for Frame 2)
                        if clean_ts:
                            occ = ts_counts.get(clean_ts, 0) + 1
                            ts_counts[clean_ts] = occ
                            image_name = f"{clean_ts}.png" if occ == 1 else f"{clean_ts}_{occ}.png"
                        else:
                            occ = 1  # <--- Added initialization
                            image_name = f"sentence_{idx}.png"

                        save_path = os.path.join(image_dir, image_name)

                        # Check if this specific frame image already exists
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
                                    # --- CONTINUITY CHAINING PAYLOAD ---
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

                                    # Calculate attachment count based on toggle setting
                                    if (
                                        is_multiframe_continuity
                                        and prev_prompt_text
                                        and prev_idx is not None
                                    ):
                                        if cumulative_chaining_enabled:
                                            # Cumulative sliding window mode (e.g. up to 3 images)
                                            num_prev = frame_idx - 1 if frame_idx > 1 else occ - 1
                                            attach_count = min(max(0, num_prev), max_chain_limit)
                                        else:
                                            # Standard single-frame fallback mode (always 1 image)
                                            attach_count = 1
                                    else:
                                        attach_count = 0

                                    # Flatten prompt structure into natural language
                                    natural_prompt = flatten_visual_prompt_to_diffusion_text(
                                        prompt_text
                                    )

                                    # Construct dynamic, character-aware continuity directive
                                    if attach_count > 0:
                                        # Detect active character entity to anchor correct visual biometrics
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

                                    # Apply the Arabic sanitizer right before submitting
                                    payload_text = enforce_arabic_in_prompt(payload_text)

                                    flow_page.wait_for_timeout(1000)
                                    pre_image_srcs = set()
                                    for loc in flow_page.locator("img").all():
                                        try:
                                            src = loc.get_attribute("src")
                                            if src:
                                                pre_image_srcs.add(src)
                                        except Exception:
                                            pass

                                    # 1. Attach previous continuity frames OR clear chips
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

                                        # 2. Summon Character or Scene Presets if enabled
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

                                            # A. Summon Character ONLY if character toggle is active
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
                                                        continue  # Skip host preset on skeptic-only shots
                                                    if char_k.lower() in subject_details.lower():
                                                        summon_asset_in_prompt(
                                                            flow_page,
                                                            char_v["name"],
                                                            category="Characters",
                                                        )
                                                        time.sleep(1)
                                                        break

                                            # B. Summon Scene Presets ONLY if scene toggle is active
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
                                                        time.sleep(1)
                                                        break

                                    input_box = None
                                    selectors = [
                                        "textarea[placeholder*='What do you want' i]",
                                        "input[placeholder*='What do you want' i]",
                                    ]
                                    for sel in selectors:
                                        loc = flow_page.locator(sel).first
                                        if loc.is_visible():
                                            input_box = loc
                                            break

                                    if not input_box:
                                        # Pick the widest visible contenteditable as the workspace
                                        # prompt bar; excludes small character-body popups.
                                        best_ce = None
                                        best_w = -1.0
                                        for ce in flow_page.locator(
                                            "div[contenteditable='true']"
                                        ).all():
                                            try:
                                                if ce.is_visible():
                                                    box = ce.bounding_box()
                                                    if box and box["width"] > best_w:
                                                        best_w = box["width"]
                                                        best_ce = ce
                                            except Exception:
                                                continue
                                        if best_ce is not None:
                                            input_box = best_ce

                                    if not input_box:
                                        input_box = flow_page.get_by_placeholder(
                                            re.compile(
                                                r"(what do you want|describe|صف|أنشئ|اكتب)",
                                                re.IGNORECASE,
                                            )
                                        ).first

                                    if not input_box or not input_box.is_visible():
                                        raise Exception(
                                            "Could not find Google Flow prompt input box on page."
                                        )

                                    input_box.scroll_into_view_if_needed()
                                    input_box.click(force=True)
                                    time.sleep(0.5)

                                    # Safely select trailing text without destroying attached asset chips
                                    chips_count = count_attached_prompt_chips(flow_page)
                                    if chips_count == 0 and attach_count == 0:
                                        flow_page.keyboard.press("Control+a")
                                        flow_page.keyboard.press("Backspace")
                                        time.sleep(0.2)
                                    else:
                                        # Focus end of contenteditable / input to preserve chips
                                        flow_page.keyboard.press("End")
                                        time.sleep(0.1)

                                    flow_page.keyboard.insert_text(f" {payload_text}")
                                    time.sleep(0.8)
                                    flow_page.keyboard.press("Enter")

                                    print(
                                        f"  Attempt {attempt}: Prompt submitted. Monitoring generation engine..."
                                    )
                                    time.sleep(2)

                                    has_started = False
                                    try:
                                        if flow_page.locator("[role='progressbar']").is_visible():
                                            has_started = True
                                        else:
                                            for load_idx in range(
                                                flow_page.get_by_text(re.compile(r"\d+%")).count()
                                            ):
                                                if (
                                                    flow_page.get_by_text(re.compile(r"\d+%"))
                                                    .nth(load_idx)
                                                    .is_visible()
                                                ):
                                                    has_started = True
                                                    break
                                    except Exception:
                                        pass

                                    if not has_started:
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
                                            time.sleep(2)

                                    final_generated_locators = []
                                    start_gen_time = time.time()
                                    max_wait_seconds = 180
                                    generation_has_started = False
                                    last_activity_time = time.time()

                                    while time.time() - start_gen_time < max_wait_seconds:
                                        error_locators = flow_page.get_by_text(
                                            re.compile(
                                                r"(unusual activity|couldn't generate|failed to generate|policy violation)",
                                                re.IGNORECASE,
                                            )
                                        )
                                        for err_idx in range(error_locators.count()):
                                            if error_locators.nth(err_idx).is_visible():
                                                error_msg = error_locators.nth(err_idx).inner_text()
                                                print(
                                                    f"  ⚠️ Google Flow rejected the prompt: {error_msg}"
                                                )
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
                                                        time.sleep(5)
                                                        if not failed_media_locator.is_visible():
                                                            print(
                                                                "  🟢 Card retry succeeded! Continuing monitoring..."
                                                            )
                                                            card_retry_success = True
                                                            break
                                                except Exception:
                                                    pass
                                                time.sleep(2)

                                            if (
                                                not card_retry_success
                                                and failed_media_locator.is_visible()
                                            ):
                                                raise Exception(
                                                    "Media loading failed completely on this card."
                                                )

                                        is_loading = False
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

                                        # 1. Collect and filter new images strictly inside the workspace feed
                                        new_workspace_imgs = []
                                        for loc in flow_page.locator("img").all():
                                            try:
                                                src = loc.get_attribute("src")
                                                if src and src not in pre_image_srcs:
                                                    if loc.is_visible():
                                                        box = loc.bounding_box()
                                                        # Exclude left sidebar (x < 200) and small UI badges (w/h < 180x120)
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

                                        # 2. Sort by (y, x) ascending -> Index 0 is GUARANTEED to be the top-left newest card
                                        new_workspace_imgs.sort(key=lambda item: (item[0], item[1]))
                                        new_images = [item[2] for item in new_workspace_imgs]

                                        if len(new_images) > 0 and not is_loading:
                                            print(
                                                "  ✅ New image render 100% complete! Waiting for overlay to clear..."
                                            )
                                            time.sleep(5)
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

                                        time.sleep(2)

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

                                        # --- TIERED EXTRACTION: Base64 -> Network -> Blob -> Screenshot ---
                                        saved = extract_high_res_image(
                                            flow_page,
                                            img_locator,
                                            current_save_path,
                                            min_size_kb=20,
                                        )
                                        if saved:
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
                                        # Record telemetry heartbeat non-blockingly
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
                                    time.sleep(3)
                                    flow_page.goto(
                                        active_project_url, wait_until="domcontentloaded"
                                    )
                                    time.sleep(3)

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
                            break  # Break out of subfolder loop so outer while-loop retries current folder with new account

                # All folders processed successfully without failover -> exit the while True loop
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
            # Gracefully detach the CDP browser handle so no in-flight Playwright
            # tasks are left orphaned (avoids "Future exception was never retrieved").
            if browser_handle is not None:
                try:
                    browser_handle.close()
                except Exception:
                    pass
                browser_handle = None


if __name__ == "__main__":
    main()
