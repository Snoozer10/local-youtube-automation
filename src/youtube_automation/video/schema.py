"""Declarative schemas and typed errors for video compilation.

Conforms to ADR 0002 and ADR 0006.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CompilationProfile(str, Enum):
    """Target compilation profile governing resolution ladder and kinematics."""

    PREVIEW = "preview"
    BROADCAST_MASTER = "broadcast_master"


@dataclass(frozen=True)
class DialogueCue:
    """Timeline dialogue subtitle cue for synchronous burn-in."""

    start_frame: int
    end_frame: int
    text: str
    style: str = "Default"


@dataclass(frozen=True)
class CompilationSpan:
    """Atomic timeline or shot span representing a visual segment."""

    index: int
    shot_id: str
    start_frame: int
    end_frame: int
    asset_id: str
    zoom: float = 1.0
    camera_motion: str = "static"
    overlays: tuple[Any, ...] = ()
    dialogue_events: tuple[Any, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def duration_sec(self, fps: int = 30) -> float:
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        return self.duration_frames / fps


@dataclass(frozen=True)
class CompilationTarget:
    """Explicit output rendition target specification."""

    width: int
    height: int
    fps: int = 30
    pixel_format: str = "yuv420p"
    color_range: str = "tv"

    def __post_init__(self) -> None:
        if self.width < 2 or self.height < 2:
            raise ValueError(
                f"Output dimensions must be at least 2x2, got {self.width}x{self.height}"
            )
        if self.width % 2 != 0 or self.height % 2 != 0:
            raise ValueError(
                f"Output dimensions must be even, got {self.width}x{self.height}"
            )
        if self.fps <= 0:
            raise ValueError(f"Output fps must be positive, got {self.fps}")
        if self.color_range not in {"tv", "pc", "limited", "full"}:
            raise ValueError(
                f"Invalid color range: {self.color_range} (expected 'tv' or 'pc')"
            )


@dataclass(frozen=True)
class CompilationRequest:
    """In-memory, declarative request for compiling a complete video artifact."""

    spans: tuple[CompilationSpan, ...]
    audio_path: Path
    asset_paths: dict[str, Path]
    output_path: Path
    profile: CompilationProfile = CompilationProfile.PREVIEW
    target: CompilationTarget | None = None
    work_dir: Path | None = None
    encoder_override: str | None = None
    font: str = "Arial"
    dialogue_events: tuple[Any, ...] = ()
    subtitles_path: Path | None = None
    extra_config: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate request contracts and invariants."""
        if not self.spans:
            raise ValueError("CompilationRequest must contain at least one span")

        inputs = [self.audio_path, *self.asset_paths.values()]
        if self.subtitles_path is not None:
            inputs.append(self.subtitles_path)
        output = self.output_path.resolve()
        for source in inputs:
            try:
                aliases = output == source.resolve() or (
                    self.output_path.exists()
                    and source.exists()
                    and self.output_path.samefile(source)
                )
            except OSError as exc:
                raise ValueError("Cannot verify output/input path separation") from exc
            if aliases:
                raise ValueError(f"Output path aliases a compilation input: {source}")

        prev_end = 0
        for i, span in enumerate(self.spans):
            if span.start_frame < 0:
                raise ValueError(
                    f"Span {span.index} has negative start_frame: {span.start_frame}"
                )
            if span.end_frame <= span.start_frame:
                raise ValueError(
                    f"Span {span.index} end_frame ({span.end_frame}) must be strictly "
                    f"greater than start_frame ({span.start_frame})"
                )
            if span.asset_id not in self.asset_paths:
                raise ValueError(
                    f"Span {span.index} references asset '{span.asset_id}' "
                    f"missing from asset_paths"
                )
            if i > 0 and span.start_frame < prev_end:
                raise ValueError(
                    f"Span {i} (starts {span.start_frame}) overlaps with "
                    f"span {i - 1} (ends {prev_end})"
                )
            if span.start_frame != prev_end:
                raise ValueError(
                    f"Spans must be contiguous from frame 0: span {i} "
                    f"starts at {span.start_frame}, expected {prev_end}"
                )
            prev_end = span.end_frame

        if self.target is not None:
            # Re-verify target invariants if explicitly provided
            if self.target.width < 2 or self.target.height < 2:
                raise ValueError("Target dimensions must be at least 2x2")
            if self.target.width % 2 != 0 or self.target.height % 2 != 0:
                raise ValueError("Target dimensions must be even")


@dataclass(frozen=True)
class CompilationResult:
    """Immutable, verified result of a video compilation run."""

    output_path: Path
    profile: CompilationProfile
    total_frames: int
    fps: int
    duration: float
    width: int
    height: int
    encoder_used: str
    fallback_occurred: bool = False
    fallback_from: str | None = None
    verified: bool = True
    sha256: str = ""
    clip_count: int = 0
    generation_hash: str = ""
    reused_clip_count: int = 0
    clip_executions: tuple[dict[str, Any], ...] = ()
    receipt_path: Path | None = None


class CompilationError(RuntimeError):
    """Raised when video compilation fails permanently."""

    def __init__(
        self,
        message: str,
        *,
        stage: str = "compilation",
        clip_index: int | None = None,
        cmd: list[str] | None = None,
        returncode: int | None = None,
        stderr: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.clip_index = clip_index
        self.cmd = list(cmd) if cmd else []
        self.returncode = returncode
        self.stderr = stderr or ""
        self.details = details or {}
