import os
import json
import re
import sys
import subprocess
from datetime import datetime

def load_video_config(config_path="video_config.txt") -> dict:
    """
    Parse video_config.txt into typed dict.
    Supports: bool (true/false), int, float, str.
    Comments (# ...) and blank lines ignored.
    Missing keys -> sensible defaults (defined in DEFAULTS dict below).
    """
    DEFAULTS = {
        "ENABLE_ANIMATIONS": False,
        "ENABLE_SUBTITLES": False,
        "ENABLE_HARDWARE_ENCODER": True,
        "ENABLE_SINGLE_PASS": True,
        "ENABLE_CHECKPOINT_RESUME": True,
        "ENABLE_LOUDNORM_TWOPASS": True,
        "ENABLE_VBV": True,
        "OUTPUT_WIDTH": 1920,
        "OUTPUT_HEIGHT": 1080,
        "OUTPUT_FPS": 24,
        "OUTPUT_PIX_FMT": "yuv420p",
        "OUTPUT_PROFILE": "high",
        "OUTPUT_LEVEL": "4.1",
        "CPU_CRF": 18,
        "CPU_PRESET": "fast",
        "CPU_TUNE": "film",
        "ENCODER_FORCE": "",
        "QSV_PRESET": "fast",
        "QSV_GLOBAL_QUALITY": 22,
        "QSV_LOOKAHEAD": 1,
        "QSV_LOOKAHEAD_DEPTH": 40,
        "NVENC_PRESET": "p4",
        "NVENC_CQ": 22,
        "NVENC_RC": "vbr",
        "NVENC_MULTIPASS": "fullres",
        "NVENC_SPATIAL_AQ": 1,
        "NVENC_TEMPORAL_AQ": 1,
        "KEN_BURNS_ZOOM_MIN": 1.0,
        "KEN_BURNS_ZOOM_MAX": 1.15,
        "KEN_BURNS_EASING": "parabolic",
        "KEN_BURNS_UPSCALE_FACTOR": 2.0,
        "KEN_BURNS_INTERP_ALGO": "lanczos",
        "KEN_BURNS_PAN_SPEED": 0.08,
        "KEN_BURNS_ZOOM_SPEED": 0.12,
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
        "VBV_MAXRATE": "10000k",
        "VBV_BUFSIZE": "20000k",
        "FFMPEG_THREADS": 0,
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
    """Run `ffmpeg -hide_banner -encoders` to check if encoder is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10
        )
        return encoder_name in result.stdout
    except Exception:
        return False


def _build_encoder_config(encoder: str, config: dict) -> dict:
    """Build encoder-specific argument list from config."""
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
            base["encoder_args"].extend([
                "-maxrate", config["VBV_MAXRATE"],
                "-bufsize", config["VBV_BUFSIZE"],
            ])

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
            base["encoder_args"].extend([
                "-maxrate", config["VBV_MAXRATE"],
                "-bufsize", config["VBV_BUFSIZE"],
            ])

    else:  # libx264 CPU fallback
        base["encoder_args"] = [
            "-preset", config["CPU_PRESET"],
            "-crf", str(config["CPU_CRF"]),
            "-tune", config["CPU_TUNE"],
            "-profile:v", config["OUTPUT_PROFILE"],
            "-level", config["OUTPUT_LEVEL"],
        ]
        if config["ENABLE_VBV"]:
            base["encoder_args"].extend([
                "-maxrate", config["VBV_MAXRATE"],
                "-bufsize", config["VBV_BUFSIZE"],
            ])

    # Common to all encoders
    base["encoder_args"].extend([
        "-pix_fmt", config["OUTPUT_PIX_FMT"],
        "-movflags", "+faststart",
        "-threads", str(config["FFMPEG_THREADS"]),
    ])

    return base


def detect_hardware_encoder(config: dict) -> dict:
    """
    Probe ffmpeg for available hardware encoders.
    Priority: QSV (Intel) → NVENC (NVIDIA) → CPU (libx264).
    Returns encoder config dict with codec name and optimized args.
    """
    if config["ENCODER_FORCE"]:
        return _build_encoder_config(config["ENCODER_FORCE"], config)

    # 1. Probe QSV (Intel QuickSync) — h264_qsv, hevc_qsv
    if _probe_encoder("h264_qsv"):
        return _build_encoder_config("h264_qsv", config)

    # 2. Probe NVENC (NVIDIA) — h264_nvenc, hevc_nvenc
    if _probe_encoder("h264_nvenc"):
        return _build_encoder_config("h264_nvenc", config)

    # 3. Fallback: CPU libx264
    return _build_encoder_config("libx264", config)


class CheckpointManager:
    """Tracks per-clip render state for resume-safe video compilation."""

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
        os.replace(tmp_path, self.checkpoint_path)  # atomic write

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

    def mark_clip_failed(self, clip_idx: int, error: str):
        self.data["clip_states"][str(clip_idx)] = {
            "status": "failed",
            "error": error,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if clip_idx not in self.data["failed_clips"]:
            self.data["failed_clips"].append(clip_idx)
        self.save()

    def get_pending_indices(self) -> list:
        return [i for i in range(self.data["total_clips"]) if not self.is_clip_done(i)]

    def get_concat_entries(self) -> list:
        """Return sorted concat file entries for completed clips."""
        entries = []
        for i in range(self.data["total_clips"]):
            state = self.data["clip_states"].get(str(i), {})
            if state.get("status") == "done":
                entries.append(f"file 'temp_clips/clip_{i:04d}.mp4'")
        return entries

    def cleanup_on_success(self):
        if os.path.exists(self.checkpoint_path):
            os.remove(self.checkpoint_path)


def build_ken_burns_filter(config: dict, duration: float, camera_action: str, pix_fmt: str = "yuv420p") -> str:
    """
    Build a frame-accurate Ken Burns zoompan filter string for one clip.
    Matches the proven Phase 1 inline math: native-resolution upscale canvas,
    parabolic easing, lanczos interpolation. Returns a `-vf`-ready string.
    """
    zoom_min = config["KEN_BURNS_ZOOM_MIN"]
    zoom_max = config["KEN_BURNS_ZOOM_MAX"]
    upscale = config["KEN_BURNS_UPSCALE_FACTOR"]
    interp = config["KEN_BURNS_INTERP_ALGO"]
    fps = config["OUTPUT_FPS"]
    w = config["OUTPUT_WIDTH"]
    h = config["OUTPUT_HEIGHT"]
    upscale_w = int(w * upscale)
    upscale_h = int(h * upscale)
    frames = max(1, int(duration * fps))

    # Normalize every clip to a consistent SAR (1:1) and pixel format so the
    # concat filter receives uniform inputs regardless of source image aspect ratio.
    # Without this, concat aborts ("Input link ... SAR ... do not match").
    norm = f",setsar=1,format={pix_fmt}"

    if "zoom_in" in camera_action:
        return (f"scale={upscale_w}:{upscale_h}:flags={interp},"
                f"zoompan=z='{zoom_min}+({zoom_max}-{zoom_min})*(on/{frames})*(on/{frames})*(3-2*(on/{frames}))':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={w}x{h}:fps={fps}" + norm)
    elif "zoom_out" in camera_action:
        return (f"scale={upscale_w}:{upscale_h}:flags={interp},"
                f"zoompan=z='{zoom_max}-({zoom_max}-{zoom_min})*(on/{frames})*(on/{frames})*(3-2*(on/{frames}))':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={w}x{h}:fps={fps}" + norm)
    elif "pan_left" in camera_action:
        # Keep static zoom-margin level for clear panning boundaries
        pan_zoom = zoom_min + (zoom_max - zoom_min) * config["KEN_BURNS_PAN_SPEED"]
        return (f"scale={upscale_w}:{upscale_h}:flags={interp},"
                f"zoompan=z='{pan_zoom}':"
                f"x='(iw-iw/zoom)*(1-(on/{frames})*(on/{frames})*(3-2*(on/{frames})))':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={w}x{h}:fps={fps}" + norm)
    elif "pan_right" in camera_action:
        # Keep static zoom-margin level for clear panning boundaries
        pan_zoom = zoom_min + (zoom_max - zoom_min) * config["KEN_BURNS_PAN_SPEED"]
        return (f"scale={upscale_w}:{upscale_h}:flags={interp},"
                f"zoompan=z='{pan_zoom}':"
                f"x='(iw-iw/zoom)*(on/{frames})*(on/{frames})*(3-2*(on/{frames}))':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={w}x{h}:fps={fps}" + norm)
    else:
        # Explicitly truncate the looped image stream to match the timeline duration
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1:color=black,"
                f"trim=start_frame=0:end_frame={frames},setpts=PTS-STARTPTS" + norm)


def get_config_value(file_path, key, default):
    """Reads a true/false string from the config text file."""
    if not os.path.exists(file_path): return default
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith(key):
                return line.split('=')[1].strip().lower()
    return default

def get_audio_duration(audio_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
    return float(subprocess.check_output(cmd).decode('utf-8').strip())

def get_latest_run_folder(runs_path="youtube_runs"):
    """Finds the latest run folder by checking both CWD and script-relative paths."""
    # First, try to resolve relative to compile_video.py's own directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    rel_to_script = os.path.join(script_dir, runs_path)
    
    resolved_path = runs_path
    if os.path.exists(rel_to_script):
        resolved_path = rel_to_script
    elif not os.path.exists(resolved_path):
        return None

    subdirs = [os.path.join(resolved_path, name) for name in os.listdir(resolved_path) if os.path.isdir(os.path.join(resolved_path, name))]
    return max(subdirs, key=os.path.getmtime) if subdirs else None

def load_ai_camera_decisions(json_path):
    camera_map = {}
    if not os.path.exists(json_path): return camera_map
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read()
            json_blocks = re.findall(r'\[\s*\{.*?\}\s*\]', content, re.DOTALL)
            for block in json_blocks:
                data = json.loads(block)
                for item in data:
                    ts = str(item.get("timestamp", "")).replace("[", "").replace("]", "").replace(":", "_").strip()
                    vp = item.get("visual_prompt", {})
                    if isinstance(vp, dict):
                        # Parse camera_specifications string for movement keywords
                        cam_spec = vp.get("camera_specifications", "").lower()
                        if "zoom in" in cam_spec:
                            cam = "zoom_in"
                        elif "zoom out" in cam_spec:
                            cam = "zoom_out"
                        elif "pan left" in cam_spec:
                            cam = "pan_left"
                        elif "pan right" in cam_spec:
                            cam = "pan_right"
                        else:
                            cam = "static"
                        if ts: camera_map[ts] = cam
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] Failed to parse camera decisions from {json_path}: {e}")
    return camera_map

def load_manual_overrides(txt_path):
    overrides = {}
    if not os.path.exists(txt_path): return overrides
    with open(txt_path, 'r') as f:
        for line in f:
            if '=' in line:
                k, v = line.split('=')
                overrides[k.strip()] = v.strip().lower()
    return overrides

def parse_image_timeline(txt_path, srt_path):
    """Parse image timeline from timestamped_transcript.txt.
    
    Uses the paragraph-level timestamps from the .txt file which match the 
    generated image names (e.g., [00:08] -> 00_08.png). This ensures perfect
    sync since images are generated per-paragraph, not per-word like SRT entries.
    """
    blocks = []
    
    if not os.path.exists(txt_path):
        return blocks
        
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Match [MM:SS] or [HH:MM:SS] format
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
                
    return blocks

def fix_arabic_srt(input_path, output_path):
    # utf-8-sig strips a leading BOM if present so we never write a double BOM
    # (which ffmpeg's SRT demuxer cannot parse -> "Unable to open"). Write plain
    # utf-8 (no BOM) for maximum compatibility with the subtitles filter.
    with open(input_path, "r", encoding="utf-8-sig") as f: content = f.read()
    with open(output_path, "w", encoding="utf-8") as f: f.write(content)


def build_subtitle_style_string(config: dict) -> str:
    """Build the ASS force_style string from config subtitle keys."""
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


def _resolve_image_path(block, idx, images_dir, available_images, last_valid_image):
    """Resolve the on-disk image path for a timeline block with fallbacks."""
    img_name = f"{block['name']}.png"
    abs_image_path = os.path.join(images_dir, img_name)
    if not os.path.exists(abs_image_path) and idx < len(available_images):
        abs_image_path = os.path.join(images_dir, available_images[idx])
        img_name = available_images[idx]
    if not os.path.exists(abs_image_path):
        if last_valid_image is None:
            return None, None
        return last_valid_image, os.path.basename(last_valid_image)
    return abs_image_path, img_name


def validate_assets(image_blocks: list, images_dir: str) -> list:
    """Validate that all timeline clips have existing, non-empty image files.
    
    Returns a list of tuples (index, block_name) for any missing/invalid assets.
    """
    invalid = []
    if not image_blocks:
        return invalid
    available_images = get_sorted_images(images_dir)
    last_valid_image = None
    for idx, block in enumerate(image_blocks):
        abs_image_path, _ = _resolve_image_path(block, idx, images_dir, available_images, last_valid_image)
        if abs_image_path is None or not os.path.exists(abs_image_path) or os.path.getsize(abs_image_path) == 0:
            invalid.append((idx, block.get("name", "unknown")))
        else:
            last_valid_image = abs_image_path
    return invalid


def _extract_loudnorm_measured(stderr: str, config: dict, run_folder: str) -> dict:
    """Parse ffmpeg loudnorm JSON output and persist measured values for a 2nd pass.

    loudnorm with print_format=json emits a pretty-printed JSON object spread
    across multiple stderr lines (logged at info level), so we grab the text
    between the first '{' and the last '}' rather than matching a single line.
    """
    measured = {}
    data = None
    start = stderr.find('{')
    end = stderr.rfind('}')
    if start != -1 and end != -1 and end > start:
        blob = stderr[start:end + 1]
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            data = None
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
                for k, v in config.items():
                    f.write(f"{k}={v}\n")
        except OSError:
            pass
        print(f"  [LOUDNORM] Measured: I={measured['LOUDNORM_MEASURED_I']:.1f} "
              f"TP={measured['LOUDNORM_MEASURED_TP']:.1f} "
              f"LRA={measured['LOUDNORM_MEASURED_LRA']:.1f}")
    return measured


def _measure_loudnorm(audio_path: str, config: dict) -> str:
    """Run loudnorm pass 1 (measure) and return a pass-2 loudnorm filter string."""
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
    return (f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:"
            f"LRA={config['LOUDNORM_LRA']}")


def build_single_pass_filter_graph(config: dict, encoder_config: dict, image_blocks: list,
                                   images_dir: str, audio_path: str, subtitle_path: str | None,
                                   ai_cameras: dict, manual_cameras: dict, anim_enabled: bool) -> tuple:
    """
    Build (input_args, filter_complex) for a single ffmpeg invocation that does:
    per-clip Ken Burns -> concat -> (subtitles) -> audio loudnorm -> mux.
    Inputs ordered: [img0, img1, ..., imgN, audio].
    """
    fps = config["OUTPUT_FPS"]
    w = config["OUTPUT_WIDTH"]
    h = config["OUTPUT_HEIGHT"]
    available_images = get_sorted_images(images_dir)
    last_valid_image = None

    input_args = []
    filter_parts = []
    concat_inputs = []

    for idx, block in enumerate(image_blocks):
        abs_image_path, _ = _resolve_image_path(block, idx, images_dir, available_images, last_valid_image)
        if abs_image_path is None:
            print(f"  [SKIP] Block {idx}: no image available")
            continue
        last_valid_image = abs_image_path

        start_sec = block['sec']
        end_sec = image_blocks[idx+1]['sec'] if idx < len(image_blocks)-1 else config.get("_audio_duration", start_sec + 5.0)
        duration = max(config["MIN_CLIP_DURATION"], end_sec - start_sec)
        frames = max(1, int(duration * fps))

        camera_action = "static"
        if anim_enabled:
            camera_action = ai_cameras.get(block['name'], "static")
            if block['name'] in manual_cameras:
                camera_action = manual_cameras[block['name']]

        kb = build_ken_burns_filter(config, duration, camera_action)
        input_args.extend(["-loop", "1", "-framerate", str(fps), "-i", abs_image_path])
        filter_parts.append(f"[{len(concat_inputs)}:v]{kb}[v{len(concat_inputs)}];")
        concat_inputs.append(f"[v{len(concat_inputs)}]")

    n_clips = len(concat_inputs)
    audio_input_idx = n_clips
    input_args.extend(["-i", audio_path])

    if n_clips == 0:
        raise ValueError("No image clips to render")

    # Concat video streams
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={n_clips}:v=1:a=0[vconcat];")
    # Guarantee exact output resolution
    filter_parts.append(f"[vconcat]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                        f"pad={w}:{h}:-1:-1:color=black[vscaled];")

    video_label = "vscaled"
    if subtitle_path and os.path.exists(subtitle_path):
        sub_style = build_subtitle_style_string(config)
        safe_sub = os.path.basename(subtitle_path).replace("'", "\\'")
        filter_parts.append(f"[vscaled]subtitles='{safe_sub}':force_style='{sub_style}'[vout];")
        video_label = "vout"

    # B7: Explicit Pixel Format Allocation so encoder does not guess
    final_format = "nv12" if encoder_config.get("video_codec") == "h264_qsv" else "yuv420p"
    filter_parts.append(f"[{video_label}]format={final_format}[vformat];")
    video_label = "vformat"

    # Audio loudnorm (EBU R128)
    if config["ENABLE_LOUDNORM_TWOPASS"]:
        ln = _measure_loudnorm(audio_path, config)
    else:
        ln = (f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:"
              f"LRA={config['LOUDNORM_LRA']}")
    filter_parts.append(f"[{audio_input_idx}:a]{ln}[aout];")

    filter_complex = "".join(filter_parts)
    return input_args, filter_complex, video_label


def run_single_pass(config: dict, encoder_config: dict, image_blocks: list, images_dir: str,
                    audio_path: str, run_folder: str, checkpoint: CheckpointManager = None) -> bool:
    """Execute the single-pass render. Returns True on success."""
    output_path = os.path.abspath(os.path.join(run_folder, "youtube_ready_video.mp4"))

    # B3: If checkpoint resume is enabled and checkpoint contains data, skip rendering if completed
    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint and checkpoint.data is not None:
        if checkpoint.data["completed_clips"] == checkpoint.data["total_clips"] and os.path.exists(output_path):
            print("  [RESUME] Single-pass already completed. Skipping rendering.")
            return True

    subtitle_path = None
    if config["ENABLE_SUBTITLES"]:
        srt_path = os.path.join(run_folder, "timestamped_transcript.srt")
        if os.path.exists(srt_path):
            fixed_srt = os.path.join(run_folder, "timestamped_transcript_fixed.srt")
            if not config["DEBUG_DRY_RUN"]:
                fix_arabic_srt(srt_path, fixed_srt)
            subtitle_path = fixed_srt
        else:
            print("  [WARN] Subtitles enabled but SRT missing; rendering without subs")

    if config["DEBUG_DRY_RUN"]:
        print("[DRY RUN] Would execute single-pass FFmpeg")
        return True

    # B3: If checkpoint resume is enabled but checkpoint data is None, initialize it
    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint and checkpoint.data is None:
        audio_duration = config.get("_audio_duration", 0.0)
        checkpoint.initialize(len(image_blocks), encoder_config, audio_path, audio_duration, subtitle_path)

    ai_cameras = load_ai_camera_decisions(os.path.join(run_folder, "flow_prompts.json"))
    manual_cameras = load_manual_overrides("manual_animations.txt")

    # Image/audio input paths must be absolute: run_single_pass invokes ffmpeg
    # with cwd=run_folder (so the subtitle basename resolves), but images_dir and
    # audio_path are computed relative to the project root and would not be found.
    images_dir = os.path.abspath(images_dir)
    audio_path = os.path.abspath(audio_path)

    current_encoder = encoder_config
    while True:
        try:
            input_args, filter_complex, video_label = build_single_pass_filter_graph(
                config, current_encoder, image_blocks, images_dir, audio_path,
                subtitle_path, ai_cameras, manual_cameras, config["ENABLE_ANIMATIONS"])
        except ValueError as e:
            print(f"  [ERROR] {e}")
            return False

        if config["DEBUG_FILTER_GRAPH_DUMP"]:
            with open(os.path.join(run_folder, "filter_graph.dot"), "w", encoding="utf-8") as f:
                f.write("digraph G {\n" + filter_complex.replace(";", ";\n") + "\n}")

        # Write the filtergraph to a file and use -/filter_complex. Windows has a
        # ~32K command-line length limit; a 100+ clip Ken Burns graph exceeds it and
        # raises WinError 206 ("filename or extension is too long").
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

        print(f"\n[Single-Pass] Rendering {len(image_blocks)} clips + audio + subs in one FFmpeg ({current_encoder['video_codec']})...")
        failed = False
        res = None
        try:
            res = subprocess.run(cmd, cwd=run_folder, timeout=config["FFMPEG_FINAL_TIMEOUT"],
                                 capture_output=True, text=True, encoding='utf-8', errors='ignore')
            if res.returncode != 0:
                print(f"  [ERROR] FFmpeg failed with {current_encoder['video_codec']}:\n{res.stderr[-2000:]}")
                failed = True
        except subprocess.TimeoutExpired:
            print(f"  [ERROR] FFmpeg timeout ({config['FFMPEG_FINAL_TIMEOUT']}s) with {current_encoder['video_codec']}")
            failed = True
        except Exception as e:
            print(f"  [ERROR] FFmpeg execution error with {current_encoder['video_codec']}: {e}")
            failed = True

        if not failed:
            print(f"  [SUCCESS] Single-pass render complete: {output_path}")
            break
        else:
            if current_encoder["video_codec"] == "libx264":
                return False
            print(f"\n  [FALLBACK] Hardware encoder {current_encoder['video_codec']} failed. Retrying with CPU encoder libx264...")
            current_encoder = _build_encoder_config("libx264", config)

    # B3: Mark all clips as done in the checkpoint on success
    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint:
        for idx, block in enumerate(image_blocks):
            start_sec = block['sec']
            end_sec = image_blocks[idx+1]['sec'] if idx < len(image_blocks)-1 else config.get("_audio_duration", start_sec + 5.0)
            duration = max(config["MIN_CLIP_DURATION"], end_sec - start_sec)
            checkpoint.mark_clip_done(idx, "youtube_ready_video.mp4", duration)

    return True


def get_sorted_images(images_dir):
    """Sorts images naturally so sentence_2 comes before sentence_10."""
    if not os.path.exists(images_dir): return []
    images = [f for f in os.listdir(images_dir) if f.endswith('.png')]
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
    return sorted(images, key=natural_sort_key)

def main(run_folder: str = None):
    print("=============================================")
    print("Starting SILKY CINEMATIC Video Compilation")
    print("=============================================")

    latest_run = run_folder if run_folder else get_latest_run_folder()
    if not latest_run:
        print("[FATAL ERROR] No run folder detected in 'youtube_runs'.")
        print(f"  - Current working directory: {os.getcwd()}")
        print("  - Please ensure that the 'youtube_runs' folder exists at this location and contains at least one active run subdirectory.")
        sys.exit(1)

    # 1. Load Custom Configs (Animations & Subtitles) from video_config.txt
    config = load_video_config("video_config.txt")
    anim_enabled = config["ENABLE_ANIMATIONS"]
    subs_enabled = config["ENABLE_SUBTITLES"]

    # 2. Detect hardware encoder (QSV → NVENC → CPU)
    encoder_config = detect_hardware_encoder(config)
    print(f"  [ENCODER] Using {encoder_config['encoder_name']} ({encoder_config['hwaccel']})")

    ai_cameras = load_ai_camera_decisions(os.path.join(latest_run, "flow_prompts.json"))
    manual_cameras = load_manual_overrides("manual_animations.txt")

    txt_path = os.path.join(latest_run, "timestamped_transcript.txt")
    srt_path = os.path.join(latest_run, "timestamped_transcript.srt")
    image_blocks = parse_image_timeline(txt_path, srt_path)

    # Sort blocks by timestamp to ensure chronological order
    image_blocks.sort(key=lambda b: b['sec'])

    # Validate monotonic timestamps
    for i in range(1, len(image_blocks)):
        if image_blocks[i]['sec'] <= image_blocks[i-1]['sec']:
            print(f"[WARN] Non-monotonic timestamp at index {i}: {image_blocks[i]['sec']} <= {image_blocks[i-1]['sec']}")

    audio_path = os.path.join(latest_run, "full_episode_voice.wav")
    audio_duration = get_audio_duration(audio_path)
    config["_audio_duration"] = audio_duration  # used by single-pass graph for last clip

    images_dir = os.path.join(latest_run, "generated_images")
    output_file = os.path.join(latest_run, "youtube_ready_video.mp4")

    # 3. Pre-compilation Clip/Asset Validation
    print("Validating image assets...")
    invalid_assets = validate_assets(image_blocks, images_dir)
    if invalid_assets:
        print(f"[FATAL ERROR] Image validation failed. Found {len(invalid_assets)} missing or empty image assets:")
        for idx, name in invalid_assets:
            print(f"  - Clip {idx}: {name}")
        sys.exit(1)
    print(f"  [OK] All {len(image_blocks)} image assets verified on disk.")

    print(f"\nAnimations Enabled: {anim_enabled}")
    print(f"Subtitles Enabled: {subs_enabled}")
    print(f"Single-Pass Mode: {config['ENABLE_SINGLE_PASS']}")
    checkpoint = CheckpointManager(latest_run, config)

    # -------- Single-Pass path (Phase 2 default) --------
    if config["ENABLE_SINGLE_PASS"]:
        ok = run_single_pass(config, encoder_config, image_blocks, images_dir, audio_path, latest_run, checkpoint)
        if ok:
            print("\n[SUCCESS] Master Video Completed!")
            if not config["DEBUG_SAVE_INTERMEDIATES"]:
                temp_clips_dir = os.path.join(latest_run, "temp_clips")
                if os.path.exists(temp_clips_dir):
                    import shutil
                    shutil.rmtree(temp_clips_dir, ignore_errors=True)
        else:
            print("\n[ERROR] Single-pass render failed.")
            sys.exit(1)
        return

    # -------- Legacy per-clip path (checkpoint + config + encoder) --------
    temp_clips_dir = os.path.join(latest_run, "temp_clips")
    os.makedirs(temp_clips_dir, exist_ok=True)
    concat_file_path = os.path.join(latest_run, "concat.txt")

    available_images = get_sorted_images(images_dir)
    last_valid_image = None

    if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint.data is not None:
        print(f"  [RESUME] Checkpoint found: {checkpoint.data['completed_clips']}/"
              f"{checkpoint.data['total_clips']} clips done")
    else:
        checkpoint.initialize(len(image_blocks), encoder_config, audio_path, audio_duration,
                              srt_path if subs_enabled else None)

    print("Pre-processing image timeline (Silky Camera Engine)...")

    valid_clips = 0
    for idx, block in enumerate(image_blocks):
        if config["ENABLE_CHECKPOINT_RESUME"] and checkpoint.is_clip_done(idx):
            print(f"  [SKIP] Clip {idx}: already rendered")
            valid_clips += 1
            continue

        abs_image_path, img_name = _resolve_image_path(
            block, idx, images_dir, available_images, last_valid_image)
        if abs_image_path is None:
            print(f"  [SKIP] Block {idx}: No image found to start the video.")
            continue
        last_valid_image = abs_image_path

        start_sec = block['sec']
        end_sec = image_blocks[idx+1]['sec'] if idx < len(image_blocks)-1 else audio_duration
        duration = max(config["MIN_CLIP_DURATION"], end_sec - start_sec)

        camera_action = "static"
        if anim_enabled:
            camera_action = ai_cameras.get(block['name'], "static")
            if block['name'] in manual_cameras:
                camera_action = manual_cameras[block['name']]

        vf_string = build_ken_burns_filter(config, duration, camera_action, pix_fmt="nv12" if encoder_config["video_codec"] == "h264_qsv" else "yuv420p")

        clip_name = f"clip_{idx:04d}.mp4"
        clip_path = os.path.join(temp_clips_dir, clip_name)

        encoder_args = ["-c:v", encoder_config["video_codec"]]
        encoder_args.extend(encoder_config["encoder_args"])

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loop", "1", "-framerate", str(config["OUTPUT_FPS"]),
            "-i", abs_image_path,
            "-vf", vf_string,
            *encoder_args,
            "-t", str(duration),
            "-pix_fmt", config["OUTPUT_PIX_FMT"], "-movflags", "+faststart",
            clip_path
        ]

        try:
            res = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=config["FFMPEG_CLIP_TIMEOUT"])
        except subprocess.TimeoutExpired:
            print(f"  [ERROR] {img_name}: FFmpeg timeout ({config['FFMPEG_CLIP_TIMEOUT']}s)")
            checkpoint.mark_clip_failed(idx, "timeout")
            continue
        if res.returncode != 0:
            print(f"  [ERROR] {img_name}: {res.stderr.decode('utf-8', errors='ignore')}")
            checkpoint.mark_clip_failed(idx, "ffmpeg_error")
            continue

        if config["ENABLE_CHECKPOINT_RESUME"]:
            checkpoint.mark_clip_done(idx, os.path.join("temp_clips", clip_name), duration)
        print(f"  [OK] {img_name} -> {duration:.2f}s ({camera_action.upper()})")
        valid_clips += 1

    # Build concat.txt from checkpoint (resume-safe) or from valid clips
    if config["ENABLE_CHECKPOINT_RESUME"]:
        entries = checkpoint.get_concat_entries()
    else:
        entries = [f"file '{os.path.abspath(os.path.join(temp_clips_dir, f'clip_{i:04d}.mp4'))}'"
                   for i in range(len(image_blocks))
                   if os.path.exists(os.path.join(temp_clips_dir, f"clip_{i:04d}.mp4"))]
    with open(concat_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(entries) + "\n")

    if not entries:
        print("\n[FATAL ERROR] Zero video clips were processed. FFmpeg compiler aborted to prevent crashes.")
        sys.exit(1)

    # Final Compositing (audio + subs + loudnorm)
    print("\nExecuting Final Burn (Audio + Compositing)...")
    audio_file = audio_path
    output_file = os.path.join(latest_run, "youtube_ready_video.mp4")

    loudnorm_filter = _measure_loudnorm(audio_file, config) if config["ENABLE_LOUDNORM_TWOPASS"] else \
        f"loudnorm=I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:LRA={config['LOUDNORM_LRA']}"

    final_cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file_path, "-i", audio_file
    ]

    if subs_enabled:
        print("  -> Subtitles are ENABLED. Burning Arabic SRT to video track...")
        fixed_srt = os.path.join(latest_run, "timestamped_transcript_fixed.srt")
        fix_arabic_srt(srt_path, fixed_srt)
        sub_style = build_subtitle_style_string(config)
        final_cmd.extend(["-vf", f"subtitles={os.path.basename(fixed_srt)}:force_style='{sub_style}'"])
    else:
        print("  -> Subtitles are DISABLED. Skipping text rendering...")

    final_encoder_args = ["-c:v", encoder_config["video_codec"]]
    final_encoder_args.extend(encoder_config["encoder_args"])

    final_cmd.extend([
        *final_encoder_args,
        "-c:a", config["AUDIO_CODEC"], "-b:a", config["AUDIO_BITRATE"],
        "-af", loudnorm_filter,
        "-map", "0:v", "-map", "1:a", "-shortest",
        output_file
    ])

    try:
        subprocess.run(final_cmd, cwd=latest_run, check=True, timeout=config["FFMPEG_FINAL_TIMEOUT"])
    except subprocess.TimeoutExpired:
        print(f"\n[ERROR] Final encode timeout ({config['FFMPEG_FINAL_TIMEOUT']}s)")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Final encode failed: {e}")
        sys.exit(1)

    if config["ENABLE_CHECKPOINT_RESUME"]:
        checkpoint.cleanup_on_success()
    print("\n[SUCCESS] Master Video Completed!")

if __name__ == "__main__":
    # Pass the first argument to main if called by the pipeline orchestrator
    run_folder_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(run_folder_arg)