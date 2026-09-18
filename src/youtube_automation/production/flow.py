"""Adapt editorial shots to the existing Flow worker without feed-position guesses."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Page

from youtube_automation.core.utils import atomic_write_json

from .assets import accepted_asset, pixel_digest, read_receipt
from .contracts import Brief, load_brief
from .ledger import publication_guard
from .shots import ShotPlan, ensure_shot_plan, generation_prompt


def prepare_flow(root: Path, ask: Callable[[str], str]) -> tuple[ShotPlan, Brief]:
    brief = load_brief(root)
    plan = ensure_shot_plan(root, ask)
    generated = [s for s in plan.shots if s.operation != "reuse"]
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
    )
    from youtube_automation.visuals.image_extractor import extract_high_res_image

    receipt = read_receipt(root, asset_id)
    if not receipt["source_url"] or receipt["project_url"] != page.url:
        raise RuntimeError(
            f"Reference {asset_id} is not available in this Flow project; restore its exact asset before continuing"
        )
    candidates = [
        loc
        for loc in page.locator("img").all()
        if loc.get_attribute("src") == receipt["source_url"] and loc.is_visible()
    ]
    if not candidates:
        raise RuntimeError(f"Verified reference {asset_id} is absent from the Flow workspace")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
        path = temp.name
    try:
        for candidate in candidates:
            if not extract_high_res_image(page, candidate, path, min_size_kb=1):
                continue
            if pixel_digest(path) != receipt["pixel_sha256"]:
                continue
            clear_attached_prompt_chips(page)
            if count_attached_prompt_chips(page) != 0:
                raise RuntimeError("Could not clear unrelated Flow references")
            if not _click_add_to_prompt_on_image(page, candidate):
                raise RuntimeError("Could not attach verified Flow reference")
            if count_attached_prompt_chips(page) != 1:
                raise RuntimeError("Flow reference attachment did not verify")
            return
        raise RuntimeError(f"Reference content differs from the accepted asset: {asset_id}")
    finally:
        if os.path.exists(path):
            os.unlink(path)


def verify_generated_assets(root: Path, plan: ShotPlan, brief: Brief) -> None:
    missing = [
        s.asset_id
        for s in plan.shots
        if s.operation != "reuse" and accepted_asset(root, s, brief) is None
    ]
    if missing:
        raise RuntimeError("Incomplete adaptive generation: " + ", ".join(missing))
