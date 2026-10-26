"""Unified filtergraph generation and camera kinematics engine.

Conforms to ADR 0002 and ADR 0006.
Consolidates Ken Burns smoothstep kinematics, dynamic duration scaling,
clamped zero-safe evaluation clip(on, 0, N), ASS overlay pass composition,
TV color range normalization, and file-backed -/filter_complex scripts.
"""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from .encoder import EncoderConfig
from .ken_burns import build_ken_burns_filter
from .subtitles import format_dialogue_ass, overlay_filter_recipe

if TYPE_CHECKING:
    from .schema import CompilationTarget

CMD_LENGTH_THRESHOLD: int = 1000


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

class _TimelineBlockRequired(TypedDict):
    name: str
    sec: float
    end_sec: float
    start_frame: int
    end_frame: int
    frame_count: int
    duration: float
    occurrence: int


class TimelineBlock(_TimelineBlockRequired, total=False):
    span: dict[str, Any]
    text: str
    camera_action: str
    words_per_second: float


@dataclass(frozen=True)
class SpanFilterGraphResult:
    """Encapsulates the rendered FFmpeg command arguments and backing filter script."""

    args: list[str]
    filter_string: str
    is_file_backed: bool
    script_path: Path | None
    ass_files: tuple[Path, ...]


# ---------------------------------------------------------------------------
# Camera Kinematics & Focal Framing
# ---------------------------------------------------------------------------

def framed_focal(
    shot_or_span: Any,
    width: int,
    height: int,
    source_size: tuple[int, int] | None = None,
) -> tuple[float, float]:
    """Keep the chosen subject point aligned after the source aspect-ratio crop."""
    focal_x = getattr(shot_or_span, "focal_x", None)
    if focal_x is None:
        meta = getattr(shot_or_span, "metadata", {}) or {}
        focal_x = meta.get("focal_x", 0.5)
    focal_y = getattr(shot_or_span, "focal_y", None)
    if focal_y is None:
        meta = getattr(shot_or_span, "metadata", {}) or {}
        focal_y = meta.get("focal_y", 0.5)

    if source_size is None:
        return float(focal_x), float(focal_y)
    source_width, source_height = source_size
    if min(source_width, source_height, width, height) <= 0:
        raise ValueError("Source and output dimensions must be positive")
    scale = max(2 * width / source_width, 2 * height / source_height)
    scaled_width, scaled_height = source_width * scale, source_height * scale

    def adjusted(focal: float, scaled: float, target: int) -> float:
        crop = 2 * target
        offset = min(max(scaled * focal - crop / 2, 0), max(0, scaled - crop))
        return min(1.0, max(0.0, (scaled * focal - offset) / crop))

    return adjusted(float(focal_x), scaled_width, width), adjusted(float(focal_y), scaled_height, height)


def build_camera_filter(
    shot_or_span: Any,
    width: int,
    height: int,
    fps: int,
    source_size: tuple[int, int] | None = None,
    dynamic_scale: bool = True,
) -> str:
    """Build high-precision Ken Burns smoothstep camera motion filter with zero-safe evaluation."""
    start_frame = int(getattr(shot_or_span, "start_frame", 0))
    end_frame = int(getattr(shot_or_span, "end_frame", 0))
    frames = getattr(shot_or_span, "duration_frames", None)
    if frames is None:
        frames = end_frame - start_frame
    frames = max(1, int(frames))

    shot_id = str(getattr(shot_or_span, "shot_id", "span"))
    motion = str(getattr(shot_or_span, "motion", None) or getattr(shot_or_span, "camera_motion", "static"))
    zoom_raw = getattr(shot_or_span, "zoom", 1.0)
    zoom_val = float(zoom_raw)

    focal_x, focal_y = framed_focal(shot_or_span, width, height, source_size)
    den = max(1, frames - 1)
    t = f"clip(on,0,{den})/{den}"
    ease = f"(({t})*({t})*(3-2*({t})))"

    # Map motion aliases
    if motion == "zoom_in":
        motion = "push"
    elif motion == "zoom_out":
        motion = "pull"

    # Dynamic duration-based scale clamping
    if dynamic_scale and motion in {"push", "pull"} and zoom_val == 1.0:
        dur = frames / max(1, fps)
        zoom_val = round(max(1.06, min(1.10, 1.06 + (dur - 2.5) / 2.0 * 0.04)), 3)

    zoom = str(zoom_val)
    if motion == "push":
        zoom = f"1+({zoom_val}-1)*{ease}"
    elif motion == "pull":
        zoom = f"{zoom_val}-({zoom_val}-1)*{ease}"

    x = f"clip(iw*{focal_x}-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip(ih*{focal_y}-ih/zoom/2,0,ih-ih/zoom)"

    if motion in {"pan_left", "pan_right"}:
        if zoom_val <= 1.0:
            zoom_val = 1.05
            zoom = str(zoom_val)
        viewport = 1 / zoom_val
        travel = 1 - viewport
        safe_start = min(travel, max(0.0, focal_x - 0.75 * viewport))
        safe_end = min(travel, max(0.0, focal_x - 0.25 * viewport))
        if safe_end - safe_start < 0.005:
            raise ValueError(f"No safe pan travel around the focal subject in {shot_id}; use hold")
        left = f"clip(iw*{focal_x}-0.75*iw/zoom,0,iw-iw/zoom)"
        right = f"clip(iw*{focal_x}-0.25*iw/zoom,0,iw-iw/zoom)"
        x = f"{right}+({left}-{right})*{ease}" if motion == "pan_left" else f"{left}+({right}-{left})*{ease}"

    return (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width * 2}:{height * 2}:"
        f"x='clip(iw*{focal_x}-{width},0,iw-{width * 2})':"
        f"y='clip(ih*{focal_y}-{height},0,ih-{height * 2})',"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
        f"trim=end_frame={frames},setpts=PTS-STARTPTS,setsar=1"
    )


camera_filter = build_camera_filter


# ---------------------------------------------------------------------------
# Pixel Format & Color Range Normalization
# ---------------------------------------------------------------------------

def pixel_format_for_encoder(encoder_recipe: Mapping[str, Any]) -> str:
    """Return the hardware-compliant pixel format for the selected encoder."""
    return "nv12" if encoder_recipe.get("video_codec") == "h264_qsv" else "yuv420p"


def normalize_color_range_filter(pixel_format: str) -> str:
    """Convert detected source range to TV range, then tag the supported output format."""
    if pixel_format not in {"nv12", "yuv420p"}:
        raise ValueError("Render pixel format must be nv12 or yuv420p")
    return (
        f"scale=w=iw:h=ih:in_range=auto:out_range=tv,"
        f"format={pixel_format},setparams=range=tv"
    )


# ---------------------------------------------------------------------------
# Unified Span Filtergraph Builder
# ---------------------------------------------------------------------------

def build_span_filter_graph(
    span: Any,
    target: CompilationTarget,
    encoder_config: Mapping[str, Any],
    work_dir: Path,
    source_size: tuple[int, int] | None = None,
    font: str = "Arial",
    force_file_backed: bool = False,
    cmd_length_threshold: int = CMD_LENGTH_THRESHOLD,
    external_subtitles_path: Path | None = None,
) -> SpanFilterGraphResult:
    """Build the unified single-pass filtergraph for one span.

    External ASS files keep episode-global timestamps. Shift each span's PTS to
    the episode timeline only while libass evaluates the file, then restore
    local PTS so concatenation remains gap-free.
    """
    cam_filter = build_camera_filter(span, target.width, target.height, target.fps, source_size)
    filter_elements = [cam_filter]

    overlays = getattr(span, "overlays", ()) or ()
    dialogue_events = getattr(span, "dialogue_events", ()) or ()
    ass_files: list[Path] = []
    span_idx = int(getattr(span, "index", 0))

    if overlays:
        recipe = overlay_filter_recipe(span, target.width, target.height, target.fps, font=font)
        ass_names = [
            f"overlay_{span_idx:05d}_{pass_idx:02d}.ass"
            for pass_idx in range(len(recipe.passes))
        ]
        for ass_name, ass_pass in zip(ass_names, recipe.passes, strict=True):
            ass_path = work_dir / ass_name
            ass_path.write_text(ass_pass.ass_text, encoding="utf-8")
            ass_files.append(ass_path)
        recipe_filters = recipe.filter_chain(ass_names)
        if recipe_filters:
            filter_elements.append(recipe_filters)

    if external_subtitles_path is not None:
        external_path = Path(external_subtitles_path)
        if not external_path.is_file():
            raise FileNotFoundError(f"External subtitles not found: {external_path}")
        external_name = f"external_subtitles_{span_idx:05d}.ass"
        external_copy = work_dir / external_name
        if external_path.resolve() != external_copy.resolve():
            external_copy.write_bytes(external_path.read_bytes())
        ass_files.append(external_copy)
        offset_seconds = float(getattr(span, "start_frame", 0)) / float(target.fps)
        filter_elements.append(f"setpts=PTS+{offset_seconds:.9f}/TB")
        filter_elements.append(f"ass={external_name}")
        filter_elements.append(f"setpts=PTS-{offset_seconds:.9f}/TB")

    if dialogue_events:
        dialogue_ass_name = f"dialogue_{span_idx:05d}.ass"
        dialogue_path = work_dir / dialogue_ass_name
        dialogue_text = format_dialogue_ass(
            dialogue_events, target.width, target.height, target.fps, font=font
        )
        dialogue_path.write_text(dialogue_text, encoding="utf-8")
        ass_files.append(dialogue_path)
        filter_elements.append(f"ass={dialogue_ass_name}")

    pix_fmt = pixel_format_for_encoder(encoder_config)
    color_filter = normalize_color_range_filter(pix_fmt)
    filter_elements.append(color_filter)

    full_filter = ",".join(filter_elements)

    needs_file_backed = (
        force_file_backed
        or len(full_filter) > cmd_length_threshold
        or bool(overlays)
        or bool(dialogue_events)
        or external_subtitles_path is not None
    )

    if needs_file_backed:
        graph_name = f"graph_{span_idx:05d}.txt"
        graph_path = work_dir / graph_name
        graph_content = f"[0:v]{full_filter}[vout]"
        graph_path.write_text(graph_content, encoding="utf-8")
        args = ["-/filter_complex", graph_name, "-map", "[vout]"]
        return SpanFilterGraphResult(
            args=args,
            filter_string=full_filter,
            is_file_backed=True,
            script_path=graph_path,
            ass_files=tuple(ass_files),
        )

    return SpanFilterGraphResult(
        args=["-vf", full_filter],
        filter_string=full_filter,
        is_file_backed=False,
        script_path=None,
        ass_files=tuple(ass_files),
    )


# ---------------------------------------------------------------------------
# Legacy Chunked Filtergraph Builder (for backwards compatibility)
# ---------------------------------------------------------------------------

def _natural_sort_key(s: str) -> list[str | int]:
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def get_sorted_images(images_dir: str) -> list[str]:
    if not os.path.exists(images_dir):
        return []
    images = [f for f in os.listdir(images_dir) if f.endswith(".png")]
    return sorted(images, key=_natural_sort_key)


def _resolve_image_path(
    block_name: str,
    idx: int,
    images_dir: str,
    available_images: Sequence[str],
    last_valid_image: str | None,
    occurrence: int = 1,
) -> tuple[str | None, str | None]:
    """Search both primary and duplicate folders to resolve image candidate."""
    ts_name = block_name
    ts_variants = [ts_name]

    if ts_name.startswith("00_"):
        ts_variants.append(ts_name[3:])
    elif len(ts_name.split("_")) == 2:
        ts_variants.append(f"00_{ts_name}")

    possible_names = []
    parent_run_folder = os.path.dirname(images_dir)
    dup_images_dir = os.path.join(parent_run_folder, "generated_images_duplicates")

    search_dirs = [images_dir]
    if os.path.exists(dup_images_dir):
        search_dirs.append(dup_images_dir)

    for tv in ts_variants:
        if occurrence == 1:
            possible_names.extend(
                [
                    f"{tv}.png",
                    f"{tv}_1.png",
                    f"{tv}_frame1.png",
                    f"{tv}_duplicate_0.png",
                    f"sentence_{idx + 1}.png",
                ]
            )
        else:
            possible_names.extend(
                [
                    f"{tv}_{occurrence}.png",
                    f"{tv}_frame{occurrence}.png",
                    f"{tv}_duplicate_{occurrence - 1}.png",
                    f"{tv}_duplicate_{occurrence}.png",
                    f"sentence_{idx + 1}.png",
                ]
            )

    for s_dir in search_dirs:
        for candidate in possible_names:
            candidate_path = os.path.join(s_dir, candidate)
            if os.path.exists(candidate_path) and os.path.getsize(candidate_path) > 0:
                return candidate_path, candidate

    for s_dir in search_dirs:
        if os.path.exists(s_dir):
            all_files = os.listdir(s_dir)
            for tv in ts_variants:
                matching = [f for f in all_files if f.startswith(tv) and f.endswith(".png")]
                matching.sort(key=_natural_sort_key)
                if matching:
                    chosen = matching[min(occurrence - 1, len(matching) - 1)]
                    chosen_path = os.path.join(s_dir, chosen)
                    if os.path.exists(chosen_path) and os.path.getsize(chosen_path) > 0:
                        return chosen_path, chosen

    if idx < len(available_images):
        fallback_path = os.path.join(images_dir, available_images[idx])
        if os.path.exists(fallback_path) and os.path.getsize(fallback_path) > 0:
            return fallback_path, available_images[idx]

    if last_valid_image and os.path.exists(last_valid_image):
        return last_valid_image, os.path.basename(last_valid_image)

    return None, None


def build_chunk_filter_graph(
    config: Mapping[str, Any],
    encoder_config: EncoderConfig,
    chunk_timeline: Sequence[TimelineBlock],
    images_dir: str,
    ai_cameras: Mapping[str, str],
    manual_cameras: Mapping[str, str],
    anim_enabled: bool,
    global_offset_idx: int = 0,
) -> tuple[list[str], str, str]:
    available_images = get_sorted_images(images_dir)
    last_valid_image = None

    input_args = []
    filter_parts = []
    clip_labels = []
    input_idx = 0

    for i, block in enumerate(chunk_timeline):
        global_idx = global_offset_idx + i
        abs_image_path, _ = _resolve_image_path(
            block["name"],
            global_idx,
            images_dir,
            available_images,
            last_valid_image,
            occurrence=block["occurrence"],
        )
        if abs_image_path is None:
            continue
        last_valid_image = abs_image_path

        frame_count = block["frame_count"]

        camera_action = (block.get("camera_action") or "static") if anim_enabled else "static_hold"
        if anim_enabled and camera_action == "static":
            ai_action = ai_cameras.get(block["name"], "")
            if ai_action:
                camera_action = str(ai_action)
            else:
                pool = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
                camera_action = pool[global_idx % len(pool)]
            if block["name"] in manual_cameras:
                camera_action = str(manual_cameras[block["name"]])

        words_per_second = block.get("words_per_second")
        if words_per_second is None:
            span = block.get("span")
            if isinstance(span, dict) and span.get("text") and float(span.get("duration", 0) or 0) > 0:
                words_per_second = len(str(span.get("text", "")).split()) / max(0.1, float(span.get("duration", 1.0)))
            elif block.get("text") and float(block.get("duration", 0) or 0) > 0:
                words_per_second = len(str(block.get("text", "")).split()) / max(0.1, float(block.get("duration", 1.0)))
            else:
                words_per_second = 3.0
        else:
            try:
                words_per_second = float(words_per_second)
            except (ValueError, TypeError):
                words_per_second = 3.0

        kb_params = inspect.signature(build_ken_burns_filter).parameters
        if "words_per_second" in kb_params:
            kb = build_ken_burns_filter(
                config, frame_count, camera_action, words_per_second=words_per_second
            )
        else:
            kb = build_ken_burns_filter(config, frame_count, camera_action)

        safe_image_path = os.path.abspath(abs_image_path).replace("\\", "/")
        input_args.extend(["-i", safe_image_path])
        filter_parts.append(f"[{input_idx}:v]{kb}[v{input_idx}];")
        clip_labels.append(f"[v{input_idx}]")
        input_idx += 1

    n_clips = len(clip_labels)
    if n_clips == 0:
        raise ValueError("No image clips to render in chunk")

    final_format = "nv12" if encoder_config.get("video_codec") == "h264_qsv" else "yuv420p"
    filter_parts.append(
        f"{''.join(clip_labels)}concat=n={n_clips}:v=1:a=0,format={final_format}[vout]"
    )

    filter_complex = "".join(filter_parts)
    return input_args, filter_complex, "vout"
