"""Create sampled, run-bound PNG evidence before a visual audit exists."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from youtube_automation.core.utils import atomic_write_json
from youtube_automation.video.compiler import load_video_config

from .assets import asset_storage_id, file_digest, read_shot_receipt
from .contracts import fingerprint, load_brief
from .flow import verify_generated_assets
from .ledger import leased_resource, resource_database
from .render import (
    _normalize_color_range_filter,
    _pixel_format_for_encoder,
    camera_filter,
    current_render_inputs,
    overlay_filter_recipe,
)
from .shots import ShotPlan, require_editorial_review, validate_plan
from .visual_gate import enforce_visual_budget


def _contained_path(root: Path, value: Path) -> Path:
    candidate = Path(os.path.abspath(value))
    if not candidate.is_relative_to(root):
        raise ValueError("Proof output must remain inside the selected run")
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Proof output cannot traverse a symlink")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Proof output must remain inside the selected run")
    return resolved


def _timeline_boundaries(value: Any, fps: int, path: tuple[str, ...] = ()) -> dict[int, set[str]]:
    boundaries: dict[int, set[str]] = {}

    def add(frame: int, reason: str) -> None:
        boundaries.setdefault(frame, set()).add(reason)

    if isinstance(value, dict):
        semantic_context = any(
            tag in part for part in path for tag in ("word", "span", "cue", "timer")
        )
        for raw_key, child in value.items():
            key = str(raw_key).lower()
            if "frame" in key and any(
                tag in key for tag in ("word", "cue", "timer", "start", "end", "arrival", "global")
            ) and isinstance(child, int) and not isinstance(child, bool):
                add(child, key)
            if semantic_context and key in {
                "start", "end", "start_seconds", "end_seconds", "start_sec", "end_sec"
            } and isinstance(child, (int, float)) and not isinstance(child, bool):
                seconds = float(child)
                if math.isfinite(seconds) and seconds >= 0:
                    edge = "start" if key.startswith("start") else "end"
                    add(round(seconds * fps), f"{path[-1]}_{edge}_seconds")
            if isinstance(child, (dict, list)):
                boundaries_child = _timeline_boundaries(child, fps, path + (key,))
                for frame, reasons in boundaries_child.items():
                    boundaries.setdefault(frame, set()).update(reasons)
    elif isinstance(value, list):
        for child in value:
            boundaries_child = _timeline_boundaries(child, fps, path)
            for frame, reasons in boundaries_child.items():
                boundaries.setdefault(frame, set()).update(reasons)
    return boundaries


def _samples_for_shot(
    shot: Any, fps: int, global_boundaries: dict[int, set[str]]
) -> dict[int, set[str]]:
    length = shot.end_frame - shot.start_frame
    if length <= 0:
        raise ValueError(f"Shot {shot.shot_id} has no frames")
    samples: dict[int, set[str]] = {}

    def add(index: int, reason: str) -> None:
        local = max(0, min(length - 1, index))
        samples.setdefault(local, set()).add(reason)

    for local, reason in (
        (0, "shot_first"),
        (length - 1, "shot_last"),
        (length // 4, "shot_early"),
        (length // 2, "shot_mid"),
        ((3 * length) // 4, "shot_late"),
    ):
        add(local, reason)

    for overlay in shot.overlays:
        start = int(getattr(overlay, "start_frame", 0))
        end = int(getattr(overlay, "end_frame", length))
        middle = (start + end) // 2
        for local, reason in (
            (start - 1, "overlay_pre_start"),
            (start, "overlay_start"),
            (start + 1, "overlay_start_plus_one"),
            (middle, "overlay_mid"),
            (end - 1, "overlay_end_minus_one"),
            (end, "overlay_end"),
        ):
            add(local, f"{getattr(overlay, 'kind', 'overlay')}:{reason}")
        motion_end = getattr(overlay, "motion_end_frame", None)
        if motion_end is not None and getattr(overlay, "motion_to", None) is not None:
            arrival = int(motion_end)
            motion_mid = (start + arrival) // 2
            hold_frame = min(end - 1, max(arrival + 1, (arrival + end) // 2))
            for local, reason in (
                (motion_mid, "overlay_motion_mid"),
                (arrival, "overlay_motion_arrival"),
                (arrival + 1, "overlay_motion_arrival_plus_one"),
                (hold_frame, "overlay_motion_hold"),
            ):
                add(local, f"{getattr(overlay, 'kind', 'overlay')}:{reason}")
        clock_start = getattr(overlay, "clock_start_frame", None)
        if clock_start is not None:
            local_clock = int(clock_start) - shot.start_frame
            for delta in (-1, 0, 1):
                add(local_clock + delta, "timer_boundary")

    if shot.motion != "hold":
        add(length - 1, "motion_arrival")
        add(length, "motion_arrival_plus_one")

    for global_frame, boundary_reasons in global_boundaries.items():
        for delta in (-1, 0, 1):
            sample_global = global_frame + delta
            if shot.start_frame <= sample_global < shot.end_frame:
                suffix = "pre" if delta < 0 else "post" if delta > 0 else "at"
                for reason in boundary_reasons:
                    add(
                        sample_global - shot.start_frame,
                        f"{reason}_boundary_{suffix}",
                    )

    return samples


def _audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=True,
    )
    return float(result.stdout.strip())


def _run_sample_command(args: list[str], cwd: Path, log_path: Path) -> None:
    with log_path.open("xb") as log:
        result = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=log,
            timeout=180,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(f"FFmpeg PNG sampling failed; see {log_path.name}")


def _preserve_sanitized_log(log_path: Path, destination: Path, root: Path, work_root: Path) -> None:
    raw = log_path.read_bytes().decode("utf-8", errors="replace")
    sanitized = raw.replace(str(root), "<RUN_ROOT>").replace(str(work_root), "<TEMP_ROOT>")
    destination.write_text(sanitized, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_current_proofs(run_dir: str | Path, output_dir: str | Path | None = None) -> Path:
    """Render sampled PNG evidence while holding the shared encoder lease."""
    with leased_resource(resource_database(), "encoder"):
        return _render_current_proofs_locked(run_dir, output_dir)


def _render_current_proofs_locked(
    run_dir: str | Path, output_dir: str | Path | None = None
) -> Path:
    """Render sampled PNG evidence from a validated current run without creating an audit."""
    from .audio_adoption import (
        assert_current_audio_state,
        capture_audio_state,
        require_adopted_audio_review,
    )
    from .ledger import publication_guard

    root = Path(run_dir).resolve(strict=True)
    with publication_guard():
        audio_state = capture_audio_state(root, validate_pair=True)
    if not root.is_dir():
        raise ValueError("Run directory must already exist")
    brief = load_brief(root)
    require_adopted_audio_review(root, brief)
    timeline_path = _contained_path(root, root / "timeline.json")
    plan_path = _contained_path(root, root / "shot_plan.json")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    plan = ShotPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    validate_plan(plan, timeline, brief)
    if brief.version >= 3:
        require_editorial_review(root, plan, brief)
    enforce_visual_budget(root, plan)
    verify_generated_assets(root, plan, brief)

    audio_path = _contained_path(root, root / timeline["audio_file"])
    if not audio_path.is_file():
        raise ValueError("Canonical timeline audio is missing")
    duration = _audio_duration(audio_path)
    expected_duration = plan.total_frames / plan.fps
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Canonical audio duration must be finite and positive")
    if abs(duration - expected_duration) > 1 / plan.fps:
        raise ValueError("Canonical audio duration differs from the planned frame budget")

    receipts = {asset_storage_id(shot): read_shot_receipt(root, shot) for shot in plan.shots}
    asset_hashes = {asset_id: receipt["sha256"] for asset_id, receipt in receipts.items()}
    config = load_video_config("video_config.txt")
    render_inputs = current_render_inputs(plan, asset_hashes, audio_path, config)
    render_inputs_digest = fingerprint(render_inputs)
    encoder_recipe = render_inputs["encoder_recipe"]
    width, height = int(config["OUTPUT_WIDTH"]), int(config["OUTPUT_HEIGHT"])
    if min(width, height) < 2 or width % 2 or height % 2:
        raise ValueError("Output dimensions must be even")
    for shot in plan.shots:
        source_width, source_height = receipts[asset_storage_id(shot)]["dimensions"]
        if max(width / source_width, height / source_height) * shot.zoom > 2:
            raise ValueError(
                f"Excessive source enlargement for {shot.shot_id}; provide a higher-resolution asset"
            )

    proof_root = _contained_path(root, root / ".adaptive_diagnostics" / "render_proofs")
    proof_root.mkdir(parents=True, exist_ok=True)
    if proof_root.is_symlink():
        raise ValueError("Proof directory cannot be a symlink")
    recipe_id = fingerprint(encoder_recipe)[:12]
    requested_output = Path(output_dir) if output_dir is not None else None
    if requested_output is not None and not requested_output.is_absolute():
        requested_output = root / requested_output
    destination = (
        _contained_path(root, requested_output) if requested_output is not None else
        proof_root / f"{recipe_id}-{uuid.uuid4()}"
    )
    if not destination.is_relative_to(proof_root):
        raise ValueError("Proof output must be inside .adaptive_diagnostics/render_proofs")
    destination.mkdir(parents=True, exist_ok=False)
    debug_dir = destination / "debug"
    debug_dir.mkdir()

    global_boundaries = _timeline_boundaries(timeline, plan.fps)
    expected_samples: list[dict[str, Any]] = []
    samples_by_shot: dict[str, dict[int, set[str]]] = {}
    for shot in plan.shots:
        sample_map = _samples_for_shot(shot, plan.fps, global_boundaries)
        samples_by_shot[shot.shot_id] = sample_map
        for local_frame, reasons in sorted(sample_map.items()):
            expected_samples.append({
                "shot_id": shot.shot_id,
                "local_frame_index": local_frame,
                "global_frame_index": shot.start_frame + local_frame,
                "reasons": sorted(reasons),
            })

    generated: list[dict[str, Any]] = []
    pixel_format = _pixel_format_for_encoder(encoder_recipe)
    range_filter = _normalize_color_range_filter(pixel_format)
    try:
        with tempfile.TemporaryDirectory(prefix="rpf-") as temporary:
            work_root = Path(temporary)
            for shot in plan.shots:
                sample_map = samples_by_shot[shot.shot_id]
                receipt = receipts[asset_storage_id(shot)]
                image = _contained_path(root, root / receipt["path"])
                source_size = (int(receipt["dimensions"][0]), int(receipt["dimensions"][1]))
                shot_work = work_root / re.sub(r"[^A-Za-z0-9_-]", "_", shot.shot_id)[:32]
                shot_work.mkdir()
                recipe = overlay_filter_recipe(shot, width, height, plan.fps)
                ass_files: list[str] = []
                for index, overlay_pass in enumerate(recipe.passes):
                    ass_name = f"overlay_{index}.ass"
                    (shot_work / ass_name).write_text(overlay_pass.ass_text, encoding="utf-8")
                    shutil.copyfile(shot_work / ass_name, debug_dir / f"{shot.shot_id}_{ass_name}")
                    ass_files.append(ass_name)
                chain = camera_filter(shot, width, height, plan.fps, source_size=source_size)
                if ass_files:
                    chain += "," + recipe.filter_chain(ass_files)
                chain += "," + range_filter + ",format=rgb24"
                indexes = sorted(sample_map)
                select = "+".join(f"eq(n\\,{index})" for index in indexes)
                graph = (
                    f"[0:v]{chain},select='{select}',setpts=N/({plan.fps}*TB)[vout]\n"
                )
                graph_name = f"{shot.shot_id}.ffgraph"
                graph_path = shot_work / graph_name
                graph_path.write_text(graph, encoding="utf-8")
                shutil.copyfile(graph_path, debug_dir / graph_name)
                pattern = shot_work / "frame_%05d.png"
                args = [
                    "ffmpeg", "-hide_banner", "-nostdin", "-y",
                    "-loop", "1", "-framerate", str(plan.fps), "-i", str(image),
                    "-/filter_complex", str(graph_path), "-map", "[vout]",
                    "-frames:v", str(len(indexes)), "-vsync", "0", "-start_number", "0",
                    "-c:v", "png", str(pattern),
                ]
                log_path = shot_work / "ffmpeg.log"
                durable_log = debug_dir / f"{shot.shot_id}.ffmpeg.log"
                try:
                    _run_sample_command(args, shot_work, log_path)
                except Exception:
                    if log_path.is_file():
                        _preserve_sanitized_log(log_path, durable_log, root, work_root)
                    raise
                _preserve_sanitized_log(log_path, durable_log, root, work_root)
                outputs = sorted(shot_work.glob("frame_*.png"))
                if len(outputs) != len(indexes):
                    raise RuntimeError(
                        f"Shot {shot.shot_id} produced {len(outputs)} of {len(indexes)} expected samples"
                    )
                for local_frame, png in zip(indexes, outputs, strict=True):
                    safe_shot = re.sub(r"[^A-Za-z0-9_-]", "_", shot.shot_id)[:48]
                    relative = Path("samples") / safe_shot / f"frame_{local_frame:06d}.png"
                    final_path = _contained_path(root, destination / relative)
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(png, final_path)
                    if final_path.stat().st_size < 8 or final_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                        raise RuntimeError(f"Shot {shot.shot_id} produced an invalid PNG sample")
                    try:
                        with Image.open(final_path) as decoded_png:
                            decoded_png.load()
                            valid_png = (
                                decoded_png.format == "PNG"
                                and decoded_png.size == (width, height)
                            )
                    except (OSError, SyntaxError, ValueError) as exc:
                        raise RuntimeError(
                            f"Shot {shot.shot_id} produced an invalid PNG sample"
                        ) from exc
                    if not valid_png:
                        raise RuntimeError(f"Shot {shot.shot_id} produced an invalid PNG sample")
                    generated.append({
                        "shot_id": shot.shot_id,
                        "local_frame_index": local_frame,
                        "global_frame_index": shot.start_frame + local_frame,
                        "reasons": sorted(sample_map[local_frame]),
                        "path": relative.as_posix(),
                        "sha256": _sha256(final_path),
                    })
    except Exception:
        raise

    expected_keys = {
        (item["shot_id"], item["local_frame_index"]) for item in expected_samples
    }
    generated_keys = {
        (item["shot_id"], item["local_frame_index"]) for item in generated
    }
    missing = sorted(expected_keys - generated_keys)
    if missing or expected_keys != generated_keys:
        raise RuntimeError(f"Proof samples are incomplete; missing={missing}")

    source_path = Path(__file__).resolve()
    manifest = {
        "schema_version": 1,
        "status": "COMPLETE_SAMPLED_PNGS",
        "run_dir": str(root),
        "plan_fingerprint": fingerprint(plan),
        "audio_sha256": file_digest(audio_path),
        "assets": asset_hashes,
        "current_render_inputs": render_inputs,
        "current_render_inputs_sha256": render_inputs_digest,
        "proof_helper_sha256": _sha256(source_path),
        "renderer_version": render_inputs["renderer_version"],
        "ffmpeg_build": render_inputs["tool"],
        "selected_encoder_recipe": encoder_recipe,
        "production_h264_encoder_executed": False,
        "full_moving_preview_proof": False,
        "encoding_or_pacing_approval": False,
        "visual_budget": {
            "max_images": enforce_visual_budget(root, plan).max_images,
            "counted_proof_frames_as_stills": False,
        },
        "expected_samples": expected_samples,
        "samples": generated,
    }
    with publication_guard():
        assert_current_audio_state(root, audio_state)
        atomic_write_json(str(destination / "manifest.json"), manifest)
    return destination
