import os
import json
import re
import sys
import time 
import random
import subprocess
from datetime import datetime

def load_video_config(config_path="video_config.txt") -> dict:
    """
    Parse video_config.txt into typed dict.
    Supports: bool (true/false), int, float, str.
    Comments (# ...) and blank lines ignored.
    """
    DEFAULTS = {
        "ENABLE_ANIMATIONS": True,
        "ENABLE_SUBTITLES": False,
        "ENABLE_HARDWARE_ENCODER": False,
        "ENABLE_SINGLE_PASS": True,
        "ENABLE_CHECKPOINT_RESUME": True,
        "ENABLE_LOUDNORM_TWOPASS": True,
        "ENABLE_VBV": True,
        "OUTPUT_WIDTH": 1920,
        "OUTPUT_HEIGHT": 1080,
        "OUTPUT_FPS": 30,
        "OUTPUT_PIX_FMT": "yuv420p",
        "OUTPUT_PROFILE": "high",
        "OUTPUT_LEVEL": "4.1",
        "CPU_CRF": 23,
        "CPU_PRESET": "ultrafast",
        "CPU_TUNE": "fastdecode",
        "ENCODER_FORCE": "libx264",
        "QSV_PRESET": "fast",
        "QSV_GLOBAL_QUALITY": 22,
        "QSV_LOOKAHEAD": 0,
        "QSV_LOOKAHEAD_DEPTH": 20,
        "NVENC_PRESET": "p4",
        "NVENC_CQ": 22,
        "NVENC_RC": "vbr",
        "NVENC_MULTIPASS": "fullres",
        "NVENC_SPATIAL_AQ": 1,
        "NVENC_TEMPORAL_AQ": 1,
        "KEN_BURNS_ZOOM_MIN": 1.0,
        "KEN_BURNS_ZOOM_MAX": 1.10,
        "KEN_BURNS_EASING": "smoothstep",
        "KEN_BURNS_UPSCALE_FACTOR": 1.2,
        "KEN_BURNS_INTERP_ALGO": "bicubic",
        "KEN_BURNS_PAN_SPEED": 0.08,
        "KEN_BURNS_ZOOM_SPEED": 0.10,
        "MIN_CLIP_DURATION": 0.5,
        "DEFAULT_CLIP_DURATION": 5.0,
        "MAX_CLIP_DURATION": 30.0,
        "AUDIO_CODEC": "aac",
        "AUDIO_BITRATE": "192k",
        "AUDIO_SAMPLE_RATE": 48000,
        "LOUDNORM_I": -16,
        "LOUDNORM_TP": -1.5,
        "LOUDNORM_LRA": 11,
        "LOUDNORM_MEASURED_I": -99,
        "LOUDNORM_MEASURED_TP": -99,
        "LOUDNORM_MEASURED_LRA": -99,
        "LOUDNORM_MEASURED_THRESH": -99,
        "LOUDNORM_OFFSET": 0,
        "LOUDNORM_LINEAR": True,
        "LOUDNORM_PRINT_FORMAT": "json",
        "VBV_MAXRATE": "8000k",
        "VBV_BUFSIZE": "16000k",
        "FFMPEG_THREADS": 4,
        "FFMPEG_CLIP_TIMEOUT": 300,
        "FFMPEG_FINAL_TIMEOUT": 5400,
        "FFMPEG_LOGLEVEL": "warning",
        "CHECKPOINT_FILE": "compile_checkpoint.json",
        "CHECKPOINT_SAVE_INTERVAL": 5,
        "SUB_FONT_NAME": "Tahoma",
        "SUB_FONT_SIZE": 22,
        "SUB_PRIMARY_COLOR": "&H00FFFFFF",
        "SUB_OUTLINE_COLOR": "&H00000000",
        "SUB_BORDER_STYLE": 1,
        "SUB_OUTLINE": 2.5,
        "SUB_SHADOW": 1,
        "SUB_ALIGNMENT": 2,
        "SUB_MARGIN_V": 50,
        "SUB_BOLD": 1,
        "DEBUG_SAVE_INTERMEDIATES": False,
        "DEBUG_DRY_RUN": False,
        "DEBUG_FILTER_GRAPH_DUMP": False,
        "ENABLE_TRANSITIONS": False,
        "TRANSITION_TYPE": "fade",
        "TRANSITION_DURATION": 0.5,
        "ENABLE_SFX": False,
        "SFX_DIR": "",
        "SFX_DEFAULT_VOLUME": 0.3,
        "EXPORT_SFX_STEM": False,
        "BURN_SFX_INTO_VIDEO": False,
    }

    if not os.path.exists(config_path):
        return DEFAULTS.copy()

    config = DEFAULTS.copy()
    with open(config_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if '#' in value:
                    value = value.split('#', 1)[0].strip()

                if key in DEFAULTS:
                    default_val = DEFAULTS[key]
                    if isinstance(default_val, bool):
                        config[key] = value.lower() in ('true', '1', 'yes', 'on')
                    elif isinstance(default_val, int):
                        config[key] = int(float(value))
                    elif isinstance(default_val, float):
                        config[key] = float(value)
                    else:
                        config[key] = value
    return config


def _probe_encoder(encoder_name: str) -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10
        )
        return encoder_name in result.stdout
    except Exception:
        return False


def _build_encoder_config(encoder: str, config: dict) -> dict:
    base = {
        "video_codec": encoder,
        "encoder_name": encoder,
        "hwaccel": "qsv" if "qsv" in encoder else ("cuda" if "nvenc" in encoder else "none"),
        "encoder_args": [],
    }

    if encoder == "h264_qsv":
        base["encoder_args"] = [
            "-preset", config["QSV_PRESET"],
            "-global_quality", str(config["QSV_GLOBAL_QUALITY"]),
            "-look_ahead", str(config["QSV_LOOKAHEAD"]),
            "-look_ahead_depth", str(config["QSV_LOOKAHEAD_DEPTH"]),
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]])

    elif encoder == "h264_nvenc":
        base["encoder_args"] = [
            "-preset", config["NVENC_PRESET"],
            "-cq", str(config["NVENC_CQ"]),
            "-rc", config["NVENC_RC"],
            "-multipass", config["NVENC_MULTIPASS"],
            "-spatial_aq", str(config["NVENC_SPATIAL_AQ"]),
            "-temporal_aq", str(config["NVENC_TEMPORAL_AQ"]),
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]])

    else:  # libx264 CPU
        base["encoder_args"] = [
            "-preset", config["CPU_PRESET"],
            "-crf", str(config["CPU_CRF"]),
            "-tune", config["CPU_TUNE"],
            "-profile:v", config["OUTPUT_PROFILE"],
            "-level", config["OUTPUT_LEVEL"],
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]])

    base["encoder_args"].extend([
        "-pix_fmt", config["OUTPUT_PIX_FMT"],
        "-movflags", "+faststart",
        "-threads", str(config["FFMPEG_THREADS"]),
    ])

    return base


def detect_hardware_encoder(config: dict) -> dict:
    if config["ENCODER_FORCE"]:
        return _build_encoder_config(config["ENCODER_FORCE"], config)
    if _probe_encoder("h264_qsv"):
        return _build_encoder_config("h264_qsv", config)
    if _probe_encoder("h264_nvenc"):
        return _build_encoder_config("h264_nvenc", config)
    return _build_encoder_config("libx264", config)


class CheckpointManager:
    def __init__(self, run_folder: str, config: dict):
        self.run_folder = run_folder
        self.config = config
        self.checkpoint_path = os.path.join(run_folder, config["CHECKPOINT_FILE"])
        self.data = self._load()

    def _load(self) -> dict | None:
        if not os.path.exists(self.checkpoint_path):
            return None
        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def save(self):
        self.data["updated_at"] = datetime.utcnow().isoformat() + "Z"
        tmp_path = self.checkpoint_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.checkpoint_path)

    def initialize(self, total_clips: int, encoder_config: dict, audio_path: str,
                   audio_duration: float, subtitle_path: str = None):
        self.data = {
            "version": 2,
            "run_folder": self.run_folder,
            "encoder": encoder_config["video_codec"],
            "encoder_args": encoder_config["encoder_args"],
            "total_clips": total_clips,
            "completed_clips": 0,
            "failed_clips": [],
            "clip_states": {str(i): {"status": "pending"} for i in range(total_clips)},
            "concat_file": "concat.txt",
            "audio_path": os.path.basename(audio_path),
            "audio_duration": audio_duration,
            "subtitle_path": os.path.basename(subtitle_path) if subtitle_path else None,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        self.save()

    def is_clip_done(self, clip_idx: int) -> bool:
        state = self.data["clip_states"].get(str(clip_idx), {})
        return state.get("status") == "done" and os.path.exists(
            os.path.join(self.run_folder, state.get("path", "")))

    def mark_clip_done(self, clip_idx: int, clip_path: str, duration: float):
        self.data["clip_states"][str(clip_idx)] = {
            "status": "done",
            "path": clip_path,
            "duration": duration,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self.data["completed_clips"] += 1
        self.save()

    def cleanup_on_success(self):
        if os.path.exists(self.checkpoint_path):
            os.remove(self.checkpoint_path)


def build_ken_burns_filter(config: dict, frame_count: int, camera_action: str, pix_fmt: str = "yuv420p") -> str:
    """Builds frame-accurate Ken Burns camera movement based on integer frame counts."""
    zoom_min = config.get("KEN_BURNS_ZOOM_MIN", 1.0)
    zoom_max = config.get("KEN_BURNS_ZOOM_MAX", 1.10)
    upscale = config.get("KEN_BURNS_UPSCALE_FACTOR", 1.2)
    interp = config.get("KEN_BURNS_INTERP_ALGO", "bicubic")
    fps = config["OUTPUT_FPS"]
    w = config["OUTPUT_WIDTH"]
    h = config["OUTPUT_HEIGHT"]
    
    upscale_w = int(w * upscale)
    upscale_h = int(h * upscale)
    frames = max(1, frame_count)

    norm = f",setsar=1,format={pix_fmt}"
    t = f"((on-1)/max(1\,{frames-1}))"
    ease = f"({t}*{t}*(3-2*{t}))"

    center_x = f"'({upscale_w}-{upscale_w}/zoom)/2'"
    center_y = f"'({upscale_h}-{upscale_h}/zoom)/2'"

    if "zoom_in" in camera_action:
        z_expr = f"'{zoom_min}+({zoom_max}-{zoom_min})*{ease}'"
        x_expr = center_x
        y_expr = center_y
    elif "zoom_out" in camera_action:
        z_expr = f"'{zoom_max}-({zoom_max}-{zoom_min})*{ease}'"
        x_expr = center_x
        y_expr = center_y
    elif "pan_left" in camera_action:
        z_expr = f"'{zoom_max}'"
        x_expr = f"'({upscale_w}-{upscale_w}/zoom)*(1-{ease})'"
        y_expr = center_y
    elif "pan_right" in camera_action:
        z_expr = f"'{zoom_max}'"
        x_expr = f"'({upscale_w}-{upscale_w}/zoom)*{ease}'"
        y_expr = center_y
    elif "tilt_up" in camera_action:
        z_expr = f"'{zoom_max}'"
        x_expr = center_x
        y_expr = f"'({upscale_h}-{upscale_h}/zoom)*(1-{ease})'"
    elif "tilt_down" in camera_action:
        z_expr = f"'{zoom_max}'"
        x_expr = center_x
        y_expr = f"'({upscale_h}-{upscale_h}/zoom)*{ease}'"
    else:  # static
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1:color=black,"
                f"trim=start_frame=0:end_frame={frames},setpts=PTS-STARTPTS" + norm)

    return (f"scale={upscale_w}:{upscale_h}:flags=bicubic,"
            f"zoompan=z={z_expr}:x={x_expr}:y={y_expr}:d={frames}:s={upscale_w}x{upscale_h}:fps={fps},"
            f"scale={w}:{h}:flags={interp}" + norm)


def get_audio_duration(audio_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
    return float(subprocess.check_output(cmd).decode('utf-8').strip())


def get_latest_run_folder(runs_path="youtube_runs"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rel_to_script = os.path.join(script_dir, runs_path)
    
    resolved_path = runs_path
    if os.path.exists(rel_to_script):
        resolved_path = rel_to_script
    elif not os.path.exists(resolved_path):
        return None

    subdirs = [os.path.join(resolved_path, name) for name in os.listdir(resolved_path) if os.path.isdir(os.path.join(resolved_path, name))]
    return max(subdirs, key=os.path.getmtime) if subdirs else None


def load_ai_camera_decisions(json_path: str) -> dict:
    camera_map = {}
    if not os.path.exists(json_path):
        return camera_map

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        cleaned_content = re.sub(r'\]\s*\[', ',', content)
        if not cleaned_content.startswith('['): cleaned_content = '[' + cleaned_content
        if not cleaned_content.endswith(']'): cleaned_content += ']'

        data = json.loads(cleaned_content)
        for item in data:
            ts_raw = str(item.get("timestamp", "")).strip("[] ")
            parts = ts_raw.split(":")
            if len(parts) == 2:
                ts_key = f"{int(parts[0]):02d}_{int(parts[1]):02d}"
            elif len(parts) == 3:
                ts_key = f"{int(parts[0]):02d}_{int(parts[1]):02d}_{int(parts[2]):02d}"
            else:
                continue

            vp = item.get("visual_prompt", {})
            if isinstance(vp, dict):
                cam_spec = vp.get("camera_specifications", "").lower()
                if any(k in cam_spec for k in ["push-in", "zoom in", "push in"]): cam = "zoom_in"
                elif any(k in cam_spec for k in ["pull-out", "zoom out", "pull out"]): cam = "zoom_out"
                elif any(k in cam_spec for k in ["pan left", "tracking left"]): cam = "pan_left"
                elif any(k in cam_spec for k in ["pan right", "tracking right"]): cam = "pan_right"
                elif "tilt up" in cam_spec or "upward" in cam_spec: cam = "tilt_up"
                elif "tilt down" in cam_spec or "downward" in cam_spec: cam = "tilt_down"
                else: cam = "static"
                camera_map[ts_key] = cam
    except Exception as e:
        print(f"  [WARN] Failed to parse camera decisions from {json_path}: {e}")

    return camera_map


def load_manual_overrides(txt_path="manual_animations.txt"):
    overrides = {}
    if not os.path.exists(txt_path):
        return overrides
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    k, v = line.split('=', 1)
                    overrides[k.strip()] = v.strip().lower()
    except OSError:
        pass
    return overrides


def parse_image_timeline(run_folder: str) -> list:
    txt_path = os.path.join(run_folder, "image_timestamps.txt")
    if not os.path.exists(txt_path):
        txt_path = os.path.join(run_folder, "timestamped_transcript.txt")

    blocks = []
    if not os.path.exists(txt_path):
        return blocks

    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^\[(?:(\d{2}):)?(\d{2}):(\d{2})\]", line)
            if match:
                hours = int(match.group(1)) if match.group(1) else 0
                minutes = int(match.group(2))
                seconds = int(match.group(3))
                total_sec = hours * 3600 + minutes * 60 + seconds
                
                if match.group(1) is not None:
                    timestamp_key = f"{hours:02d}_{minutes:02d}_{seconds:02d}"
                else:
                    timestamp_key = f"{minutes:02d}_{seconds:02d}"

                blocks.append({
                    "sec": float(total_sec),
                    "name": timestamp_key
                })

    blocks.sort(key=lambda x: x["sec"])
    return blocks


def prepare_synchronized_timeline(image_blocks: list, audio_duration: float, fps: int) -> list:
    """
    ZERO-DRIFT TIMELINE CALCULATOR:
    Allocates exact integer frames to clips to guarantee audio/visual sync.
    """
    if not image_blocks:
        return []

    processed = []
    i = 0
    n = len(image_blocks)

    while i < n:
        current_sec = image_blocks[i]['sec']
        group = [image_blocks[i]]
        j = i + 1
        while j < n and abs(image_blocks[j]['sec'] - current_sec) < 0.1:
            group.append(image_blocks[j])
            j += 1

        group_end_sec = image_blocks[j]['sec'] if j < n else audio_duration
        group_duration = max(0.1, group_end_sec - current_sec)
        sub_duration = group_duration / len(group)

        for sub_idx, item in enumerate(group):
            sub_start = current_sec + (sub_idx * sub_duration)
            sub_end = current_sec + ((sub_idx + 1) * sub_duration)
            processed.append({
                "sec": sub_start,
                "end_sec": sub_end,
                "name": item["name"],
                "occurrence": sub_idx + 1
            })
        i = j

    final_timeline = []
    total_audio_frames = int(round(audio_duration * fps))

    for idx, block in enumerate(processed):
        start_frame = int(round(block["sec"] * fps))
        if idx < len(processed) - 1:
            end_frame = int(round(processed[idx + 1]["sec"] * fps))
        else:
            end_frame = total_audio_frames

        if end_frame <= start_frame:
            end_frame = start_frame + 1

        frame_count = end_frame - start_frame
        clip_dur_sec = frame_count / float(fps)

        final_timeline.append({
            "name": block["name"],
            "sec": block["sec"],
            "end_sec": block["end_sec"],
            "start_frame": start_frame,
            "end_frame": end_frame,
            "frame_count": frame_count,
            "duration": clip_dur_sec,
            "occurrence": block["occurrence"]
        })

    return final_timeline


def fix_arabic_srt(input_path, output_path):
    with open(input_path, "r", encoding="utf-8-sig") as f: content = f.read()
    with open(output_path, "w", encoding="utf-8") as f: f.write(content)


def build_subtitle_style_string(config: dict) -> str:
    return (f"Fontname={config['SUB_FONT_NAME']},"
            f"Fontsize={config['SUB_FONT_SIZE']},"
            f"PrimaryColour={config['SUB_PRIMARY_COLOR']},"
            f"OutlineColour={config['SUB_OUTLINE_COLOR']},"
            f"BorderStyle={config['SUB_BORDER_STYLE']},"
            f"Outline={config['SUB_OUTLINE']},"
            f"Shadow={config['SUB_SHADOW']},"
            f"Alignment={config['SUB_ALIGNMENT']},"
            f"MarginV={config['SUB_MARGIN_V']},"
            f"Bold={config['SUB_BOLD']}")


def get_sorted_images(images_dir):
    if not os.path.exists(images_dir): return []
    images = [f for f in os.listdir(images_dir) if f.endswith('.png')]
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
    return sorted(images, key=natural_sort_key)


def _resolve_image_path(block_name, idx, images_dir, available_images, last_valid_image, occurrence=1):
    """
    Searches both primary 'generated_images' and 'generated_images_duplicates' folders 
    to resolve standalone images and multi-frame set duplicates.
    """
    ts_name = block_name
    possible_names = []

    parent_run_folder = os.path.dirname(images_dir)
    dup_images_dir = os.path.join(parent_run_folder, "generated_images_duplicates")

    search_dirs = [images_dir]
    if os.path.exists(dup_images_dir):
        search_dirs.append(dup_images_dir)

    if occurrence == 1:
        possible_names.extend([
            f"{ts_name}.png",
            f"{ts_name}_1.png",
            f"{ts_name}_frame1.png",
            f"sentence_{idx+1}.png"
        ])
    else:
        possible_names.extend([
            f"{ts_name}_{occurrence}.png",
            f"{ts_name}_frame{occurrence}.png",
            f"{ts_name}_duplicate_{occurrence-1}.png"
        ])

    # 1. Direct candidate match in search directories
    for s_dir in search_dirs:
        for candidate in possible_names:
            candidate_path = os.path.join(s_dir, candidate)
            if os.path.exists(candidate_path) and os.path.getsize(candidate_path) > 0:
                return candidate_path, candidate

    # 2. Prefix match inside search directories
    for s_dir in search_dirs:
        if os.path.exists(s_dir):
            all_files = os.listdir(s_dir)
            matching = [f for f in all_files if f.startswith(f"{ts_name}") and f.endswith('.png')]
            matching.sort()
            if matching:
                chosen = matching[min(occurrence - 1, len(matching) - 1)]
                chosen_path = os.path.join(s_dir, chosen)
                if os.path.getsize(chosen_path) > 0:
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


def validate_assets(sync_timeline: list, images_dir: str) -> list:
    invalid = []
    if not sync_timeline: return invalid
    available_images = get_sorted_images(images_dir)
    last_valid_image = None
    
    for idx, block in enumerate(sync_timeline):
        abs_image_path, _ = _resolve_image_path(
            block['name'], idx, images_dir, available_images, last_valid_image, occurrence=block['occurrence']
        )
        if abs_image_path is None or not os.path.exists(abs_image_path) or os.path.getsize(abs_image_path) == 0:
            invalid.append((idx, block.get("name", "unknown")))
        else:
            last_valid_image = abs_image_path
    return invalid


def _extract_loudnorm_measured(stderr: str, config: dict, run_folder: str) -> dict:
    measured = {}
    data = None
    start = stderr.find('{')
    end = stderr.rfind('}')
    if start != -1 and end != -1 and end > start:
        blob = stderr[start:end + 1]
        try: data = json.loads(blob)
        except json.JSONDecodeError: data = None
    if isinstance(data, dict):
        measured["LOUDNORM_MEASURED_I"] = float(data.get("input_i", config["LOUDNORM_MEASURED_I"]))
        measured["LOUDNORM_MEASURED_TP"] = float(data.get("input_tp", config["LOUDNORM_MEASURED_TP"]))
        measured["LOUDNORM_MEASURED_LRA"] = float(data.get("input_lra", config["LOUDNORM_MEASURED_LRA"]))
        measured["LOUDNORM_MEASURED_THRESH"] = float(data.get("input_thresh", config["LOUDNORM_MEASURED_THRESH"]))
        measured["LOUDNORM_OFFSET"] = float(data.get("target_offset", config["LOUDNORM_OFFSET"]))
    if measured:
        config.update(measured)
        local_config = os.path.join(run_folder, "video_config.local.txt")
        try:
            with open(local_config, 'w', encoding='utf-8') as f:
                for k, v in config.items(): f.write(f"{k}={v}\n")
        except OSError: pass
    return measured


def _measure_loudnorm(audio_path: str, config: dict) -> str:
    measure_cmd = [
        "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "info",
        "-i", audio_path,
        "-af", (f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:"
                f"LRA={config['LOUDNORM_LRA']}:print_format=json"),
        "-f", "null", "NUL"
    ]
    try:
        res = subprocess.run(measure_cmd, capture_output=True, text=True,
                             encoding='utf-8', errors='ignore', timeout=120)
        measured = _extract_loudnorm_measured(res.stderr, config, os.path.dirname(audio_path))
        if measured:
            return (f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:"
                    f"LRA={config['LOUDNORM_LRA']}:"
                    f"measured_I={measured['LOUDNORM_MEASURED_I']}:"
                    f"measured_TP={measured['LOUDNORM_MEASURED_TP']}:"
                    f"measured_LRA={measured['LOUDNORM_MEASURED_LRA']}:"
                    f"measured_thresh={measured['LOUDNORM_MEASURED_THRESH']}:"
                    f"offset={measured['LOUDNORM_OFFSET']}:linear=true:print_format=summary")
    except Exception as e:
        print(f"  [WARN] Loudnorm measurement failed ({e}), single-pass mode")
    return (f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:LRA={config['LOUDNORM_LRA']}")


def build_single_pass_filter_graph(config: dict, encoder_config: dict, sync_timeline: list,
                                   images_dir: str, audio_path: str, subtitle_path: str | None,
                                   ai_cameras: dict, manual_cameras: dict, anim_enabled: bool,
                                   run_folder: str = "") -> tuple:
    fps = config["OUTPUT_FPS"]
    w = config["OUTPUT_WIDTH"]
    h = config["OUTPUT_HEIGHT"]

    available_images = get_sorted_images(images_dir)
    last_valid_image = None

    input_args = []
    filter_parts = []
    clip_labels = []

    for idx, block in enumerate(sync_timeline):
        abs_image_path, _ = _resolve_image_path(
            block['name'], idx, images_dir, available_images, last_valid_image, occurrence=block['occurrence']
        )
        if abs_image_path is None:
            continue
        last_valid_image = abs_image_path

        frame_count = block['frame_count']

        camera_action = "static"
        if anim_enabled:
            camera_action = ai_cameras.get(block['name'], "static")
            if block['name'] in manual_cameras:
                camera_action = manual_cameras[block['name']]

        kb = build_ken_burns_filter(config, frame_count, camera_action)
        
        rel_image_path = os.path.relpath(abs_image_path, run_folder).replace("\\", "/")
        input_args.extend(["-loop", "1", "-framerate", str(fps), "-i", rel_image_path])
        filter_parts.append(f"[{idx}:v]{kb}[v{idx}];")
        clip_labels.append(f"[v{idx}]")

    n_clips = len(clip_labels)
    voice_audio_idx = n_clips
    
    rel_audio_path = os.path.relpath(audio_path, run_folder).replace("\\", "/")
    input_args.extend(["-i", rel_audio_path])

    if n_clips == 0:
        raise ValueError("No image clips to render")

    filter_parts.append(f"{''.join(clip_labels)}concat=n={n_clips}:v=1:a=0[vconcat];")
    filter_parts.append(f"[vconcat]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                        f"pad={w}:{h}:-1:-1:color=black[vscaled];")

    video_label = "vscaled"
    if subtitle_path and os.path.exists(subtitle_path):
        sub_style = build_subtitle_style_string(config)
        safe_sub = os.path.abspath(subtitle_path).replace("\\", "/").replace(":", "\\:").replace("'", "'\\\\''")
        filter_parts.append(f"[vscaled]subtitles='{safe_sub}':force_style='{sub_style}'[vout];")
        video_label = "vout"

    final_format = "nv12" if encoder_config.get("video_codec") == "h264_qsv" else "yuv420p"
    filter_parts.append(f"[{video_label}]format={final_format}[vformat];")
    video_label = "vformat"

    if config["ENABLE_LOUDNORM_TWOPASS"]:
        ln = _measure_loudnorm(audio_path, config)
    else:
        ln = f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:LRA={config['LOUDNORM_LRA']}"
    filter_parts.append(f"[{voice_audio_idx}:a]{ln}[aout];")

    filter_complex = "".join(filter_parts)
    return input_args, filter_complex, video_label


def run_single_pass(config: dict, encoder_config: dict, sync_timeline: list, images_dir: str,
                    audio_path: str, run_folder: str, checkpoint: CheckpointManager = None) -> bool:
    output_path = os.path.abspath(os.path.join(run_folder, "youtube_ready_video.mp4"))

    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint and checkpoint.data is not None:
        if checkpoint.data["completed_clips"] == checkpoint.data["total_clips"] and os.path.exists(output_path):
            print("  [RESUME] Single-pass render already complete. Skipping.")
            return True

    subtitle_path = None
    if config["ENABLE_SUBTITLES"]:
        srt_path = os.path.join(run_folder, "timestamped_transcript.srt")
        if os.path.exists(srt_path):
            fixed_srt = os.path.join(run_folder, "timestamped_transcript_fixed.srt")
            if not config["DEBUG_DRY_RUN"]:
                fix_arabic_srt(srt_path, fixed_srt)
            subtitle_path = fixed_srt

    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint and checkpoint.data is None:
        audio_duration = config.get("_audio_duration", 0.0)
        checkpoint.initialize(len(sync_timeline), encoder_config, audio_path, audio_duration, subtitle_path)

    ai_cameras = load_ai_camera_decisions(os.path.join(run_folder, "flow_prompts.json"))
    manual_cameras = load_manual_overrides("manual_animations.txt")

    images_dir = os.path.abspath(images_dir)
    audio_path = os.path.abspath(audio_path)

    current_encoder = encoder_config
    while True:
        try:
            input_args, filter_complex, video_label = build_single_pass_filter_graph(
                config, current_encoder, sync_timeline, images_dir, audio_path,
                subtitle_path, ai_cameras, manual_cameras, config["ENABLE_ANIMATIONS"], run_folder
            )
        except ValueError as e:
            print(f"  [ERROR] {e}")
            return False

        filter_path = os.path.abspath(os.path.join(run_folder, "filter_complex.txt"))
        with open(filter_path, "w", encoding="utf-8") as f:
            f.write(filter_complex)

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", config["FFMPEG_LOGLEVEL"],
            *input_args,
            "-/filter_complex", filter_path,
            "-map", f"[{video_label}]",
            "-map", "[aout]",
            "-c:v", current_encoder["video_codec"],
            *current_encoder["encoder_args"],
            "-c:a", config["AUDIO_CODEC"],
            "-b:a", config["AUDIO_BITRATE"],
            "-ar", str(config["AUDIO_SAMPLE_RATE"]),
            "-shortest",
            output_path
        ]

        print(f"\n[Single-Pass] Rendering {len(sync_timeline)} synchronized clips + audio in FFmpeg ({current_encoder['video_codec']})...")
        failed = False
        
        try:
            duration_sec = config.get("_audio_duration", 1.0)
            start_time = time.time()
            timeout = config["FFMPEG_FINAL_TIMEOUT"]

            process = subprocess.Popen(
                cmd, cwd=run_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                text=True, encoding='utf-8', errors='ignore'
            )

            stderr_logs = []
            while True:
                if time.time() - start_time > timeout:
                    process.kill()
                    raise subprocess.TimeoutExpired(cmd, timeout)

                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    stderr_logs.append(line)
                    if "time=" in line:
                        match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                        if match:
                            h, m, s = map(float, match.groups())
                            current_sec = h * 3600 + m * 60 + s
                            pct = min(100.0, (current_sec / duration_sec) * 100)
                            print(f"\r  [Rendering] Progress: {pct:.1f}% ({int(current_sec)}s / {int(duration_sec)}s)", end="", flush=True)

            process.wait()
            print("\n")

            if process.returncode != 0:
                full_stderr = "".join(stderr_logs)
                print(f"  [ERROR] FFmpeg failed with {current_encoder['video_codec']}:\n{full_stderr[-2000:]}")
                failed = True
        except subprocess.TimeoutExpired:
            print(f"\n  [ERROR] FFmpeg timeout ({config['FFMPEG_FINAL_TIMEOUT']}s)")
            failed = True
        except Exception as e:
            print(f"\n  [ERROR] FFmpeg execution error: {e}")
            failed = True

        if not failed:
            print(f"  [SUCCESS] Single-pass render complete: {output_path}")
            break
        else:
            if current_encoder["video_codec"] == "libx264":
                return False
            print(f"\n  [FALLBACK] Retrying with CPU encoder libx264...")
            current_encoder = _build_encoder_config("libx264", config)

    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint:
        for idx, block in enumerate(sync_timeline):
            checkpoint.mark_clip_done(idx, "youtube_ready_video.mp4", block['duration'])

    return True


def main(run_folder: str = None):
    print("=============================================")
    print("Starting SILKY CINEMATIC Video Compilation")
    print("=============================================")

    latest_run = run_folder if run_folder else get_latest_run_folder()
    if not latest_run:
        print("[FATAL ERROR] No run folder detected in 'youtube_runs'.")
        sys.exit(1)

    print(f"Target Video Folder: {latest_run}")

    config = load_video_config("video_config.txt")
    anim_enabled = config["ENABLE_ANIMATIONS"]
    subs_enabled = config["ENABLE_SUBTITLES"]

    encoder_config = detect_hardware_encoder(config)
    print(f"  [ENCODER] Using {encoder_config['encoder_name']} ({encoder_config['hwaccel']})")

    # Audio path priority resolution: Polished Audacity audio -> Raw audio fallback
    polished_audio = os.path.join(latest_run, "audacity_voice", "full_episode_voice.wav")
    raw_audio = os.path.join(latest_run, "full_episode_voice.wav")

    if os.path.exists(polished_audio):
        audio_path = polished_audio
        print(f"  [AUDIO] Target: Audacity Polished Voice Track ('{audio_path}')")
    elif os.path.exists(raw_audio):
        audio_path = raw_audio
        print(f"  [AUDIO] Audacity track missing. Fallback to Raw Voice Track ('{audio_path}')")
    else:
        print(f"[FATAL ERROR] No voice track found in '{latest_run}'. Expected 'full_episode_voice.wav'.")
        sys.exit(1)

    audio_duration = get_audio_duration(audio_path)
    config["_audio_duration"] = audio_duration

    images_dir = os.path.join(latest_run, "generated_images")

    # 1. Parse timeline blocks from transcript
    raw_image_blocks = parse_image_timeline(latest_run)

    # 2. Build ZERO-DRIFT synchronized timeline
    sync_timeline = prepare_synchronized_timeline(raw_image_blocks, audio_duration, config["OUTPUT_FPS"])

    print("Validating image assets...")
    invalid_assets = validate_assets(sync_timeline, images_dir)
    if invalid_assets:
        print(f"[FATAL ERROR] Image validation failed. Found {len(invalid_assets)} missing image assets:")
        for idx, name in invalid_assets:
            print(f"  - Clip {idx}: {name}")
        sys.exit(1)
    print(f"  [OK] All {len(sync_timeline)} image assets synchronized & verified on disk.")

    print(f"Animations Enabled: {anim_enabled}")
    print(f"Subtitles Enabled: {subs_enabled}")
    checkpoint = CheckpointManager(latest_run, config)

    # 3. Execute Single-Pass Zero-Drift Render
    ok = run_single_pass(config, encoder_config, sync_timeline, images_dir, audio_path, latest_run, checkpoint)
    if ok:
        print("\n[SUCCESS] Master Video Completed Perfectly in Sync!")
        if not config["DEBUG_SAVE_INTERMEDIATES"]:
            for d in ["temp_clips", "temp_sfx"]:
                tdir = os.path.join(latest_run, d)
                if os.path.exists(tdir):
                    import shutil
                    shutil.rmtree(tdir, ignore_errors=True)
    else:
        print("\n[ERROR] Single-pass render failed.")
        sys.exit(1)


if __name__ == "__main__":
    run_folder_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(run_folder_arg)