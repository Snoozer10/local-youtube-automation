"""Asset Studio: Character & Scene Presets Generation & Management.

Manages Flow character setups, character turnaround model sheets (3-view orthographic lineups),
orthographic consistency prompts, and scene plates. Provides pre-flight generation routines,
asset drawer summoning into prompt bars, and card renaming workflows.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

try:
    from utils import get_config_value
except ImportError:
    from youtube_automation.core.utils import get_config_value

from youtube_automation.browser.cdp_client import capture_debug_state


def log(msg: str) -> None:
    """Outputs real-time timestamped logs with immediate buffer flushing."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


# ==========================================
# ASSET PRESETS (CHARACTERS & SCENES)
# ==========================================
LIGHT_LIMBO_SUBSTRATE: str = "#F8F8FA"
AHWA_STUDIO_GROUND: str = "#2A2420"
STRUCTURAL_CHARCOAL: str = "#2D3444"
CODEC_SAFE_RED: str = "#EB191E"
ACCENT_ELECTRIC_CYAN: str = "#00E5FF"
ACCENT_AMBER: str = "#FFB300"
ACCENT_SPRING_GREEN: str = "#00E676"

STYLE_DNA_TEXT: str = (
    "2D graphic vector animation explainer style, uniform 3px deep charcoal (#2D3444) contour linework, "
    "flat 2-step cel-shading with razor-sharp shadow edges, zero gradients, 1-2-3 shape hierarchy, "
    "clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, "
    "leaving 10% peripheral bleed padding, "
    "Palette: 60% base ground (#F8F8FA), 30% charcoal lines (#2D3444), 10% kinetic accents (Cyan #00E5FF, Amber #FFB300, Spring Green #00E676, Codec-Safe Red #EB191E)"
)

FLOW_ASSET_PRESETS: dict[str, dict[str, Any]] = {
    "CHARACTERS": {
        "HOST": {
            "name": "CHARACTER_HOST_MAIN",
            "info": (
                "Character Visual DNA: Ahmed El-Ghandour (Al-Daheeh). "
                "Anatomy: Voluminous dark curly afro hair, thin round wire-rim glasses, animated hazel eyes, expressive comedic eyebrows, light stubble. "
                "Outfit: Matte charcoal-grey pullover hoodie (#2B2D42), black relaxed joggers, clean white minimal sneakers. "
                "Rendering Invariant: 2D graphic vector animation style, uniform 3px black contour outlines, flat 2-step cel-shading, 1-2-3 shape hierarchy."
            ),
            "portrait_prompt": (
                "Studio character visual development bust portrait of Ahmed El-Ghandour (Al-Daheeh) in a 2D graphic vector animation explainer style. "
                "Chest-up framing with 15% upper headroom: thin circular wire-rim glasses, wide energetic comic eyes, wild voluminous curly black afro hair, expressive eyebrows, light comedic stubble. "
                "Wearing an unbranded matte charcoal-grey pullover hoodie (#2B2D42). "
                "Rendering: Crisp 3px black vector contour outlines, vibrant flat 2-step cel-shading, 1-2-3 shape hierarchy, Da Vinci Sfumato chiaroscuro lighting against desaturated negative space, pure solid seamless white background (#FFFFFF). "
                "Visual rule: Clean 2D animation art only. Zero 3D CGI, zero photorealism, zero gradients, zero shadows on backdrop."
            ),
            "body_prompt": (
                "Professional animation character turnaround model sheet. "
                "Horizontal 3-view orthographic lineup: full-body front view, 3/4 dynamic perspective view, and side profile view. "
                "Character: Ahmed El-Ghandour (Al-Daheeh) in 2D graphic vector animated style. "
                "Biometrics & Wardrobe: Circular wireframe glasses, voluminous dark curly afro hair, matte charcoal-grey pullover hoodie (#2B2D42), relaxed black joggers, minimal white canvas sneakers. "
                "Technical constraints: Aligned eye-lines and identical proportions across all 3 views, crisp 3px black vector contour lines, flat 2-step cel-shading, 1-2-3 shape hierarchy, pure solid seamless white background (#FFFFFF). "
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
        "LIGHT_LIMBO": {
            "name": "SCENE_LIGHT_LIMBO_ENV",
            "scene_prompt": (
                "2D graphic vector animation explainer studio substrate plate. "
                "Neutral studio table ground (#F8F8FA) with aluminum diagnostic clipboard, clean uniform illumination, zero gradients. "
                "Uniform 3px deep charcoal (#2D3444) contour outlines, flat 2-step cel-shading, 1-2-3 shape hierarchy, "
                "clean 16:9 widescreen composition strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980, leaving 10% peripheral bleed padding. "
                "Visual rule: Studio substrate plate only. Zero human figures, zero 3D CGI, zero text."
            ),
        },
        "HOST_STUDIO_DESK": {
            "name": "SCENE_HOST_STUDIO_ENV",
            "scene_prompt": (
                "2D graphic vector animation explainer studio presenter desk plate. "
                "Clean educational studio presenter desk resting on neutral studio limbo ground (#F8F8FA), "
                "uniform 3px deep charcoal (#2D3444) contour linework, flat 2-step cel-shading, zero gradients, "
                "clean 16:9 widescreen composition bounded inside coordinates X: 180 to 1740, Y: 90 to 980, "
                "leaving 10% peripheral bleed padding. Visual rule: Empty studio desk plate only. Zero text, zero 3D CGI."
            ),
        },
        "AHWA_STUDIO": {
            "name": "SCENE_AHWA_STUDIO_ENV",
            "scene_prompt": (
                "2D animation layout background plate of a cozy Cairo studio. "
                "Warm dark mahogany desk (#2A2420), stacked encyclopedias, retro CRT monitor, Egyptian glass teacup with mint, warm 3200K tungsten lighting with razor-sharp shadow falloff. "
                "Uniform 3px deep charcoal (#2D3444) vector outlines, flat 2-step cel-shading, 1-2-3 shape hierarchy, open central staging area strictly bounded inside coordinates X: 180 to 1740, Y: 90 to 980 with 10% bleed padding, 16:9 widescreen. "
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
                "2D animation layout plate of a scientific drafting desk setup. "
                "Orthographic cyan drafting placard resting flat on the studio workbench (#F8F8FA), vector HUD schematics, coordinate grid lines. "
                "High-contrast vector illumination, uniform 3px deep charcoal (#2D3444) outlines, clean 16:9 widescreen composition bounded within coordinates X: 180 to 1740, Y: 90 to 980. "
                "Visual rule: Drafting placard setup only. Zero full-screen dark navy void, zero text, zero human characters."
            ),
        },
        "HISTORICAL_MUSEUM": {
            "name": "SCENE_HISTORICAL_MUSEUM_ENV",
            "scene_prompt": (
                "2D animation layout plate of a historical archival desk setup. "
                "Framed archival document and miniature portrait resting flat on the studio workbench (#F8F8FA), clean studio illumination. "
                "Uniform 3px deep charcoal (#2D3444) contour linework, flat 2-step cel-shading, clean 16:9 widescreen composition bounded within coordinates X: 180 to 1740, Y: 90 to 980. "
                "Visual rule: Archival desk placard plate only. Zero full-screen crimson wallpaper, zero characters, zero 3D CGI."
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
        "KEYNOTE_SLATE": {
            "name": "SCENE_KEYNOTE_SLATE_ENV",
            "scene_prompt": (
                "2D graphic vector explainer presentation background plate. "
                "Matte dark charcoal canvas (#1E2026) with subtle geometric grid overlay. "
                "Dual floating container cards with soft drop shadows, clean 3px vector outlines, "
                "generous negative space in the lower 25% for video subtitles, 16:9 widescreen. "
                "Visual rule: Presentation graphic plate only. Zero characters, zero 3D CGI."
            ),
        },
    },
}


def get_profile_assets_manifest_path(subfolder: str, profile_index: str) -> str:
    """Returns the persistent asset manifest path scoped to the active topic subfolder and browser profile."""
    return os.path.join(subfolder, f"flow_assets_profile_{profile_index}.json")


def is_profile_assets_initialized(subfolder: str, profile_index: str) -> bool:
    """Checks whether presets have already been created and verified for the specified profile."""
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
    """Persists asset initialization state atomically."""
    os.makedirs(subfolder, exist_ok=True)
    manifest_path = get_profile_assets_manifest_path(subfolder, profile_index)
    payload = {
        "assets_initialized": True,
        "profile_index": profile_index,
        "project_url": project_url,
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        tmp_path = manifest_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, manifest_path)
    except Exception as e:
        print(f"  \u26a0\ufe0f Warning saving asset manifest: {e}")


def wait_for_prompt_format_completion(
    page: Any,
    input_locator: Any,
    timeout_seconds: int = 12,
) -> bool:
    """Waits for Google Flow's AI prompt format / rewrite operation to complete
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

    log("  \u26a0\ufe0f Format operation timed out. Capturing debug state...")
    capture_debug_state(page, "format_timeout")
    return False


def summon_asset_in_prompt(page: Any, asset_name: str, category: str = "Characters") -> bool:
    """DOM Helper: Focuses the prompt bar, clicks '+', searches the unique character name,
    selects the character card, and clicks 'Add to Prompt'.
    """
    try:
        print(f"  \U0001f3f7\ufe0f Summoning asset '@{asset_name}' into prompt...")

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
            print("  \u26a0\ufe0f Could not open asset drawer modal.")
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
            print("  \u26a0\ufe0f Search assets input box not found.")
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
            print(f"  \u26a0\ufe0f Character card '{asset_name}' not found in search results.")
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
            print(f"  \u2795 Successfully added '@{asset_name}' asset chip to prompt!")
            return True
        else:
            print("  \u2716 'Add to Prompt' button not found in asset dialog.")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"  \u26a0\ufe0f Error summoning asset '{asset_name}': {e}")
        page.keyboard.press("Escape")
        return False


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
            print("  \u26a0\ufe0f 'Rename' option could not be opened for scene card.")
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
            print(f"  \u2705 Successfully renamed scene card to '{new_name}'!")
            return True
        else:
            print("  \u26a0\ufe0f Could not locate inline rename input popup on the card.")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"  \u26a0\ufe0f Error renaming card: {e}")
        page.keyboard.press("Escape")
        return False


def setup_flow_characters_and_scenes(
    page: Any,
    subfolder: str,
    profile_index: str = "1",
    wait_app_ready_fn: Any = None,
    wait_generation_idle_fn: Any = None,
) -> None:
    """Pre-flight Routine: Checks and creates registered Characters and Scenes
    in Google Flow before the main rendering loop begins.
    Performs live DOM verification and memoizes per topic subfolder.
    """
    if wait_app_ready_fn is None:
        try:
            from youtube_automation.visuals.flow_generator import (
                wait_for_flow_app_ready as wait_app_ready_fn,
            )
        except ImportError:
            from flow_image_generator import wait_for_flow_app_ready as wait_app_ready_fn

    if wait_generation_idle_fn is None:
        try:
            from youtube_automation.visuals.flow_generator import (
                wait_for_flow_generation_idle as wait_generation_idle_fn,
            )
        except ImportError:
            from flow_image_generator import (
                wait_for_flow_generation_idle as wait_generation_idle_fn,
            )

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
            f"  \u26a1 [PRE-FLIGHT] Presets for Profile {profile_index} already verified in {os.path.basename(subfolder)}. Skipping creation."
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
    wait_app_ready_fn(page, timeout_seconds=60)

    # -------------------------------------------------------------
    # 1. CHARACTER CREATION (PORTRAIT -> RENAME -> INFO -> CREATE BODY -> DONE)
    # -------------------------------------------------------------
    try:
        char_presets = FLOW_ASSET_PRESETS.get("CHARACTERS", {}) if enable_characters else {}
        for _char_key, char_info in char_presets.items():
            char_name = char_info["name"]

            # Step 1: Ensure we are STRICTLY on the Characters tab.
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
                log(f"  \u2705 Character '{char_name}' already exists. Skipping creation.")
                continue

            log(f"  \U0001f680 Creating Character Preset: '{char_name}'...")

            # Step 3: Click '+ New Character' card and GUARANTEE transition to the
            # 'Describe your character' view.
            char_input = None
            for card_attempt in range(1, 4):
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
                            continue

                if cand_input.is_visible():
                    char_input = cand_input
                    log("  \u2705 Already on 'Describe your character' view.")
                    break

                log(f"  \U0001f5c2\ufe0f Clicking 'New Character' card (Attempt {card_attempt}/3)...")
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
                            continue

                if cand_input.is_visible():
                    char_input = cand_input
                    log("  \u2705 Transitioned to 'Describe your character' view!")
                    break

            if not char_input or not char_input.is_visible():
                capture_debug_state(page, f"char_card_click_fail_{char_name}", subfolder)
                raise Exception(
                    "Failed to open 'Describe your character' screen after clicking New Character card."
                )

            # Step 4: Fill Portrait Prompt strictly in the character box
            log(f"  \U0001f4dd Filling portrait prompt for '{char_name}'...")
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
                    print("  \u2728 Applying AI prompt formatting to character portrait...")
                    format_btn.click(force=True)
                    wait_for_prompt_format_completion(page, char_input, timeout_seconds=10)

            # 2. Re-focus input box
            char_input.click(force=True)
            time.sleep(0.3)

            # Submit character prompt
            log("  \U0001f680 Submitting Character portrait prompt...")

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
                    continue
                if submit_clicked:
                    break

            page.keyboard.press("Enter")
            page.keyboard.press("Control+Enter")

            # 3. Editor Mount Handshake
            log("  \u23f3 Waiting for Character Editor to mount (portrait rendering)...")
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
                        log("  \u2705 Character Editor mounted.")
                        break
                except Exception:
                    pass
                time.sleep(1)

            if not editor_mounted:
                capture_debug_state(page, f"char_editor_fail_{char_name}", subfolder)
                raise Exception(
                    f"Character Editor did not mount for '{char_name}'. Current URL: {page.url}"
                )

            time.sleep(2)

            # Step B: Rename Character & Fill Character Info
            print(f"  \U0001f3f7\ufe0f Setting character name to '{char_name}'...")
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
                    print(f"  \u2705 Character name set to '{char_name}'.")
            except Exception as rename_err:
                print(f"  \u26a0\ufe0f Warning setting character name: {rename_err}")

            # Fill Character Info
            try:
                info_box = page.locator(
                    "textarea[placeholder*='Describe how your character acts' i], textarea[placeholder*='Character Info' i]"
                ).first
                if info_box.is_visible():
                    print("  \U0001f4dd Filling Character Info (personality & acting context)...")
                    info_box.click(force=True)
                    time.sleep(0.3)
                    page.keyboard.press("Control+a")
                    page.keyboard.press("Backspace")
                    info_box.fill(char_info.get("info", char_info["portrait_prompt"]))
                    time.sleep(1)
                    print("  \u2705 Character Info filled successfully.")
            except Exception as info_err:
                print(f"  \u26a0\ufe0f Warning setting character info: {info_err}")

            # Step C: Wait for Portrait Image to Fully Render and Unlock 'Create Body'
            print(
                "  \u23f3 Generating Character Portrait (Waiting for image render and 'Create Body' unlock)..."
            )
            start_portrait_wait = time.time()

            while time.time() - start_portrait_wait < 60:
                create_body_btn = page.locator("button:has-text('Create Body')").first
                is_btn_unlocked = False
                if create_body_btn.is_visible():
                    is_disabled = create_body_btn.evaluate(
                        "el => el.disabled || el.getAttribute('aria-disabled') === 'true' || el.classList.contains('disabled')"
                    )
                    is_btn_unlocked = not is_disabled

                has_rendered_image = False
                try:
                    for img in page.locator("img").all():
                        if not img.is_visible():
                            continue
                        box = img.bounding_box()
                        if box and box["width"] > 180 and box["height"] > 180:
                            if img.evaluate(
                                "el => el.complete && el.naturalWidth > 180 && el.naturalHeight > 100 && el.naturalWidth < 5000"
                            ):
                                has_rendered_image = True
                                break
                        elif img.evaluate("el => el.complete && el.naturalWidth > 180"):
                            has_rendered_image = True
                            break
                except Exception:
                    has_rendered_image = False

                is_spinner_active = (
                    page.locator("button .animate-spin, svg.animate-spin").count() > 0
                )

                if is_btn_unlocked and has_rendered_image and not is_spinner_active:
                    print("  \u2705 Character Portrait 100% rendered and 'Create Body' is unlocked!")
                    break

                time.sleep(2)

            time.sleep(2)

            # Step D: Click 'Create Body' Button & Generate Body Triptych
            create_body_btn = page.locator("button:has-text('Create Body')").first
            if create_body_btn.is_visible():
                print("  \U0001f9cd Clicking 'Create Body' button...")
                create_body_btn.scroll_into_view_if_needed()
                create_body_btn.click(force=True)
                time.sleep(3)

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
                        continue

                if body_input:
                    print("  \U0001f4dd Inserting Body Triptych prompt into popup bar...")
                    body_input.scroll_into_view_if_needed()
                    body_input.click(force=True)
                    time.sleep(0.5)

                    try:
                        body_input.fill(char_info["body_prompt"])
                    except Exception:
                        body_input.evaluate(
                            f"el => {{ el.innerText = `{char_info['body_prompt']}`; el.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
                        )
                    time.sleep(1)

                    if format_prompt_enabled:
                        body_dialog = page.locator(
                            "mat-dialog-container, [role='dialog'], .cdk-overlay-pane"
                        ).last
                        body_format_btn = body_dialog.locator(
                            "button:has-text('Format'), button[aria-label*='Format' i]"
                        ).first
                        if body_format_btn.is_visible():
                            print("  \u2728 Applying AI prompt formatting to body triptych...")
                            body_format_btn.click(force=True)
                            wait_for_prompt_format_completion(page, body_input, timeout_seconds=10)

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

                    print("  \u23f3 Generating Character Body Triptych (Monitoring DOM render)...")

                    start_body_wait = time.time()
                    stable_rendered_cycles = 0

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

                        has_loaded_triptych = False
                        try:
                            imgs = page.locator("img").all()
                            for img in imgs:
                                if img.is_visible():
                                    box = img.bounding_box()
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
                            if stable_rendered_cycles >= 4:
                                print(
                                    "  \u2705 Character Body Triptych 100% rendered and confirmed in DOM!"
                                )
                                break
                        else:
                            stable_rendered_cycles = 0

                        time.sleep(1.5)

                    time.sleep(2)
                else:
                    print("  \u26a0\ufe0f Could not locate Body prompt popup box.")

            # Step E: Click 'Done' to Save Character
            done_btn = page.locator(
                "button:has-text('Done'), button:has-text('تم'), button:has-text('حفظ')"
            ).first
            if done_btn.is_visible():
                print("  \U0001f4be Clicking 'Done' button to save character preset...")
                done_btn.click(force=True)
                time.sleep(3)

    except Exception as e:
        print(f"  \u274c Character setup encountered an error: {e}")
        all_presets_successful = False

    # -------------------------------------------------------------
    # 2. SCENE CREATION (SCENES TAB -> SUBMIT -> RENDER -> 3-DOTS RENAME)
    # -------------------------------------------------------------
    try:
        scene_presets = FLOW_ASSET_PRESETS.get("SCENES", {}) if enable_scenes else {}

        if (
            scene_presets
            and re.search(r"/character/[a-zA-Z0-9_-]+", page.url)
            and "/characters" not in page.url
        ):
            log("  \U0001f9ed In Character Editor — navigating back to workspace root before scenes...")
            page.goto(
                page.url.split("/character/")[0], wait_until="domcontentloaded", timeout=60000
            )
            time.sleep(3)

        for _scene_key, scene_info in scene_presets.items():
            scene_name = scene_info["name"]

            existing_scene = (
                page.locator("[role='listitem'], [role='article'], .scene-card, div:has(> img)")
                .filter(has_text=re.compile(rf"\b{re.escape(scene_name)}\b", re.IGNORECASE))
                .first
            )
            if existing_scene.is_visible():
                print(f"  \u2705 Scene '{scene_name}' already exists. Skipping creation.")
                continue

            print(f"\n[PRE-FLIGHT] Creating Scene Preset: '{scene_name}'...")

            scenes_sidebar_btn = page.locator(
                "button:has-text('Scenes'), a:has-text('Scenes'), [aria-label*='Scenes' i]"
            ).first
            if scenes_sidebar_btn.is_visible():
                scenes_sidebar_btn.click(force=True)
                time.sleep(2.5)

            pre_scene_srcs = set()
            for loc in page.locator("img").all():
                try:
                    src = loc.get_attribute("src")
                    if src:
                        pre_scene_srcs.add(src)
                except Exception:
                    pass

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
                        print("  \u2728 Applying AI prompt formatting to scene...")
                        scene_format_btn.click(force=True)
                        wait_for_prompt_format_completion(page, scene_input, timeout_seconds=10)

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

                print(f"  \u23f3 Generating Scene '{scene_name}' (Waiting for render on feed)...")

                wait_generation_idle_fn(page, timeout_seconds=120)
                time.sleep(4)

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

                workspace_imgs.sort(key=lambda item: (item[0], item[1]))

                if workspace_imgs:
                    top_scene_img = workspace_imgs[0][2]
                    print(f"  \U0001f3f7\ufe0f Renaming newest scene card to '{scene_name}' via 3-dots menu...")
                    _rename_workspace_image_card(page, top_scene_img, scene_name)
                else:
                    print("  \u26a0\ufe0f No scene image card found on workspace feed.")
            else:
                print(f"  \u274c Could not locate prompt input box for scene '{scene_name}'.")
                all_presets_successful = False

            time.sleep(2)

    except Exception as e:
        print(f"  \u274c Scene setup encountered an error: {e}")
        all_presets_successful = False

    # Step E: Explicitly return to 'All Media' main workspace
    try:
        all_media_btn = page.locator(
            "button:has-text('All Media'), a:has-text('All Media'), [aria-label*='All Media' i]"
        ).first
        if all_media_btn.is_visible():
            print("  \U0001f3e0 Navigating back to 'All Media' main workspace...")
            all_media_btn.click(force=True)
            time.sleep(3)
    except Exception:
        pass

    if project_url and "/project/" in project_url and page.url != project_url:
        try:
            page.goto(project_url, wait_until="domcontentloaded")
            time.sleep(3)
        except Exception as e:
            print(f"  \u26a0\ufe0f Warning returning to workspace: {e}")

    # Mark assets initialized on complete success
    if all_presets_successful:
        mark_profile_assets_initialized(subfolder, profile_index, project_url)
        print(
            f"  \U0001f4be [PRE-FLIGHT] Successfully saved preset manifest in '{os.path.basename(subfolder)}' for Profile {profile_index}."
        )
    else:
        print(
            "  \u26a0\ufe0f [PRE-FLIGHT] Preset creation completed with warnings/errors. Manifest will retry on next run."
        )
