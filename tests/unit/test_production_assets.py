import json

import pytest
from PIL import Image

from youtube_automation.production import assets


def test_strict_background_requires_actual_ocr_and_rejects_any_region(tmp_path, monkeypatch):
    path = tmp_path / "frame.png"
    Image.new("RGB", (640, 360), "white").save(path)
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: None)
    with pytest.raises(RuntimeError, match="unavailable"):
        assets.validate_background(path)
    monkeypatch.setattr(
        assets, "_detect_via_pytesseract", lambda *_: [{"text": "X: 180", "bbox": [0, 0, 80, 12]}]
    )
    with pytest.raises(ValueError, match="text"):
        assets.validate_background(path)
    monkeypatch.setattr(assets, "_detect_via_pytesseract", lambda *_: [])
    assert assets.validate_background(path) == (640, 360)


def test_corrupt_image_is_not_accepted(tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"not an image" * 200)
    with pytest.raises(OSError):
        assets.validate_background(path)


def test_asset_receipt_geometry_must_match_accepted_pixels(tmp_path):
    accepted = tmp_path / "accepted_assets"
    receipts = tmp_path / "asset_receipts"
    accepted.mkdir()
    receipts.mkdir()
    image = accepted / "asset.png"
    Image.new("RGB", (640, 360), "blue").save(image)
    payload = {
        "asset_id": "asset",
        "path": "accepted_assets/asset.png",
        "sha256": assets.file_digest(image),
        "pixel_sha256": assets.pixel_digest(image),
        "dimensions": [640, 360],
        "technical_status": "verified",
        "version": 1,
    }
    path = receipts / "asset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert assets.read_receipt(tmp_path, "asset")["dimensions"] == [640, 360]
    payload["dimensions"] = [1920, 1080]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="geometry or pixels changed"):
        assets.read_receipt(tmp_path, "asset")
    payload["dimensions"] = [640, 360]
    payload["pixel_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="geometry or pixels changed"):
        assets.read_receipt(tmp_path, "asset")
