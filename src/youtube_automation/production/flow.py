"""Adapt editorial shots to the existing Flow worker without feed-position guesses."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Page

from youtube_automation.core.utils import atomic_write_json

from .assets import accepted_asset, ensure_local_canvas, pixel_digest, read_receipt
from .contracts import Brief, load_brief
from .ledger import publication_guard
from .shots import (
    Shot,
    ShotPlan,
    ensure_shot_plan,
    generation_prompt,
    require_editorial_review,
)


def _provider_image_id(url: str) -> str:
    path = urlsplit(url).path
    return path.split("/image/", 1)[1].split("/", 1)[0] if "/image/" in path else ""


def _attached_reference_matches(page: Page, receipt: dict[str, Any]) -> bool:
    from youtube_automation.visuals.flow_generator import visible_attached_prompt_images
    from youtube_automation.visuals.image_extractor import extract_high_res_image

    images = visible_attached_prompt_images(page)
    if len(images) != 1:
        return False
    image = images[0]
    attached_url = image.get_attribute("src") or ""
    expected_provider_id = _provider_image_id(receipt.get("source_url", ""))
    attached_provider_id = _provider_image_id(attached_url)
    if expected_provider_id and attached_provider_id:
        return expected_provider_id == attached_provider_id
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
        path = temp.name
    try:
        return bool(
            extract_high_res_image(page, image, path, min_size_kb=1)
            and pixel_digest(path) == receipt["pixel_sha256"]
        )
    finally:
        if os.path.exists(path):
            os.unlink(path)


def verify_exact_reference(page: Page, root: Path, asset_id: str) -> None:
    receipt = read_receipt(root, asset_id)
    if not _attached_reference_matches(page, receipt):
        raise RuntimeError(f"Reference {asset_id} exact reference chip is not attached")


def verify_adaptive_prompt_references(page: Page, root: Path, shot: Shot) -> None:
    from youtube_automation.visuals.flow_generator import count_attached_prompt_chips

    if shot.reference_asset_id:
        verify_exact_reference(page, root, shot.reference_asset_id)
    elif count_attached_prompt_chips(page) != 0:
        raise RuntimeError(f"Shot {shot.shot_id} has an unexpected reference chip")


def _attach_uploaded_reference(
    page: Page, image_path: Path, receipt: dict[str, Any]
) -> bool:
    """Restore an accepted local image when Flow no longer mounts its provider card."""
    from youtube_automation.visuals.flow_generator import (
        clear_attached_prompt_chips,
        count_attached_prompt_chips,
    )

    clear_attached_prompt_chips(page)
    if count_attached_prompt_chips(page) != 0:
        return False
    add_ingredients = page.locator("button[aria-label*='Add ingredients' i]").last
    if not add_ingredients.is_visible():
        return False
    add_ingredients.click(force=True)
    page.wait_for_timeout(500)
    overlay = page.locator("div.cdk-overlay-container")
    asset_name = image_path.name

    def uploaded_asset() -> Any | None:
        asset = overlay.locator("button.asset-item").filter(has_text=asset_name).first
        if asset.is_visible() and "uploading" not in asset.inner_text().lower():
            return asset
        return None

    asset = uploaded_asset()
    if asset is None:
        upload = overlay.locator("button").filter(has_text="Upload media").first
        if not upload.is_visible():
            page.keyboard.press("Escape")
            return False
        with page.expect_file_chooser(timeout=5000) as chooser:
            upload.click(force=True)
        chooser.value.set_files(str(image_path))
        for _ in range(120):
            asset = uploaded_asset()
            if asset is not None:
                break
            page.wait_for_timeout(500)
    if asset is None:
        page.keyboard.press("Escape")
        return False
    asset.click(force=True)
    page.wait_for_timeout(400)
    if count_attached_prompt_chips(page) == 1:
        return _attached_reference_matches(page, receipt)
    add_to_prompt = overlay.locator("button").filter(has_text="Add to prompt").first
    if not add_to_prompt.is_visible():
        page.keyboard.press("Escape")
        return False
    add_to_prompt.click(force=True)
    for _ in range(20):
        if count_attached_prompt_chips(page) == 1:
            return _attached_reference_matches(page, receipt)
        page.wait_for_timeout(250)
    return False


def prepare_flow(root: Path, ask: Callable[[str], str]) -> tuple[ShotPlan, Brief]:
    brief = load_brief(root)
    plan = ensure_shot_plan(root, ask)
    if brief.version >= 3:
        require_editorial_review(root, plan, brief)
    for shot in plan.shots:
        if shot.operation == "local_canvas":
            ensure_local_canvas(root, shot, brief)
    generated = [s for s in plan.shots if s.operation not in {"reuse", "local_canvas"}]
    payloads = []
    for i, shot in enumerate(generated, 1):
        second = shot.start_frame // plan.fps
        payloads.append(
            {
                "index": i,
                "timestamp": f"[{second // 60:02d}:{second % 60:02d}]",
                "sequence_type": "STANDALONE",
                "sequence_metadata": {
                    "set_id": shot.scene_id,
                    "frame_index": 1,
                    "total_frames_in_set": 1,
                },
                "visual_prompt": {
                    "subject": shot.subject,
                    "action": shot.visible_state,
                    "setting": shot.setting,
                    "composition": shot.composition,
                    "style": brief.channel.style,
                },
                "master_setup_prompt": generation_prompt(shot, brief),
                "adaptive_shot": shot.model_dump(mode="json"),
            }
        )
    with publication_guard():
        atomic_write_json(str(root / "flow_prompts.json"), payloads)
    return plan, brief


def attach_exact_reference(page: Page, root: Path, asset_id: str) -> None:
    from youtube_automation.visuals.flow_generator import (
        _click_add_to_prompt_on_image,
        clear_attached_prompt_chips,
        count_attached_prompt_chips,
        dismiss_blocking_flow_modals,
        wait_for_flow_input_box,
    )

    receipt = read_receipt(root, asset_id)
    if not receipt["source_url"] or not receipt["project_url"]:
        raise RuntimeError(
            f"Reference {asset_id} is not available in this Flow project; restore its exact asset before continuing"
        )
    if receipt["project_url"] != page.url:
        page.goto(receipt["project_url"], wait_until="domcontentloaded", timeout=45000)
        if page.url != receipt["project_url"]:
            raise RuntimeError(
                f"Reference {asset_id} project could not be restored; refusing a recent-card fallback"
            )
        dismiss_blocking_flow_modals(page)
        wait_for_flow_input_box(page, timeout_seconds=15.0)
    visible_images = [loc for loc in page.locator("img").all() if loc.is_visible()]
    exact_url = [
        loc for loc in visible_images if loc.get_attribute("src") == receipt["source_url"]
    ]
    # Flow replaces signed image URLs when a project reloads. Restrict fallback discovery
    # to actual generated-media tiles, then verify the stable provider media ID exposed
    # by the attached prompt chip. Page chrome must never become a reference.
    refreshed_tiles = [
        loc
        for loc in visible_images
        if (loc.get_attribute("alt") or "").lower().startswith("tile displaying")
        or "/asb/" in (loc.get_attribute("src") or "")
        or "flow-content.google/image/" in (loc.get_attribute("src") or "")
    ]
    candidates = exact_url + [loc for loc in refreshed_tiles if loc not in exact_url]
    for candidate in candidates:
        clear_attached_prompt_chips(page)
        if count_attached_prompt_chips(page) != 0:
            raise RuntimeError("Could not clear unrelated Flow references")
        if not _click_add_to_prompt_on_image(page, candidate):
            continue
        for _ in range(20):
            if count_attached_prompt_chips(page) == 1:
                if _attached_reference_matches(page, receipt):
                    return
                break
            page.wait_for_timeout(250)
        clear_attached_prompt_chips(page)
    accepted_path = (root / receipt["path"]).resolve()
    if not accepted_path.is_relative_to(root.resolve()):
        raise RuntimeError(f"Reference {asset_id} escapes its accepted asset store")
    if _attach_uploaded_reference(page, accepted_path, receipt):
        return
    raise RuntimeError(f"Reference content differs from the accepted asset: {asset_id}")


def verify_generated_assets(root: Path, plan: ShotPlan, brief: Brief) -> None:
    missing = [
        s.asset_id
        for s in plan.shots
        if s.operation != "reuse" and accepted_asset(root, s, brief) is None
    ]
    if missing:
        raise RuntimeError("Incomplete adaptive generation: " + ", ".join(missing))
