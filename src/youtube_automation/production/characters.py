"""Episode-owned character receipts; provider identity never substitutes for accepted bytes."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_serializer

from youtube_automation.core.utils import atomic_write_json

from .contracts import Brief, Contract, Digest, Identifier, Text, episode_cast, fingerprint
from .ledger import publication_guard


class CharacterPreview(Contract):
    path: Text
    sha256: Digest
    pixel_sha256: Digest


class CharacterImage(Contract):
    path: Text
    sha256: Digest
    pixel_sha256: Digest
    source_url: Text
    source_aliases: list[Text] = Field(default_factory=list, max_length=4)
    preview: CharacterPreview | None = None

    @model_serializer(mode="wrap")
    def serialize_image(self, handler: Any) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if not self.source_aliases:
            data.pop("source_aliases", None)
        if self.preview is None:
            data.pop("preview", None)
        return data


class CharacterReceipt(Contract):
    version: Literal[1] = 1
    character_id: Identifier
    definition_sha256: Digest
    recipe: Digest
    provider_id: Text
    provider_name: Text
    project_url: Text
    profile_index: Text
    portrait: CharacterImage
    body: CharacterImage | None = None


class CharacterSetupBlocked(RuntimeError):
    """A character receipt state requires stopping for explicit reconciliation."""


class CharacterProfileMismatch(CharacterSetupBlocked):
    """A canonical provider character is pinned to another Flow profile."""


class CharacterReceiptReconciliationRequired(CharacterSetupBlocked):
    """A character journal exists without the receipt that proves its result."""


def character_recipe(brief: Brief, character_id: str) -> str:
    character = episode_cast(brief)[character_id]
    return fingerprint({"version": 1, "character": character.model_dump(mode="json"), "style": brief.channel.style, "count": "1x"})


def character_provider_name(brief: Brief, character_id: str) -> str:
    return f"episode-{character_id}-{character_recipe(brief, character_id)[:12]}"


def read_character_receipt(
    root: Path, brief: Brief, character_id: str, *, profile_index: str | None = None,
    project_url: str | None = None,
) -> CharacterReceipt:
    from youtube_automation.visuals.asset_studio import flow_image_identity

    from .assets import file_digest, pixel_digest

    cast = episode_cast(brief)
    if character_id not in cast:
        raise ValueError(f"Unknown episode character: {character_id}")
    receipt = CharacterReceipt.model_validate_json(
        (root / "character_receipts" / f"{character_id}.json").read_text(encoding="utf-8")
    )
    if profile_index is not None and receipt.profile_index != profile_index:
        raise CharacterProfileMismatch(
            f"Character {character_id} is pinned to Flow profile {receipt.profile_index}, "
            f"not active profile {profile_index}"
        )
    if (
        receipt.character_id != character_id
        or receipt.definition_sha256 != fingerprint(cast[character_id])
        or receipt.recipe != character_recipe(brief, character_id)
        or receipt.provider_name != character_provider_name(brief, character_id)
        or (project_url is not None and receipt.project_url.split("/character")[0].rstrip("/") != project_url.split("/character")[0].rstrip("/"))
    ):
        raise ValueError(f"Character binding changed: {character_id}")
    for image in (receipt.portrait, receipt.body):
        if image is None:
            continue
        if any(not flow_image_identity(alias) for alias in image.source_aliases):
            raise ValueError(f"Character source alias is invalid: {character_id}")
        path = (root / image.path).resolve()
        if not path.is_relative_to(root.resolve()) or file_digest(path) != image.sha256 or pixel_digest(path) != image.pixel_sha256:
            raise ValueError(f"Character canonical image changed: {character_id}")
        if image.preview is not None:
            preview_path = (root / image.preview.path).resolve()
            if not preview_path.is_relative_to(root.resolve()) or file_digest(preview_path) != image.preview.sha256 or pixel_digest(preview_path) != image.preview.pixel_sha256:
                raise ValueError(f"Character preview image changed: {character_id}")
    return receipt


def _canonical_image_lineage(image: CharacterImage | None) -> dict[str, str] | None:
    if image is None:
        return None
    return {"sha256": image.sha256, "pixel_sha256": image.pixel_sha256}


def character_lineage(root: Path, brief: Brief, character_ids: list[str]) -> dict[str, str]:
    lineage = {}
    for character_id in character_ids:
        receipt = read_character_receipt(root, brief, character_id)
        lineage[character_id] = fingerprint({
            "character_id": receipt.character_id,
            "definition_sha256": receipt.definition_sha256,
            "recipe": receipt.recipe,
            "provider_id": receipt.provider_id,
            "provider_name": receipt.provider_name,
            "project_url": receipt.project_url,
            "profile_index": receipt.profile_index,
            "portrait": _canonical_image_lineage(receipt.portrait),
            "body": _canonical_image_lineage(receipt.body),
        })
    return lineage


def _required_character_ids(plan: Any, selected_ids: set[str] | None) -> set[str]:
    required = {character_id for shot in plan.shots for character_id in shot.character_ids}
    if selected_ids is None:
        return required
    selected = set(selected_ids)
    if not selected <= required:
        raise ValueError(f"Selected characters are outside the current plan: {sorted(selected - required)}")
    return selected


def resolve_character_project(
    root: Path,
    plan: Any,
    brief: Brief,
    *,
    profile_index: str,
    saved_project_url: str | None,
    character_ids: set[str] | None = None,
) -> str | None:
    """Recover only the selected plan characters' current-profile canonical project."""
    required = _required_character_ids(plan, character_ids)
    projects = {
        read_character_receipt(root, brief, character_id, profile_index=profile_index).project_url
        for character_id in required
        if (root / "character_receipts" / f"{character_id}.json").is_file()
    }
    import re
    normalized_saved = None
    if saved_project_url:
        match = re.search(r"https://flow\.google\.com/project/[a-zA-Z0-9_-]+", saved_project_url)
        normalized_saved = match.group(0) if match else saved_project_url
    if len(projects) > 1 or (projects and normalized_saved and normalized_saved not in projects):
        raise ValueError("Saved workspace conflicts with the canonical character project")
    return normalized_saved or next(iter(projects), None)


def _preserve_image(root: Path, path: Path, source_url: str) -> CharacterImage:
    from .assets import file_digest, pixel_digest

    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Character candidate escapes the run")
    digest, pixels = file_digest(path), pixel_digest(path)
    store = root / "accepted_characters"
    store.mkdir(exist_ok=True)
    target = store / f"{digest}.png"
    with tempfile.NamedTemporaryFile(dir=store, delete=False) as handle:
        temporary = Path(handle.name)
        with path.open("rb") as source:
            shutil.copyfileobj(source, handle)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if file_digest(temporary) != digest or pixel_digest(temporary) != pixels:
            raise ValueError("Character candidate changed during publication")
        with publication_guard():
            os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return CharacterImage(path=str(target.relative_to(root)), sha256=digest, pixel_sha256=pixels, source_url=source_url)


def ensure_episode_characters(
    page: Any,
    root: Path,
    plan: Any,
    brief: Brief,
    *,
    profile_index: str,
    project_url: str,
    character_ids: set[str] | None = None,
) -> None:
    """Only explicit episode cast enters Characters; failed/uncertain creation needs review."""
    from youtube_automation.visuals.asset_studio import (
        capture_episode_character_alias,
        create_episode_character,
        preflight_episode_character,
    )

    from .visual_gate import reserve_flow_submission

    required = sorted(_required_character_ids(plan, character_ids))
    for character_id in required:
        receipt_path = root / "character_receipts" / f"{character_id}.json"
        if receipt_path.exists():
            receipt = read_character_receipt(root, brief, character_id, profile_index=profile_index, project_url=project_url)
            if receipt.body is None and receipt.portrait.preview is None:
                original = receipt_path.read_bytes()
                output = root / ".character_candidates" / character_id
                alias = capture_episode_character_alias(
                    page, receipt.provider_name, receipt.provider_id, receipt.portrait.source_url,
                    receipt.portrait.pixel_sha256, output,
                )
                preview = _preserve_image(root, output / "alias_ingredient_preview.png", alias)
                receipt.portrait.preview = CharacterPreview(path=preview.path, sha256=preview.sha256, pixel_sha256=preview.pixel_sha256)
                if alias != receipt.portrait.source_url:
                    receipt.portrait.source_aliases = [alias]
                with publication_guard():
                    if receipt_path.read_bytes() != original:
                        raise RuntimeError("Character receipt changed during alias proof")
                    (output / ("receipt_before_alias_" + fingerprint(json.loads(original)) + ".json")).write_bytes(original)
                    atomic_write_json(str(receipt_path), receipt.model_dump(mode="json"))
            continue
        character = episode_cast(brief)[character_id]
        journal = root / ".publication_journal" / "characters" / f"{character_id}.json"
        if journal.exists():
            raise CharacterReceiptReconciliationRequired(
                f"Character creation journal exists without its receipt; manual reconciliation "
                f"is required before retry: {character_id}"
            )
        # UI capability failures precede durable send intent and never consume spending.
        try:
            preflight_episode_character(page)
        except Exception:
            page.goto(project_url, wait_until="domcontentloaded", timeout=45000)
            raise
        journal.parent.mkdir(parents=True, exist_ok=True)
        state: dict[str, Any] = {"version": 1, "character_id": character_id, "recipe": character_recipe(brief, character_id), "state": "preparing", "profile_index": profile_index, "project_url": project_url}
        with publication_guard():
            atomic_write_json(str(journal), state)

        def reserve(stage: str, state: dict[str, Any] = state, journal: Path = journal) -> None:
            reserve_flow_submission(root, plan)
            state.update(state="submission_pending", stage=stage)
            with publication_guard():
                atomic_write_json(str(journal), state)

        created = create_episode_character(
            page, character_provider_name(brief, character_id), character.description,
            brief.channel.style, root / ".character_candidates" / character_id, reserve,
        )
        body_path = created.get("body_path")
        body_url = created.get("body_url")
        if body_path and body_url is None:
            raise CharacterSetupBlocked("Created character body has no provider image URL")
        receipt = CharacterReceipt(
            character_id=character_id, definition_sha256=fingerprint(character), recipe=state["recipe"],
            provider_id=created["provider_id"], provider_name=character_provider_name(brief, character_id),
            project_url=project_url, profile_index=profile_index,
            portrait=_preserve_image(root, Path(created["portrait_path"]), created["portrait_url"]),
            body=_preserve_image(root, Path(body_path), body_url) if body_path and body_url is not None else None,
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with publication_guard():
            atomic_write_json(str(receipt_path), receipt.model_dump(mode="json"))
        read_character_receipt(root, brief, character_id, profile_index=profile_index, project_url=project_url)
        state.update(state="completed")
        with publication_guard():
            atomic_write_json(str(journal), state)
        page.goto(project_url, wait_until="domcontentloaded", timeout=45000)
        if page.url != project_url:
            raise RuntimeError("Character setup could not restore its exact Flow project")
