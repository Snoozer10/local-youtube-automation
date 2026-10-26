"""Media runner port and execution adapters for FFmpeg and FFprobe.

Establishes an explicit execution seam between high-level video compilation
orchestration and low-level external process execution, conforming to ADR 0006.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


def _stream_duration(stream: dict[str, Any], fallback: float) -> float:
    """Read stream timing independently, preserving unknown timing as invalid."""
    raw = stream.get("duration")
    if raw not in (None, "", "N/A"):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return math.nan
    try:
        numerator, denominator = str(stream["time_base"]).split("/")
        return float(stream["duration_ts"]) * int(numerator) / int(denominator)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return fallback


class MediaExecutionError(RuntimeError):
    """Raised when an external media subprocess fails."""

    def __init__(
        self,
        message: str,
        cmd: list[str],
        returncode: int,
        stderr: str = "",
        stdout: str = "",
    ) -> None:
        super().__init__(message)
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


@dataclass(frozen=True)
class MediaProbeResult:
    """Normalized metadata for a probed media container."""

    duration: float
    total_frames: int
    width: int
    height: int
    fps: float
    pix_fmt: str
    color_range: str
    has_audio: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    audio_duration: float | None = None
    video_duration: float | None = None


@runtime_checkable
class MediaRunner(Protocol):
    """Protocol defining media tool subprocess execution and stream probing."""

    def run_ffmpeg(
        self,
        args: list[str],
        *,
        cwd: Path | str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        """Execute FFmpeg with the given argument list.

        Returns (stdout, stderr).
        Raises MediaExecutionError if return code is non-zero.
        """
        ...

    def probe(
        self,
        path: Path | str,
        *,
        require_audio: bool = False,
        timeout: float = 60.0,
    ) -> MediaProbeResult:
        """Probe a media file using FFprobe.

        Returns MediaProbeResult.
        Raises FileNotFoundError if file is absent, or MediaExecutionError on probe failure.
        """
        ...


class SubprocessMediaRunner:
    """Production adapter executing native FFmpeg and FFprobe subprocesses."""

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
    ) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.last_execution_cwd: Path | None = None

    def run_ffmpeg(
        self,
        args: list[str],
        *,
        cwd: Path | str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        cmd = [self.ffmpeg_bin] + list(args)
        execution_cwd = Path(cwd) if cwd is not None else Path.cwd()
        scratch: tempfile.TemporaryDirectory[str] | None = None
        if "-/filter_complex" in args or len(str(execution_cwd)) > 240:
            scratch = tempfile.TemporaryDirectory(prefix="youtube-overlay-")
            execution_cwd = Path(scratch.name)
            if cwd is not None:
                src_dir = Path(cwd)
                for f in src_dir.glob("*.txt"):
                    (execution_cwd / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
                for f in src_dir.glob("*.ass"):
                    (execution_cwd / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        self.last_execution_cwd = execution_cwd
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=execution_cwd,
                shell=False,
            )
            if result.returncode != 0:
                raise MediaExecutionError(
                    f"FFmpeg returned non-zero exit code {result.returncode}",
                    cmd=cmd,
                    returncode=result.returncode,
                    stderr=result.stderr,
                    stdout=result.stdout,
                )
            return result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            raise MediaExecutionError(
                f"FFmpeg command timed out after {timeout}s: {' '.join(cmd)}",
                cmd=cmd,
                returncode=-1,
                stderr=str(exc),
            ) from exc
        except MediaExecutionError:
            raise
        except Exception as exc:
            raise MediaExecutionError(
                f"Failed to execute FFmpeg command {' '.join(cmd)}: {exc}",
                cmd=cmd,
                returncode=-1,
                stderr=str(exc),
            ) from exc
        finally:
            if scratch is not None:
                scratch.cleanup()

    def probe(
        self,
        path: Path | str,
        *,
        require_audio: bool = False,
        timeout: float = 60.0,
    ) -> MediaProbeResult:
        p = Path(path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Media file not found for probing: {p}")

        cmd = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,color_range,nb_read_frames,duration,duration_ts,time_base:format=duration",
            "-count_frames",
            "-of",
            "json",
            str(p),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaExecutionError(
                f"FFprobe command timed out after {timeout}s: {' '.join(cmd)}",
                cmd=cmd,
                returncode=-1,
                stderr=str(exc),
            ) from exc
        except Exception as exc:
            raise MediaExecutionError(
                f"Failed to execute FFprobe command {' '.join(cmd)}: {exc}",
                cmd=cmd,
                returncode=-1,
                stderr=str(exc),
            ) from exc

        if result.returncode != 0:
            raise MediaExecutionError(
                f"FFprobe returned non-zero exit code {result.returncode}",
                cmd=cmd,
                returncode=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout,
            )

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MediaExecutionError(
                f"Failed to parse FFprobe JSON output: {exc}",
                cmd=cmd,
                returncode=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout,
            ) from exc

        streams = payload.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        has_audio = audio_stream is not None
        if not video_stream and not has_audio:
            raise MediaExecutionError(
                f"No video or audio stream found in {p}",
                cmd=cmd,
                returncode=result.returncode,
                stdout=result.stdout,
            )

        if require_audio and not has_audio:
            raise MediaExecutionError(
                f"Required audio stream missing from {p}",
                cmd=cmd,
                returncode=result.returncode,
                stdout=result.stdout,
            )

        format_info = payload.get("format", {})
        duration = float(format_info.get("duration", 0.0))

        if video_stream is None:
            return MediaProbeResult(
                duration=duration,
                total_frames=int(round(duration * 30.0)),
                width=0,
                height=0,
                fps=30.0,
                pix_fmt="",
                color_range="tv",
                has_audio=has_audio,
                raw=payload,
                audio_duration=_stream_duration(audio_stream, duration) if audio_stream else None,
            )

        fps = 30.0
        fps_raw = video_stream.get("avg_frame_rate", "30/1")
        if "/" in fps_raw:
            num, den = map(int, fps_raw.split("/"))
            fps = (num / den) if den != 0 else 30.0
        else:
            fps = float(fps_raw) if fps_raw else 30.0

        total_frames = 0
        if "nb_read_frames" in video_stream and str(video_stream["nb_read_frames"]).isdigit():
            total_frames = int(video_stream["nb_read_frames"])
        else:
            total_frames = int(round(duration * fps))

        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        pix_fmt = str(video_stream.get("pix_fmt", ""))
        color_range = str(video_stream.get("color_range", ""))

        return MediaProbeResult(
            duration=duration,
            total_frames=total_frames,
            width=width,
            height=height,
            fps=fps,
            pix_fmt=pix_fmt,
            color_range=color_range,
            has_audio=has_audio,
            raw=payload,
            audio_duration=_stream_duration(audio_stream, math.nan) if audio_stream else None,
            video_duration=_stream_duration(video_stream, total_frames / fps if fps > 0 else math.nan),
        )


class FakeMediaRunner:
    """Test adapter simulating deterministic FFmpeg execution and stream probes."""

    def __init__(
        self,
        auto_create_output: bool = True,
        available_encoders: set[str] | list[str] | None = None,
        error_on_encoder: set[str] | list[str] | None = None,
        default_total_frames: int = 90,
        default_duration: float = 3.0,
        default_width: int = 1920,
        default_height: int = 1080,
        default_fps: float = 30.0,
        default_pix_fmt: str = "yuv420p",
    ) -> None:
        self.auto_create_output = auto_create_output
        self.available_encoders: set[str] | None = (
            set(available_encoders) if available_encoders is not None else None
        )
        self.error_on_encoder: set[str] = (
            set(error_on_encoder) if error_on_encoder is not None else set()
        )
        self.default_total_frames = default_total_frames
        self.default_duration = default_duration
        self.default_width = default_width
        self.default_height = default_height
        self.default_fps = default_fps
        self.default_pix_fmt = default_pix_fmt
        self.commands_run: list[list[str]] = []
        self._registered_probes: dict[str, MediaProbeResult] = {}
        self._next_error: Exception | None = None

    def set_next_error(self, exc: Exception | None) -> None:
        """Inject a transient error to be raised on the next invocation."""
        self._next_error = exc

    def register_probe(self, path: Path | str, probe: MediaProbeResult) -> None:
        """Register a deterministic probe result for a specific file path."""
        p = str(Path(path).resolve())
        self._registered_probes[p] = probe

    def run_ffmpeg(
        self,
        args: list[str],
        *,
        cwd: Path | str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        if self._next_error is not None:
            err = self._next_error
            self._next_error = None
            raise err

        cmd = ["ffmpeg"] + list(args)
        self.commands_run.append(cmd)

        if "-c:v" in args:
            idx = args.index("-c:v")
            if idx + 1 < len(args):
                codec = args[idx + 1]
                if (
                    codec != "copy"
                    and self.available_encoders is not None
                    and codec not in self.available_encoders
                ):
                    raise MediaExecutionError(
                        f"Encoder '{codec}' is not available in fake runner",
                        cmd=cmd,
                        returncode=1,
                        stderr=f"Unknown encoder '{codec}'",
                    )
                is_probe = "-f" in args and ("null" in args or "lavfi" in args)
                if not is_probe and codec in self.error_on_encoder:
                    raise MediaExecutionError(
                        f"Hardware device error for encoder '{codec}'",
                        cmd=cmd,
                        returncode=1,
                        stderr=f"Hardware failure with {codec}",
                    )

        if self.auto_create_output and args:
            candidate = args[-1]
            if not candidate.startswith("-") and not candidate.startswith("pipe:"):
                out_path = Path(candidate)
                if cwd is not None and not out_path.is_absolute():
                    out_path = Path(cwd) / out_path
                try:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    if not out_path.exists():
                        # Distinct claimed media facts must not share a fictional
                        # all-zero artifact hash. Keep output paths out of identity.
                        out_path.write_bytes(b"\x00" * 1024)
                        probe = self.probe(out_path)
                        inputs: list[str | list[str]] = []
                        input_format: str | None = None
                        for index, argument in enumerate(args[:-1]):
                            if argument == "-f" and index + 1 < len(args):
                                input_format = args[index + 1]
                                continue
                            if argument != "-i" or index + 1 >= len(args):
                                continue
                            source = Path(args[index + 1])
                            if cwd is not None and not source.is_absolute():
                                source = Path(cwd) / source
                            sources = [source]
                            if input_format == "concat" and source.is_file():
                                sources = []
                                for line in source.read_text(encoding="utf-8").splitlines():
                                    if line.startswith("file '") and line.endswith("'"):
                                        item = Path(line[6:-1])
                                        sources.append(item if item.is_absolute() else source.parent / item)
                            hashes: list[str] = []
                            for item in sources:
                                digest = hashlib.sha256()
                                if item.is_file():
                                    with item.open("rb") as stream:
                                        while chunk := stream.read(1024 * 1024):
                                            digest.update(chunk)
                                else:
                                    digest.update(b"missing synthetic input")
                                hashes.append(digest.hexdigest())
                            inputs.append(hashes)
                            input_format = None
                        identity = {
                            "duration": probe.duration, "frames": probe.total_frames,
                            "width": probe.width, "height": probe.height, "fps": probe.fps,
                            "pixel_format": probe.pix_fmt, "color_range": probe.color_range,
                            "has_audio": probe.has_audio, "audio_duration": probe.audio_duration,
                            "video_duration": probe.video_duration, "inputs": inputs,
                        }
                        encoded_digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).digest()
                        out_path.write_bytes(encoded_digest * 32)
                except Exception:
                    pass

        return ("fake ffmpeg banner\nversion 7.0-fake\n", "")

    def probe(
        self,
        path: Path | str,
        *,
        require_audio: bool = False,
        timeout: float = 60.0,
    ) -> MediaProbeResult:
        p = Path(path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Media file does not exist: {p}")

        path_key = str(p)
        if path_key not in self._registered_probes:
            pending = re.fullmatch(r"(.+)\.pending_([0-9a-f]{8})\.mp4", p.name)
            if pending is not None:
                aliases = [
                    key for key in self._registered_probes
                    if Path(key).with_suffix(f".pending_{pending.group(2)}.mp4") == p
                ]
                if len(aliases) > 1:
                    raise ValueError(f"Ambiguous registered candidate probe: {p}")
                if aliases:
                    path_key = aliases[0]
        if path_key in self._registered_probes:
            res = self._registered_probes[path_key]
            if require_audio and not res.has_audio:
                raise MediaExecutionError(
                    f"Required audio missing from fake probe: {p}",
                    cmd=["ffprobe", str(p)],
                    returncode=1,
                )
            return res

        return MediaProbeResult(
            duration=self.default_duration,
            total_frames=self.default_total_frames,
            width=self.default_width,
            height=self.default_height,
            fps=self.default_fps,
            pix_fmt=self.default_pix_fmt,
            color_range="tv",
            has_audio=True,
            raw={"simulated": True},
        )

_DEFAULT_RUNNER: MediaRunner | None = None


def get_default_runner() -> MediaRunner:
    """Return the active default MediaRunner (defaults to SubprocessMediaRunner)."""
    global _DEFAULT_RUNNER
    return _DEFAULT_RUNNER if _DEFAULT_RUNNER is not None else SubprocessMediaRunner()


def set_default_runner(runner: MediaRunner | None) -> None:
    """Configure the active default MediaRunner for testing or process lifecycle."""
    global _DEFAULT_RUNNER
    _DEFAULT_RUNNER = runner

