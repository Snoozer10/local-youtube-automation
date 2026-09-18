"""Vector Compositor Module.

Implements the PIL vector pre-pass for directional arrows, focus brackets,
and highlight callout boxes, outputting composited images.
Preserves strictly 1 input stream per clip in FFmpeg, completely avoiding
multi-stream chunk filtergraph crashes under Intel QSV (QSV_LOOKAHEAD=0, format=nv12).
"""

from __future__ import annotations

import math
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def draw_directional_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int, int] = (224, 159, 62, 230),
    width: int = 6,
    arrow_size: float = 24.0,
) -> None:
    """Draws an anti-aliased directional arrow from start to end with an arrowhead."""
    draw.line([start, end], fill=color, width=width)

    # Calculate angle for arrowhead
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.atan2(dy, dx)

    # Left and right wings of arrowhead (30 degrees from stem)
    wing_angle = math.radians(30)
    p1 = (
        end[0] - arrow_size * math.cos(angle - wing_angle),
        end[1] - arrow_size * math.sin(angle - wing_angle),
    )
    p2 = (
        end[0] - arrow_size * math.cos(angle + wing_angle),
        end[1] - arrow_size * math.sin(angle + wing_angle),
    )

    draw.polygon([end, p1, p2], fill=color)


def draw_focus_brackets(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[float, float, float, float],
    color: tuple[int, int, int, int] = (224, 159, 62, 230),
    bracket_len: float = 40.0,
    width: int = 4,
) -> None:
    """Draws 4 corner focus brackets around a bounding box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = bbox

    # Top-Left Corner
    draw.line([(x0, y0), (x0 + bracket_len, y0)], fill=color, width=width)
    draw.line([(x0, y0), (x0, y0 + bracket_len)], fill=color, width=width)

    # Top-Right Corner
    draw.line([(x1, y0), (x1 - bracket_len, y0)], fill=color, width=width)
    draw.line([(x1, y0), (x1, y0 + bracket_len)], fill=color, width=width)

    # Bottom-Left Corner
    draw.line([(x0, y1), (x0 + bracket_len, y1)], fill=color, width=width)
    draw.line([(x0, y1), (x0, y1 - bracket_len)], fill=color, width=width)

    # Bottom-Right Corner
    draw.line([(x1, y1), (x1 - bracket_len, y1)], fill=color, width=width)
    draw.line([(x1, y1), (x1 - bracket_len, y1)], fill=color, width=width)


def draw_callout_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple[float, float],
    bg_color: tuple[int, int, int, int] = (30, 30, 36, 220),
    text_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    padding: int = 12,
    font: Any = None,
) -> None:
    """Draws a rounded dark rectangular badge with a callout label."""
    if font is None:
        font = ImageFont.load_default()

    # Calculate text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x, y = position
    rect_box = (
        x - padding,
        y - padding,
        x + text_w + padding,
        y + text_h + padding,
    )

    draw.rounded_rectangle(rect_box, radius=8, fill=bg_color, outline=(224, 159, 62, 200), width=2)
    draw.text((x, y), text, fill=text_color, font=font)


def composite_vector_overlays(
    base_image_path: str | Path,
    output_image_path: str | Path,
    overlays: Sequence[dict[str, Any]] | None = None,
) -> str:
    """Composites vector shapes onto a base image and writes to output atomically."""
    base_p = Path(base_image_path)
    out_p = Path(output_image_path)

    if not base_p.exists():
        raise FileNotFoundError(f"Base image not found: {base_p}")

    with Image.open(base_p) as img:
        base_img = img.convert("RGBA")
        overlay_canvas = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_canvas)

        if overlays:
            for ov in overlays:
                ov_type = str(ov.get("type", "")).upper()
                if ov_type == "ARROW":
                    start = tuple(ov.get("start", (100, 100)))
                    end = tuple(ov.get("end", (300, 300)))
                    color = tuple(ov.get("color", (224, 159, 62, 230)))
                    width = int(ov.get("width", 6))
                    draw_directional_arrow(draw, start, end, color=color, width=width)  # type: ignore
                elif ov_type == "FOCUS_BRACKET":
                    bbox = tuple(ov.get("bbox", (200, 200, 600, 600)))
                    color = tuple(ov.get("color", (224, 159, 62, 230)))
                    draw_focus_brackets(draw, bbox, color=color)  # type: ignore
                elif ov_type == "CALLOUT_BADGE":
                    text = str(ov.get("text", ""))
                    pos = tuple(ov.get("position", (100, 100)))
                    draw_callout_badge(draw, text, pos)  # type: ignore

        # Composite and convert back to RGB
        composited = Image.alpha_composite(base_img, overlay_canvas).convert("RGB")

        # Atomic write
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", dir=out_p.parent, delete=False, suffix=".png") as tf:
            composited.save(tf, format="PNG")
            temp_name = tf.name

        os.replace(temp_name, out_p)
        return str(out_p)
