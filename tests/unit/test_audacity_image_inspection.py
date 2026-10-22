"""Offline tests for the bounded technical Audacity screenshot verifier."""

from __future__ import annotations

import hashlib
import json
import struct

import pytest

from youtube_automation.audio.audacity_image_inspection import (
    ImageInspectionError,
    inspect_owned_capture,
)


def _bmp(width: int = 2, height: int = 2) -> bytes:
    row_size = ((width * 24 + 31) // 32) * 4
    pixels = bytes([1, 2, 3] * width + [0] * (row_size - width * 3)) * height
    offset = 54
    size = offset + len(pixels)
    return (
        struct.pack("<2sIHHI", b"BM", size, 0, 0, offset)
        + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 0, 0, 0, 0)
        + pixels
    )


def _fixture(tmp_path, *, ready_state="ready", width=2, height=2):
    capture_dir = tmp_path / "capture"
    capture_dir.mkdir()
    image_path = capture_dir / "owned-window.bmp"
    image = _bmp(width, height)
    image_path.write_bytes(image)
    capture = {
        "image_path": str(image_path),
        "sha256": hashlib.sha256(image).hexdigest(),
        "pid": 123,
        "creation_time": "2026-10-13T00:00:00Z",
        "hwnd": 456,
        "utc": "2026-10-13T00:00:01Z",
        "width": width,
        "height": height,
    }
    snapshot = {
        "pid": 123,
        "creation_time": "2026-10-13T00:00:00Z",
        "executable": "audacity.exe",
        "windows": [
            {"hwnd": 456, "pid": 123, "role": "main", "visible": True, "modal": False}
        ],
    }
    identity = {
        "run_id": tmp_path.name,
        "ready_state": ready_state,
        "ready_observations": 3,
        "ready_window_snapshot": snapshot,
        "ready_snapshot_sha256": hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "capture_dir": str(capture_dir),
        "pid": 123,
        "creation_time": "2026-10-13T00:00:00Z",
        "executable": "audacity.exe",
        "executable_sha256": "a" * 64,
        "hwnd": 456,
    }
    return capture, identity, image


def test_owned_bmp_receipt_binds_hash_dimensions_and_ready_proof(tmp_path):
    capture, identity, image = _fixture(tmp_path)

    receipt = inspect_owned_capture(capture, identity)

    assert receipt["run_id"] == tmp_path.name
    assert receipt["image_sha256"] == hashlib.sha256(image).hexdigest()
    assert (receipt["width"], receipt["height"]) == (2, 2)
    assert receipt["ready_state"] == "ready"
    assert receipt["ready_observations"] == 3
    assert receipt["inspection_kind"] == "owned_window_technical"


@pytest.mark.parametrize("state", ["welcome", "recovery", "unknown_modal", "exited"])
def test_nonready_state_cannot_produce_inspection(tmp_path, state):
    capture, identity, _ = _fixture(tmp_path, ready_state=state)

    with pytest.raises(ImageInspectionError, match="capture_not_from_ready_window"):
        inspect_owned_capture(capture, identity)


def test_capture_hash_mismatch_is_rejected(tmp_path):
    capture, identity, _ = _fixture(tmp_path)
    capture["sha256"] = "0" * 64

    with pytest.raises(ImageInspectionError, match="capture_hash_mismatch"):
        inspect_owned_capture(capture, identity)


def test_capture_dimension_mismatch_is_rejected(tmp_path):
    capture, identity, _ = _fixture(tmp_path)
    capture["width"] = 3

    with pytest.raises(ImageInspectionError, match="capture_dimensions_mismatch"):
        inspect_owned_capture(capture, identity)


def test_capture_outside_run_directory_is_rejected(tmp_path):
    capture, identity, image = _fixture(tmp_path)
    outside_image = tmp_path / "other.bmp"
    outside_image.write_bytes(image)
    capture["image_path"] = str(outside_image)

    with pytest.raises(ImageInspectionError, match="capture_path_outside_run"):
        inspect_owned_capture(capture, identity)


def test_incomplete_ready_observation_proof_is_rejected(tmp_path):
    capture, identity, _ = _fixture(tmp_path)
    identity["ready_observations"] = 1

    with pytest.raises(ImageInspectionError, match="ready_window_proof_incomplete"):
        inspect_owned_capture(capture, identity)


def test_tampered_ready_snapshot_digest_is_rejected(tmp_path):
    capture, identity, _ = _fixture(tmp_path)
    identity["ready_snapshot_sha256"] = "0" * 64

    with pytest.raises(ImageInspectionError, match="ready_window_proof_hash_mismatch"):
        inspect_owned_capture(capture, identity)


def test_missing_capture_path_fails_closed(tmp_path):
    capture, identity, _ = _fixture(tmp_path)
    (tmp_path / "capture" / "owned-window.bmp").unlink()

    with pytest.raises(ImageInspectionError, match="capture_file_missing"):
        inspect_owned_capture(capture, identity)
