"""Content-bound receipts for generated backgrounds, distinct from editorial approval."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from youtube_automation.core.utils import atomic_write_json, get_config_value
from youtube_automation.visuals.text_gate import _detect_via_pytesseract

from .contracts import Brief, fingerprint
from .ledger import publication_guard
from .shots import Shot, generation_prompt

_PUBLICATION_JOURNAL_VERSION = 1


def file_digest(path: str | Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def image_identity(path: str | Path) -> tuple[tuple[int, int], str]:
    with Image.open(path) as image:
        image.load()
        return image.size, hashlib.sha256(
            str(image.size).encode() + image.convert("RGB").tobytes()
        ).hexdigest()


def pixel_digest(path: str | Path) -> str:
    return image_identity(path)[1]


def validate_background(path: str | Path) -> tuple[int, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        size = image.size
    if min(size) < 256:
        raise ValueError("Background is too small for a video shot")
    boxes = _detect_via_pytesseract(
        str(path), {"MIN_BBOX": 0.00001, "MIN_TEXT_LEN": 1, "OCR_LANG": "eng+ara"}
    )
    if boxes is None:
        raise RuntimeError("Required background OCR is unavailable; asset remains unverified")
    if boxes:
        raise ValueError("Generated background contains detected text")
    return size


def recipe(shot: Shot, brief: Brief, reference_hash: str | None) -> str:
    return fingerprint(
        {
            "version": 2,
            "prompt": generation_prompt(shot, brief),
            "reference": reference_hash,
            "entities": shot.entity_ids,
            "model": get_config_value("FLOW_IMAGE_MODEL", "Nano Banana 2"),
            "count": get_config_value("FLOW_IMAGE_COUNT", "1x"),
        }
    )


def _validate_receipt_payload(
    root: Path, asset_id: str, receipt: dict[str, Any]
) -> dict[str, Any]:
    if receipt.get("version") != 1:
        raise ValueError("Unsupported asset receipt version")
    image = (root / receipt["path"]).resolve()
    if not image.is_relative_to(root.resolve()):
        raise ValueError("Asset receipt escapes its run")
    if receipt["asset_id"] != asset_id or file_digest(image) != receipt["sha256"]:
        raise ValueError("Asset receipt content mismatch")
    dimensions, pixels = image_identity(image)
    if list(dimensions) != receipt.get("dimensions") or pixels != receipt.get("pixel_sha256"):
        raise ValueError("Asset receipt image geometry or pixels changed")
    if receipt["technical_status"] != "verified":
        raise ValueError("Asset has not passed technical validation")
    return receipt


def read_receipt(root: Path, asset_id: str) -> dict[str, Any]:
    path = root / "asset_receipts" / f"{asset_id}.json"
    receipt: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return _validate_receipt_payload(root, asset_id, receipt)


def _journal_path(root: Path, asset_id: str) -> Path:
    return root / ".publication_journal" / "assets" / f"{asset_id}.json"


def _remove_journal(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # A valid active receipt wins. A leftover journal is revalidated on the next run.
        pass


def _recover_pending_asset(
    root: Path,
    asset_id: str,
    *,
    expected_recipe: str,
    expected_reference: str | None,
) -> dict[str, Any] | None:
    journal = _journal_path(root, asset_id)
    try:
        pending: dict[str, Any] = json.loads(journal.read_text(encoding="utf-8"))
        receipt = pending["receipt"]
        if (
            pending.get("version") != _PUBLICATION_JOURNAL_VERSION
            or pending.get("kind") != "asset"
            or not isinstance(receipt, dict)
            or receipt.get("recipe") != expected_recipe
            or receipt.get("reference_sha256") != expected_reference
        ):
            return None
        validated = _validate_receipt_payload(root, asset_id, receipt)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    destination = root / "asset_receipts"
    destination.mkdir(exist_ok=True)
    with publication_guard():
        atomic_write_json(str(destination / f"{asset_id}.json"), validated)
    _remove_journal(journal)
    return read_receipt(root, asset_id)


def accepted_asset(root: Path, shot: Shot, brief: Brief) -> dict[str, Any] | None:
    try:
        ref = (
            read_receipt(root, shot.reference_asset_id)["sha256"]
            if shot.reference_asset_id
            else None
        )
    except (OSError, KeyError, ValueError):
        return None
    expected_recipe = recipe(shot, brief, ref)
    try:
        receipt = read_receipt(root, shot.asset_id)
        if receipt["recipe"] == expected_recipe:
            return receipt
    except (OSError, KeyError, ValueError):
        pass
    return _recover_pending_asset(
        root,
        shot.asset_id,
        expected_recipe=expected_recipe,
        expected_reference=ref,
    )


def register_asset(
    root: Path, shot: Shot, brief: Brief, path: Path, *, source_url: str = "", project_url: str = ""
) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Generated assets must be inside the selected run")
    dimensions = validate_background(path)
    reference = (
        read_receipt(root, shot.reference_asset_id)["sha256"] if shot.reference_asset_id else None
    )
    # Preserve accepted bytes even when the provider adapter overwrites its candidate path.
    digest = file_digest(path)
    store = root / "accepted_assets"
    store.mkdir(exist_ok=True)
    accepted = store / (digest + ".png")
    candidate_dimensions, candidate_pixels = image_identity(path)
    if candidate_dimensions != dimensions:
        raise ValueError("Candidate geometry changed during asset registration")
    receipt = {
        "version": 1,
        "asset_id": shot.asset_id,
        "path": str(accepted.resolve().relative_to(root.resolve())),
        "sha256": digest,
        "pixel_sha256": candidate_pixels,
        "dimensions": list(dimensions),
        "reference_sha256": reference,
        "recipe": recipe(shot, brief, reference),
        "prompt": generation_prompt(shot, brief),
        "source_url": source_url,
        "project_url": project_url,
        "technical_status": "verified",
        "editorial_status": "pending",
    }
    journal = _journal_path(root, shot.asset_id)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with publication_guard():
        atomic_write_json(
            str(journal),
            {
                "version": _PUBLICATION_JOURNAL_VERSION,
                "kind": "asset",
                "receipt": receipt,
            },
        )
    if not accepted.exists() or file_digest(accepted) != digest:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=store, delete=False) as handle:
                temporary = Path(handle.name)
                with path.open("rb") as source:
                    shutil.copyfileobj(source, handle)
                handle.flush()
                os.fsync(handle.fileno())
            if file_digest(temporary) != digest or image_identity(temporary) != (
                dimensions,
                candidate_pixels,
            ):
                raise ValueError("Candidate changed during asset registration")
            with publication_guard():
                os.replace(temporary, accepted)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    _validate_receipt_payload(root, shot.asset_id, receipt)
    destination = root / "asset_receipts"
    destination.mkdir(exist_ok=True)
    with publication_guard():
        atomic_write_json(str(destination / f"{shot.asset_id}.json"), receipt)
    _remove_journal(journal)
    return receipt
