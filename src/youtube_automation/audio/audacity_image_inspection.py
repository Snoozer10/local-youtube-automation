"""Technical inspection of an owned Audacity window capture.

This module verifies capture identity and BMP structure. It does not decide
whether the window's visual content is editorially acceptable.
"""

from __future__ import annotations

import hashlib
import json
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_IMAGE_PIXELS = 32_000_000
_BMP_FILE_HEADER = struct.Struct("<2sIHHI")
_BMP_INFO_HEADER = struct.Struct("<IiiHHIIiiII")


class ImageInspectionError(ValueError):
    """Raised when a screenshot cannot prove a current owned ready window."""


def inspect_owned_capture(
    capture: dict[str, Any], identity: dict[str, Any]
) -> dict[str, Any]:
    """Validate a current owned-window BMP and return a technical receipt."""
    if identity.get("ready_state") != "ready":
        raise ImageInspectionError("capture_not_from_ready_window")
    observations = identity.get("ready_observations")
    if type(observations) is not int or observations < 2:
        raise ImageInspectionError("ready_window_proof_incomplete")
    snapshot = identity.get("ready_window_snapshot")
    if not isinstance(snapshot, dict):
        raise ImageInspectionError("ready_window_proof_invalid")
    snapshot_sha256 = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if identity.get("ready_snapshot_sha256") != snapshot_sha256:
        raise ImageInspectionError("ready_window_proof_hash_mismatch")
    if any(
        snapshot.get(key) != identity.get(identity_key)
        for key, identity_key in (
            ("pid", "pid"),
            ("creation_time", "creation_time"),
            ("executable", "executable"),
        )
    ):
        raise ImageInspectionError("ready_window_identity_mismatch")
    windows = snapshot.get("windows")
    if (
        not isinstance(windows, list)
        or any(not isinstance(item, dict) for item in windows)
    ):
        raise ImageInspectionError("ready_window_snapshot_invalid")
    visible = [item for item in windows if item.get("visible") is True]
    if (
        any(item.get("pid") != identity.get("pid") for item in windows)
        or len(visible) != 1
        or visible[0].get("hwnd") != identity.get("hwnd")
        or visible[0].get("role") != "main"
        or visible[0].get("modal") is not False
    ):
        raise ImageInspectionError("ready_window_snapshot_not_unique_main")

    capture_dir = Path(identity["capture_dir"])
    if capture_dir.is_symlink():
        raise ImageInspectionError("capture_path_is_symlink")
    try:
        expected_capture_dir = capture_dir.resolve(strict=True)
    except OSError:
        raise ImageInspectionError("capture_directory_invalid") from None
    if not expected_capture_dir.is_dir():
        raise ImageInspectionError("capture_directory_invalid")
    image_path = Path(capture["image_path"])
    if image_path.is_symlink():
        raise ImageInspectionError("capture_path_is_symlink")
    try:
        resolved_image = image_path.resolve(strict=True)
    except OSError:
        raise ImageInspectionError("capture_file_missing") from None
    if resolved_image.parent != expected_capture_dir or image_path.suffix.lower() != ".bmp":
        raise ImageInspectionError("capture_path_outside_run")
    if image_path != resolved_image:
        raise ImageInspectionError("capture_path_not_canonical")

    max_bytes = MAX_IMAGE_PIXELS * 4 + 1_048_576
    try:
        image_size = resolved_image.stat().st_size
        if image_size <= 0 or image_size > max_bytes:
            raise ImageInspectionError("capture_extent_invalid")
        with resolved_image.open("rb") as source:
            image = source.read(max_bytes + 1)
    except ImageInspectionError:
        raise
    except OSError:
        raise ImageInspectionError("capture_read_failed") from None
    if len(image) != image_size or len(image) > max_bytes:
        raise ImageInspectionError("capture_extent_invalid")
    image_sha256 = hashlib.sha256(image).hexdigest()
    if capture.get("sha256") != image_sha256:
        raise ImageInspectionError("capture_hash_mismatch")
    width, height, pixel_bytes = _bmp_dimensions(image)
    if (capture.get("width"), capture.get("height")) != (width, height):
        raise ImageInspectionError("capture_dimensions_mismatch")
    if (
        capture.get("pid") != identity.get("pid")
        or capture.get("creation_time") != identity.get("creation_time")
    ):
        raise ImageInspectionError("capture_identity_mismatch")
    if capture.get("hwnd") != identity.get("hwnd"):
        raise ImageInspectionError("capture_window_mismatch")
    captured_utc = capture.get("utc")
    if not isinstance(captured_utc, str) or not captured_utc:
        raise ImageInspectionError("capture_time_missing")

    return {
        "schema": 1,
        "run_id": identity["run_id"],
        "approved": True,
        "reviewer": "local_owned_window_bmp_verifier",
        "inspected_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "inspection_kind": "owned_window_technical",
        "ready_state": "ready",
        "ready_observations": observations,
        "ready_snapshot_sha256": snapshot_sha256,
        "pid": identity["pid"],
        "creation_time": identity["creation_time"],
        "executable": identity["executable"],
        "executable_sha256": identity["executable_sha256"],
        "hwnd": identity["hwnd"],
        "captured_utc": captured_utc,
        "image_sha256": image_sha256,
        "image_path": str(resolved_image),
        "image_format": "BMP",
        "width": width,
        "height": height,
        "pixel_bytes": pixel_bytes,
    }


def _bmp_dimensions(image: bytes) -> tuple[int, int, int]:
    """Parse a bounded uncompressed 24/32-bit BMP and prove pixel extent."""
    if len(image) < _BMP_FILE_HEADER.size + _BMP_INFO_HEADER.size:
        raise ImageInspectionError("bmp_header_truncated")
    magic, file_size, reserved1, reserved2, pixel_offset = _BMP_FILE_HEADER.unpack_from(image)
    dib_size, width, signed_height, planes, bits, compression, image_size, *_ = (
        _BMP_INFO_HEADER.unpack_from(image, _BMP_FILE_HEADER.size)
    )
    if magic != b"BM" or file_size != len(image) or reserved1 or reserved2:
        raise ImageInspectionError("bmp_header_invalid")
    if dib_size < _BMP_INFO_HEADER.size or dib_size > 124:
        raise ImageInspectionError("bmp_header_unsupported")
    if width <= 0 or signed_height == 0 or planes != 1 or bits not in (24, 32) or compression != 0:
        raise ImageInspectionError("bmp_format_unsupported")
    height = abs(signed_height)
    pixels = width * height
    if pixels > MAX_IMAGE_PIXELS:
        raise ImageInspectionError("bmp_dimensions_exceed_limit")
    row_bytes = ((width * bits + 31) // 32) * 4
    pixel_bytes = row_bytes * height
    minimum_offset = _BMP_FILE_HEADER.size + dib_size
    if pixel_offset < minimum_offset or pixel_offset > len(image):
        raise ImageInspectionError("bmp_pixel_offset_invalid")
    if pixel_offset + pixel_bytes != len(image):
        raise ImageInspectionError("bmp_pixel_extent_invalid")
    if image_size not in (0, pixel_bytes):
        raise ImageInspectionError("bmp_image_size_invalid")
    if not any(image[pixel_offset:]):
        raise ImageInspectionError("bmp_pixels_empty")
    return width, height, pixel_bytes


__all__ = ["ImageInspectionError", "inspect_owned_capture"]
