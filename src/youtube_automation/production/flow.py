"""Adapt editorial shots to the existing Flow worker without feed-position guesses."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    uses_local_canvas,
)
from .visual_gate import enforce_visual_budget


def _provider_image_id(url: str) -> str:
    from youtube_automation.visuals.asset_studio import flow_image_identity

    identity = flow_image_identity(url)
    if not isinstance(identity, str):
        raise TypeError("Flow image identity must be a string")
    return identity


def _is_trusted_flow_alias_native_pair(first_id: str, second_id: str) -> bool:
    if first_id.startswith("asb:"):
        alias_id, native_id = first_id[4:], second_id
    elif second_id.startswith("asb:"):
        alias_id, native_id = second_id[4:], first_id
    else:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", alias_id)) and bool(
        re.fullmatch(r"[A-Za-z0-9_-]+", native_id)
    )


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
        if expected_provider_id == attached_provider_id:
            return True
        if not _is_trusted_flow_alias_native_pair(expected_provider_id, attached_provider_id):
            return False
    elif expected_provider_id or attached_provider_id:
        return False
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


def verify_adaptive_prompt_references(page: Page, root: Path, shot: Shot, profile_index: str | None = None) -> None:
    from youtube_automation.visuals.flow_generator import count_attached_prompt_chips

    if list(shot.character_ids):
        from youtube_automation.visuals.asset_studio import visible_episode_ingredients

        from .characters import read_character_receipt

        brief = load_brief(root)
        chips = visible_episode_ingredients(page)
        if len(chips) != len(shot.character_ids) + bool(shot.reference_asset_id):
            raise RuntimeError("Adaptive ingredient set has missing, duplicate or extra chips")
        used: set[int] = set()
        for character_id in shot.character_ids:
            receipt = read_character_receipt(root, brief, character_id, profile_index=profile_index, project_url=page.url)
            matches = [index for index, chip in enumerate(chips) if _character_chip_matches(page, chip, receipt)]
            if len(matches) != 1 or matches[0] in used:
                raise RuntimeError(f"Exact character chip is not attached: {character_id}")
            used.add(matches[0])
        if shot.reference_asset_id:
            remaining = [chip for index, chip in enumerate(chips) if index not in used]
            if len(remaining) != 1 or not _scene_reference_chip_matches(page, remaining[0], read_receipt(root, shot.reference_asset_id)):
                raise RuntimeError("Exact scene reference is not attached alongside characters")
        return
    if shot.reference_asset_id:
        verify_exact_reference(page, root, shot.reference_asset_id)
    elif count_attached_prompt_chips(page) != 0:
        raise RuntimeError(f"Shot {shot.shot_id} has an unexpected reference chip")


def _scene_reference_chip_matches(page: Page, chip: Any, receipt: dict[str, Any]) -> bool:
    from youtube_automation.visuals.image_extractor import extract_high_res_image

    images = [image for image in chip.locator("img").all() if image.is_visible()]
    if len(images) != 1:
        return False
    url = images[0].get_attribute("src") or ""
    expected_id, actual_id = _provider_image_id(receipt.get("source_url", "")), _provider_image_id(url)
    if expected_id and actual_id:
        if expected_id == actual_id:
            return True
        if not _is_trusted_flow_alias_native_pair(expected_id, actual_id):
            return False
    elif expected_id or actual_id:
        return False
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = handle.name
    try:
        return bool(extract_high_res_image(page, images[0], path, min_size_kb=1)) and pixel_digest(path) == receipt["pixel_sha256"]
    finally:
        Path(path).unlink(missing_ok=True)


def _character_chip_matches(page: Page, chip: Any, receipt: Any) -> bool:
    from youtube_automation.visuals.image_extractor import extract_high_res_image

    name = chip.evaluate("el => { const clone = el.cloneNode(true); clone.querySelectorAll('button').forEach(b => b.remove()); return clone.textContent.trim(); }")
    # Current Flow renders a typed character chip without its name/ID. Its exact
    # named picker selection plus receipt-bound image establishes the appearance.
    typed_character = chip.locator("flow-character-ingredient-chip").count() == 1
    if name != receipt.provider_name and not (not name and typed_character):
        return False
    exposed_id = chip.get_attribute("data-character-id")
    if exposed_id and exposed_id != receipt.provider_id:
        return False
    images = [image for image in chip.locator("img").all() if image.is_visible()]
    if len(images) != 1:
        return False
    url = images[0].get_attribute("src") or ""
    expected = tuple(image for image in (receipt.portrait, receipt.body) if image is not None)
    provider_id = _provider_image_id(url)
    if provider_id and any(
        provider_id == _provider_image_id(source)
        for image in expected
        for source in [image.source_url, *image.source_aliases]
    ):
        return True
    if provider_id and not any(image.preview is not None for image in expected):
        return False
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        path = handle.name
    try:
        accepted_pixels = {image.pixel_sha256 for image in expected}
        accepted_pixels.update(image.preview.pixel_sha256 for image in expected if image.preview is not None)
        return bool(extract_high_res_image(page, images[0], path, min_size_kb=1)) and pixel_digest(path) in accepted_pixels
    finally:
        Path(path).unlink(missing_ok=True)


def attach_episode_characters(page: Page, root: Path, shot: Shot, profile_index: str) -> None:
    from youtube_automation.visuals.asset_studio import attach_episode_character

    from .characters import read_character_receipt

    brief = load_brief(root)
    for character_id in shot.character_ids:
        receipt = read_character_receipt(root, brief, character_id, profile_index=profile_index, project_url=page.url)
        attach_episode_character(page, receipt.provider_name)
    verify_adaptive_prompt_references(page, root, shot, profile_index)


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
    from .audio_adoption import (
        assert_audio_lineage,
        assert_current_audio_state,
        capture_audio_state,
        require_adopted_audio_review,
    )
    brief = load_brief(root)
    require_adopted_audio_review(root, brief)
    plan = ensure_shot_plan(root, ask)

    with publication_guard():
        audio_state = capture_audio_state(root)
        assert_audio_lineage(root, brief, plan=plan)
        require_adopted_audio_review(root, brief)
    enforce_visual_budget(root, plan)
    if brief.version >= 3:
        require_editorial_review(root, plan, brief)
    for shot in plan.shots:
        if uses_local_canvas(shot):
            ensure_local_canvas(root, shot, brief)
    generated = [s for s in plan.shots if s.operation != "reuse" and not uses_local_canvas(s)]
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
        assert_current_audio_state(root, audio_state)
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


def verify_generated_assets(root: Path, plan: ShotPlan, brief: Brief, *, shot_ids: set[str] | None = None) -> None:
    from .audio_adoption import require_adopted_audio_review

    require_adopted_audio_review(root, brief, plan)
    if shot_ids is not None and (not shot_ids or not shot_ids <= {shot.shot_id for shot in plan.shots}):
        raise ValueError("Unknown or empty adaptive generation verification scope")
    missing = [
        s.asset_id
        for s in plan.shots
        if (shot_ids is None or s.shot_id in shot_ids) and (s.operation != "reuse" or uses_local_canvas(s)) and accepted_asset(root, s, brief) is None
    ]
    if missing:
        raise RuntimeError("Incomplete adaptive generation: " + ", ".join(missing))
