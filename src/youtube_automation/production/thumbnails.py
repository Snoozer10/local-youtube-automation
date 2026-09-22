"""Channel-bound thumbnail prompts and immutable accepted image receipts."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from youtube_automation.core.utils import atomic_write_json
from youtube_automation.visuals.text_gate import _detect_via_pytesseract

from .assets import file_digest
from .contracts import Brief, fingerprint, load_brief
from .ledger import publication_guard
from .writing import verify_written_episode

RECEIPT = "adaptive_thumbnail_receipt.json"


def recipe(brief: Brief, script: str, titles: list[dict[str, Any]], model: str) -> str:
    return fingerprint({"version": 1, "brief": fingerprint(brief), "script": script, "titles": titles, "model": model})


def concept_prompt(brief: Brief, titles: list[dict[str, Any]], script: str) -> str:
    channel = brief.channel
    host = (
        f"Recurring host: {channel.host_description}. Use only when editorially relevant."
        if channel.host_mode == "CUSTOM_AVATAR"
        else "No recurring channel host or mascot. People may appear only when relevant to the episode subject."
    )
    return (
        "Design one distinct YouTube thumbnail concept for each numbered title. Return a JSON array only, "
        "with title_index, title_text, curiosity_archetype, scene, text_overlay and visual_recipe "
        "(lighting, color_palette, composition). Use one instantly legible focal idea per image and a "
        "truthful curiosity gap. The thumbnail should add information to its title, not repeat the title. "
        "Do not invent evidence, people, products or events. Reserve negative space for optional local "
        "typography; never ask the image model to draw text. Keep overlays to at most three words in "
        f"the channel language.\nChannel: {channel.name}. Audience: {channel.audience}. "
        f"Language: {channel.language}; dialect: {channel.dialect}. Tone: {channel.tone}. "
        f"Style: {channel.style}. {host}\n"
        f"Episode proposition: {brief.analysis.proposition}. Topics: {', '.join(brief.analysis.topics)}. "
        f"Narrative form: {brief.analysis.form}.\n"
        f"Titles: {json.dumps(titles, ensure_ascii=False)}\n"
        f"Script excerpt: {script[:6000]}"
    )


def image_prompt(brief: Brief, concept: dict[str, Any], negative_prompt: str) -> str:
    if not isinstance(concept.get("scene"), str) or not concept["scene"].strip():
        raise ValueError("Thumbnail concept needs a concrete scene")
    recipe_data = concept.get("visual_recipe", {})
    if not isinstance(recipe_data, dict):
        raise ValueError("Thumbnail visual_recipe must be an object")
    channel = brief.channel
    host = (
        f"If a recurring host appears, use this exact identity: {channel.host_description}. "
        if channel.host_mode == "CUSTOM_AVATAR"
        else "Do not insert a recurring channel host or mascot. "
    )
    return (
        f"Create a 16:9 YouTube thumbnail for {channel.name}. "
        f"Subject and action: {concept['scene']}. "
        f"Visual style: {channel.style}. Tone: {channel.tone}. {host}"
        f"Lighting: {recipe_data.get('lighting', 'clear subject separation')}. "
        f"Palette: {recipe_data.get('color_palette', 'channel-consistent colors')}. "
        f"Composition: {recipe_data.get('composition', 'one clear focal point')}. "
        "Keep the subject readable at phone size and reserve uncluttered negative space for optional "
        "local typography. Do not render any letters, words, logos or interface labels into "
        f"the image. NEGATIVE PROMPT: [{negative_prompt}]"
    )


def critique_prompt(brief: Brief, top_n: int) -> str:
    return (
        f"Review the title-thumbnail concepts for {brief.channel.name}. Select exactly {top_n} distinct "
        "title indices. Rank truthful title synergy, factual relevance to the script, one-second "
        "mobile legibility, visual variety, and consistency with the selected channel's style and "
        f"host policy ({brief.channel.host_mode}). Avoid sensational claims or invented visual evidence. "
        "Return only a JSON object with winners as integer title indices and improvements as an "
        "object keyed by title index. Improvements must preserve the channel policy and episode facts."
    )


def validate_concepts(concepts: Any, titles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(concepts, list) or len(concepts) != len(titles):
        raise ValueError("Thumbnail concept count must match selected titles")
    expected = {title["index"] for title in titles}
    seen: set[int] = set()
    for concept in concepts:
        if not isinstance(concept, dict):
            raise ValueError("Thumbnail concept must be an object")
        index = concept.get("title_index")
        if type(index) is not int or index not in expected or index in seen:
            raise ValueError("Thumbnail concept has an unknown or duplicate title index")
        if not isinstance(concept.get("scene"), str) or not concept["scene"].strip():
            raise ValueError("Thumbnail concept needs a concrete scene")
        overlay = concept.get("text_overlay", "")
        if not isinstance(overlay, str) or len(overlay.split()) > 3:
            raise ValueError("Thumbnail text overlay must have at most three words")
        seen.add(index)
    return concepts


def validate_critique(critique: Any, titles: list[dict[str, Any]], top_n: int) -> dict[str, Any]:
    if not isinstance(critique, dict):
        raise ValueError("Adaptive thumbnail critique must be a JSON object")
    winners = critique.get("winners")
    expected = {title["index"] for title in titles}
    if (
        not isinstance(winners, list)
        or len(winners) != min(top_n, len(titles))
        or any(type(index) is not int or index not in expected for index in winners)
        or len(set(winners)) != len(winners)
    ):
        raise ValueError("Adaptive thumbnail critique has invalid winners")
    improvements = critique.get("improvements", {})
    if not isinstance(improvements, dict) or any(
        key not in {str(index) for index in winners} or not isinstance(value, str)
        for key, value in improvements.items()
    ):
        raise ValueError("Adaptive thumbnail critique has invalid improvements")
    return {"winners": winners, "improvements": improvements}


def verify_image(path: Path) -> None:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
    if width < 640 or height < 360 or not 1.6 <= width / height <= 2.0:
        raise ValueError("Thumbnail image needs a usable landscape 16:9 composition")


def _journal_path(root: Path, expected_recipe: str) -> Path:
    return root / ".publication_journal" / "thumbnails" / f"{expected_recipe}.json"


def _remove_journal(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _validate_payload(root: Path, payload: dict[str, Any], expected_recipe: str) -> list[str]:
    if payload.get("version") != 1 or payload.get("recipe") != expected_recipe:
        raise ValueError("Thumbnail receipt is stale; use a fresh run for changed inputs")
    records = payload.get("images")
    if not isinstance(records, list) or not records:
        raise ValueError("Thumbnail receipt has no accepted images")
    images = []
    for item in records:
        target = (root / item["path"]).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            raise ValueError("Accepted thumbnail is missing or outside this run")
        if file_digest(target) != item["sha256"]:
            raise ValueError("Accepted thumbnail bytes changed")
        if item.get("ocr_status") != "passed":
            raise ValueError("Accepted thumbnail has no verified OCR gate")
        verify_image(target)
        images.append(str(target))
    return images


def _recover_pending(root: Path, expected_recipe: str) -> list[str] | None:
    journal = _journal_path(root, expected_recipe)
    try:
        pending = json.loads(journal.read_text(encoding="utf-8"))
        if pending.get("version") != 1 or pending.get("kind") != "thumbnail":
            return None
        payload = pending["receipt"]
        images = _validate_payload(root, payload, expected_recipe)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    with publication_guard():
        atomic_write_json(str(root / RECEIPT), payload)
    _remove_journal(journal)
    return images


def validate_receipt(root: str | Path, expected_recipe: str) -> list[str] | None:
    root = Path(root)
    path = root / RECEIPT
    if not path.exists():
        return _recover_pending(root, expected_recipe)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_payload(root, payload, expected_recipe)


def publish(
    root: str | Path,
    brief: Brief,
    script: str,
    titles: list[dict[str, Any]],
    model: str,
    generated: list[str],
) -> list[str]:
    root = Path(root)
    if not generated:
        raise ValueError("No verified thumbnail images to publish")
    verify_written_episode(root)
    if fingerprint(load_brief(root)) != fingerprint(brief):
        raise ValueError("Adaptive thumbnail brief changed during generation")
    if (root / "refined_script.txt").read_text(encoding="utf-8").strip() != script:
        raise ValueError("Adaptive thumbnail script changed during generation")
    accepted = root / "thumbnails" / "accepted"
    accepted.mkdir(parents=True, exist_ok=True)
    records = []
    for source_name in generated:
        source = Path(source_name)
        if not source.resolve().is_relative_to(root.resolve()):
            raise ValueError("Generated thumbnail must be inside the selected run")
        verify_image(source)
        ocr = _detect_via_pytesseract(
            str(source), {"MIN_BBOX": 0.00001, "MIN_TEXT_LEN": 1, "OCR_LANG": "eng+ara"}
        )
        if ocr is None:
            raise RuntimeError("Required thumbnail OCR is unavailable; no image accepted")
        if ocr:
            raise ValueError("Generated thumbnail contains detected text")
        digest = file_digest(source)
        target = accepted / f"{source.stem}-{digest[:16]}.png"
        if target.exists():
            if file_digest(target) != digest:
                raise ValueError("Accepted thumbnail digest collision")
        else:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=accepted, delete=False) as dst:
                    temporary = Path(dst.name)
                    with source.open("rb") as src:
                        shutil.copyfileobj(src, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
                if file_digest(temporary) != digest:
                    raise ValueError("Generated thumbnail changed while copying")
                with publication_guard():
                    os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        records.append(
            {"path": target.relative_to(root).as_posix(), "sha256": digest, "ocr_status": "passed"}
        )
    expected_recipe = recipe(brief, script, titles, model)
    payload = {"version": 1, "recipe": expected_recipe, "images": records}
    journal = _journal_path(root, expected_recipe)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with publication_guard():
        atomic_write_json(
            str(journal),
            {"version": 1, "kind": "thumbnail", "receipt": payload},
        )
        atomic_write_json(str(root / RECEIPT), payload)
    _remove_journal(journal)
    return _validate_payload(root, payload, expected_recipe)
