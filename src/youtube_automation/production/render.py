"""Render approved editorial instructions with exact frame budgets and atomic activation."""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from youtube_automation.core.utils import atomic_write_json
from youtube_automation.video.encoder import _build_encoder_config, detect_hardware_encoder

from .assets import file_digest, read_receipt
from .contracts import fingerprint, load_brief
from .flow import verify_generated_assets
from .ledger import leased_resource, publication_guard, resource_database
from .shots import Shot, ShotPlan, require_editorial_review, validate_plan
from .writing import atomic_text


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
    path: Path, frames: int, fps: int, *, require_audio: bool = False
) -> dict[str, Any]:
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
    if int(video["nb_read_frames"]) != frames:
        raise ValueError("Rendered frame count differs from the edit plan")
    num, den = map(int, video["avg_frame_rate"].split("/"))
    if den == 0 or num / den != fps:
        raise ValueError("Rendered frame rate differs from the edit plan")
    if require_audio and not any(s["codec_type"] == "audio" for s in streams):
        raise ValueError("Final output has no audio stream")
    return video


def _render_journal_path(root: Path, generation: str, preview: bool) -> Path:
    kind = "preview" if preview else "master"
    return root / ".publication_journal" / "renders" / f"{kind}-{generation}.json"


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
) -> Path | None:
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
        probe_video(destination, frames, fps, require_audio=True)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return None
    with publication_guard():
        atomic_write_json(
            str(root / ("adaptive_preview.json" if preview else "active_master.json")),
            pointer,
        )
    _remove_journal(journal)
    return destination


def framed_focal(
    shot: Shot, width: int, height: int, source_size: tuple[int, int] | None
) -> tuple[float, float]:
    """Keep the chosen subject point aligned after the source aspect-ratio crop."""
    if source_size is None:
        return shot.focal_x, shot.focal_y
    source_width, source_height = source_size
    if min(source_width, source_height, width, height) <= 0:
        raise ValueError("Source and output dimensions must be positive")
    scale = max(2 * width / source_width, 2 * height / source_height)
    scaled_width, scaled_height = source_width * scale, source_height * scale

    def adjusted(focal: float, scaled: float, target: int) -> float:
        crop = 2 * target
        offset = min(max(scaled * focal - crop / 2, 0), max(0, scaled - crop))
        return min(1.0, max(0.0, (scaled * focal - offset) / crop))

    return adjusted(shot.focal_x, scaled_width, width), adjusted(shot.focal_y, scaled_height, height)


def camera_filter(
    shot: Shot, width: int, height: int, fps: int, source_size: tuple[int, int] | None = None
) -> str:
    frames = shot.end_frame - shot.start_frame
    focal_x, focal_y = framed_focal(shot, width, height, source_size)
    t = f"clip(on,0,{max(1, frames - 1)})/{max(1, frames - 1)}"
    ease = f"(({t})*({t})*(3-2*({t})))"
    zoom = str(float(shot.zoom))
    if shot.motion == "push":
        zoom = f"1+({shot.zoom}-1)*{ease}"
    elif shot.motion == "pull":
        zoom = f"{shot.zoom}-({shot.zoom}-1)*{ease}"
    x = f"clip(iw*{focal_x}-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip(ih*{focal_y}-ih/zoom/2,0,ih-ih/zoom)"
    if shot.motion in {"pan_left", "pan_right"}:
        viewport = 1 / shot.zoom
        travel = 1 - viewport
        safe_start = min(travel, max(0, focal_x - 0.75 * viewport))
        safe_end = min(travel, max(0, focal_x - 0.25 * viewport))
        if safe_end - safe_start < 0.005:
            raise ValueError(f"No safe pan travel around the focal subject in {shot.shot_id}; use hold")
        left = f"clip(iw*{focal_x}-0.75*iw/zoom,0,iw-iw/zoom)"
        right = f"clip(iw*{focal_x}-0.25*iw/zoom,0,iw-iw/zoom)"
        x = f"{right}+({left}-{right})*{ease}" if shot.motion == "pan_left" else f"{left}+({right}-{left})*{ease}"
    return (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width * 2}:{height * 2}:"
        f"x='clip(iw*{shot.focal_x}-{width},0,iw-{width * 2})':"
        f"y='clip(ih*{shot.focal_y}-{height},0,ih-{height * 2})',"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
        f"trim=end_frame={frames},setpts=PTS-STARTPTS,setsar=1"
    )


def _ass_time(frame: int, fps: int) -> str:
    cs = round(frame * 100 / fps)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _safe_ass_text(value: str) -> str:
    return (
        value.replace("\\", "＼")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", "")
        .replace("\n", "\\N")
    )


def overlay_ass(shot: Shot, width: int, height: int, fps: int, font: str = "Arial") -> str:
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
                contents.append(
                    f"{{\\an5\\b1\\fs{max(28, h // 2)}\\bord3\\pos({x + w // 2},{y + h // 2})}}{text}"
                )
            else:
                contents.append(f"{{\\pos({x},{y})}}{text}")
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
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord2\\1c&H20283A&\\3c&H5AE0FF&}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{max(22, h // 4)}\\pos({x + w // 2},{y + h // 2})}}"
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
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord2\\1c&H20283A&\\3c&H697386&}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0 m {w // 2} 0 l {w // 2} {h}{{\\p0}}",
                    f"{{\\an5\\b1\\pos({x + w // 4},{y + h // 2})}}{_safe_ass_text(overlay.text)}",
                    f"{{\\an5\\b1\\1c&H5AE0FF&\\pos({x + 3 * w // 4},{y + h // 2})}}"
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
                    f"{{\\an8\\b1\\fs{max(24, height // 22)}\\1c&H5AE0FF&"
                    f"\\pos({x + w // 2},{max(36, y - height // 30)})}}{_safe_ass_text(overlay.text)}",
                ]
            )
        elif overlay.kind == "rule_reveal":
            contents.extend(
                [
                    f"{{\\pos({x},{y})\\p1\\bord0\\1c&H20283A&\\1a&H20&\\fad(180,0)}}"
                    f"m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{max(22, h // 3)}\\pos({x + w // 2},{y + h // 2})"
                    f"\\fad(180,0)}}{_safe_ass_text(overlay.text)}",
                ]
            )
        elif overlay.kind == "fixation_cue":
            cx, cy = x + w // 2, y + h // 2
            radius = max(8, min(w, h) // 5)
            duration_ms = max(1, round((overlay.end_frame - overlay.start_frame) * 1000 / fps))
            contents.extend(
                [
                    f"{{\\pos({cx},{cy})\\p1\\bord3\\1a&HFF&\\3c&H5AE0FF&"
                    f"\\t(0,{duration_ms},\\fscx125\\fscy125\\3a&H80&)}}"
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
            contents.extend(
                [
                    f"{{\\move(0,0,{width},0)\\p1\\bord0\\1c&H20283A&"
                    f"\\clip(0,0,{width},{height})}}"
                    f"m 0 0 l {width} 0 {width} {height} 0 {height} 0 0{{\\p0}}",
                    f"{{\\an5\\b1\\fs{max(36, height // 12)}\\pos({width // 2},{height // 2})"
                    f"\\fad(80,160)}}{_safe_ass_text(overlay.text)}",
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
            contents.append(
                f"{{\\pos({x},{y})\\p1\\bord2\\1a&HFF&\\3c&H303030&}}"
                + " ".join(grid_path)
                + "{\\p0}"
            )
            font_size = max(18, round(min(cell_w, cell_h) * 0.36))
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


def render_plan(run_dir: str | Path, config: dict[str, Any], *, preview: bool = False) -> Path:
    with leased_resource(resource_database(), "encoder"):
        return _render_plan(run_dir, config, preview=preview)


def _render_plan(run_dir: str | Path, config: dict[str, Any], *, preview: bool = False) -> Path:
    root = Path(run_dir).resolve()
    brief = load_brief(root)
    plan = ShotPlan.model_validate_json((root / "shot_plan.json").read_text(encoding="utf-8"))
    timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    validate_plan(plan, timeline, brief)
    if brief.version >= 3:
        require_editorial_review(root, plan, brief)
    verify_generated_assets(root, plan, brief)
    receipts = {s.asset_id: read_receipt(root, s.asset_id) for s in plan.shots}
    asset_hashes = {key: r["sha256"] for key, r in receipts.items()}
    if not preview:
        approval = json.loads((root / "editorial_approval.json").read_text(encoding="utf-8"))
        if approval.get("plan") != fingerprint(plan) or approval.get("assets") != asset_hashes:
            raise ValueError("Editorial approval does not match this plan and these assets")
    audio = (root / timeline["audio_file"]).resolve()
    if not audio.is_relative_to(root) or not audio.is_file():
        raise ValueError("Canonical audio is unavailable inside the selected run")
    duration_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    if abs(float(duration_result.stdout) - plan.total_frames / plan.fps) > 1 / plan.fps:
        raise ValueError("Canonical audio duration differs from planned frame coverage")
    width, height = int(config["OUTPUT_WIDTH"]), int(config["OUTPUT_HEIGHT"])
    if min(width, height) < 2 or width % 2 or height % 2:
        raise ValueError("Output dimensions must be even")
    render_config = dict(config, OUTPUT_FPS=plan.fps)
    encoder = detect_hardware_encoder(render_config)
    audio_hash = file_digest(audio)
    tool_version = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, timeout=15, check=True
    ).stdout.splitlines()[0]
    inputs = {
        "renderer_version": 3,
        "tool": tool_version,
        "plan": fingerprint(plan),
        "assets": asset_hashes,
        "audio": audio_hash,
        "config": render_config,
    }
    generation = fingerprint(inputs)
    if not preview and approval.get("generation") != generation:
        raise ValueError("Render settings or audio changed after preview approval")
    recovered = _recover_render_publication(
        root,
        generation,
        inputs,
        plan.total_frames,
        plan.fps,
        preview=preview,
    )
    if recovered is not None:
        return recovered
    work = root / "adaptive_renders" / generation
    work.mkdir(parents=True, exist_ok=True)
    invocation = uuid.uuid4().hex
    clips = []
    for index, shot in enumerate(plan.shots):
        receipt = receipts[shot.asset_id]
        iw, ih = receipt["dimensions"]
        if max(width / iw, height / ih) * shot.zoom > 2:
            raise ValueError(
                f"Excessive source enlargement for {shot.shot_id}; provide a higher-resolution asset"
            )
        frames = shot.end_frame - shot.start_frame
        clip = work / f"clip_{index:05d}.mp4"
        clip_receipt = clip.with_suffix(".json")
        if clip.exists() and clip_receipt.exists():
            try:
                cached = json.loads(clip_receipt.read_text(encoding="utf-8"))
                if cached != {"generation": generation, "sha256": file_digest(clip)}:
                    raise ValueError("Cached clip content changed")
                probe_video(clip, frames, plan.fps)
                clips.append(clip)
                continue
            except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError):
                pass
        ass_name = f"overlay_{index:05d}_{invocation}.ass"
        ass_content = ""
        if shot.overlays:
            ass_content = overlay_ass(shot, width, height, plan.fps)
            atomic_text(work / ass_name, ass_content)
        for attempt in range(2):
            filters = camera_filter(shot, width, height, plan.fps, (iw, ih))
            if shot.overlays:
                filters += f",ass={ass_name}"
            filters += ",format=" + ("nv12" if encoder["video_codec"] == "h264_qsv" else "yuv420p")
            graph_name = f"graph_{index:05d}_{invocation}.txt"
            graph_content = f"[0:v]{filters}[vout]"
            atomic_text(work / graph_name, graph_content)
            execution_dir = work
            scratch: tempfile.TemporaryDirectory[str] | None = None
            if shot.overlays or len(str(work)) > 240:
                # libass and Windows CreateProcess fail when process cwd resolves beyond
                # the legacy MAX_PATH limit. Keep durable debug copies in the run, but execute
                # from a short system-temp directory.
                scratch = tempfile.TemporaryDirectory(prefix="youtube-overlay-")
                execution_dir = Path(scratch.name)
                if shot.overlays:
                    atomic_text(execution_dir / ass_name, ass_content)
                atomic_text(execution_dir / graph_name, graph_content)
            temporary = work / f"clip_{index:05d}_{invocation}.pending.mp4"
            args = [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(root / receipt["path"]),
                "-/filter_complex",
                graph_name,
                "-map",
                "[vout]",
                "-frames:v",
                str(frames),
                "-an",
                "-c:v",
                encoder["video_codec"],
                *encoder["encoder_args"],
                str(temporary),
            ]
            try:
                run_command(args, execution_dir)
                probe_video(temporary, frames, plan.fps)
                clip_hash = file_digest(temporary)
                with publication_guard():
                    os.replace(temporary, clip)
                    atomic_write_json(
                        str(clip_receipt), {"generation": generation, "sha256": clip_hash}
                    )
                break
            except (RuntimeError, ValueError, KeyError, StopIteration, subprocess.SubprocessError):
                if attempt or encoder["video_codec"] == "libx264":
                    raise
                encoder = _build_encoder_config("libx264", render_config)
            finally:
                if scratch is not None:
                    scratch.cleanup()
        clips.append(clip)
    concat_lines = [
        f"file '{p.resolve().as_posix()}'\n" if len(str(work)) > 240 else f"file '{p.name}'\n"
        for p in clips
    ]
    atomic_text(work / "concat.txt", "".join(concat_lines))
    pending = work / f"master_{invocation}.pending.mp4"
    concat_scratch: tempfile.TemporaryDirectory[str] | None = None
    concat_cwd = work
    concat_input = "concat.txt"
    safe_flag = "1"
    if len(str(work)) > 240:
        concat_scratch = tempfile.TemporaryDirectory(prefix="youtube-concat-")
        concat_cwd = Path(concat_scratch.name)
        concat_input = (work / "concat.txt").resolve().as_posix()
        safe_flag = "0"
    try:
        # Re-encode the assembled stream so a hardware fallback cannot mix incompatible SPS.
        run_command(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                safe_flag,
                "-i",
                concat_input,
                "-i",
                str(audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(config.get("CPU_CRF", 17)),
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(plan.fps),
                "-fps_mode",
                "cfr",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(pending.resolve()),
            ],
            concat_cwd,
            timeout=5400,
        )
    finally:
        if concat_scratch is not None:
            concat_scratch.cleanup()
    probe_video(pending, plan.total_frames, plan.fps, require_audio=True)
    # Inputs can be edited while a long render is running; never activate stale work.
    current_plan = ShotPlan.model_validate_json(
        (root / "shot_plan.json").read_text(encoding="utf-8")
    )
    current_timeline = json.loads((root / "timeline.json").read_text(encoding="utf-8"))
    if (
        load_brief(root) != brief
        or current_plan != plan
        or fingerprint(current_timeline) != plan.timeline_sha256
        or file_digest(audio) != audio_hash
    ):
        raise ValueError("Production inputs changed during rendering")
    if {key: read_receipt(root, key)["sha256"] for key in asset_hashes} != asset_hashes:
        raise ValueError("Assets changed during rendering")
    if (
        not preview
        and json.loads((root / "editorial_approval.json").read_text(encoding="utf-8")) != approval
    ):
        raise ValueError("Editorial approval changed during rendering")
    output_hash = file_digest(pending)
    destination = work / (("preview-" if preview else "master-") + output_hash + ".mp4")
    pointer = {
        "version": 1,
        "generation": generation,
        "inputs": inputs,
        "path": str(destination.relative_to(root)),
        "sha256": output_hash,
        "frames": plan.total_frames,
        "editorial_status": "pending" if preview else "approved",
    }
    journal = _render_journal_path(root, generation, preview)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with publication_guard():
        atomic_write_json(
            str(journal),
            {
                "version": 1,
                "kind": "preview" if preview else "master",
                "pointer": pointer,
            },
        )
    with publication_guard():
        os.replace(pending, destination)
        atomic_write_json(
            str(root / ("adaptive_preview.json" if preview else "active_master.json")),
            pointer,
        )
    _remove_journal(journal)
    return destination
