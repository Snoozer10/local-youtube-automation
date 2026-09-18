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
