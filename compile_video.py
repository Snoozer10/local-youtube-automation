from __future__ import annotations
import os
import json
import re
import sys
import time 
import random
import subprocess
import shutil
from datetime import datetime, timezone

# Ensure WinGet binaries (ffmpeg / ffprobe) are accessible
winget_links_path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links")
if os.path.exists(winget_links_path):
    os.environ["PATH"] = winget_links_path + os.pathsep + os.environ["PATH"]

def load_video_config(config_path="video_config.txt") -> dict:
    """
    Parse video_config.txt into typed dict.
    Supports: bool (true/false), int, float, str.
    Comments (# ...) and blank lines ignored.
    """
    DEFAULTS = {
        "ENABLE_ANIMATIONS": True,
        "ENABLE_SUBTITLES": False,
        "ENABLE_HARDWARE_ENCODER": True,
        "ENABLE_SINGLE_PASS": True,
        "ENABLE_CHECKPOINT_RESUME": True,
        "ENABLE_LOUDNORM_TWOPASS": True,
        "ENABLE_VBV": True,
        "CHUNK_SIZE": 40,
        "OUTPUT_WIDTH": 1920,
        "OUTPUT_HEIGHT": 1080,
        "OUTPUT_FPS": 30,
        "OUTPUT_PIX_FMT": "yuv420p",
        "OUTPUT_PROFILE": "high",
        "OUTPUT_LEVEL": "4.1",
        "CPU_CRF": 23,
        "CPU_PRESET": "ultrafast",
        "CPU_TUNE": "fastdecode",
        "ENCODER_FORCE": "",
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
                        try:
                            config[key] = int(float(value))
                        except ValueError:
                            pass
                    elif isinstance(default_val, float):
                        try:
                            config[key] = float(value)
                        except ValueError:
                            pass
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
        # 1440p requires H.264 Level 5.0 or 5.1
        target_level = "5.1" if int(config.get("OUTPUT_HEIGHT", 1080)) >= 1440 else config.get("OUTPUT_LEVEL", "4.1")
        base["encoder_args"] = [
            "-preset", config["CPU_PRESET"],
            "-crf", str(config["CPU_CRF"]),
            "-tune", config["CPU_TUNE"],
            "-profile:v", config["OUTPUT_PROFILE"],
            "-level", target_level,
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]])

    base["encoder_args"].extend([
        "-pix_fmt", config["OUTPUT_PIX_FMT"],
        "-g", str(config["OUTPUT_FPS"] * 2),
        "-keyint_min", str(config["OUTPUT_FPS"]),
        "-flags", "+cgop",
        "-movflags", "+faststart",
        "-threads", str(config["FFMPEG_THREADS"]),
    ])

    return base


def detect_hardware_encoder(config: dict) -> dict:
    if config.get("ENCODER_FORCE"):
        return _build_encoder_config(config["ENCODER_FORCE"], config)
    if config.get("ENABLE_HARDWARE_ENCODER"):
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
        self.data["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp_path = self.checkpoint_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.checkpoint_path)

    def initialize(self, total_clips: int, encoder_config: dict, audio_path: str,
                   audio_duration: float, subtitle_path: str = None):
        now_str = datetime.now(timezone.utc).isoformat()
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
            "created_at": now_str,
            "updated_at": now_str,
        }
        self.save()

    def is_clip_done(self, clip_idx: int) -> bool:
        state = self.data.get("clip_states", {}).get(str(clip_idx), {})
        return state.get("status") == "done"

    def mark_clip_done(self, clip_idx: int, clip_path: str, duration: float, save_now: bool = True):
        if "clip_states" not in self.data:
            self.data["clip_states"] = {}
        self.data["clip_states"][str(clip_idx)] = {
            "status": "done",
            "path": clip_path,
            "duration": duration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.data["completed_clips"] = sum(
            1 for v in self.data["clip_states"].values() if v.get("status") == "done"
        )
        if save_now:
            self.save()

    def cleanup_on_success(self):
        if os.path.exists(self.checkpoint_path):
            try:
                os.remove(self.checkpoint_path)
            except OSError:
                pass


def build_ken_burns_filter(config: dict, frame_count: int, camera_action: str, pix_fmt: str = "yuv420p") -> str:
    """Builds frame-accurate Ken Burns camera movement without quote escape errors or thread starvation."""
    zoom_min = float(config.get("KEN_BURNS_ZOOM_MIN", 1.0))
    zoom_max = float(config.get("KEN_BURNS_ZOOM_MAX", 1.10))
    upscale = float(config.get("KEN_BURNS_UPSCALE_FACTOR", 1.15))
    interp = config.get("KEN_BURNS_INTERP_ALGO", "bicubic")
    fps = int(config["OUTPUT_FPS"])
    w = int(config["OUTPUT_WIDTH"])
    h = int(config["OUTPUT_HEIGHT"])
    
    upscale_w = int(w * upscale)
    upscale_h = int(h * upscale)
    # Ensure dimensions are even numbers for YUV420p
    upscale_w = upscale_w if upscale_w % 2 == 0 else upscale_w + 1
    upscale_h = upscale_h if upscale_h % 2 == 0 else upscale_h + 1
    frames = max(1, int(frame_count))

    norm = f",setsar=1,format={pix_fmt}"
    den = max(1, frames - 1)
    t = f"((on-1)/{den})"
    ease = f"({t}*{t}*(3-2*{t}))"

    center_x = f"(iw-iw/zoom)/2"
    center_y = f"(ih-ih/zoom)/2"

    if "zoom_in" in camera_action:
        z_expr = f"{zoom_min}+({zoom_max}-{zoom_min})*{ease}"
        x_expr = center_x
        y_expr = center_y
    elif "zoom_out" in camera_action:
        z_expr = f"{zoom_max}-({zoom_max}-{zoom_min})*{ease}"
        x_expr = center_x
        y_expr = center_y
    elif "pan_left" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = f"(iw-iw/zoom)*(1-{ease})"
        y_expr = center_y
    elif "pan_right" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = f"(iw-iw/zoom)*{ease}"
        y_expr = center_y
    elif "tilt_up" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = center_x
        y_expr = f"(ih-ih/zoom)*(1-{ease})"
    elif "tilt_down" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = center_x
        y_expr = f"(ih-ih/zoom)*{ease}"
    else:  # static
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"trim=start_frame=0:end_frame={frames},setpts=PTS-STARTPTS" + norm)

    return (f"scale={upscale_w}:{upscale_h}:force_original_aspect_ratio=increase:flags=bicubic,"
            f"crop={upscale_w}:{upscale_h},"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={w}x{h}:fps={fps},"
            f"trim=start_frame=0:end_frame={frames},setpts=PTS-STARTPTS" + norm)


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


def _parse_pre_planned_prompts_txt(txt_path: str) -> dict:
    camera_map = {}
    if not os.path.exists(txt_path):
        return camera_map

    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        entries = re.split(r'\bIndex:\s*\d+', content)
        for entry in entries:
            if not entry.strip():
                continue
            
            ts_match = re.search(r'\[(?:(\d+):)?(\d+):(\d+)\]', entry)
            if not ts_match:
                continue

            h = ts_match.group(1)
            m = int(ts_match.group(2))
            s = int(ts_match.group(3))
            
            ts_keys = []
            if h is not None:
                h_int = int(h)
                ts_keys.append(f"{h_int:02d}_{m:02d}_{s:02d}")
                if h_int == 0:
                    ts_keys.append(f"{m:02d}_{s:02d}")
            else:
                ts_keys.append(f"{m:02d}_{s:02d}")
                ts_keys.append(f"00_{m:02d}_{s:02d}")

            cam_spec = entry.lower()
            cam = "static"
            if any(k in cam_spec for k in ["push-in", "zoom in", "push in", "zoom_in"]): cam = "zoom_in"
            elif any(k in cam_spec for k in ["pull-out", "zoom out", "pull out", "zoom_out"]): cam = "zoom_out"
            elif any(k in cam_spec for k in ["pan left", "tracking left", "pan_left"]): cam = "pan_left"
            elif any(k in cam_spec for k in ["pan right", "tracking right", "pan_right"]): cam = "pan_right"
            elif "tilt up" in cam_spec or "upward" in cam_spec or "tilt_up" in cam_spec: cam = "tilt_up"
            elif "tilt down" in cam_spec or "downward" in cam_spec or "tilt_down" in cam_spec: cam = "tilt_down"

            for key in ts_keys:
                camera_map[key] = cam

    except Exception as e:
        print(f"  [WARN] Failed to parse camera decisions from {txt_path}: {e}")

    return camera_map


def load_ai_camera_decisions(run_folder: str) -> dict:
    camera_map = {}
    
    json_path = os.path.join(run_folder, "flow_prompts.json") if os.path.isdir(run_folder) else run_folder
    txt_path = os.path.join(run_folder, "pre_planned_prompts.txt") if os.path.isdir(run_folder) else os.path.join(os.path.dirname(run_folder), "pre_planned_prompts.txt")

    # 1. Primary: Try flow_prompts.json
    if os.path.exists(json_path) and os.path.isfile(json_path):
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
                
                ts_keys = []
                if len(parts) == 2:
                    ts_keys.append(f"{int(parts[0]):02d}_{int(parts[1]):02d}")
                elif len(parts) == 3:
                    ts_keys.append(f"{int(parts[0]):02d}_{int(parts[1]):02d}_{int(parts[2]):02d}")
                    if int(parts[0]) == 0:
                        ts_keys.append(f"{int(parts[1]):02d}_{int(parts[2]):02d}")
                else:
                    continue

                vp = item.get("visual_prompt", {})
                cam_spec = ""
                if isinstance(vp, dict):
                    cam_spec = (vp.get("composition_layout", "") + " " +
                                vp.get("camera_specifications", "") + " " +
                                vp.get("subject_action_increment", "")).lower()
                elif isinstance(vp, str):
                    cam_spec = vp.lower()
                
                # Check sequence_type as well
                seq_t = str(item.get("sequence_type", "")).lower()
                if "zoom" in seq_t or "push" in cam_spec or "zoom in" in cam_spec or "zoom_in" in cam_spec:
                    cam = "zoom_in"
                elif "pull" in cam_spec or "zoom out" in cam_spec or "zoom_out" in cam_spec:
                    cam = "zoom_out"
                elif "pan left" in cam_spec or "pan_left" in cam_spec or "tracking left" in cam_spec:
                    cam = "pan_left"
                elif "pan right" in cam_spec or "pan_right" in cam_spec or "tracking right" in cam_spec:
                    cam = "pan_right"
                elif "tilt up" in cam_spec or "tilt_up" in cam_spec or "upward" in cam_spec:
                    cam = "tilt_up"
                elif "tilt down" in cam_spec or "tilt_down" in cam_spec or "downward" in cam_spec:
                    cam = "tilt_down"
                else:
                    cam = "static"
                    
                    for key in ts_keys:
                        camera_map[key] = cam
            if camera_map:
                print(f"  [CAMERA] Loaded {len(camera_map)} AI camera decisions from 'flow_prompts.json'")
        except Exception as e:
            print(f"  [WARN] Failed to parse camera decisions from {json_path}: {e}")

    # 2. Fallback: Try pre_planned_prompts.txt
    if not camera_map and os.path.exists(txt_path):
        camera_map = _parse_pre_planned_prompts_txt(txt_path)
        if camera_map:
            print(f"  [CAMERA] Loaded {len(camera_map)} AI camera decisions from 'pre_planned_prompts.txt'")

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
            match = re.match(r"^\[(?:(\d+):)?(\d+):(\d+)\]", line)
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
        # Force clip 0 to start at frame 0 to prevent audio/video sync gap at origin
        start_frame = 0 if idx == 0 else int(round(block["sec"] * fps))
        
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
            possible_names.extend([
                f"{tv}.png",
                f"{tv}_1.png",
                f"{tv}_frame1.png",
                f"sentence_{idx+1}.png"
            ])
        else:
            possible_names.extend([
                f"{tv}_{occurrence}.png",
                f"{tv}_frame{occurrence}.png",
                f"{tv}_duplicate_{occurrence-1}.png"
            ])

    # 1. Direct candidate match in search directories
    for s_dir in search_dirs:
        for candidate in possible_names:
            candidate_path = os.path.join(s_dir, candidate)
            if os.path.exists(candidate_path) and os.path.getsize(candidate_path) > 0:
                return candidate_path, candidate

    # Helper for natural sorting (e.g. 00_15_2.png before 00_15_10.png)
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

    # 2. Prefix match inside search directories with natural numeric ordering
    for s_dir in search_dirs:
        if os.path.exists(s_dir):
            all_files = os.listdir(s_dir)
            for tv in ts_variants:
                matching = [f for f in all_files if f.startswith(tv) and f.endswith('.png')]
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
    # Safely search specifically for the loudnorm JSON block to avoid metadata traps
    match = re.search(r'(\{[\s\S]*?"input_i"[\s\S]*?\})', stderr)
    if match:
        blob = match.group(1)
        try: 
            data = json.loads(blob)
        except json.JSONDecodeError: 
            data = None
    if isinstance(data, dict) and "input_i" in data:
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
        "-f", "null", os.devnull
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


def build_chunk_filter_graph(config: dict, encoder_config: dict, chunk_timeline: list,
                             images_dir: str, ai_cameras: dict, manual_cameras: dict,
                             anim_enabled: bool, global_offset_idx: int = 0) -> tuple:
    fps = config["OUTPUT_FPS"]
    w = config["OUTPUT_WIDTH"]
    h = config["OUTPUT_HEIGHT"]

    available_images = get_sorted_images(images_dir)
    last_valid_image = None

    input_args = []
    filter_parts = []
    clip_labels = []
    input_idx = 0

    for i, block in enumerate(chunk_timeline):
        global_idx = global_offset_idx + i
        abs_image_path, _ = _resolve_image_path(
            block['name'], global_idx, images_dir, available_images, last_valid_image, occurrence=block['occurrence']
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
        
        safe_image_path = os.path.abspath(abs_image_path).replace("\\", "/")
        clip_duration = block['duration']
        # Limit image loop duration at demuxer level to prevent memory explosion
        input_args.extend(["-loop", "1", "-t", f"{clip_duration + 0.5:.3f}", "-framerate", str(fps), "-i", safe_image_path])
        filter_parts.append(f"[{input_idx}:v]{kb}[v{input_idx}];")
        clip_labels.append(f"[v{input_idx}]")
        input_idx += 1

    n_clips = len(clip_labels)
    if n_clips == 0:
        raise ValueError("No image clips to render in chunk")

    filter_parts.append(f"{''.join(clip_labels)}concat=n={n_clips}:v=1:a=0[vconcat];")
    filter_parts.append(f"[vconcat]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                        f"pad={w}:{h}:-1:-1:color=black[vscaled];")

    final_format = "nv12" if encoder_config.get("video_codec") == "h264_qsv" else "yuv420p"
    filter_parts.append(f"[vscaled]format={final_format}[vout]")

    filter_complex = "".join(filter_parts)
    return input_args, filter_complex, "vout"


def render_chunk(config: dict, encoder_config: dict, chunk_timeline: list, images_dir: str,
                 ai_cameras: dict, manual_cameras: dict, anim_enabled: bool,
                 chunk_idx: int, temp_dir: str, run_folder: str, global_offset_idx: int) -> str | None:
    chunk_filename = f"chunk_{chunk_idx:04d}.mp4"
    chunk_output_path = os.path.abspath(os.path.join(temp_dir, chunk_filename))

    chunk_duration_sec = sum(b['duration'] for b in chunk_timeline)

    if os.path.exists(chunk_output_path) and os.path.getsize(chunk_output_path) > 1000:
        print(f"  [CHUNK {chunk_idx+1}] Already rendered: {chunk_filename} ({chunk_duration_sec:.1f}s)")
        return chunk_output_path

    try:
        input_args, filter_complex, video_label = build_chunk_filter_graph(
            config, encoder_config, chunk_timeline, images_dir, ai_cameras, manual_cameras,
            anim_enabled, global_offset_idx
        )
    except ValueError as e:
        print(f"  [ERROR Chunk {chunk_idx+1}] {e}")
        return None

    filter_script_path = os.path.abspath(os.path.join(temp_dir, f"filter_chunk_{chunk_idx:04d}.txt"))
    with open(filter_script_path, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", config["FFMPEG_LOGLEVEL"],
        *input_args,
        "-filter_complex_script", filter_script_path,
        "-map", f"[{video_label}]",
        "-c:v", encoder_config["video_codec"],
        *encoder_config["encoder_args"],
        "-an",
        chunk_output_path
    ]

    start_time = time.time()
    timeout = config.get("FFMPEG_CLIP_TIMEOUT", 300)

    try:
        process = subprocess.Popen(
            cmd, cwd=run_folder, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='ignore'
        )

        stderr_logs = []
        while True:
            if time.time() - start_time > timeout:
                process.kill()
                print(f"\n  [ERROR Chunk {chunk_idx+1}] FFmpeg timeout ({timeout}s)")
                return None

            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break

            if line:
                stderr_logs.append(line)
                if "time=" in line:
                    match = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
                    if match:
                        h, m, s = map(float, match.groups())
                        current_sec = h * 3600 + m * 60 + s
                        pct = min(100.0, (current_sec / max(0.1, chunk_duration_sec)) * 100)
                        print(f"\r  [Chunk {chunk_idx+1}] Progress: {pct:.1f}% ({int(current_sec)}s / {int(chunk_duration_sec)}s)", end="", flush=True)

        process.wait()

        if process.returncode != 0:
            full_stderr = "".join(stderr_logs)
            print(f"\n  [ERROR Chunk {chunk_idx+1}] FFmpeg failed:\n{full_stderr[-1500:]}")
            return None

        print(f"\r  [Chunk {chunk_idx+1}] Done! ({chunk_filename})                             ")
        return chunk_output_path

    except Exception as e:
        print(f"\n  [ERROR Chunk {chunk_idx+1}] Execution error: {e}")
        return None


def assemble_final_video(config: dict, encoder_config: dict, chunk_files: list[str],
                         audio_path: str, subtitle_path: str | None, run_folder: str) -> bool:
    output_path = os.path.abspath(os.path.join(run_folder, "youtube_ready_video.mp4"))
    temp_dir = os.path.abspath(os.path.join(run_folder, "temp_clips"))
    concat_txt_path = os.path.join(temp_dir, "concat_chunks.txt")

    with open(concat_txt_path, "w", encoding="utf-8") as f:
        for c_file in chunk_files:
            safe_c_path = os.path.abspath(c_file).replace("\\", "/")
            f.write(f"file '{safe_c_path}'\n")

    safe_audio_path = os.path.abspath(audio_path).replace("\\", "/")

    filter_parts = []
    if config["ENABLE_LOUDNORM_TWOPASS"]:
        ln = _measure_loudnorm(audio_path, config)
    else:
        ln = f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:LRA={config['LOUDNORM_LRA']}"

    filter_parts.append(f"[1:a]{ln}[aout]")

    video_label = "0:v"
    video_codec_args = ["-c:v", "copy"]

    if subtitle_path and os.path.exists(subtitle_path):
        sub_style = build_subtitle_style_string(config)
        safe_sub = os.path.abspath(subtitle_path).replace("\\", "/").replace(":", "\\:").replace("'", "'\\\\''")
        filter_parts.append(f"[0:v]subtitles='{safe_sub}':force_style='{sub_style}'[vout]")
        video_label = "[vout]"
        video_codec_args = [
            "-c:v", encoder_config["video_codec"],
            *encoder_config["encoder_args"]
        ]

    filter_complex = ";".join(filter_parts)
    filter_script_path = os.path.join(temp_dir, "filter_final_assembly.txt")
    with open(filter_script_path, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", config["FFMPEG_LOGLEVEL"],
        "-f", "concat", "-safe", "0", "-i", concat_txt_path,
        "-i", safe_audio_path,
        "-filter_complex_script", filter_script_path,
        "-map", video_label,
        "-map", "[aout]",
        *video_codec_args,
        "-c:a", config["AUDIO_CODEC"],
        "-b:a", config["AUDIO_BITRATE"],
        "-ar", str(config["AUDIO_SAMPLE_RATE"]),
        "-shortest",
        output_path
    ]

    print("\n[Final Assembly] Combining chunk videos + audio track...")
    start_time = time.time()
    audio_duration = config.get("_audio_duration", 1.0)
    timeout = config.get("FFMPEG_FINAL_TIMEOUT", 5400)

    try:
        process = subprocess.Popen(
            cmd, cwd=run_folder, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='ignore'
        )

        stderr_logs = []
        while True:
            if time.time() - start_time > timeout:
                process.kill()
                print(f"\n  [ERROR Final Assembly] FFmpeg timeout ({timeout}s)")
                return False

            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break

            if line:
                stderr_logs.append(line)
                if "time=" in line:
                    match = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
                    if match:
                        h, m, s = map(float, match.groups())
                        current_sec = h * 3600 + m * 60 + s
                        pct = min(100.0, (current_sec / max(0.1, audio_duration)) * 100)
                        print(f"\r  [Assembly] Progress: {pct:.1f}% ({int(current_sec)}s / {int(audio_duration)}s)", end="", flush=True)

        process.wait()
        print("\n")

        if process.returncode != 0:
            full_stderr = "".join(stderr_logs)
            print(f"  [ERROR Final Assembly] FFmpeg failed:\n{full_stderr[-2000:]}")
            return False

        print(f"  [SUCCESS] Master Video Created: {output_path}")
        return True

    except Exception as e:
        print(f"\n  [ERROR Final Assembly] Execution error: {e}")
        return False


def run_chunked_compile(config: dict, encoder_config: dict, sync_timeline: list, images_dir: str,
                        audio_path: str, run_folder: str, checkpoint: CheckpointManager = None) -> bool:
    output_path = os.path.abspath(os.path.join(run_folder, "youtube_ready_video.mp4"))

    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint and checkpoint.data is not None:
        if checkpoint.data.get("completed_clips") == checkpoint.data.get("total_clips") and os.path.exists(output_path):
            print("  [RESUME] Video render already complete. Skipping.")
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

    ai_cameras = load_ai_camera_decisions(run_folder)
    manual_cameras = load_manual_overrides("manual_animations.txt")

    images_dir = os.path.abspath(images_dir)
    audio_path = os.path.abspath(audio_path)
    temp_dir = os.path.abspath(os.path.join(run_folder, "temp_clips"))
    os.makedirs(temp_dir, exist_ok=True)

    chunk_size = config.get("CHUNK_SIZE", 40)
    total_clips = len(sync_timeline)
    
    chunks = [sync_timeline[i:i + chunk_size] for i in range(0, total_clips, chunk_size)]
    num_chunks = len(chunks)

    current_encoder = encoder_config

    while True:
        print(f"\n[Chunked Render] Processing {total_clips} synchronized clips in {num_chunks} chunk(s) (batch size: {chunk_size}) using {current_encoder['video_codec']}...")
        
        chunk_files = []
        failed = False

        for chunk_idx, chunk_timeline in enumerate(chunks):
            global_offset = chunk_idx * chunk_size
            chunk_file = render_chunk(
                config, current_encoder, chunk_timeline, images_dir,
                ai_cameras, manual_cameras, config["ENABLE_ANIMATIONS"],
                chunk_idx, temp_dir, run_folder, global_offset
            )

            if not chunk_file:
                failed = True
                break

            chunk_files.append(chunk_file)

            if checkpoint:
                for clip_i, block in enumerate(chunk_timeline):
                    checkpoint.mark_clip_done(global_offset + clip_i, chunk_file, block['duration'], save_now=False)
                checkpoint.save()

        if not failed and len(chunk_files) == num_chunks:
            ok = assemble_final_video(config, current_encoder, chunk_files, audio_path, subtitle_path, run_folder)
            if ok:
                return True
            else:
                failed = True

        if failed:
            if current_encoder["video_codec"] == "libx264":
                return False
            print(f"\n  [FALLBACK] Hardware encoder failed. Retrying all chunks with CPU encoder libx264...")
            current_encoder = _build_encoder_config("libx264", config)


# Backwards compatibility alias
run_single_pass = run_chunked_compile


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

    # 3. Execute Chunked Zero-Drift Render
    ok = run_chunked_compile(config, encoder_config, sync_timeline, images_dir, audio_path, latest_run, checkpoint)
    if ok:
        print("\n[SUCCESS] Master Video Completed Perfectly in Sync!")
        if checkpoint:
            checkpoint.cleanup_on_success()
        if not config["DEBUG_SAVE_INTERMEDIATES"]:
            for d in ["temp_clips", "temp_sfx"]:
                tdir = os.path.join(latest_run, d)
                if os.path.exists(tdir):
                    shutil.rmtree(tdir, ignore_errors=True)
    else:
        print("\n[ERROR] Video rendering failed.")
        sys.exit(1)


if __name__ == "__main__":
    run_folder_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(run_folder_arg)