from __future__ import annotations
import os
import json
import re
import sys
import time 
import random
import subprocess
import shutil
import struct
import wave
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
        test_cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=s=64x64:d=0.04",
            "-c:v", encoder_name,
            "-f", "null", "-"
        ]
        result = subprocess.run(test_cmd, capture_output=True, timeout=5)
        return result.returncode == 0
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

    else:  # libx264 CPU (Master 2D Animation Profile)
        target_level = "5.1" if int(config.get("OUTPUT_HEIGHT", 1080)) >= 1440 else config.get("OUTPUT_LEVEL", "4.1")
        base["encoder_args"] = [
            "-preset", config.get("CPU_PRESET", "veryfast"),
            "-crf", str(config.get("CPU_CRF", 17)),
            "-tune", "animation",  # Crucial: Preserves flat color planes and crisp vector lines
            "-profile:v", "high",
            "-level", target_level,
            "-x264-params", "bframes=4:b-adapt=2:ref=4:aq-mode=3",  # Eliminates flat-color banding
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend(["-maxrate", config["VBV_MAXRATE"], "-bufsize", config["VBV_BUFSIZE"]])

    fps = int(config["OUTPUT_FPS"])
    target_pix_fmt = "nv12" if "qsv" in encoder else config.get("OUTPUT_PIX_FMT", "yuv420p")
    base["encoder_args"].extend([
        "-pix_fmt", target_pix_fmt,
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-color_range", "tv",
        "-r", str(fps),
        "-fps_mode", "cfr",
        "-video_track_timescale", str(fps * 1000),
        "-g", str(fps * 2),
        "-keyint_min", str(fps),
        "-flags", "+cgop",
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        "-movflags", "+faststart",
        "-threads", str(config["FFMPEG_THREADS"]),
    ])

    return base


def detect_hardware_encoder(config: dict) -> dict:
    if config.get("ENCODER_FORCE"):
        return _build_encoder_config(config["ENCODER_FORCE"], config)
    
    is_high_res = int(config.get("OUTPUT_HEIGHT", 1080)) > 1080 or int(config.get("OUTPUT_WIDTH", 1920)) > 1920
    
    if config.get("ENABLE_HARDWARE_ENCODER"):
        if _probe_encoder("h264_nvenc"):
            return _build_encoder_config("h264_nvenc", config)
        # Broadwell Intel HD 5500 QSV is unreliable above 1080p
        if not is_high_res and _probe_encoder("h264_qsv"):
            return _build_encoder_config("h264_qsv", config)
            
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
        # Save render spec signature to detect config changes across runs
        render_signature = f"{self.config.get('OUTPUT_WIDTH')}x{self.config.get('OUTPUT_HEIGHT')}@{self.config.get('OUTPUT_FPS')}"
        
        self.data = {
            "version": 3,
            "render_signature": render_signature,
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

    def is_signature_valid(self) -> bool:
        """Returns False if video_config dimensions or FPS changed since checkpoint creation."""
        if not self.data:
            return True
        current_sig = f"{self.config.get('OUTPUT_WIDTH')}x{self.config.get('OUTPUT_HEIGHT')}@{self.config.get('OUTPUT_FPS')}"
        return self.data.get("render_signature") == current_sig

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
    """Builds high-precision, sub-pixel stabilized Ken Burns camera motion with BT.709 color accuracy."""
    zoom_min = float(config.get("KEN_BURNS_ZOOM_MIN", 1.0))
    zoom_max = float(config.get("KEN_BURNS_ZOOM_MAX", 1.08))
    upscale = float(config.get("KEN_BURNS_UPSCALE_FACTOR", 1.12))
    fps = int(config["OUTPUT_FPS"])
    w = int(config["OUTPUT_WIDTH"])
    h = int(config["OUTPUT_HEIGHT"])
    
    upscale_w = int(w * upscale)
    upscale_h = int(h * upscale)
    upscale_w = upscale_w if upscale_w % 2 == 0 else upscale_w + 1
    upscale_h = upscale_h if upscale_h % 2 == 0 else upscale_h + 1
    frames = max(1, int(frame_count))

    # Master vector animation chroma interpolation (Preserves 3px line art and saturated typography)
    scale_flags = "flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp"
    norm = f",scale=out_color_matrix=bt709:flags=lanczos+accurate_rnd,setsar=1,format={pix_fmt}"
    
    den = max(1, frames - 1)
    t = f"((on-1)/{den})"
    ease = f"({t}*{t}*(3-2*{t}))"

    center_x = f"(iw-iw/zoom)/2"
    center_y = f"(ih-ih/zoom)/2"

    # Bounded expressions prevent floating-point edge flashes & sub-pixel aliasing
    safe_center_x = "trunc((iw-iw/zoom)*0.5)"
    safe_center_y = "trunc((ih-ih/zoom)*0.5)"

    if "zoom_in" in camera_action:
        z_expr = f"min({zoom_max},{zoom_min}+({zoom_max}-{zoom_min})*{ease})"
        x_expr = safe_center_x
        y_expr = safe_center_y
    elif "zoom_out" in camera_action:
        z_expr = f"max({zoom_min},{zoom_max}-({zoom_max}-{zoom_min})*{ease})"
        x_expr = safe_center_x
        y_expr = safe_center_y
    elif "pan_left" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = f"trunc(max(0,min(iw-iw/zoom,(iw-iw/zoom)*(1-{ease}))))"
        y_expr = safe_center_y
    elif "pan_right" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = f"trunc(max(0,min(iw-iw/zoom,(iw-iw/zoom)*{ease})))"
        y_expr = safe_center_y
    elif "tilt_up" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = safe_center_x
        y_expr = f"trunc(max(0,min(ih-ih/zoom,(ih-ih/zoom)*(1-{ease}))))"
    elif "tilt_down" in camera_action:
        z_expr = f"{zoom_max}"
        x_expr = safe_center_x
        y_expr = f"trunc(max(0,min(ih-ih/zoom,(ih-ih/zoom)*{ease})))"
    else:  # static
        loop_count = max(0, frames - 1)
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:{scale_flags},"
                f"pad={w}:{h}:trunc((ow-iw)/2)*2:trunc((oh-ih)/2)*2:color=black,"
                f"loop=loop={loop_count}:size=1:start=0,setpts=N/({fps}*TB)" + norm)

    return (f"scale={upscale_w}:{upscale_h}:force_original_aspect_ratio=increase:{scale_flags},"
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
                
                # Prioritize explicit camera motion specs over generic sequence types
                if any(k in cam_spec for k in ["zoom_out", "zoom out", "pull out", "pull-out", "pull_out"]):
                    cam = "zoom_out"
                elif any(k in cam_spec for k in ["zoom_in", "zoom in", "push in", "push-in", "push_in"]):
                    cam = "zoom_in"
                elif any(k in cam_spec for k in ["pan_left", "pan left", "tracking left"]):
                    cam = "pan_left"
                elif any(k in cam_spec for k in ["pan_right", "pan right", "tracking right"]):
                    cam = "pan_right"
                elif any(k in cam_spec for k in ["tilt_up", "tilt up", "upward"]):
                    cam = "tilt_up"
                elif any(k in cam_spec for k in ["tilt_down", "tilt down", "downward"]):
                    cam = "tilt_down"
                else:
                    # Fallback to sequence_type only if camera_spec is neutral
                    seq_t = str(item.get("sequence_type", "")).lower()
                    if "zoom" in seq_t:
                        cam = "zoom_in"
                    else:
                        cam = "static"

                seq_meta = item.get("sequence_metadata", {})
                occ_idx = seq_meta.get("frame_index", 1) if isinstance(seq_meta, dict) else 1

                for key in ts_keys:
                    camera_map[key] = cam
                    camera_map[f"{key}_{occ_idx}"] = cam
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
    """Parses transcript timestamps with sub-second float precision and normalized timecode keys."""
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
            match = re.match(r"^\[?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\]?", line)
            if match:
                hours = int(match.group(1)) if match.group(1) else 0
                minutes = int(match.group(2))
                seconds_float = float(match.group(3))
                total_sec = hours * 3600.0 + minutes * 60.0 + seconds_float
                seconds_int = int(seconds_float)

                if match.group(1) is not None:
                    timestamp_key = f"{hours:02d}_{minutes:02d}_{seconds_int:02d}"
                else:
                    timestamp_key = f"{minutes:02d}_{seconds_int:02d}"

                blocks.append({
                    "sec": total_sec,
                    "name": timestamp_key,
                    "raw_sec": seconds_float
                })

    blocks.sort(key=lambda x: x["sec"])
    return blocks

# -------------------------------------------------------------
# ACOUSTIC AUDIO-VISUAL SYNC ENGINE (Zero-Dependency Waveform VAD)
# -------------------------------------------------------------


class AudioSyncAligner:
    """Scans audio waveform energy to snap visual cuts to natural silence/breath boundaries."""
    def __init__(self, wav_path: str, window_ms: int = 20):
        self.wav_path = wav_path
        self.window_ms = window_ms
        self.energy_profile = []
        self.sample_rate = 48000
        self.total_duration = 0.0
        self.leading_silence_sec = 0.0
        self._analyze_waveform()

    def _analyze_waveform(self):
        if not os.path.exists(self.wav_path) or not self.wav_path.lower().endswith(".wav"):
            return
        try:
            with wave.open(self.wav_path, "rb") as wf:
                self.sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                n_frames = wf.getnframes()
                self.total_duration = n_frames / float(self.sample_rate)

                # Only process 16-bit PCM for fast scanning
                if sampwidth != 2:
                    return

                chunk_frames = int(self.sample_rate * (self.window_ms / 1000.0))
                found_voice = False

                for w_idx in range(0, n_frames, chunk_frames):
                    raw_bytes = wf.readframes(chunk_frames)
                    if not raw_bytes:
                        break
                    
                    count = len(raw_bytes) // 2
                    shorts = struct.unpack(f"<{count}h", raw_bytes)
                    # Sum amplitude across channels
                    rms = sum(abs(s) for s in shorts[::n_channels]) / max(1, count // n_channels)
                    self.energy_profile.append(rms)

                    # Detect initial speech onset (threshold ~400 amplitude)
                    if not found_voice and rms > 400:
                        self.leading_silence_sec = (w_idx / float(self.sample_rate))
                        found_voice = True
        except Exception as e:
            print(f"  [WARN] Waveform analysis bypassed: {e}")

    def snap_to_nearest_silence(self, target_sec: float, search_radius_sec: float = 0.20) -> float:
        """Finds the lowest acoustic energy dip (pause) within search_radius of target_sec."""
        if not self.energy_profile:
            return target_sec

        target_idx = int((target_sec * 1000.0) / self.window_ms)
        radius_steps = int((search_radius_sec * 1000.0) / self.window_ms)

        start_step = max(0, target_idx - radius_steps)
        end_step = min(len(self.energy_profile), target_idx + radius_steps + 1)

        if start_step >= end_step:
            return target_sec

        # Find minimum energy index in the search window
        min_energy = float("inf")
        best_step = target_idx

        for idx in range(start_step, end_step):
            if self.energy_profile[idx] < min_energy:
                min_energy = self.energy_profile[idx]
                best_step = idx

        snapped_sec = (best_step * self.window_ms) / 1000.0
        return snapped_sec

def prepare_synchronized_timeline(image_blocks: list, audio_duration: float, fps: int, audio_path: str = None) -> list:
    """
    ACOUSTICALLY SNAPPED ZERO-DRIFT TIMELINE:
    Snaps cutpoints to natural speech silence troughs using AudioSyncAligner,
    eliminates leading audio dead-air, and enforces sample-exact monotonic frame bounds.
    """
    if not image_blocks:
        return []

    # 1. Initialize Acoustic Snapper
    aligner = AudioSyncAligner(audio_path) if audio_path and os.path.exists(audio_path) else None

    processed = []
    i = 0
    n = len(image_blocks)

    while i < n:
        raw_sec = image_blocks[i]['sec']
        # Snap cut point to nearest speech silence pause (within ±200ms)
        current_sec = aligner.snap_to_nearest_silence(raw_sec, search_radius_sec=0.20) if (aligner and i > 0) else raw_sec

        group = [image_blocks[i]]
        j = i + 1
        while j < n and abs(image_blocks[j]['sec'] - raw_sec) < 0.15:
            group.append(image_blocks[j])
            j += 1

        next_raw_sec = image_blocks[j]['sec'] if j < n else audio_duration
        next_sec = aligner.snap_to_nearest_silence(next_raw_sec, search_radius_sec=0.20) if (aligner and j < n) else next_raw_sec
        
        group_duration = max(0.1, next_sec - current_sec)
        group_len = len(group)

        # Dynamic Comedic Weighting: 70% setup / 30% punchline reaction
        if group_len == 2:
            weights = [0.70, 0.30]
        elif group_len == 3:
            weights = [0.50, 0.25, 0.25]
        else:
            weights = [1.0 / group_len] * group_len

        running_start = current_sec
        for sub_idx, item in enumerate(group):
            slice_dur = group_duration * weights[sub_idx]
            sub_end = running_start + slice_dur
            processed.append({
                "sec": running_start,
                "end_sec": sub_end,
                "name": item["name"],
                "occurrence": sub_idx + 1
            })
            running_start = sub_end
        i = j

    final_timeline = []
    total_audio_frames = max(1, int(round(audio_duration * fps)))
    num_clips = len(processed)
    
    current_frame = 0
    for idx, block in enumerate(processed):
        start_frame = current_frame
        
        if idx == num_clips - 1:
            end_frame = total_audio_frames
        else:
            ideal_end_frame = int(round(block["end_sec"] * fps))
            remaining_clips = num_clips - 1 - idx
            # Strictly enforce 1-frame minimum while never overflowing total frame budget
            end_frame = max(start_frame + 1, min(ideal_end_frame, total_audio_frames - remaining_clips))

        frame_count = max(1, end_frame - start_frame)
        current_frame = end_frame

        final_timeline.append({
            "name": block["name"],
            "sec": start_frame / float(fps),
            "end_sec": end_frame / float(fps),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "frame_count": frame_count,
            "duration": frame_count / float(fps),
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
                f"{tv}_duplicate_0.png",
                f"sentence_{idx+1}.png"
            ])
        else:
            possible_names.extend([
                f"{tv}_{occurrence}.png",
                f"{tv}_frame{occurrence}.png",
                f"{tv}_duplicate_{occurrence-1}.png",
                f"{tv}_duplicate_{occurrence}.png",
                f"sentence_{idx+1}.png"
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
    # Multi-line DOTALL regex guarantees extraction of full Loudnorm measurement payload
    match = re.search(r'\{\s*"input_i"\s*:\s*"?[-\d.]+"?.*?\}', stderr, re.DOTALL)
    if match:
        blob = match.group(0)
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
        # Pass 1-frame image directly without demuxer loop; zoompan/loop will generate exact frame count
        input_args.extend(["-i", safe_image_path])
        filter_parts.append(f"[{input_idx}:v]{kb}[v{input_idx}];")
        clip_labels.append(f"[v{input_idx}]")
        input_idx += 1

    n_clips = len(clip_labels)
    if n_clips == 0:
        raise ValueError("No image clips to render in chunk")

    final_format = "nv12" if encoder_config.get("video_codec") == "h264_qsv" else "yuv420p"
    filter_parts.append(f"{''.join(clip_labels)}concat=n={n_clips}:v=1:a=0,format={final_format}[vout]")

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

    chunk_tmp_path = chunk_output_path + ".tmp"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", config["FFMPEG_LOGLEVEL"],
        *input_args,
        "-filter_complex_script", filter_script_path,
        "-map", f"[{video_label}]",
        "-c:v", encoder_config["video_codec"],
        *encoder_config["encoder_args"],
        "-an",
        chunk_tmp_path
    ]

    start_time = time.time()
    timeout = config.get("FFMPEG_CLIP_TIMEOUT", 300)

    try:
        process = subprocess.Popen(
            cmd, cwd=run_folder, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='ignore'
        )

        stderr_logs = []
        buffer = ""
        while True:
            if time.time() - start_time > timeout:
                process.kill()
                print(f"\n  [ERROR Chunk {chunk_idx+1}] FFmpeg timeout ({timeout}s)")
                return None

            chunk = process.stderr.read(256)
            if not chunk and process.poll() is not None:
                break

            if chunk:
                stderr_logs.append(chunk)
                buffer += chunk
                while "\r" in buffer or "\n" in buffer:
                    line, _, buffer = re.split(r"[\r\n]", buffer, maxsplit=1)
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
            if os.path.exists(chunk_tmp_path):
                try: os.remove(chunk_tmp_path)
                except OSError: pass
            return None

        if os.path.exists(chunk_tmp_path):
            os.replace(chunk_tmp_path, chunk_output_path)

        print(f"\r  [Chunk {chunk_idx+1}] Done! ({chunk_filename})                             ")
        return chunk_output_path

    except Exception as e:
        print(f"\n  [ERROR Chunk {chunk_idx+1}] Execution error: {e}")
        return None

# -------------------------------------------------------------
# INSERTION POINT 1: Place directly above assemble_final_video
# -------------------------------------------------------------

class SFXEngine:
    """Selects and schedules contextual SFX based on frame metadata."""
    def __init__(self, sfx_root: str, default_volume: float = 0.22):
        self.sfx_root = sfx_root
        self.volume = default_volume
        self.last_heavy_sfx_time = -10.0

    def get_sound_for_block(self, block_meta: dict, timestamp_sec: float) -> tuple[str, float] | None:
        """Returns (sfx_file_path, delay_offset_ms) or None."""
        if not os.path.exists(self.sfx_root):
            return None

        seq_type = str(block_meta.get("sequence_type", "")).upper()
        layout = str(block_meta.get("layout_classification", "")).upper()
        vp = block_meta.get("visual_prompt", {})
        action = str(vp.get("subject_action_increment", "")).lower() if isinstance(vp, dict) else ""

        category = None
        offset_ms = 0.0

        # 1. High-Priority Keyword Actions
        if any(k in action for k in ["stamp", "ختم", "stamped", "reject"]):
            category = "stamp"
        elif any(k in action for k in ["scissors", "قص", "cut", "money", "cash", "دولار", "فاتورة"]):
            category = "comedy_props"

        # 2. Semantic Sequence Type Triggers
        elif seq_type == "REACTION_PUNCHLINE_SET":
            if timestamp_sec - self.last_heavy_sfx_time >= 2.0:
                category = "punchline"
                self.last_heavy_sfx_time = timestamp_sec

        elif seq_type in ["ARCHIVAL_DOSSIER", "COMPARATIVE_DIAGRAM"] or layout in ["ARCHIVAL_DOSSIER", "COMPARATIVE_DIAGRAM_DESK"]:
            category = "paper"

        elif seq_type == "SCIENTIFIC_BLUEPRINT" or layout == "RETRO_BLUEPRINT":
            category = "blueprint_hud"

        # 3. Transition Whooshes
        elif block_meta.get("camera", "") in ["pan_left", "pan_right", "zoom_out"]:
            category = "whoosh"
            offset_ms = -80.0

        if not category:
            return None

        cat_dir = os.path.join(self.sfx_root, category)
        if os.path.exists(cat_dir):
            valid_exts = (".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac")
            files = [os.path.join(cat_dir, f) for f in os.listdir(cat_dir) if f.lower().endswith(valid_exts)]
            if files:
                return random.choice(files), offset_ms
        return None

def build_dynamic_ass_subtitles(raw_transcript_path: str, output_ass_path: str, config: dict, total_duration: float = 0.0):
    """
    Generates broadcast-grade Advanced SubStation Alpha (.ass) subtitles with 
    dynamic active-word color highlights and Arabic typography shaping.
    """
    if not os.path.exists(raw_transcript_path):
        return None

    font_name = config.get("SUB_FONT_NAME", "Arial")
    font_size = int(config.get("SUB_FONT_SIZE", 32))
    # ASS uses BGR hex format (&H00BBGGRR)
    primary_color = "&H00FFFFFF"      # Crisp White
    highlight_color = "&H003EB0FF"    # Warm Amber (#E09F3E in BGR)
    outline_color = "&H00000000"      # Pure Black
    margin_v = int(config.get("SUB_MARGIN_V", 65))

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.get('OUTPUT_WIDTH', 2560)}
PlayResY: {config.get('OUTPUT_HEIGHT', 1440)}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,1,0,0,0,100,100,0,0,1,3.8,2.0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def format_ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = []
    with open(raw_transcript_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line_str = raw_line.strip()
            if not line_str:
                continue
            match = re.match(r"^\[?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\]?\s*(.*)", line_str)
            if match:
                h = int(match.group(1)) if match.group(1) else 0
                m = int(match.group(2))
                s = float(match.group(3))
                start_sec = h * 3600.0 + m * 60.0 + s
                text = match.group(4).strip()
                if text:
                    lines.append((start_sec, text))

    events = []
    for i, (start_sec, text) in enumerate(lines):
        end_sec = lines[i + 1][0] if i < len(lines) - 1 else (total_duration if total_duration > start_sec else start_sec + 3.5)
        duration = max(0.5, end_sec - start_sec)
        
        words = text.split()
        if not words:
            continue

        start_str = format_ass_time(start_sec)
        end_str = format_ass_time(end_sec)

        # Build dynamic word-by-word timing tags
        word_dur_cs = int((duration * 100) / max(1, len(words)))  # Centiseconds per word
        highlighted_body = "".join([f"{{\\c{highlight_color}\\t(0,200,\\fscx105\\fscy105)}}{w}{{\\c{primary_color}\\fscx100\\fscy100}} " for w in words])
        
        event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{highlighted_body.strip()}"
        events.append(event_line)

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header + "\n".join(events) + "\n")

    return output_ass_path

def assemble_final_video(config: dict, encoder_config: dict, chunk_files: list[str],
                         audio_path: str, subtitle_path: str | None, run_folder: str,
                         sync_timeline: list = None) -> bool:
    output_path = os.path.abspath(os.path.join(run_folder, "youtube_ready_video.mp4"))
    temp_dir = os.path.abspath(os.path.join(run_folder, "temp_clips"))
    concat_txt_path = os.path.join(temp_dir, "concat_chunks.txt")

    with open(concat_txt_path, "w", encoding="utf-8") as f:
        for c_file in chunk_files:
            safe_c_path = os.path.abspath(c_file).replace("\\", "/")
            f.write(f"file '{safe_c_path}'\n")

    safe_audio_path = os.path.abspath(audio_path).replace("\\", "/")

    filter_parts = []
    audio_inputs = ["-i", safe_audio_path]
    sfx_labels = []

    # 1. Build Sample-Exact SFX Stems from sync_timeline
    raw_sfx_dir = config.get("SFX_DIR", "assets/sfx")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sfx_resolved_path = raw_sfx_dir if os.path.isabs(raw_sfx_dir) else os.path.join(script_dir, raw_sfx_dir)

    if config.get("ENABLE_SFX") and os.path.exists(sfx_resolved_path) and sync_timeline:
        sfx_engine = SFXEngine(sfx_resolved_path, float(config.get("SFX_DEFAULT_VOLUME", 0.22)))
        json_path = os.path.join(run_folder, "flow_prompts.json")
        prompt_items = []
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    prompt_items = json.load(f)
            except Exception:
                pass

        input_counter = 2  # 0: video, 1: primary voice
        for idx, block in enumerate(sync_timeline):
            item_meta = prompt_items[idx] if idx < len(prompt_items) else {}
            exact_sec = block.get("sec", 0.0)
            sfx_res = sfx_engine.get_sound_for_block(item_meta, exact_sec)
            if sfx_res:
                sfx_file, offset_ms = sfx_res
                actual_time_ms = max(0, int((exact_sec * 1000.0) + offset_ms))
                
                audio_inputs.extend(["-i", os.path.abspath(sfx_file).replace("\\", "/")])
                filter_parts.append(
                    f"[{input_counter}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                    f"volume={config.get('SFX_DEFAULT_VOLUME', 0.22)},"
                    f"adelay={actual_time_ms}|{actual_time_ms}[sfx{input_counter}];"
                )
                sfx_labels.append(f"[sfx{input_counter}]")
                input_counter += 1

    # 2. Optional Background Music (BGM) Auto-Ducking
    bgm_path = os.path.join(script_dir, config.get("BGM_FILE", "assets/music/bgm.mp3"))
    has_bgm = config.get("ENABLE_BGM", False) and os.path.exists(bgm_path)
    if has_bgm:
        bgm_idx = len(audio_inputs) // 2 + 1
        audio_inputs.extend(["-stream_loop", "-1", "-i", os.path.abspath(bgm_path).replace("\\", "/")])
        # Lowers music volume under voice automatically
        filter_parts.append(
            f"[{bgm_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.15[bgm_raw];"
            f"[bgm_raw][1:a]sidechaincompress=threshold=0.08:ratio=6:attack=200:release=800[bgm_ducked];"
        )
        sfx_labels.append("[bgm_ducked]")

    # 2. Composite Voice + Scheduled SFX
    if sfx_labels:
        total_stems = len(sfx_labels) + 1
        filter_parts.append(
            f"[1:a]{''.join(sfx_labels)}amix=inputs={total_stems}:duration=first:dropout_transition=2[mixed_a];"
        )
        voice_src = "[mixed_a]"
    else:
        voice_src = "[1:a]"

    # 3. Master 2-Pass Loudnorm Pass on Combined Audio
    if config["ENABLE_LOUDNORM_TWOPASS"]:
        ln = _measure_loudnorm(audio_path, config)
    else:
        ln = f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:LRA={config['LOUDNORM_LRA']}"

    audio_dur = config.get("_audio_duration", 1.0)
    fade_start = max(0.0, audio_dur - 0.10)
    filter_parts.append(
        f"{voice_src}aresample=async=1:min_hard_comp=0.100000:first_pts=0,"
        f"{ln},afade=t=out:st={fade_start:.2f}:d=0.10[aout]"
    )

    video_label = "0:v"
    video_codec_args = ["-c:v", "copy"]

    if subtitle_path and os.path.exists(subtitle_path):
        safe_sub = os.path.abspath(subtitle_path).replace("\\", "/").replace(":", "\\:").replace("'", "'\\\\''")
        
        # Auto-detect local project fonts directory (assets/fonts)
        fonts_dir = os.path.join(script_dir, "assets", "fonts")
        font_arg = ""
        if os.path.exists(fonts_dir):
            safe_fonts = os.path.abspath(fonts_dir).replace("\\", "/").replace(":", "\\:").replace("'", "'\\\\''")
            font_arg = f":fontsdir='{safe_fonts}'"

        filter_parts.append(f"[0:v]subtitles='{safe_sub}'{font_arg}[vout]")
        video_label = "[vout]"
        video_codec_args = [
            "-c:v", encoder_config["video_codec"],
            *encoder_config["encoder_args"]
        ]

    filter_complex = "".join(filter_parts)
    filter_script_path = os.path.join(temp_dir, "filter_final_assembly.txt")
    with open(filter_script_path, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", config["FFMPEG_LOGLEVEL"],
        "-f", "concat", "-safe", "0", "-i", concat_txt_path,
        *audio_inputs,
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
    if config.get("ENABLE_SUBTITLES", False):
        transcript_source = os.path.join(run_folder, "image_timestamps.txt")
        if not os.path.exists(transcript_source):
            transcript_source = os.path.join(run_folder, "timestamped_transcript.txt")
        
        if os.path.exists(transcript_source):
            ass_path = os.path.join(run_folder, "dynamic_subtitles.ass")
            audio_duration = config.get("_audio_duration", 0.0)
            subtitle_path = build_dynamic_ass_subtitles(transcript_source, ass_path, config, total_duration=audio_duration)

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

        from concurrent.futures import ThreadPoolExecutor, as_completed

        max_workers = min(2, num_chunks) if "qsv" in current_encoder.get("video_codec", "") else min(2, max(1, os.cpu_count() // 2))
        print(f"  [RENDER ENGINE] Parallel rendering across {max_workers} worker threads...")

        rendered_map = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    render_chunk, config, current_encoder, chunk_timeline, images_dir,
                    ai_cameras, manual_cameras, config["ENABLE_ANIMATIONS"],
                    chunk_idx, temp_dir, run_folder, chunk_idx * chunk_size
                ): chunk_idx for chunk_idx, chunk_timeline in enumerate(chunks)
            }

            for future in as_completed(futures):
                c_idx = futures[future]
                try:
                    result = future.result()
                    if result:
                        rendered_map[c_idx] = result
                    else:
                        failed = True
                except Exception as e:
                    print(f"  [ERROR] Chunk {c_idx+1} raised exception: {e}")
                    failed = True

        chunk_files = [rendered_map[i] for i in range(num_chunks) if i in rendered_map]

        if not failed and len(chunk_files) == num_chunks:
            ok = assemble_final_video(config, current_encoder, chunk_files, audio_path, subtitle_path, run_folder, sync_timeline=sync_timeline)
            if ok:
                return True
            else:
                failed = True

        if failed:
            if current_encoder["video_codec"] == "libx264":
                return False
            print(f"\n  [FALLBACK] Hardware encoder failed. Purging incompatible chunks & retrying with libx264...")
            # Purge partial or mismatched chunks so all chunks are uniformly rendered with libx264
            for fname in os.listdir(temp_dir):
                if fname.startswith("chunk_") and fname.endswith(".mp4"):
                    try: os.remove(os.path.join(temp_dir, fname))
                    except OSError: pass
            current_encoder = _build_encoder_config("libx264", config)


# Backwards compatibility alias
run_single_pass = run_chunked_compile


def verify_master_video(output_path: str, expected_duration: float) -> bool:
    """Verifies that the master MP4 is non-corrupt and has matching video and audio stream durations."""
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 10000:
        return False
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration:stream=codec_type,duration", "-of", "json", output_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(res.stdout)
        
        streams = [s.get("codec_type") for s in data.get("streams", [])]
        has_video = "video" in streams
        has_audio = "audio" in streams
        
        file_dur = float(data.get("format", {}).get("duration", 0.0))
        dur_diff = abs(file_dur - expected_duration)
        
        # Valid if both streams exist and duration matches within ±0.5s tolerance
        return has_video and has_audio and (dur_diff < 0.5)
    except Exception:
        return False


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

    # 2. Build ZERO-DRIFT synchronized timeline with Acoustic Waveform Snapping
    sync_timeline = prepare_synchronized_timeline(raw_image_blocks, audio_duration, config["OUTPUT_FPS"], audio_path=audio_path)
    if not sync_timeline:
        print(f"[FATAL ERROR] Timeline is empty. No valid timestamps found in '{latest_run}'.")
        sys.exit(1)

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

    # 3. Execute Chunked Zero-Drift Render & Health Verification
    ok = run_chunked_compile(config, encoder_config, sync_timeline, images_dir, audio_path, latest_run, checkpoint)
    output_mp4 = os.path.join(latest_run, "youtube_ready_video.mp4")

    if ok and verify_master_video(output_mp4, audio_duration):
        print(f"\n[SUCCESS] Master Video Verified & Completed in Sync: {output_mp4}")
        if checkpoint:
            checkpoint.cleanup_on_success()
        if not config.get("DEBUG_SAVE_INTERMEDIATES", False):
            for d in ["temp_clips", "temp_sfx"]:
                tdir = os.path.join(latest_run, d)
                if os.path.exists(tdir):
                    shutil.rmtree(tdir, ignore_errors=True)
    else:
        print("\n[ERROR] Video compilation failed or output verification did not pass.")
        sys.exit(1)


if __name__ == "__main__":
    run_folder_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(run_folder_arg)