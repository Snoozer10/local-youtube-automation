from __future__ import annotations

import inspect
import os
import re

from .ken_burns import build_ken_burns_filter


def get_sorted_images(images_dir):
    if not os.path.exists(images_dir):
        return []
    images = [f for f in os.listdir(images_dir) if f.endswith(".png")]

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

    return sorted(images, key=natural_sort_key)


def _resolve_image_path(
    block_name, idx, images_dir, available_images, last_valid_image, occurrence=1
):
    """
    Searches both primary 'generated_images' and 'generated_images_duplicates' folders
    to resolve standalone images and multi-frame set duplicates.
    """
    ts_name = block_name
    ts_variants = [ts_name]

    # Generate timestamp variant aliases (e.g. 00_01_15 <-> 01_15)
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

    # 1. Direct candidate match in search directories
    for s_dir in search_dirs:
        for candidate in possible_names:
            candidate_path = os.path.join(s_dir, candidate)
            if os.path.exists(candidate_path) and os.path.getsize(candidate_path) > 0:
                return candidate_path, candidate

    # Helper for natural sorting (e.g. 00_15_2.png before 00_15_10.png)
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]

    # 2. Prefix match inside search directories with natural numeric ordering
    for s_dir in search_dirs:
        if os.path.exists(s_dir):
            all_files = os.listdir(s_dir)
            for tv in ts_variants:
                matching = [f for f in all_files if f.startswith(tv) and f.endswith(".png")]
                matching.sort(key=natural_sort_key)
                if matching:
                    chosen = matching[min(occurrence - 1, len(matching) - 1)]
                    chosen_path = os.path.join(s_dir, chosen)
                    if os.path.exists(chosen_path) and os.path.getsize(chosen_path) > 0:
                        return chosen_path, chosen

    # 3. Fallback: Sequential index match
    if idx < len(available_images):
        fallback_path = os.path.join(images_dir, available_images[idx])
        if os.path.exists(fallback_path) and os.path.getsize(fallback_path) > 0:
            return fallback_path, available_images[idx]

    # 4. Last valid image fallback
    if last_valid_image and os.path.exists(last_valid_image):
        return last_valid_image, os.path.basename(last_valid_image)

    return None, None


def build_chunk_filter_graph(
    config: dict,
    encoder_config: dict,
    chunk_timeline: list,
    images_dir: str,
    ai_cameras: dict,
    manual_cameras: dict,
    anim_enabled: bool,
    global_offset_idx: int = 0,
) -> tuple:
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

        camera_action = "static"
        if anim_enabled:
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
        # Pass 1-frame image directly without demuxer loop; zoompan/loop will generate exact frame count
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


