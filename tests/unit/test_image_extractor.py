"""Unit tests for image_extractor.py extraction and validation engine."""

import os
from unittest.mock import MagicMock

import pytest
from PIL import Image

from youtube_automation.visuals.image_extractor import (
    extract_high_res_image,
    save_binary_image_data,
    validate_image_file,
)


@pytest.fixture
def temp_image_dir(tmp_path):
    return tmp_path


def test_validate_image_file_nonexistent():
    assert not validate_image_file("nonexistent_path_file.png")


def test_validate_image_file_too_small(temp_image_dir):
    small_path = str(temp_image_dir / "small.png")
    with open(small_path, "wb") as f:
        f.write(b'tiny')
    assert not validate_image_file(small_path, min_size_kb=20)


def test_validate_image_file_blank_canvas_rejected(temp_image_dir):
    blank_path = str(temp_image_dir / "blank.png")
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    img.save(blank_path)
    assert not validate_image_file(blank_path, min_size_kb=0)


def test_validate_image_file_valid_content(temp_image_dir):
    valid_path = str(temp_image_dir / "valid.png")
    img = Image.new("RGB", (200, 200), (255, 128, 0))
    img.save(valid_path)
    assert validate_image_file(valid_path, min_size_kb=0)


def test_save_binary_image_data(temp_image_dir):
    valid_path = str(temp_image_dir / "saved.png")
    img = Image.new("RGB", (200, 200), (100, 200, 50))
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    success = save_binary_image_data(raw_bytes, valid_path, min_size_kb=0)
    assert success
    assert os.path.exists(valid_path)


def test_extract_high_res_image_tier1_base64(temp_image_dir):
    save_path = str(temp_image_dir / "tier1.png")
    img = Image.new("RGB", (200, 200), (12, 34, 56))
    import base64
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_str = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

    mock_locator = MagicMock()
    mock_locator.get_attribute.return_value = b64_str
    mock_page = MagicMock()

    success = extract_high_res_image(mock_page, mock_locator, save_path, min_size_kb=0)
    assert success
    assert os.path.exists(save_path)


def test_extract_high_res_image_tier2a_network_stream(temp_image_dir):
    save_path = str(temp_image_dir / "tier2a.png")
    img = Image.new("RGB", (200, 200), (99, 88, 77))
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    mock_locator = MagicMock()
    mock_locator.get_attribute.return_value = "https://flow-content.google/image/abc12345"

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.body.return_value = raw_bytes

    mock_page = MagicMock()
    mock_page.url = "https://flow.google.com/project/123"
    mock_page.request.get.return_value = mock_response

    success = extract_high_res_image(mock_page, mock_locator, save_path, min_size_kb=0)
    assert success
    assert os.path.exists(save_path)
    mock_page.request.get.assert_called_once()
