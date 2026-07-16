# Compile Video Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Externalize all magic numbers to config, auto-detect hardware encoder (QSV→NVENC→CPU), replace multi-pass clip→concat→final pipeline with single-pass filter graph, add checkpoint/resume for clip rendering.

**Architecture:** Single-pass filter graph eliminates 2-3 generation loss. Encoder detection probes ffmpeg capabilities at runtime. Checkpoint JSON tracks per-clip render state for resume. All tunables externalized to `video_config.txt`.

**Tech Stack:** Python 3.10+, FFmpeg (QSV/NVENC/libx264), Windows i7-5600U + Intel HD 5500 (QSV) + NVIDIA 840M (NVENC Maxwell) + 16GB RAM

## Global Constraints

- Python 3.10+, Windows only, FFmpeg must be on PATH (WinGet paths auto-appended)
- Hardware: Intel QSV (h264_qsv/hevc_qsv), NVIDIA NVENC (h264_nvenc/hevc_nvenc), CPU fallback (libx264/libx265)
- Config file: `video_config.txt` at project root, `key=value` format (like `gemini_model.txt`)
- Checkpoint file: `youtube_runs/<Title>/compile_checkpoint.json` (auto-resume, auto-cleanup on success)
- Pipeline integration: `run_agency.py` Phase 9 calls `compile_video.py` via subprocess; checkpoint survives pipeline restart
- No external Python deps beyond stdlib + ffmpeg/ffprobe
- Arabic text handling: `encoding='utf-8'` everywhere, `ensure_ascii=False` for JSON

---

## File Structure (Modified/Created)

| File | Action | Responsibility |
|------|--------|----------------|
| `video_config.txt` | **CREATE** | Master config schema — all tunables externalized |
| `compile_video.py` | **MODIFY** | Core pipeline: config loader, encoder probe, single-pass graph, checkpoint manager |
| `run_agency.py` | **MODIFY** | Phase 9 integration: pass run folder explicitly, handle checkpoint resume |
| `compile_checkpoint.json` | **CREATE (runtime)** | Per-run render state: clip index, status, timestamps, encoder used |

---

## Task Breakdown

### Task 1: Design `video_config.txt` Schema (Complete Spec)

**Files:**
- Create: `video_config.txt` (project root)

**Interfaces:**
- Consumes: None (new file)
- Produces: Config dict consumed by `compile_video.py:load_video_config()`

**Schema (copy-paste this entire block into `video_config.txt`):**

```text
# ============================================================
# VIDEO COMPILATION CONFIG — Phase 2
# All tunables externalized. Edit in-place, no code changes.
# ============================================================

# --- Feature Toggles ---
ENABLE_ANIMATIONS=true
ENABLE_SUBTITLES=true
ENABLE_HARDWARE_ENCODER=true          # false = force CPU libx264
ENABLE_SINGLE_PASS=true               # false = legacy per-clip→concat→final
ENABLE_CHECKPOINT_RESUME=true         # false = full re-render every run
ENABLE_LOUDNORM_TWOPASS=true          # false = single-pass loudnorm (faster, less accurate)
ENABLE_VBV=true                       # VBV buffer for streaming compliance

# --- Output Spec ---
OUTPUT_WIDTH=1920
OUTPUT_HEIGHT=1080
OUTPUT_FPS=24
OUTPUT_PIX_FMT=yuv420p
OUTPUT_PROFILE=high
OUTPUT_LEVEL=4.1

# --- Encoding Quality (CPU fallback) ---
CPU_CRF=18
CPU_PRESET=fast
CPU_TUNE=film

# --- Hardware Encoder Preferences (probe order) ---
# Probed in order: qsv, nvenc, cpu. First available wins.
# Override by setting ENCODER_FORCE=h264_qsv|h264_nvenc|libx264
ENCODER_FORCE=                        # empty = auto-detect

# QSV (Intel QuickSync) - requires Intel HD 5500+ on Windows
QSV_PRESET=fast
QSV_GLOBAL_QUALITY=22                 # ICQ 1-51 (lower=better), ~CRF equivalent
QSV_LOOKAHEAD=1
QSV_LOOKAHEAD_DEPTH=40

# NVENC (NVIDIA) - requires Kepler+ (840M = Maxwell = supported)
NVENC_PRESET=p4                       # p1-p7 (p4=balanced), llhq/llhp for low-latency
NVENC_CQ=22                           # Constant Quality 1-51 (lower=better)
NVENC_RC=vbr                          # cbr|vbr|constqp
NVENC_MULTIPASS=fullres               # disabled|quarter|fullres
NVENC_SPATIAL_AQ=1
NVENC_TEMPORAL_AQ=1

# --- Ken Burns / Camera Motion ---
KEN_BURNS_ZOOM_MIN=1.0
KEN_BURNS_ZOOM_MAX=1.15
KEN_BURNS_EASING=parabolic            # linear|parabolic|ease_in|ease_out|ease_in_out
KEN_BURNS_UPSCALE_FACTOR=2.0          # 2.0 = 4K→1080p native zoom canvas (no upscale blur)
KEN_BURNS_INTERP_ALGO=lanczos         # lanczos|bicubic|bilinear|neighbor
KEN_BURNS_PAN_SPEED=0.08              # 0.0-1.0 fraction of canvas per clip
KEN_BURNS_ZOOM_SPEED=0.12             # zoom range per clip

# --- Segment/Clip Timing ---
MIN_CLIP_DURATION=0.5                 # minimum seconds per clip
DEFAULT_CLIP_DURATION=5.0             # fallback when timestamp gap unknown
MAX_CLIP_DURATION=30.0                # safety cap

# --- Audio / Loudnorm (EBU R128) ---
AUDIO_CODEC=aac
AUDIO_BITRATE=192k
AUDIO_SAMPLE_RATE=48000
LOUDNORM_I=-16                        # Integrated loudness target (LUFS)
LOUDNORM_TP=-1.5                      # True peak ceiling (dBTP)
LOUDNORM_LRA=11                       # Loudness range target (LU)
LOUDNORM_MEASURED_I=-99               # Measured values for pass 2 (-99 = auto-measure pass 1)
LOUDNORM_MEASURED_TP=-99
LOUDNORM_MEASURED_LRA=-99
LOUDNORM_MEASURED_THRESH=-99
LOUDNORM_OFFSET=0                     # Offset correction (dB)
LOUDNORM_LINEAR=true                  # Linear normalization mode
LOUDNORM_PRINT_FORMAT=json            # json|summary

# --- VBV (Video Buffering Verifier) for Streaming Compliance ---
VBV_MAXRATE=10000k                    # Max bitrate (10M for YouTube 1080p)
VBV_BUFSIZE=20000k                    # Buffer size (2x maxrate)

# --- FFmpeg Execution ---
FFMPEG_THREADS=0                      # 0 = auto (logical cores)
FFMPEG_CLIP_TIMEOUT=300               # Seconds per clip render
FFMPEG_FINAL_TIMEOUT=600              # Seconds for final compositing
FFMPEG_LOGLEVEL=warning               # quiet|panic|fatal|error|warning|info|verbose|debug|trace

# --- Checkpoint / Resume ---
CHECKPOINT_FILE=compile_checkpoint.json
CHECKPOINT_SAVE_INTERVAL=5            # Save checkpoint every N clips

# --- Subtitle Styling (used when ENABLE_SUBTITLES=true) ---
SUB_FONT_NAME=Tahoma
SUB_FONT_SIZE=22
SUB_PRIMARY_COLOR=&H00FFFFFF
SUB_OUTLINE_COLOR=&H00000000
SUB_BORDER_STYLE=1
SUB_OUTLINE=2.5
SUB_SHADOW=1
SUB_ALIGNMENT=2
SUB_MARGIN_V=50
SUB_BOLD=1

# --- Advanced / Debug ---
DEBUG_SAVE_INTERMEDIATES=false        # Keep temp_clips/ after success
DEBUG_DRY_RUN=false                   # Print ffmpeg commands without executing
DEBUG_FILTER_GRAPH_DUMP=false         # Write filter graph to .dot for GraphViz
```

---

### Task 2: Config Loader Module

**Files:**
- Modify: `compile_video.py` (add `load_video_config()` function at top)

**Interfaces:**
- Consumes: `video_config.txt` (from Task 1)
- Produces: `config: dict` with typed values (bool, int, float, str)

```python
def load_video_config(config_path="video_config.txt") -> dict:
    """
    Parse video_config.txt into typed dict.
    Supports: bool (true/false), int, float, str.
    Comments (# ...) and blank lines ignored.
    Missing keys -> sensible defaults (defined in DEFAULTS dict below).
    """
    DEFAULTS = {
        "ENABLE_ANIMATIONS": True,
        "ENABLE_SUBTITLES": True,
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
        "FFMPEG_FINAL_TIMEOUT": 600,
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

    # Parse logic: read file, split key=value, cast using DEFAULTS[key] type
    # Return merged dict (file overrides defaults)
```

**Steps:**
- [ ] Write failing test: `test_load_video_config()` with sample config string
- [ ] Run test → verify FAIL
- [ ] Implement `load_video_config()` in `compile_video.py`
- [ ] Run test → verify PASS
- [ ] Commit: `feat: add video_config.txt schema and typed config loader`

---

### Task 3: Hardware Encoder Detection (Probe Chain)

**Files:**
- Modify: `compile_video.py` (add `detect_hardware_encoder()` function)

**Interfaces:**
- Consumes: `config["ENCODER_FORCE"]`, `config["ENABLE_HARDWARE_ENCODER"]`, ffmpeg binary
- Produces: `encoder_config: dict` with keys: `video_codec`, `encoder_args`, `encoder_name`, `hwaccel`

**Detection Logic (exact probe order):**

```python
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


def _probe_encoder(encoder_name: str) -> bool:
    """Run `ffmpeg -hide_banner -encoders | grep <name>` to check availability."""
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
```

**Steps:**
- [ ] Write failing test: mock `subprocess.run` to return encoder list, verify detection order
- [ ] Run test → verify FAIL
- [ ] Implement `_probe_encoder`, `_build_encoder_config`, `detect_hardware_encoder`
- [ ] Run test → verify PASS (QSV→NVENC→CPU fallback chain)
- [ ] Commit: `feat: hardware encoder auto-detect with QSV/NVENC/CPU fallback`

---

### Task 4: Checkpoint Manager (Resume Clip Rendering)

**Files:**
- Modify: `compile_video.py` (add `CheckpointManager` class)

**Interfaces:**
- Consumes: `run_folder/checkpoint_file`, `config["CHECKPOINT_SAVE_INTERVAL"]`
- Produces: `checkpoint_data: dict` with per-clip state

**Checkpoint Schema (`compile_checkpoint.json`):**

```json
{
  "version": 2,
  "run_folder": "youtube_runs/My Video Title",
  "encoder": "h264_qsv",
  "encoder_args": ["-preset", "fast", ...],
  "total_clips": 116,
  "completed_clips": 42,
  "failed_clips": [],
  "clip_states": {
    "0": {"status": "done", "path": "temp_clips/clip_0000.mp4", "duration": 5.2, "timestamp": "2025-07-11T10:30:00Z"},
    "1": {"status": "done", "path": "temp_clips/clip_0001.mp4", "duration": 4.8, "timestamp": "2025-07-11T10:30:05Z"},
    "42": {"status": "pending", "path": "temp_clips/clip_0042.mp4", "duration": 6.1}
  },
  "concat_file": "concat.txt",
  "audio_path": "full_episode_voice.wav",
  "audio_duration": 720.5,
  "subtitle_path": "timestamped_transcript_fixed.srt",
  "created_at": "2025-07-11T10:25:00Z",
  "updated_at": "2025-07-11T10:45:00Z"
}
```

**CheckpointManager Class:**

```python
class CheckpointManager:
    def __init__(self, run_folder: str, config: dict):
        self.run_folder = run_folder
        self.config = config
        self.checkpoint_path = os.path.join(run_folder, config["CHECKPOINT_FILE"])
        self.data = self._load()

    def _load(self) -> dict:
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

    def initialize(self, total_clips: int, encoder_config: dict, audio_path: str, audio_duration: float, subtitle_path: str = None):
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
        return state.get("status") == "done" and os.path.exists(os.path.join(self.run_folder, state.get("path", "")))

    def mark_clip_done(self, clip_idx: int, clip_path: str, duration: float):
        self.data["clip_states"][str(clip_idx)] = {
            "status": "done",
            "path": clip_path,
            "duration": duration,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self.data["completed_clips"] += 1
        if self.data["completed_clips"] % self.config["CHECKPOINT_SAVE_INTERVAL"] == 0:
            self.save()

    def mark_clip_failed(self, clip_idx: int, error: str):
        self.data["clip_states"][str(clip_idx)] = {
            "status": "failed",
            "error": error,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self.data["failed_clips"].append(clip_idx)
        self.save()

    def get_pending_indices(self) -> list[int]:
        return [i for i in range(self.data["total_clips"]) if not self.is_clip_done(i)]

    def get_concat_entries(self) -> list[str]:
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
```

**Steps:**
- [ ] Write failing test: `CheckpointManager` save/load/resume cycle with temp dir
- [ ] Run test → verify FAIL
- [ ] Implement `CheckpointManager` class in `compile_video.py`
- [ ] Run test → verify PASS (atomic writes, resume logic, concat generation)
- [ ] Commit: `feat: checkpoint/resume for clip rendering with atomic JSON`

---

### Task 5: Ken Burns Filter Graph Builder (Single-Pass Ready)

**Files:**
- Modify: `compile_video.py` (add `build_ken_burns_filter()` function)

**Interfaces:**
- Consumes: `config` (Ken Burns section), `clip_idx`, `duration`, `camera_action`, `image_path`
- Produces: `filter_complex: str` for single clip (used in both per-clip and single-pass modes)

**Design:**
- Native resolution upscale: `scale=W*H:W*H` where factor = `KEN_BURNS_UPSCALE_FACTOR` (2.0 → 3840x2160)
- Parabolic easing: `z='zoom_min + (zoom_max - zoom_min) * 4 * (t/d) * (1 - t/d)'` for zoom_in
- Pan easing: `x='(iw-iw/zoom) * (1 - 4*(t/d)*(1-t/d))'` for smooth accel/decel
- Lanczos interpolation: `interp_algo=lanczos` in zoompan
- All expressions use `on` (frame number) and `d` (total frames) — frame-accurate

```python
def build_ken_burns_filter(config: dict, clip_idx: int, duration: float, camera_action: str, image_path: str) -> str:
    """
    Build zoompan filter string for a single clip.
    Returns filter_complex fragment (no 'scale=' prefix — caller wraps).
    """
    fps = config["OUTPUT_FPS"]
    frames = int(duration * fps)
    zoom_min = config["KEN_BURNS_ZOOM_MIN"]
    zoom_max = config["KEN_BURNS_ZOOM_MAX"]
    upscale = config["KEN_BURNS_UPSCALE_FACTOR"]
    interp = config["KEN_BURNS_INTERP_ALGO"]
    pan_speed = config["KEN_BURNS_PAN_SPEED"]
    zoom_speed = config["KEN_BURNS_ZOOM_SPEED"]

    w = int(config["OUTPUT_WIDTH"] * upscale)
    h = int(config["OUTPUT_HEIGHT"] * upscale)

    # Base upscale (done once per clip in single-pass; per-image in legacy)
    base_scale = f"scale={w}:{h}:flags={interp}"

    if camera_action == "zoom_in":
        # Parabolic ease-in-out: 4 * t * (1-t) peaks at 0.5
        zoom_expr = f"z='{zoom_min}+({zoom_max}-{zoom_min})*4*(on/{frames})*(1-on/{frames})'"
        x_expr = f"x='iw/2-(iw/zoom/2)'"
        y_expr = f"y='ih/2-(ih/zoom/2)'"

    elif camera_action == "zoom_out":
        zoom_expr = f"z='{zoom_max}-({zoom_max}-{zoom_min})*4*(on/{frames})*(1-on/{frames})'"
        x_expr = f"x='iw/2-(iw/zoom/2)'"
        y_expr = f"y='ih/2-(ih/zoom/2)'"

    elif camera_action == "pan_left":
        zoom_expr = f"z='{zoom_min + (zoom_max - zoom_min) * pan_speed}'"
        # Parabolic pan: start right, end left, slow at edges
        x_expr = f"x='(iw-iw/zoom)*(1-4*(on/{frames})*(1-on/{frames}))'"
        y_expr = f"y='ih/2-(ih/zoom/2)'"

    elif camera_action == "pan_right":
        zoom_expr = f"z='{zoom_min + (zoom_max - zoom_min) * pan_speed}'"
        x_expr = f"x='(iw-iw/zoom)*4*(on/{frames})*(1-on/{frames})'"
        y_expr = f"y='ih/2-(ih/zoom/2)'"

    else:  # static
        return f"{base_scale},scale={config['OUTPUT_WIDTH']}:{config['OUTPUT_HEIGHT']}:force_original_aspect_ratio=decrease,pad={config['OUTPUT_WIDTH']}:{config['OUTPUT_HEIGHT']}:-1:-1:color=black"

    zoompan = f"zoompan={zoom_expr}:{x_expr}:{y_expr}:d={frames}:s={config['OUTPUT_WIDTH']}x{config['OUTPUT_HEIGHT']}:fps={fps}:interp_algo={interp}"
    return f"{base_scale},{zoompan}"
```

**Steps:**
- [ ] Write failing test: verify filter string parses by ffmpeg `-filter_complex` dry-run
- [ ] Run test → verify FAIL
- [ ] Implement `build_ken_burns_filter()` in `compile_video.py`
- [ ] Run test → verify PASS (ffmpeg accepts filter graph)
- [ ] Commit: `feat: Ken Burns filter graph builder with parabolic easing + lanczos`

---

### Task 6: Single-Pass Filter Graph (Concat + Audio + Subs + Loudnorm in One FFmpeg)

**Files:**
- Modify: `compile_video.py` (replace `main()` final compositing with `run_single_pass()`)

**Interfaces:**
- Consumes: `config`, `encoder_config`, `checkpoint`, `image_blocks`, `audio_path`, `subtitle_path`
- Produces: `youtube_ready_video.mp4` in run folder

**Architecture Comparison:**

| Stage | Legacy (3-pass) | Phase 2 Single-Pass |
|-------|-----------------|---------------------|
| 1 | Per-clip encode (libx264 CRF 18) | **Filter graph: concat + Ken Burns per segment** |
| 2 | Concat demuxer (lossless copy) | — Eliminated — |
| 3 | Final encode (audio + subs + loudnorm) | **Same pass: audio mix + subtitle burn + loudnorm** |

**Single-Pass Filter Graph Structure:**

```
[0:v]scale=3840:2160,zoompan=...[v0];
[1:v]scale=3840:2160,zoompan=...[v1];
...
[N:v]scale=3840:2160,zoompan=...[vN];
[v0][v1]...[vN]concat=n=N:v=1:a=0[vconcat];
[vconcat]scale=1920:1080[vscaled];
[vscaled]subtitles=...[vsub];          # conditional
[vsub]loudnorm=...[vout];              # video done
[audio]aloudnorm=...[aout];            # audio done
[vout][aout]concat=v=1:a=1[final]
```

**Implementation (build_filter_graph function):**

```python
def build_single_pass_filter_graph(config: dict, encoder_config: dict, checkpoint: CheckpointManager,
                                   image_blocks: list, image_dir: str, audio_path: str, subtitle_path: str) -> tuple[list, str]:
    """
    Returns: (ffmpeg_input_args, filter_complex_string)
    Inputs are ordered: [image0, image1, ..., imageN, audio, subtitle?]
    """
    fps = config["OUTPUT_FPS"]
    w = config["OUTPUT_WIDTH"]
    h = config["OUTPUT_HEIGHT"]
    upscale = config["KEN_BURNS_UPSCALE_FACTOR"]
    upscale_w = int(w * upscale)
    upscale_h = int(h * upscale)
    interp = config["KEN_BURNS_INTERP_ALGO"]
    n_clips = len(image_blocks)

    # Build input args: -loop 1 -framerate 24 -i img0.png -loop 1 -framerate 24 -i img1.png ... -i audio.wav [-i sub.srt]
    input_args = []
    filter_parts = []
    concat_inputs = []

    for idx, block in enumerate(image_blocks):
        img_name = f"{block['name']}.png"
        img_path = os.path.join(image_dir, img_name)
        # Fallback logic same as legacy (checkpoint-aware)
        if not os.path.exists(img_path):
            # Find from checkpoint or available_images...
            pass

        input_args.extend(["-loop", "1", "-framerate", str(fps), "-i", img_path])

        # Per-clip Ken Burns filter
        start_sec = block['sec']
        end_sec = image_blocks[idx+1]['sec'] if idx < n_clips-1 else checkpoint.data["audio_duration"]
        duration = max(config["MIN_CLIP_DURATION"], end_sec - start_sec)
        camera_action = "static"
        if config["ENABLE_ANIMATIONS"]:
            camera_action = checkpoint.data["clip_states"].get(str(idx), {}).get("camera", "static")
            # Or derive from ai_cameras/manual_cameras maps

        kb_filter = build_ken_burns_filter(config, idx, duration, camera_action, img_path)
        # kb_filter already includes base upscale + zoompan
        filter_parts.append(f"[{idx}:v]{kb_filter}[v{idx}];")
        concat_inputs.append(f"[v{idx}]")

    # Audio input
    audio_input_idx = n_clips
    input_args.extend(["-i", audio_path])

    # Subtitle input (optional)
    subtitle_input_idx = None
    if config["ENABLE_SUBTITLES"] and subtitle_path and os.path.exists(subtitle_path):
        subtitle_input_idx = n_clips + 1
        input_args.extend(["-i", subtitle_path])

    # Concat video streams
    filter_parts.append(f"{''.join(concat_inputs)}concat=n={n_clips}:v=1:a=0[vconcat];")

    # Downscale to output resolution
    filter_parts.append(f"[vconcat]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:-1:-1:color=black[vscaled];")

    # Subtitles (if enabled)
    video_label = "vscaled"
    if config["ENABLE_SUBTITLES"] and subtitle_input_idx is not None:
        sub_style = build_subtitle_style_string(config)
        filter_parts.append(f"[vscaled]subtitles='{os.path.basename(subtitle_path)}':force_style='{sub_style}'[vsub];")
        video_label = "vsub"

    # Video loudnorm (EBU R128) — two-pass via measured values in config
    if config["ENABLE_LOUDNORM_TWOPASS"]:
        # Pass 1 measures, pass 2 applies — but we do single-pass with pre-measured values
        # Config holds LOUDNORM_MEASURED_* from previous run or defaults
        ln_args = (
            f"I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:LRA={config['LOUDNORM_LRA']}:"
            f"measured_I={config['LOUDNORM_MEASURED_I']}:measured_TP={config['LOUDNORM_MEASURED_TP']}:"
            f"measured_LRA={config['LOUDNORM_MEASURED_LRA']}:measured_thresh={config['LOUDNORM_MEASURED_THRESH']}:"
            f"offset={config['LOUDNORM_OFFSET']}:linear={str(config['LOUDNORM_LINEAR']).lower()}:"
            f"print_format={config['LOUDNORM_PRINT_FORMAT']}"
        )
        filter_parts.append(f"[{video_label}]loudnorm={ln_args}[vout];")
    else:
        filter_parts.append(f"[{video_label}]copy[vout];")

    # Audio loudnorm (separate filter)
    aln_args = (
        f"I={config['LOUDNORM_I']}:TP={config['LOUDNORM_TP']}:LRA={config['LOUDNORM_LRA']}:"
        f"measured_I={config['LOUDNORM_MEASURED_I']}:measured_TP={config['LOUDNORM_MEASURED_TP']}:"
        f"measured_LRA={config['LOUDNORM_MEASURED_LRA']}:measured_thresh={config['LOUDNORM_MEASURED_THRESH']}:"
        f"offset={config['LOUDNORM_OFFSET']}:linear={str(config['LOUDNORM_LINEAR']).lower()}:"
        f"print_format={config['LOUDNORM_PRINT_FORMAT']}"
    )
    filter_parts.append(f"[{audio_input_idx}:a]loudnorm={aln_args}[aout];")

    # Final concat video+audio
    filter_parts.append("[vout][aout]concat=v=1:a=1[final]")

    filter_complex = "".join(filter_parts)
    return input_args, filter_complex
```

**Single-Pass Execution:**

```python
def run_single_pass(config: dict, encoder_config: dict, checkpoint: CheckpointManager,
                    image_blocks: list, image_dir: str, audio_path: str, run_folder: str):
    if config["DEBUG_DRY_RUN"]:
        print("[DRY RUN] Would execute single-pass FFmpeg")
        return True

    subtitle_path = os.path.join(run_folder, "timestamped_transcript_fixed.srt")
    if config["ENABLE_SUBTITLES"] and os.path.exists(subtitle_path):
        fix_arabic_srt(subtitle_path, subtitle_path)  # Ensure UTF-8 BOM
    else:
        subtitle_path = None

    input_args, filter_complex = build_single_pass_filter_graph(
        config, encoder_config, checkpoint, image_blocks, image_dir, audio_path, subtitle_path
    )

    output_path = os.path.join(run_folder, "youtube_ready_video.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", config["FFMPEG_LOGLEVEL"],
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-c:v", encoder_config["video_codec"],
        *encoder_config["encoder_args"],
        "-c:a", config["AUDIO_CODEC"],
        "-b:a", config["AUDIO_BITRATE"],
        "-ar", str(config["AUDIO_SAMPLE_RATE"]),
        "-shortest",
        output_path
    ]

    if config["DEBUG_FILTER_GRAPH_DUMP"]:
        with open(os.path.join(run_folder, "filter_graph.dot"), "w") as f:
            f.write("digraph G {\n" + filter_complex.replace(";", ";\n") + "\n}")

    print(f"\n[Single-Pass] Executing FFmpeg ({len(image_blocks)} clips + audio + subs)...")
    try:
        res = subprocess.run(cmd, cwd=run_folder, timeout=config["FFMPEG_FINAL_TIMEOUT"],
                             capture_output=True, text=True, encoding='utf-8', errors='ignore')
    except subprocess.TimeoutExpired:
        print(f"  [ERROR] FFmpeg timeout ({config['FFMPEG_FINAL_TIMEOUT']}s)")
        return False

    if res.returncode != 0:
        print(f"  [ERROR] FFmpeg failed:\n{res.stderr}")
        # Try to extract loudnorm measured values for next pass
        _extract_loudnorm_measured(res.stderr, config, run_folder)
        return False

    print(f"  [SUCCESS] Single-pass render complete: {output_path}")
    return True
```

**Steps:**
- [ ] Write failing test: build filter graph for 3 clips, verify ffmpeg `-filter_complex` syntax check passes
- [ ] Run test → verify FAIL
- [ ] Implement `build_single_pass_filter_graph()`, `run_single_pass()`, `build_subtitle_style_string()`, `_extract_loudnorm_measured()`
- [ ] Run test → verify PASS (single-pass produces valid MP4)
- [ ] Commit: `feat: single-pass filter graph (concat+KenBurns+subs+loudnorm in one ffmpeg)`

---

### Task 7: Legacy Per-Clip Mode (Fallback When Single-Pass Disabled)

**Files:**
- Modify: `compile_video.py` (keep existing per-clip logic, refactor to use config + encoder + checkpoint)

**Interfaces:**
- Consumes: `config`, `encoder_config`, `checkpoint`, `image_blocks`, `ai_cameras`, `manual_cameras`
- Produces: `temp_clips/clip_XXXX.mp4` + `concat.txt`

**Refactor Notes:**
- Replace hardcoded CRF/preset with `encoder_config["encoder_args"]`
- Use `checkpoint.is_clip_done()` to skip rendered clips
- Use `build_ken_burns_filter()` for consistency
- Timeout from `config["FFMPEG_CLIP_TIMEOUT"]`
- Save checkpoint after each clip (interval from config)

**Steps:**
- [ ] Refactor per-clip loop to use `encoder_config`, `build_ken_burns_filter()`, `CheckpointManager`
- [ ] Test: run with `ENABLE_SINGLE_PASS=false`, verify 116 clips render with resume
- [ ] Commit: `refactor: legacy per-clip mode uses config/encoder/checkpoint`

---

### Task 8: Pipeline Integration (`run_agency.py` Phase 9)

**Files:**
- Modify: `run_agency.py` (Phase 9 section)

**Changes:**
1. Pass run folder explicitly to `compile_video.py` (instead of auto-detecting latest)
2. Handle checkpoint resume: if `compile_checkpoint.json` exists, `compile_video.py` auto-resumes
3. Telegram notification on compile start/complete/fail
4. Clean up `temp_clips/` only on full success (or keep if `DEBUG_SAVE_INTERMEDIATES=true`)

```python
# In run_agency.py Phase 9:
print(f"\n⏳ [RUNNING] Phase 9: Video Compilation (compile_video.py)...")
try:
    # Pass run folder explicitly so compile_video.py doesn't guess
    result = subprocess.run(
        [sys.executable, "compile_video.py", folder],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=3600
    )
    state["video"] = True
    save_pipeline_state(folder, state)
    clean_browser_tabs()
    send_telegram_notification(f"✅ [Render Complete]\nVideo: {video_title}\nReady for upload!")
except subprocess.CalledProcessError as e:
    print(f"\n❌ [ERROR] Failed at compile_video.py:\n{e.stdout}\n{e.stderr}")
    send_telegram_notification(f"⚠️ [Alert]\nVideo: {video_title}\nFailed at: compile_video.py\n{e.stderr[:500]}")
    continue
```

**Modify `compile_video.py` `main()` to accept CLI arg:**

```python
def main(run_folder: str = None):
    if run_folder is None:
        run_folder = get_latest_run_folder()
    if not run_folder:
        sys.exit(1)
    # ... rest of pipeline uses run_folder ...
```

**Steps:**
- [ ] Modify `compile_video.py main()` to accept optional `run_folder` argument
- [ ] Modify `run_agency.py` Phase 9 to pass folder explicitly
- [ ] Test: run full pipeline, verify compile resumes from checkpoint on interruption
- [ ] Commit: `feat: pipeline integration — explicit run folder + checkpoint resume`

---

### Task 9: Loudnorm Two-Pass Measurement Persistence

**Files:**
- Modify: `compile_video.py` (add loudnorm measurement extraction + config update)

**Logic:**
1. First single-pass run (or per-clip final pass) with `measured_I=-99` → ffmpeg outputs measured values in stderr
2. Parse stderr for `Input Integrated:`, `Input True Peak:`, `Input LRA:`, `Input Threshold:`
3. Write measured values back to `video_config.txt` (or run-local config) for Pass 2
4. Pass 2 uses measured values → accurate EBU R128 compliance

```python
def _extract_loudnorm_measured(stderr: str, config: dict, run_folder: str):
    """Parse ffmpeg loudnorm output and update config for second pass."""
    import re
    patterns = {
        "LOUDNORM_MEASURED_I": r"Input Integrated:\s+([-\d.]+)",
        "LOUDNORM_MEASURED_TP": r"Input True Peak:\s+([-\d.]+)",
        "LOUDNORM_MEASURED_LRA": r"Input LRA:\s+([-\d.]+)",
        "LOUDNORM_MEASURED_THRESH": r"Input Threshold:\s+([-\d.]+)",
    }
    measured = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, stderr)
        if match:
            measured[key] = float(match.group(1))

    if measured:
        # Update in-memory config for immediate re-run
        config.update(measured)
        # Persist to run-local config for pipeline resume
        local_config = os.path.join(run_folder, "video_config.local.txt")
        with open(local_config, 'w') as f:
            for k, v in config.items():
                f.write(f"{k}={v}\n")
        print(f"  [LOUDNORM] Measured values captured: {measured}")
```

**Steps:**
- [ ] Implement `_extract_loudnorm_measured()` 
- [ ] Test: run single-pass twice, verify second pass uses measured values
- [ ] Commit: `feat: loudnorm two-pass measurement persistence`

---

### Task 10: End-to-End Test & Validation

**Files:**
- Test: Create test run folder with 5-10 sample images + audio + SRT
- Run: `python compile_video.py` with `ENABLE_SINGLE_PASS=true`, `ENABLE_CHECKPOINT_RESUME=true`

**Validation Checklist:**
- [ ] `video_config.txt` loads all keys with correct types
- [ ] Encoder detection: QSV → NVENC → CPU (log which wins)
- [ ] Single-pass: 1 ffmpeg invocation produces `youtube_ready_video.mp4`
- [ ] Output: 1920x1080, 24fps, yuv420p, high profile, level 4.1
- [ ] Audio: AAC 192k, 48kHz, loudnorm -16 LUFS integrated
- [ ] VBV: maxrate 10M, bufsize 20M (verify with `ffprobe -show_streams`)
- [ ] Subtitles: burned if enabled, correct Arabic rendering
- [ ] Ken Burns: smooth parabolic easing, no jitter, lanczos quality
- [ ] Checkpoint: interrupt at clip 50, resume completes from 51
- [ ] Cleanup: `compile_checkpoint.json` deleted on success
- [ ] Pipeline: `run_agency.py` Phase 9 calls compile with explicit folder

**Performance Targets (i7-5600U + HD 5500 + 840M):**
- Single-pass 12-min video (116 clips): < 8 minutes wall time
- Peak RAM: < 4 GB (filter graph frames buffered)
- QSV encode: ~2x realtime; NVENC: ~3x realtime; CPU: ~0.5x realtime

---

## Execution Handoff

**Plan complete and saved to:** `docs/superpowers/plans/2025-07-11-compile-video-phase2.md`

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
   - **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development

2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints
   - **REQUIRED SUB-SKILL:** Use superpowers:executing-plans

**Which approach?**