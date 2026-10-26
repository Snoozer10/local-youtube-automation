"""Hash-bound, atomic verification receipts for final compilation artifacts.

Receipts are immutable measured facts, not editorial approval or authentication.
Preparing the receipt before the single video rename keeps either the old pair
or the new pair usable after interruption; an orphan prepared receipt is harmless.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from ..core.utils import atomic_write_json
from .runner import MediaProbeResult
from .schema import CompilationError

_MAX_RECEIPT_BYTES = 65536
_FIELDS = frozenset({
    "schema_version", "sha256", "size_bytes", "total_frames", "fps", "duration",
    "video_duration", "audio_duration", "width", "height", "pixel_format",
    "color_range", "has_audio",
})


def _failure(message: str) -> CompilationError:
    return CompilationError(f"Compilation receipt {message}", stage="receipt")


def _signature(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _fingerprint(path: Path) -> tuple[str, int, tuple[int, int, int, int, int]]:
    """Hash an opened file and reject replacement or mutation during that read."""
    before = path.stat()
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not os.path.isfile(path) or _signature(opened) != _signature(before):
            raise _failure("artifact changed before hashing")
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(stream.fileno())
    signature = _signature(before)
    if size <= 0 or size != before.st_size:
        raise _failure("artifact is empty or changed while hashing")
    if _signature(after) != signature or _signature(path.stat()) != signature:
        raise _failure("artifact changed while hashing")
    return digest.hexdigest(), size, signature


def _path_for_hash(video: Path, sha256: str) -> Path:
    directory = video.parent / ".compilation-receipts"
    expected = video.parent.resolve() / ".compilation-receipts"
    if directory.is_symlink() or directory.resolve() != expected:
        raise _failure("directory must not be a symlink or redirected junction")
    return directory / f"{sha256}.json"


def verification_receipt_path(video: Path | str) -> Path:
    """Locate the receipt for the video's current bytes, without trusting a pointer."""
    try:
        path = Path(video)
        digest, _, _ = _fingerprint(path)
        return _path_for_hash(path, digest)
    except (OSError, ValueError) as exc:
        raise _failure(f"artifact cannot be read: {exc}") from exc


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field {key}")
        result[key] = value
    return result


def _validate(payload: Any, digest: str, size: int) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise _failure("schema fields are invalid")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise _failure("schema version is unsupported")
    if type(payload["sha256"]) is not str or payload["sha256"] != digest:
        raise _failure("artifact hash does not match")
    if type(payload["size_bytes"]) is not int or payload["size_bytes"] != size:
        raise _failure("artifact size does not match")
    for key in ("total_frames", "width", "height"):
        if type(payload[key]) is not int or payload[key] <= 0:
            raise _failure(f"{key} must be a positive integer")
    for key in ("fps", "duration", "video_duration", "audio_duration"):
        value = payload[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise _failure(f"{key} must be a positive finite number")
    if payload["pixel_format"] != "yuv420p" or payload["color_range"] != "tv":
        raise _failure("decoded format or color range is invalid")
    if payload["has_audio"] is not True:
        raise _failure("audio stream is required")
    if abs(payload["audio_duration"] - payload["video_duration"]) > 1.0 / payload["fps"] + 1e-6:
        raise _failure("audio/video duration drift exceeds one frame")
    # Each compiler measurement is within one frame of the canonical timeline.
    # Two independently measured values may therefore differ by two frames.
    tolerance = 2.0 / payload["fps"] + 1e-9
    duration = payload["duration"]
    if any(abs(actual - duration) > tolerance for actual in (
        payload["total_frames"] / payload["fps"],
        payload["video_duration"], payload["audio_duration"],
    )):
        raise _failure("frame count and durations are inconsistent")
    return dict(payload)


def _read_receipt(path: Path, digest: str, size: int) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise _failure("file must be a regular file, not a symlink")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(_MAX_RECEIPT_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > _MAX_RECEIPT_BYTES:
        raise _failure("file exceeds the size limit")
    if _signature(before) != _signature(after) or _signature(path.stat()) != _signature(before):
        raise _failure("file changed while reading")
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields)
    return _validate(payload, digest, size)


def verify_compilation_receipt(video: Path | str) -> dict[str, Any]:
    """Validate bounded receipt facts against stable current artifact bytes.

    This verifies the compiler's recorded evidence. It does not authenticate an
    untrusted writer or replace editorial approval. Callers enforce their own
    required frame count and target against the returned measured facts.
    """
    try:
        path = Path(video)
        before = _fingerprint(path)
        payload = _read_receipt(_path_for_hash(path, before[0]), before[0], before[1])
        if _fingerprint(path) != before:
            raise _failure("artifact changed during verification")
        return payload
    except (OSError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise _failure(f"cannot be verified: {exc}") from exc


def _prepare_verification_receipt(
    candidate: Path, destination: Path, probe: MediaProbeResult, sha256: str,
) -> Path:
    """Prepare immutable evidence under the caller's publication guard."""
    try:
        before = _fingerprint(candidate)
        if before[0] != sha256:
            raise _failure("candidate changed after media verification")
        payload = _validate({
            "schema_version": 1, "sha256": sha256, "size_bytes": before[1],
            "total_frames": probe.total_frames, "fps": probe.fps,
            "duration": probe.duration,
            "video_duration": probe.video_duration if probe.video_duration is not None else probe.duration,
            "audio_duration": probe.audio_duration if probe.audio_duration is not None else probe.duration,
            "width": probe.width, "height": probe.height,
            "pixel_format": probe.pix_fmt, "color_range": probe.color_range,
            "has_audio": probe.has_audio,
        }, sha256, before[1])
        path = _path_for_hash(destination, sha256)
        path.parent.mkdir(exist_ok=True)
        _path_for_hash(destination, sha256)
        if path.exists() or path.is_symlink():
            if _read_receipt(path, sha256, before[1]) != payload:
                raise _failure("conflicts with existing immutable evidence")
        else:
            atomic_write_json(str(path), payload, indent=2)
            if _read_receipt(path, sha256, before[1]) != payload:
                raise _failure("write readback differs from measured facts")
        if _fingerprint(candidate) != before:
            raise _failure("candidate changed before publication")
        return path
    except (OSError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise _failure(f"cannot be prepared: {exc}") from exc
