"""Atomic, content-addressed clip journal and generation fingerprinting.

Conforms to ADR 0002 and ADR 0006.
Guarantees deterministic restart-resumption across preview and broadcast
master compilation runs without redundant re-encodes.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from youtube_automation.core.utils import atomic_write_json

from .encoder import EncoderConfig
from .schema import CompilationRequest, CompilationTarget


def get_file_sha256(path: Path | str) -> str:
    """Compute SHA-256 of file contents, or hash of string path if file is absent."""
    p = Path(path)
    if p.is_file():
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    return hashlib.sha256(str(p).encode("utf-8")).hexdigest()


def _serialize_overlay(overlay: Any) -> Any:
    """Serialize an overlay specification into a canonical JSON-serializable structure."""
    if overlay is None or isinstance(overlay, (str, int, float, bool)):
        return overlay
    if isinstance(overlay, (list, tuple)):
        return [_serialize_overlay(item) for item in overlay]
    if isinstance(overlay, dict):
        return {str(k): _serialize_overlay(v) for k, v in sorted(overlay.items())}
    if dataclasses.is_dataclass(overlay) and not isinstance(overlay, type):
        return {
            str(k): _serialize_overlay(v)
            for k, v in sorted(dataclasses.asdict(overlay).items())
        }
    if hasattr(overlay, "model_dump"):
        return _serialize_overlay(overlay.model_dump(mode="json"))
    if hasattr(overlay, "__dict__"):
        return {
            str(k): _serialize_overlay(v)
            for k, v in sorted(vars(overlay).items())
            if not k.startswith("_")
        }
    return str(overlay)


def compute_generation_fingerprint(
    request: CompilationRequest,
    target: CompilationTarget,
    encoder: EncoderConfig,
    asset_hashes: Mapping[str, str] | None = None,
) -> str:
    """Compute deterministic SHA-256 generation fingerprint.

    Derived from spans, asset contents, audio contents, target dimensions,
    and encoder settings.
    """
    subtitles_path = getattr(request, "subtitles_path", None)
    if subtitles_path is not None:
        subtitles_path = Path(subtitles_path)
        if not subtitles_path.is_file():
            raise FileNotFoundError(f"External subtitles not found: {subtitles_path}")
        subtitles_sha256 = get_file_sha256(subtitles_path)
    else:
        subtitles_sha256 = None
    resolved_asset_hashes = dict(asset_hashes or {})
    span_payloads = []
    for span in request.spans:
        asset_path = request.asset_paths.get(span.asset_id)
        if span.asset_id not in resolved_asset_hashes:
            resolved_asset_hashes[span.asset_id] = (
                get_file_sha256(asset_path) if asset_path is not None else ""
            )
        span_payloads.append(
            {
                "index": span.index,
                "shot_id": span.shot_id,
                "start_frame": span.start_frame,
                "end_frame": span.end_frame,
                "duration_frames": span.duration_frames,
                "asset_id": span.asset_id,
                "asset_sha256": resolved_asset_hashes[span.asset_id],
                "zoom": float(span.zoom),
                "camera_motion": str(span.camera_motion),
                "overlays": [_serialize_overlay(o) for o in span.overlays],
                "dialogue_events": [
                    _serialize_overlay(d)
                    for d in getattr(span, "dialogue_events", ())
                ],
                "metadata": {
                    str(k): _serialize_overlay(v)
                    for k, v in sorted(span.metadata.items())
                },
            }
        )

    payload = {
        "version": 1,
        "profile": request.profile.value,
        "target": {
            "width": target.width,
            "height": target.height,
            "fps": target.fps,
            "pixel_format": target.pixel_format,
            "color_range": target.color_range,
        },
        "encoder": {
            "codec": encoder["video_codec"],
            "args": list(encoder["encoder_args"]),
        },
        "font": request.font,
        "dialogue_events": [
            _serialize_overlay(d)
            for d in getattr(request, "dialogue_events", ())
        ],
        "subtitles_sha256": subtitles_sha256,
        "subtitles_path": (
            str(request.subtitles_path)
            if getattr(request, "subtitles_path", None)
            else None
        ),
        "audio": {
            "name": request.audio_path.name,
            "sha256": get_file_sha256(request.audio_path),
        },
        "spans": span_payloads,
    }

    canonical_repr = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ClipJournalEntry:
    """Immutable entry for a single compiled clip in the journal."""

    index: int
    shot_id: str
    asset_id: str
    asset_sha256: str
    duration_frames: int
    duration_sec: float
    clip_path: str
    clip_sha256: str
    verified: bool
    encoder: str
    created_at: str
    execution: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, val: Mapping[str, Any]) -> ClipJournalEntry:
        raw_exec = val.get("execution")
        return cls(
            index=int(val["index"]),
            shot_id=str(val["shot_id"]),
            asset_id=str(val["asset_id"]),
            asset_sha256=str(val["asset_sha256"]),
            duration_frames=int(val["duration_frames"]),
            duration_sec=float(val["duration_sec"]),
            clip_path=str(val["clip_path"]),
            clip_sha256=str(val.get("clip_sha256") or val.get("sha256", "")),
            verified=bool(val["verified"]),
            encoder=str(val["encoder"]),
            created_at=str(val.get("created_at", "")),
            execution=dict(raw_exec) if isinstance(raw_exec, dict) else {},
        )


class RenderJournal:
    """Atomic, content-addressed clip journal managing compilation checkpoints."""

    def __init__(
        self,
        work_dir: Path,
        generation: str,
        total_spans: int,
        profile: str,
        target: CompilationTarget,
        execution_validator: Callable[[Any], bool] | None = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.generation = generation
        self.total_spans = total_spans
        self.profile = profile
        self.target = target
        self.execution_validator = execution_validator
        self.journal_path = self.work_dir / "_render_journal.json"
        self._entries: dict[int, ClipJournalEntry] = {}
        self.load()

    @property
    def entries(self) -> dict[int, ClipJournalEntry]:
        """Return shallow copy of journal entries mapping index to ClipJournalEntry."""
        return dict(self._entries)

    def load(self) -> None:
        """Load journal from disk if existing and matching generation."""
        if not self.journal_path.is_file():
            return

        try:
            data = json.loads(self.journal_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            if data.get("version") != 1:
                return
            if data.get("generation") != self.generation:
                # Generation drifted, do not load stale entries
                return
            if data.get("total_spans") != self.total_spans:
                return

            clips = data.get("clips", {})
            if isinstance(clips, dict):
                for _key, val in clips.items():
                    if not isinstance(val, dict):
                        continue
                    try:
                        entry = ClipJournalEntry.from_dict(val)
                        self._entries[entry.index] = entry
                    except (KeyError, ValueError, TypeError):
                        continue
        except (OSError, json.JSONDecodeError):
            pass

    def is_clip_valid(
        self,
        index: int,
        clip_path: Path,
        expected_asset_sha256: str,
        expected_frames: int,
    ) -> bool:
        """Check whether a clip exists, matches journal/sidecar hash, and is verified."""
        entry = self._entries.get(index)

        sidecar_path = self.work_dir / f"clip_{index:05d}.json"
        if sidecar_path.is_file():
            try:
                val = json.loads(sidecar_path.read_text(encoding="utf-8"))
                if (
                    not isinstance(val, dict)
                    or val.get("version") != 1
                    or val.get("generation") != self.generation
                    or val.get("asset_sha256") != expected_asset_sha256
                    or val.get("duration_frames") != expected_frames
                    or val.get("verified") is not True
                ):
                    return False
                if self.execution_validator is not None:
                    if not self.execution_validator(val.get("execution")):
                        return False
                entry = ClipJournalEntry.from_dict(val)
                self._entries[index] = entry
            except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
                return False
        elif entry is None:
            return False

        if entry.asset_sha256 != expected_asset_sha256:
            return False
        if entry.duration_frames != expected_frames:
            return False
        if not entry.verified:
            return False

        # Verify physical on-disk file
        if not clip_path.is_file():
            return False
        if clip_path.stat().st_size == 0:
            return False

        actual_sha = get_file_sha256(clip_path)
        if actual_sha != entry.clip_sha256:
            # File corruption detected on disk
            self._entries.pop(index, None)
            return False

        return True

    def record_clip(
        self,
        *,
        index: int,
        shot_id: str,
        asset_id: str,
        asset_sha256: str,
        duration_frames: int,
        clip_path: Path,
        clip_sha256: str,
        encoder: str,
        fps: int = 30,
        execution: dict[str, Any] | None = None,
    ) -> None:
        """Atomically record a verified clip in sidecar and _render_journal.json."""
        now_iso = datetime.now(timezone.utc).isoformat()
        duration_sec = duration_frames / fps if fps > 0 else 0.0

        entry = ClipJournalEntry(
            index=index,
            shot_id=shot_id,
            asset_id=asset_id,
            asset_sha256=asset_sha256,
            duration_frames=duration_frames,
            duration_sec=duration_sec,
            clip_path=clip_path.name,
            clip_sha256=clip_sha256,
            verified=True,
            encoder=encoder,
            created_at=now_iso,
            execution=dict(execution) if execution else {},
        )
        self._entries[index] = entry

        # 1. Atomic write sidecar receipt
        sidecar_path = self.work_dir / f"clip_{index:05d}.json"
        sidecar_payload: dict[str, Any] = {
            "version": 1,
            "index": index,
            "generation": self.generation,
            "shot_id": shot_id,
            "asset_id": asset_id,
            "asset_sha256": asset_sha256,
            "duration_frames": duration_frames,
            "duration_sec": duration_sec,
            "clip_path": clip_path.name,
            "clip_sha256": clip_sha256,
            "sha256": clip_sha256,
            "verified": True,
            "encoder": encoder,
            "created_at": now_iso,
        }
        if execution is not None:
            sidecar_payload["execution"] = execution
        atomic_write_json(str(sidecar_path), sidecar_payload, indent=2, ensure_ascii=False)

        # 2. Atomic write journal
        self._flush_journal()

    def _flush_journal(self) -> None:
        """Atomically persist complete journal to disk."""
        journal_payload = {
            "version": 1,
            "generation": self.generation,
            "profile": self.profile,
            "target": {
                "width": self.target.width,
                "height": self.target.height,
                "fps": self.target.fps,
                "pixel_format": self.target.pixel_format,
                "color_range": self.target.color_range,
            },
            "total_spans": self.total_spans,
            "completed_clips": len(self._entries),
            "clips": {str(k): asdict(v) for k, v in sorted(self._entries.items())},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_json(str(self.journal_path), journal_payload, indent=2, ensure_ascii=False)

    @property
    def completed_count(self) -> int:
        return len(self._entries)

    def is_complete(self) -> bool:
        return len(self._entries) == self.total_spans

    def get_entry(self, index: int) -> ClipJournalEntry | None:
        return self._entries.get(index)
