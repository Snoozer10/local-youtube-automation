"""Render approved editorial instructions with exact frame budgets and atomic activation."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from youtube_automation.core.utils import atomic_write_json
from youtube_automation.video import filter_graph
from youtube_automation.video.engine import VideoCompiler
from youtube_automation.video.runner import (
    MediaExecutionError,
    MediaProbeResult,
    MediaRunner,
    SubprocessMediaRunner,
    get_default_runner,
)
from youtube_automation.video.schema import (
    CompilationProfile,
    CompilationRequest,
    CompilationSpan,
    CompilationTarget,
)

from ..video import encoder as video_encoder
from .assets import asset_storage_id, file_digest, read_receipt, read_shot_receipt
from .contracts import fingerprint, load_brief
from .flow import verify_generated_assets
from .graphic_cues import timer_segments
from .ledger import leased_resource, publication_guard, resource_database
from .pictograms import pictogram_ass
from .shots import Shot, ShotPlan, require_editorial_review, validate_plan

__all__ = [

    "current_render_inputs",

    "overlay_ass",
    "overlay_filter_recipe",
    "overlay_review_evidence",
    "probe_video",
    "render_code_fingerprint",
    "render_plan",
    "render_tool_version",
    "require_current_preview",
    "require_encoder_execution",
    "run_command",


    "_render_journal_path",
    "_render_plan",
]



_ORIGINAL_SUBPROCESS_RUN = subprocess.run


def run_command(args: list[str], cwd: Path, timeout: float = 600) -> None:
    # A file-backed stderr cannot block deadline enforcement on an unterminated line.
    with tempfile.TemporaryFile() as stderr:
        result = subprocess.run(
            args, cwd=cwd, stdout=subprocess.DEVNULL, stderr=stderr, timeout=timeout, check=False
        )
        if result.returncode:
            stderr.seek(0, os.SEEK_END)
            stderr.seek(max(0, stderr.tell() - 6000))
            raise RuntimeError(stderr.read().decode("utf-8", errors="replace"))


def probe_video(
    path: Path,
    frames: int,
    fps: int,
    *,
    require_audio: bool = False,
    runner: MediaRunner | None = None,
) -> dict[str, Any]:
    active_runner = _get_runner(runner, expected_frames=frames)
    if subprocess.run is not _ORIGINAL_SUBPROCESS_RUN:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=True,
        )
        streams: list[dict[str, Any]] = json.loads(result.stdout)["streams"]
        video = next(s for s in streams if s["codec_type"] == "video")
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        num, den = map(int, str(video.get("avg_frame_rate", f"{fps}/1")).split("/"))
        calc_fps = (num / den) if den else float(fps)
        probe_res = MediaProbeResult(
            duration=float(frames / fps),
            total_frames=int(video.get("nb_read_frames", 0)),
            width=int(video.get("width", 640)),
            height=int(video.get("height", 360)),
            fps=calc_fps,
            pix_fmt=str(video.get("pix_fmt", "")),
            color_range=str(video.get("color_range", "")),
            has_audio=has_audio,
            raw={"streams": streams},
        )
    else:
        probe_res = active_runner.probe(path, require_audio=require_audio)
    if probe_res.total_frames != frames:
        raise ValueError("Rendered frame count differs from the edit plan")
    if int(round(probe_res.fps)) != fps:
        raise ValueError("Rendered frame rate differs from the edit plan")
    if probe_res.pix_fmt != "yuv420p":
        raise ValueError("Rendered pixel format is not yuv420p")
    if probe_res.color_range != "tv":
        raise ValueError("Rendered color range is not limited (tv)")
    if require_audio and not probe_res.has_audio:
        raise ValueError("Final output has no audio stream")
    if isinstance(probe_res.raw, dict):
        streams_raw = probe_res.raw.get("streams", [])
        if streams_raw:
            video_s = next((s for s in streams_raw if s.get("codec_type") == "video"), None)
            if video_s:
                return cast(dict[str, Any], video_s)
    return {
        "codec_type": "video",
        "nb_read_frames": str(probe_res.total_frames),
        "avg_frame_rate": f"{int(round(probe_res.fps))}/1",
        "pix_fmt": probe_res.pix_fmt,
        "color_range": probe_res.color_range,
    }


def _render_journal_path(root: Path, generation: str, preview: bool) -> Path:
    kind = "preview" if preview else "master"
    return root / ".publication_journal" / "renders" / f"{kind}-{generation}.json"


def require_current_preview(
    root: Path, inputs: dict[str, Any], frames: int
) -> dict[str, Any]:
    """Approval and master activation require the exact still-available preview bytes."""
    pointer_value: object = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
    if not isinstance(pointer_value, dict):
        raise ValueError("current preview pointer must be a JSON object")
    pointer: dict[str, Any] = pointer_value
    if (
        not isinstance(pointer.get("path"), str)
        or not isinstance(pointer.get("sha256"), str)
        or not isinstance(pointer.get("inputs"), dict)
        or not isinstance(pointer.get("generation"), str)
        or type(pointer.get("frames")) is not int
        or not isinstance(pointer.get("editorial_status"), str)
    ):
        raise ValueError("current preview pointer metadata is malformed")
    artifact = (root / pointer["path"]).resolve()
    if (
        not artifact.is_relative_to(root.resolve())
        or not artifact.is_file()
        or file_digest(artifact) != pointer["sha256"]
        or pointer.get("inputs") != inputs
        or pointer.get("generation") != fingerprint(inputs)
        or pointer.get("frames") != frames
        or pointer.get("editorial_status") != "pending"
    ):
        raise ValueError("Preview is stale or changed; render a new preview before approval")
    require_encoder_execution(pointer, inputs)
    return pointer


def _remove_journal(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # A verified activation pointer wins; a leftover journal is harmless.
        pass


def _recover_render_publication(
    root: Path,
    generation: str,
    inputs: dict[str, Any],
    frames: int,
    fps: int,
    *,
    preview: bool,
    runner: MediaRunner | None = None,
) -> Path | None:
    from .audio_adoption import (
        assert_current_audio_state,
        capture_audio_state,
    )
    with publication_guard():
        audio_state = capture_audio_state(root)
        if (root / "shot_plan.json").is_file():
            current = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
            if fingerprint(current) != inputs["plan"]:
                raise ValueError("Recovered render has stale current audio/plan lineage")
    journal = _render_journal_path(root, generation, preview)
    try:
        pending: dict[str, Any] = json.loads(journal.read_text(encoding="utf-8"))
        pointer = pending["pointer"]
        expected_status = "pending" if preview else "approved"
        if (
            pending.get("version") != 1
            or pending.get("kind") != ("preview" if preview else "master")
            or not isinstance(pointer, dict)
            or pointer.get("generation") != generation
            or pointer.get("inputs") != inputs
            or pointer.get("frames") != frames
            or pointer.get("editorial_status") != expected_status
        ):
            return None
        relative_path = pointer.get("path")
        expected_hash = pointer.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            return None
        destination = (root / relative_path).resolve()
        render_root = (root / "adaptive_renders" / generation).resolve()
        prefix = "preview-" if preview else "master-"
        expected_name = prefix + expected_hash + ".mp4"
        if (
            not destination.is_relative_to(render_root)
            or destination.name != expected_name
            or file_digest(destination) != expected_hash
        ):
            return None
        require_encoder_execution(pointer, inputs)
        probe_video(destination, frames, fps, require_audio=True, runner=runner)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return None
    with publication_guard():
        assert_current_audio_state(root, audio_state)
        if preview:
            from .review import require_no_human_rejection

            require_no_human_rejection(root, inputs["plan"], pointer["sha256"])
        if not preview:
            from .review import require_no_human_rejection

            current_preview = require_current_preview(root, inputs, frames)
            require_no_human_rejection(root, inputs["plan"], current_preview["sha256"])
            approval = json.loads((root / "editorial_approval.json").read_text(encoding="utf-8"))
            require_no_human_rejection(root, inputs["plan"], approval.get("preview_sha256", ""))
        atomic_write_json(
            str(root / ("adaptive_preview.json" if preview else "active_master.json")),
            pointer,
        )
    _remove_journal(journal)
    return destination


# Backward-compatibility aliases for legacy test suites and proof generators
camera_filter = filter_graph.build_camera_filter
framed_focal = filter_graph.framed_focal
_normalize_color_range_filter = filter_graph.normalize_color_range_filter
_pixel_format_for_encoder = filter_graph.pixel_format_for_encoder
detect_hardware_encoder = video_encoder.detect_hardware_encoder
_build_encoder_config = video_encoder._build_encoder_config



RENDERER_VERSION = 14


def render_code_fingerprint() -> str:
    render_root = Path(__file__).resolve().parent
    video_root = render_root.parent / "video"
    paths = {
        name: render_root / name
        for name in ("render.py", "graphic_cues.py", "pictograms.py")
    }
    paths.update({
        f"video/{name}": video_root / name
        for name in (
            "engine.py",
            "filter_graph.py",
            "subtitles.py",
            "ken_burns.py",
            "journal.py",
            "runner.py",
            "schema.py",
        )
    })
    paths["video/encoder.py"] = Path(video_encoder.__file__)
    sources: dict[str, str] = {}
    for name, path in paths.items():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=name)
        sources[name] = ast.dump(tree, include_attributes=False)
    return fingerprint(sources)


def render_tool_version(runner: MediaRunner | None = None) -> str:
    """Include the actual FFmpeg build, not only its advertised release number."""
    active_runner = _get_runner(runner)
    try:
        stdout, _ = active_runner.run_ffmpeg(["-version"], timeout=15)
        return stdout.replace("\r\n", "\n").replace("\r", "\n").strip()
    except Exception:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True,
            encoding="utf-8", timeout=15, check=True,
        )
        return result.stdout.replace("\r\n", "\n").replace("\r", "\n").strip()


def current_render_inputs(
    plan: ShotPlan,
    assets: dict[str, str],
    audio: Path,
    config: dict[str, Any],
    *,
    encoder_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The same current recipe governs encoding, cache adoption and human approval."""
    width, height = int(config["OUTPUT_WIDTH"]), int(config["OUTPUT_HEIGHT"])
    if min(width, height) < 2 or width % 2 or height % 2:
        raise ValueError("Output dimensions must be even")
    render_config = dict(config, OUTPUT_FPS=plan.fps)
    selected_encoder = encoder_config
    if selected_encoder is None:
        selected_encoder = detect_hardware_encoder(render_config)
    encoder_recipe = dict(selected_encoder, encoder_args=list(selected_encoder["encoder_args"]))
    fallback = encoder_recipe if encoder_recipe["video_codec"] == "libx264" else _build_encoder_config("libx264", render_config)
    return {
        "renderer_version": RENDERER_VERSION,
        "tool": render_tool_version(),
        "plan": fingerprint(plan),
        "assets": assets,
        "audio": file_digest(audio),
        "config": dict(config, OUTPUT_FPS=plan.fps),
        "render_code_sha256": render_code_fingerprint(),
        "overlay_recipes": {
            shot.shot_id: overlay_filter_recipe(shot, width, height, plan.fps).fingerprint
            for shot in plan.shots if shot.overlays
        },
        "encoder_recipe": encoder_recipe,
        "encoder_policy": {
            "version": 1,
            "cpu_fallback": dict(fallback, encoder_args=list(fallback["encoder_args"])),
            "clip_count": len(plan.shots),
            "assembly": {"video_codec": "libx264", "preset": "veryfast",
                         "crf": str(config.get("CPU_CRF", 17)), "pix_fmt": "yuv420p",
                         "fps": plan.fps, "audio_codec": "aac", "audio_bitrate": "192k"},
        },
           }


def _require_clip_encoder_execution(execution: Any, inputs: dict[str, Any]) -> None:
    preferred = inputs["encoder_recipe"]
    fallback = inputs["encoder_policy"]["cpu_fallback"]
    if not isinstance(execution, dict):
        raise ValueError("Missing encoder execution evidence")
    actual = execution.get("encoder_recipe")
    origin = execution.get("fallback_from")
    if not ((actual == preferred and origin is None)
            or (actual == fallback and actual != preferred and origin == preferred)):
        raise ValueError("Encoder execution is inconsistent with the declared fallback policy")


def require_encoder_execution(pointer: dict[str, Any], inputs: dict[str, Any]) -> None:
    """Publication/cache metadata binds actual clip execution to the allowed recipe."""
    execution = pointer.get("encoder_execution")
    policy = inputs.get("encoder_policy")
    if not isinstance(policy, dict) or policy.get("version") != 1 or not isinstance(execution, dict):
        raise ValueError("Missing current encoder execution policy or evidence")
    clips = execution.get("clips")
    if (execution.get("version") != 1 or execution.get("assembly") != policy.get("assembly")
            or not isinstance(clips, list) or len(clips) != policy.get("clip_count")):
        raise ValueError("Incomplete encoder execution evidence")
    for index, clip in enumerate(clips):
        if (not isinstance(clip, dict) or clip.get("index") != index
                or not isinstance(clip.get("sha256"), str)
                or len(clip["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in clip["sha256"])):
            raise ValueError("Malformed encoder execution clip evidence")
        _require_clip_encoder_execution(clip.get("execution"), inputs)


def _ass_time(frame: int, fps: int) -> str:
    cs = round(frame * 100 / fps)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _timer_ass_time(frame: int, fps: int) -> str:
    cs = frame * 100 // fps
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _scaled_timer_ass_time(frame: int, fps: int) -> str:
    """Serialize a timer frame on the doubled centisecond PTS axis."""
    cs = frame * 200 // fps
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


_TIMER_FRAME_EVENT_PREFIX = "__timer_frame__:"


@dataclass(frozen=True)
class OverlayAssPass:
    layer: int
    timer_pts_scaled: bool
    ass_text: str

    @property
    def sha256(self) -> str:
        encoded = self.ass_text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class OverlayFilterRecipe:
    fps: int
    passes: tuple[OverlayAssPass, ...]

    @property
    def fingerprint(self) -> str:
        return fingerprint({
            "renderer_version": RENDERER_VERSION,
            "fps": self.fps,
            "passes": [
                {
                    "layer": item.layer,
                    "timer_pts_scaled": item.timer_pts_scaled,
                    "ass_sha256": item.sha256,
                }
                for item in self.passes
            ],
        })

    def filter_chain(self, ass_files: list[str] | tuple[str, ...]) -> str:
        if len(ass_files) != len(self.passes):
            raise ValueError("ASS file count does not match the overlay recipe")
        filters: list[str] = []
        for item, ass_file in zip(self.passes, ass_files, strict=True):
            if not ass_file or Path(ass_file).name != ass_file or any(c in ass_file for c in ",;[]"):
                raise ValueError("ASS pass filenames must be simple filter-safe names")
            if item.timer_pts_scaled:
                filters.append(f"setpts=2*PTS,ass={ass_file},setpts=PTS/2")
            else:
                filters.append(f"ass={ass_file}")
        return ",".join(filters)


def _safe_ass_text(value: str) -> str:
    return (
        value.replace("\\", "＼")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", "")
        .replace("\n", "\\N")
    )


def overlay_ass(
    shot: Shot,
    width: int,
    height: int,
    fps: int,
    font: str = "Arial",
    *,
    mark_timer_events: bool = False,
) -> str:
    if any(c in font for c in "\n\r,"):
        raise ValueError("ASS font must be a single font family")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{max(22, height // 25)},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,2,0,7,30,30,30,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    schulte_grid = next(
        (
            overlay
            for overlay in shot.overlays
            if overlay.kind == "data_grid" and overlay.preset == "schulte_6x6"
        ),
        None,
    )
    for overlay in shot.overlays:
        x, y = round(overlay.x * width), round(overlay.y * height)
        w, h = round(overlay.width * width), round(overlay.height * height)
        start = _ass_time(overlay.start_frame, fps)
        end = _ass_time(overlay.end_frame, fps)
        contents: list[str] = []
        if overlay.kind in {"label", "timer"}:
            text = (
                overlay.text.replace("\\", "＼")
                .replace("{", "(")
                .replace("}", ")")
                .replace("\r", "")
                .replace("\n", "\\N")
            )
            if overlay.kind == "timer":
                if overlay.clock_start_frame is not None:
                    assert overlay.value_from is not None
                    for begin, finish, clock_text in timer_segments(
                        overlay.start_frame, overlay.end_frame, shot.start_frame,
                        overlay.clock_start_frame, overlay.value_from, fps,
                    ):
                        timer_name = (
                            f"{_TIMER_FRAME_EVENT_PREFIX}{begin}:{finish}"
                            if mark_timer_events else ""
                        )
                        events.append(
                            f"Dialogue: 0,{_timer_ass_time(begin, fps)},{_timer_ass_time(finish, fps)},Default,{timer_name},0,0,0,,"
                            f"{{\\an5\\b1\\fs{max(54, h // 2)}\\bord0\\1c&H66391E&"
                            f"\\pos({x + w // 2},{y + h // 2})}}{clock_text}"
                        )
                    continue
                contents.append(
                    f"{{\\an5\\b1\\fs{max(54, h // 2)}\\bord0\\1c&H66391E&\\pos({x + w // 2},{y + h // 2})}}{text}"
                )
            elif shot.local_composition in {"kinetic_type", "focus_sweep"}:
                longest_line = max(len(line) for line in overlay.text.splitlines())
                primary = overlay.y < 0.55
                font_size = max(64, min(174 if primary else 104, round(w / max(1, longest_line * 0.52))))
                contents.append(
                    f"{{\\an5\\b1\\fs{font_size}\\bord0\\1c&H66391E&\\fad(180,0)"
                    f"\\pos({x + w // 2},{y + h // 2})}}{text}"
                )
            else:
                contents.append(f"{{\\pos({x},{y})}}{text}")
        elif overlay.kind == "pictogram":
            assert overlay.icon is not None
            if overlay.motion_to is None:
                contents.extend(pictogram_ass(overlay.icon, x, y, w, h))
            else:
                if overlay.motion_end_frame is None:
                    raise ValueError("Moving pictograms need an arrival frame")
                move_to = (
                    round(overlay.motion_to[0] * width),
                    round(overlay.motion_to[1] * height),
                )
                move_ms = round((overlay.motion_end_frame - overlay.start_frame) * 1000 / fps)
                if move_ms <= 0:
                    raise ValueError("Moving pictograms need a positive serialized duration")
                contents.extend(
                    pictogram_ass(
                        overlay.icon, x, y, w, h, move_to=move_to, move_ms=move_ms
                    )
                )
        elif overlay.kind == "highlight":
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H00BFFF&}}m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}"
            )
        elif overlay.kind == "arrow":
            # Arrow runs from upper-left to lower-right within its declared box.
            head = max(6, min(w, h) // 5)
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H00BFFF&}}m 0 0 l {w} {h} m {w - head} {h} l {w} {h} {w} {h - head}{{\\p0}}"
            )
        elif overlay.kind == "mask":
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord0\\1c&H111827&\\1a&H58&}}"
                f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}"
            )
        elif overlay.kind == "card":
            size = max(22, min(72, round(h * .5),
                               round((w - 32) / max(1, len(overlay.text) * .52))))
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord2\\1c&H66391E&\\3c&H5AE0FF&\\fad(120,0)}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{size}\\bord0\\1c&HFFFFFF&\\fad(120,0)"
                    f"\\pos({x + w // 2},{y + h // 2})}}"
                    f"{_safe_ass_text(overlay.text)}",
                ]
            )
        elif overlay.kind == "progress_ring":
            cx, cy = w // 2, h // 2
            radius = max(4, min(w, h) // 2 - 4)
            sweep = max(1, round(36 * (overlay.progress or 0)))
            points = [
                (
                    cx + round(radius * math.cos(math.radians(-90 + index * 10))),
                    cy + round(radius * math.sin(math.radians(-90 + index * 10))),
                )
                for index in range(sweep + 1)
            ]
            ring_path = f"m {cx} {cy} l " + " ".join(f"{px} {py}" for px, py in points)
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord0\\1c&H5AE0FF&\\1a&H18&}}"
                    f"{ring_path} {cx} {cy}{{\\p0}}"
            )
        elif overlay.kind == "tile_reveal":
            reveal = overlay.reveal_cells or list(range(len(overlay.cells)))
            cell_w = w / overlay.columns
            cell_h = h / overlay.rows
            available = max(1, overlay.end_frame - overlay.start_frame)
            step = max(1, available // max(1, len(reveal)))
            for order, cell_index in enumerate(reveal):
                row, column = divmod(cell_index, overlay.columns)
                left, top = round(column * cell_w), round(row * cell_h)
                right, bottom = round((column + 1) * cell_w), round((row + 1) * cell_h)
                reveal_frame = min(overlay.end_frame - 1, overlay.start_frame + order * step)
                reveal_start = _ass_time(reveal_frame, fps)
                shape = (
                    f"{{\\pos({x},{y})\\p1\\bord2\\1c&H20283A&\\3c&H5AE0FF&\\fad(120,0)}}"
                    f"m {left} {top} l {right} {top} {right} {bottom} {left} {bottom} {left} {top}{{\\p0}}"
                )
                label = (
                    f"{{\\an5\\b1\\fs{max(18, round(min(cell_w, cell_h) * 0.32))}"
                    f"\\pos({x + round((column + 0.5) * cell_w)},{y + round((row + 0.5) * cell_h)})"
                    f"\\fad(120,0)}}{_safe_ass_text(overlay.cells[cell_index])}"
                )
                events.extend(
                    [
                        f"Dialogue: 0,{reveal_start},{end},Default,,0,0,0,,{shape}",
                        f"Dialogue: 1,{reveal_start},{end},Default,,0,0,0,,{label}",
                    ]
                )
            continue
        elif overlay.kind == "focus_sweep":
            bar = max(3, w // 35)
            contents.append(
                f"{{\\move({x},{y},{x + w - bar},{y})\\p1\\bord0\\1c&H5AE0FF&\\1a&H35&}}"
                f"m 0 0 l {bar} 0 {bar} {h} 0 {h} 0 0{{\\p0}}"
            )
        elif overlay.kind == "comparison":
            size = max(64, min(122, round((w / 2 - 64) / max(1, max(len(overlay.text), len(overlay.secondary_text)) * 0.5))))
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&H66391E&}}"
                    f"m 0 0 l {w // 2 - 12} 0 {w // 2 - 12} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&HCEE7F2&}}"
                    f"m {w // 2 + 12} 0 l {w} 0 {w} {h} {w // 2 + 12} {h} {w // 2 + 12} 0{{\\p0}}",
                     f"{{\\an5\\b1\\fs{size}\\bord0\\1c&HFFFFFF&\\fad(180,0)\\pos({x + w // 4},{y + h // 2})}}{_safe_ass_text(overlay.text)}",
                     f"{{\\an5\\b1\\fs{size}\\bord0\\1c&H66391E&\\fad(240,0)\\pos({x + 3 * w // 4},{y + h // 2})}}"
                    f"{_safe_ass_text(overlay.secondary_text)}",
                ]
            )
        elif overlay.kind == "trace_path":
            points = [(round(px * w), round(py * h)) for px, py in overlay.points]
            trace_path = f"m {points[0][0]} {points[0][1]} l " + " ".join(
                f"{px} {py}" for px, py in points[1:]
            )
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord4\\1a&HFF&\\3c&H5AE0FF&}}{trace_path}{{\\p0}}"
            )
        elif overlay.kind == "counter":
            assert overlay.value_from is not None and overlay.value_to is not None
            values = list(range(overlay.value_from, overlay.value_to + 1))
            available = overlay.end_frame - overlay.start_frame
            for index, value in enumerate(values):
                value_start = overlay.start_frame + round(index * available / len(values))
                value_end = overlay.start_frame + round((index + 1) * available / len(values))
                suffix = f" {_safe_ass_text(overlay.text)}" if overlay.text else ""
                content = (
                    f"{{\\an5\\b1\\fs{max(28, h // 2)}\\pos({x + w // 2},{y + h // 2})}}"
                    f"{value}{suffix}"
                )
                events.append(
                    f"Dialogue: 1,{_ass_time(value_start, fps)},{_ass_time(value_end, fps)},Default,,0,0,0,,{content}"
                )
            continue
        elif overlay.kind == "challenge_frame":
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H5AE0FF&}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an8\\b1\\fs{max(54, height // 16)}\\1c&H5AE0FF&"
                    f"\\pos({x + w // 2},{max(36, y - height // 30)})}}{_safe_ass_text(overlay.text)}",
                ]
            )
        elif overlay.kind == "rule_reveal":
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&H66391E&\\1a&H00&\\fad(180,0)}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{max(48, height // 17)}\\bord0\\pos({x + w // 2},{y + h // 2})"
                    f"\\fad(180,0)}}{_safe_ass_text(overlay.text)}",
                ]
            )
        elif overlay.kind == "fixation_cue":
            cx, cy = x + w // 2, y + h // 2
            radius = max(8, min(w, h) // 5)
            contents.extend(
                [
                    f"{{\\pos({cx},{cy})\\p1\\bord3\\1a&HFF&\\3c&H5AE0FF&}}"
                    f"m {-radius} 0 l {radius} 0 m 0 {-radius} l 0 {radius}{{\\p0}}",
                    f"{{\\an5\\b1\\fs{max(18, radius)}\\pos({cx},{cy})}}+",
                ]
            )
        elif overlay.kind == "target_indicator":
            if schulte_grid is None or overlay.target_cell is None:
                raise ValueError("Schulte target indicator requires its deterministic grid")
            grid_x = round(schulte_grid.x * width)
            grid_y = round(schulte_grid.y * height)
            cell_w = round(schulte_grid.width * width / 6)
            cell_h = round(schulte_grid.height * height / 6)
            row, column = divmod(overlay.target_cell, 6)
            cx = grid_x + round((column + 0.5) * cell_w)
            cy = grid_y + round((row + 0.5) * cell_h)
            radius = max(8, round(min(cell_w, cell_h) * 0.38))
            duration_ms = max(1, round((overlay.end_frame - overlay.start_frame) * 1000 / fps))
            contents.append(
                f"{{\\pos({cx},{cy})\\p1\\bord4\\1a&HFF&\\3c&H5AE0FF&"
                f"\\t(0,{duration_ms},\\fscx112\\fscy112\\3c&H56D68B&)}}"
                f"m {-radius} {-radius} l {radius} {-radius} {radius} {radius} {-radius} {radius} {-radius} {-radius}{{\\p0}}"
            )
        elif overlay.kind == "start_transition":
            badge_y = round(height * 0.0525)
            if overlay.text == "Start":
                continue  # Generic readiness chrome must not announce a premature start.
            contents.extend(
                [
                     f"{{\\an5\\b1\\fs{max(32, min(round(height * 0.0625), round(h * 0.85)))}\\bord0\\1c&H66391E&\\pos({width // 2},{badge_y})}}"
                     f"{_safe_ass_text(overlay.text)}",
                ]
            )
        else:
            cell_w = w / overlay.columns
            cell_h = h / overlay.rows
            for cell_index in overlay.highlight_cells:
                row, column = divmod(cell_index, overlay.columns)
                left, top = round(column * cell_w), round(row * cell_h)
                right, bottom = round((column + 1) * cell_w), round((row + 1) * cell_h)
                contents.append(
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&H56D68B&\\1a&H30&}}"
                    f"m {left} {top} l {right} {top} {right} {bottom} {left} {bottom} {left} {top}{{\\p0}}"
                )
            grid_path = [f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0"]
            grid_path.extend(
                f"m {round(column * cell_w)} 0 l {round(column * cell_w)} {h}"
                for column in range(1, overlay.columns)
            )
            grid_path.extend(
                f"m 0 {round(row * cell_h)} l {w} {round(row * cell_h)}"
                for row in range(1, overlay.rows)
            )
            # libass may discard zero-area line subpaths; filled thin strips remain visible.
            interior = []
            for column in range(1, overlay.columns):
                line_x = round(column * cell_w)
                interior.append(f"m {line_x} 0 l {line_x + 2} 0 {line_x + 2} {h} {line_x} {h}")
            for row in range(1, overlay.rows):
                line_y = round(row * cell_h)
                interior.append(f"m 0 {line_y} l {w} {line_y} {w} {line_y + 2} 0 {line_y + 2}")
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord0\\1a&H00&\\1c&H303030&}}"
                + " ".join(interior) + "{\\p0}"
            )
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord2\\1a&HFF&\\3c&H303030&}}"
                + " ".join(grid_path)
                + "{\\p0}"
            )
            font_size = max(18, round(min(cell_w, cell_h) * 0.48))
            for cell_index, cell in enumerate(overlay.cells):
                row, column = divmod(cell_index, overlay.columns)
                cell_x = x + round((column + 0.5) * cell_w)
                cell_y = y + round((row + 0.5) * cell_h)
                safe_cell = (
                    cell.replace("\\", "＼")
                    .replace("{", "(")
                    .replace("}", ")")
                    .replace("\r", " ")
                    .replace("\n", " ")
                )
                contents.append(
                    f"{{\\an5\\fs{font_size}\\b1\\bord1\\3c&HFFFFFF&\\1c&H202020&"
                    f"\\pos({cell_x},{cell_y})}}{safe_cell}"
                )
        events.extend(
            f"Dialogue: 0,{start},{end},Default,,0,0,0,,{content}" for content in contents
        )
    return header + "\n".join(events) + "\n"


def _overlay_recipe_from_ass(
    ass_text: str, fps: int, *, scale_timer_events: bool
) -> OverlayFilterRecipe:
    if not scale_timer_events:
        return OverlayFilterRecipe(fps, (OverlayAssPass(0, False, ass_text),))

    first_dialogue = ass_text.find("Dialogue: ")
    if first_dialogue < 0:
        return OverlayFilterRecipe(fps, (OverlayAssPass(0, False, ass_text),))
    header = ass_text[:first_dialogue]
    lines = [
        line for line in ass_text[first_dialogue:].split("\n")
        if line.startswith("Dialogue: ")
    ]
    layered: dict[int, list[tuple[bool, str]]] = {}
    has_running_timer = False
    for line in lines:
        fields = line[len("Dialogue: "):].split(",", 9)
        if len(fields) != 10:
            raise ValueError("Malformed ASS dialogue in overlay recipe")
        try:
            layer = int(fields[0])
        except ValueError as exc:
            raise ValueError("ASS dialogue layer must be an integer") from exc
        timer_pts_scaled = False
        if fields[4].startswith(_TIMER_FRAME_EVENT_PREFIX):
            frame_parts = fields[4][len(_TIMER_FRAME_EVENT_PREFIX):].split(":")
            if len(frame_parts) != 2:
                raise ValueError("Malformed timer frame marker in ASS dialogue")
            begin, finish = (int(part) for part in frame_parts)
            fields[1] = _scaled_timer_ass_time(begin, fps)
            fields[2] = _scaled_timer_ass_time(finish, fps)
            fields[4] = ""
            timer_pts_scaled = True
            has_running_timer = True
        layered.setdefault(layer, []).append(
            (timer_pts_scaled, "Dialogue: " + ",".join(fields))
        )

    if not has_running_timer:
        layer = min(layered, default=0)
        return OverlayFilterRecipe(fps, (OverlayAssPass(layer, False, ass_text),))

    passes: list[OverlayAssPass] = []
    for layer in sorted(layered):
        run_kind: bool | None = None
        run: list[str] = []
        for timer_pts_scaled, line in layered[layer]:
            if run and timer_pts_scaled != run_kind:
                passes.append(
                    OverlayAssPass(layer, bool(run_kind), header + "\n".join(run) + "\n")
                )
                run = []
            run_kind = timer_pts_scaled
            run.append(line)
        if run:
            passes.append(
                OverlayAssPass(layer, bool(run_kind), header + "\n".join(run) + "\n")
            )
    return OverlayFilterRecipe(fps, tuple(passes))


def overlay_filter_recipe(
    shot: Shot, width: int, height: int, fps: int, font: str = "Arial"
) -> OverlayFilterRecipe:
    """Build shared ASS passes, scaling only running timer PTS above 100 FPS."""
    if not shot.overlays:
        return OverlayFilterRecipe(fps, ())
    scale_timer_events = fps > 100 and any(
        overlay.kind == "timer" and overlay.clock_start_frame is not None
        for overlay in shot.overlays
    )
    ass_text = overlay_ass(
        shot, width, height, fps, font, mark_timer_events=scale_timer_events
    )
    return _overlay_recipe_from_ass(
        ass_text, fps, scale_timer_events=scale_timer_events
    )


def overlay_review_evidence(shot: Shot, fps: int) -> dict[str, Any]:
    """Describe compiled behavior at a declared canonical review canvas size."""
    recipe = overlay_filter_recipe(shot, 1920, 1080, fps)
    rendered = "\n".join(item.ass_text for item in recipe.passes)
    ass_files = [f"overlay_pass_{index}.ass" for index in range(len(recipe.passes))]
    timer_overlays = [o for o in shot.overlays if o.kind == "timer"]
    running_clocks = sorted({
        int(o.clock_start_frame) for o in timer_overlays
        if o.clock_start_frame is not None
    })
    recipe_evidence = {
        "canvas": {"width": 1920, "height": 1080},
        "fingerprint": recipe.fingerprint,
        "passes": [
            {
                "layer": item.layer,
                "timer_pts_scaled": item.timer_pts_scaled,
                "ass_sha256": item.sha256,
            }
            for item in recipe.passes
        ],
        "filter_chain": recipe.filter_chain(ass_files) if ass_files else "",
    }
    return {
        "shot_id": shot.shot_id,
        "renderer_version": RENDERER_VERSION,
        "camera_motion": shot.motion,
        "local_position_animation": "\\move(" in rendered,
        "local_property_animation": "\\t(" in rendered,
        "local_fade_animation": "\\fad(" in rendered,
        "overlay_recipe": recipe_evidence,
        "visible_copy": [overlay.text for overlay in shot.overlays if overlay.text
                         and not (overlay.kind == "start_transition" and overlay.text == "Start")],
        "timer_behavior": (
            f"global frame countdown at clock starts {running_clocks}"
            if running_clocks else "fixed readout" if timer_overlays else None
        ),
        "start_transition_behavior": "static cue-bound header badge; grid unobscured"
            if any(o.kind == "start_transition" and o.text != "Start" for o in shot.overlays) else None,
    }



_DEFAULT_RUN_COMMAND = run_command
_DEFAULT_PROBE_VIDEO = probe_video


class _LegacyRenderRunner:
    """Execution adapter for tests that monkeypatch render.run_command or render.probe_video."""

    def __init__(self, expected_frames: int = 30) -> None:
        self.expected_frames = expected_frames

    def run_ffmpeg(
        self,
        args: list[str],
        *,
        cwd: Path | str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        cmd = ["ffmpeg"] + list(args)
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
        try:
            run_command(cmd, execution_cwd, timeout=timeout or 600)
            return ("", "")
        except RuntimeError as exc:
            raise MediaExecutionError(
                str(exc),
                cmd=cmd,
                returncode=1,
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
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Media file not found: {p}")
        try:
            if probe_video is not _DEFAULT_PROBE_VIDEO:
                res = probe_video(p, frames=self.expected_frames, fps=30, require_audio=require_audio)
                if isinstance(res, dict):
                    return MediaProbeResult(
                        duration=float(res.get("duration", self.expected_frames / 30.0)),
                        total_frames=int(res.get("nb_read_frames", self.expected_frames)),
                        width=int(res.get("width", 640)),
                        height=int(res.get("height", 360)),
                        fps=float(res.get("fps", 30.0)),
                        pix_fmt=str(res.get("pix_fmt", "yuv420p")),
                        color_range=str(res.get("color_range", "tv")),
                        has_audio=True,
                        raw=res,
                    )
        except ValueError:
            raise
        except Exception:
            pass
        if run_command is not _DEFAULT_RUN_COMMAND and p.stat().st_size < 100:
            # Test written mock byte artifact
            return MediaProbeResult(
                duration=self.expected_frames / 30.0,
                total_frames=self.expected_frames,
                width=640,
                height=360,
                fps=30.0,
                pix_fmt="yuv420p",
                color_range="tv",
                has_audio=True,
            )
        return SubprocessMediaRunner().probe(path, require_audio=require_audio, timeout=timeout)


def _get_runner(runner: MediaRunner | None = None, expected_frames: int = 30) -> MediaRunner:
    if runner is not None:
        return runner
    default = get_default_runner()
    if not isinstance(default, SubprocessMediaRunner):
        return default
    if run_command is not _DEFAULT_RUN_COMMAND or probe_video is not _DEFAULT_PROBE_VIDEO:
        return _LegacyRenderRunner(expected_frames=expected_frames)
    return default

def render_plan(
    run_dir: str | Path,
    config: dict[str, Any],
    *,
    preview: bool = False,
    runner: MediaRunner | None = None,
) -> Path:
    with leased_resource(resource_database(), "encoder"):
        return _render_plan(run_dir, config, preview=preview, runner=runner)


def _render_plan(
    run_dir: str | Path,
    config: dict[str, Any],
    *,
    preview: bool = False,
    runner: MediaRunner | None = None,
) -> Path:
    from .audio_adoption import (
        assert_current_audio_state,
        capture_audio_state,
        require_adopted_audio_review,
    )
    root = Path(run_dir).resolve()
    with publication_guard():
        audio_state = capture_audio_state(root, validate_pair=True)
    brief = load_brief(root)
    require_adopted_audio_review(root, brief)
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
    timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    validate_plan(plan, timeline, brief)
    if brief.version >= 3:
        require_editorial_review(root, plan, brief)
    verify_generated_assets(root, plan, brief)
    from .visual_gate import require_visual_audit

    require_visual_audit(root, plan, brief, render_config=config)
    receipts = {asset_storage_id(s): read_shot_receipt(root, s) for s in plan.shots}
    asset_hashes = {asset_storage_id(s): read_shot_receipt(root, s)["sha256"] for s in plan.shots}
    if not preview:
        approval = json.loads((root / "editorial_approval.json").read_text(encoding="utf-8"))
        from .review import require_no_human_rejection

        current_preview = json.loads((root / "adaptive_preview.json").read_text(encoding="utf-8"))
        require_no_human_rejection(root, fingerprint(plan), current_preview["sha256"])
        require_no_human_rejection(root, fingerprint(plan), approval.get("preview_sha256", ""))
        if approval.get("plan") != fingerprint(plan) or approval.get("assets") != asset_hashes:
            raise ValueError("Editorial approval does not match this plan and these assets")
    audio = (root / timeline["audio_file"]).resolve()
    if not audio.is_relative_to(root) or not audio.is_file():
        raise ValueError("Canonical audio is unavailable inside the selected run")

    resolved_runner = _get_runner(runner, expected_frames=plan.total_frames)

    # Audio duration probe directly via MediaRunner execution seam
    probe_res = resolved_runner.probe(audio)
    audio_duration = probe_res.duration

    if abs(audio_duration - plan.total_frames / plan.fps) > 1 / plan.fps:
        raise ValueError("Canonical audio duration differs from planned frame coverage")

    width, height = int(config["OUTPUT_WIDTH"]), int(config["OUTPUT_HEIGHT"])
    if min(width, height) < 2 or width % 2 or height % 2:
        raise ValueError("Output dimensions must be even")
    render_config = dict(config, OUTPUT_FPS=plan.fps)
    compiler = VideoCompiler(runner=resolved_runner, base_config=render_config)
    encoder = compiler.detect_encoder(render_config)
    inputs = current_render_inputs(plan, asset_hashes, audio, config, encoder_config=encoder)
    generation = fingerprint(inputs)
    if not preview and approval.get("generation") != generation:
        raise ValueError("Render settings or audio changed after preview approval")
    if not preview:
        current_preview = require_current_preview(root, inputs, plan.total_frames)
        if approval.get("preview_sha256") != current_preview["sha256"]:
            raise ValueError("Editorial approval does not match the current preview")
    recovered = _recover_render_publication(
        root,
        generation,
        inputs,
        plan.total_frames,
        plan.fps,
        preview=preview,
        runner=resolved_runner,
    )
    if recovered is not None:
        return recovered

    work = root / "adaptive_renders" / generation
    work.mkdir(parents=True, exist_ok=True)
    invocation = uuid.uuid4().hex
    pending = work / f"{'preview' if preview else 'master'}_{invocation}.pending.mp4"

    spans: list[CompilationSpan] = []
    asset_paths: dict[str, Path] = {}
    for index, shot in enumerate(plan.shots):
        storage_id = asset_storage_id(shot)
        receipt = receipts[storage_id]
        iw, ih = receipt["dimensions"]
        if max(width / iw, height / ih) * shot.zoom > 2:
            raise ValueError(
                f"Excessive source enlargement for {shot.shot_id}; provide a higher-resolution asset"
            )
        abs_asset_path = (root / receipt["path"]).resolve()
        asset_paths[storage_id] = abs_asset_path
        spans.append(
            CompilationSpan(
                index=index,
                shot_id=shot.shot_id,
                start_frame=shot.start_frame,
                end_frame=shot.end_frame,
                asset_id=storage_id,
                zoom=shot.zoom,
                camera_motion=getattr(shot, "motion", None) or getattr(shot, "camera_motion", "static") or "static",
                overlays=tuple(shot.overlays) if shot.overlays else (),
                metadata={
                    "dimensions": (iw, ih),
                    "source_size": (iw, ih),
                    "focal_x": getattr(shot, "focal_x", 0.5),
                    "focal_y": getattr(shot, "focal_y", 0.5),
                },
            )
        )

    def _execution_validator(execution: Any) -> bool:
        try:
            _require_clip_encoder_execution(execution, inputs)
            return True
        except (ValueError, KeyError, TypeError):
            return False

    target = CompilationTarget(
        width=width,
        height=height,
        fps=plan.fps,
        pixel_format="yuv420p",
        color_range="tv",
    )
    request = CompilationRequest(
        spans=tuple(spans),
        audio_path=audio,
        asset_paths=asset_paths,
        output_path=pending,
        profile=CompilationProfile.PREVIEW if preview else CompilationProfile.BROADCAST_MASTER,
        target=target,
        work_dir=work,
        extra_config=dict(
            config,
            CPU_CRF=config.get("CPU_CRF", 17),
            ASSEMBLY_CODEC="libx264",
            EXACT_WORK_DIR=True,
            GENERATION_OVERRIDE=generation,
            ENCODER_CONFIG=encoder,
            CPU_FALLBACK_CONFIG=inputs["encoder_policy"]["cpu_fallback"],
            FALLBACK_FROM_VALUE=inputs["encoder_recipe"],
            EXECUTION_VALIDATOR=_execution_validator,
        ),
    )

    compiler = VideoCompiler(runner=resolved_runner, base_config=render_config)
    result = compiler.compile(request)

    # Inputs can be edited while a long render is running; never activate stale work.
    current_plan = ShotPlan.model_validate_json(
        (root / "shot_plan.json").read_text(encoding="utf-8")
    )
    current_timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    if (
        load_brief(root) != brief
        or current_plan != plan
        or fingerprint(current_timeline) != plan.timeline_sha256
        or current_render_inputs(plan, asset_hashes, audio, config, encoder_config=encoder) != inputs
    ):
        raise ValueError("Production inputs changed during rendering")
    if {key: read_receipt(root, key)["sha256"] for key in asset_hashes} != asset_hashes:
        raise ValueError("Assets changed during rendering")
    if (
        not preview
        and json.loads((root / "editorial_approval.json").read_text(encoding="utf-8")) != approval
    ):
        raise ValueError("Editorial approval changed during rendering")

    clip_executions = []
    if result.clip_executions:
        clip_executions = list(result.clip_executions)
    else:
        fallback_from = inputs["encoder_recipe"] if result.fallback_occurred else None
        actual_encoder = (
            inputs["encoder_policy"]["cpu_fallback"]
            if result.fallback_occurred
            else inputs["encoder_recipe"]
        )
        for index, _shot in enumerate(plan.shots):
            clip = work / f"clip_{index:05d}.mp4"
            if not clip.is_file():
                raise FileNotFoundError(f"Render clip missing from work directory: {clip}")
            clip_receipt = clip.with_suffix(".json")
            clip_hash = file_digest(clip)
            cached_exec = None
            if clip_receipt.is_file():
                try:
                    cached_exec = json.loads(clip_receipt.read_text(encoding="utf-8")).get("execution")
                except Exception:
                    pass
            if not cached_exec:
                cached_exec = {
                    "encoder_recipe": actual_encoder,
                    "fallback_from": fallback_from,
                }
            if cached_exec and cached_exec.get("fallback_from") == inputs["encoder_recipe"]["video_codec"]:
                cached_exec = dict(cached_exec, fallback_from=inputs["encoder_recipe"])
            clip_executions.append(
                {
                    "index": index,
                    "sha256": clip_hash,
                    "execution": cached_exec,
                }
            )

    output_hash = result.sha256 or file_digest(pending)
    destination = work / (("preview-" if preview else "master-") + output_hash + ".mp4")
    pointer = {
        "version": 1,
        "generation": generation,
        "inputs": inputs,
        "path": str(destination.relative_to(root)),
        "sha256": output_hash,
        "frames": plan.total_frames,
        "editorial_status": "pending" if preview else "approved",
        "encoder_execution": {
            "version": 1,
            "clips": clip_executions,
            "assembly": inputs["encoder_policy"]["assembly"],
        },
    }
    require_encoder_execution(pointer, inputs)
    journal = _render_journal_path(root, generation, preview)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with publication_guard():
        assert_current_audio_state(root, audio_state, validate_pair=True)
        atomic_write_json(
            str(journal),
            {
                "version": 1,
                "kind": "preview" if preview else "master",
                "pointer": pointer,
            },
        )
    with publication_guard():
        assert_current_audio_state(root, audio_state, validate_pair=True)
        if not preview:
            current_preview = require_current_preview(root, inputs, plan.total_frames)
            require_no_human_rejection(root, fingerprint(plan), current_preview["sha256"])
            require_no_human_rejection(root, fingerprint(plan), approval.get("preview_sha256", ""))
        os.replace(pending, destination)
        atomic_write_json(
            str(root / ("adaptive_preview.json" if preview else "active_master.json")),
            pointer,
        )
    _remove_journal(journal)
    return destination
