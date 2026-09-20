"""Render approved editorial instructions with exact frame budgets and atomic activation."""

from __future__ import annotations

import json
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
from .shots import Shot, ShotPlan, validate_plan
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
    events = []
    for overlay in shot.overlays:
        x, y = round(overlay.x * width), round(overlay.y * height)
        w, h = round(overlay.width * width), round(overlay.height * height)
        if overlay.kind == "label":
            text = (
                overlay.text.replace("\\", "＼")
                .replace("{", "(")
                .replace("}", ")")
                .replace("\r", "")
                .replace("\n", "\\N")
            )
            content = f"{{\\pos({x},{y})}}{text}"
        elif overlay.kind == "highlight":
            content = f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H00BFFF&}}m 0 0 l {w} 0 {w} {h} 0 {h} 0 0{{\\p0}}"
        else:
            # Arrow runs from upper-left to lower-right within its declared box.
            head = max(6, min(w, h) // 5)
            content = f"{{\\pos({x},{y})\\p1\\bord3\\1a&HFF&\\3c&H00BFFF&}}m 0 0 l {w} {h} m {w - head} {h} l {w} {h} {w} {h - head}{{\\p0}}"
        events.append(
            f"Dialogue: 0,{_ass_time(overlay.start_frame, fps)},{_ass_time(overlay.end_frame, fps)},Default,,0,0,0,,{content}"
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
        if shot.overlays:
            atomic_text(work / ass_name, overlay_ass(shot, width, height, plan.fps))
        for attempt in range(2):
            filters = camera_filter(shot, width, height, plan.fps, (iw, ih))
            if shot.overlays:
                filters += f",ass={ass_name}"
            filters += ",format=" + ("nv12" if encoder["video_codec"] == "h264_qsv" else "yuv420p")
            graph_name = f"graph_{index:05d}_{invocation}.txt"
            atomic_text(work / graph_name, f"[0:v]{filters}[vout]")
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
                "-filter_complex_script",
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
                run_command(args, work)
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
        clips.append(clip)
    atomic_text(work / "concat.txt", "".join(f"file '{p.name}'\n" for p in clips))
    pending = work / f"master_{invocation}.pending.mp4"
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
            "1",
            "-i",
            "concat.txt",
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
            str(pending),
        ],
        work,
        timeout=5400,
    )
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
    with publication_guard():
        os.replace(pending, destination)
        atomic_write_json(
            str(root / ("adaptive_preview.json" if preview else "active_master.json")),
            {
                "version": 1,
                "generation": generation,
                "inputs": inputs,
                "path": str(destination.relative_to(root)),
                "sha256": output_hash,
                "frames": plan.total_frames,
                "editorial_status": "pending" if preview else "approved",
            },
        )
    return destination
