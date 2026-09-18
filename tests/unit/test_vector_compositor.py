"""Unit tests for the Vector Compositor module."""

import os
from pathlib import Path

from PIL import Image

from youtube_automation.video.vector_compositor import (
    composite_vector_overlays,
)


def test_composite_vector_overlays_e2e(tmp_path: Path):
    # Create base dummy image 640x360
    base_file = tmp_path / "base.png"
    img = Image.new("RGB", (640, 360), color=(50, 50, 50))
    img.save(base_file)

    out_file = tmp_path / "composited.png"
    overlays = [
        {"type": "ARROW", "start": (50, 50), "end": (150, 150), "width": 4},
        {"type": "FOCUS_BRACKET", "bbox": (200, 100, 400, 300)},
        {"type": "CALLOUT_BADGE", "text": "Focus Zone", "position": (220, 110)},
    ]

    res = composite_vector_overlays(base_file, out_file, overlays)
    assert os.path.exists(res)
    assert Path(res).stat().st_size > 0

    with Image.open(res) as out_img:
        assert out_img.size == (640, 360)
        assert out_img.mode == "RGB"
