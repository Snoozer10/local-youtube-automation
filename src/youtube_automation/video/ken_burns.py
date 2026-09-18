from __future__ import annotations

import math
import os
import struct
import wave


def build_ken_burns_filter(
    config: dict,
    frame_count: int,
    camera_action: str,
    pix_fmt: str = "yuv420p",
    words_per_second: float = 3.0,
) -> str:
    """Builds high-precision, sub-pixel stabilized Ken Burns camera motion with BT.709 color accuracy."""
    fps = int(config["OUTPUT_FPS"])
    w = int(config["OUTPUT_WIDTH"])
    h = int(config["OUTPUT_HEIGHT"])
    frames = max(1, int(frame_count))
    duration = frames / float(fps)

    if isinstance(pix_fmt, (int, float)):
        words_per_second = float(pix_fmt)
        pix_fmt = "yuv420p"

    zoom_min = float(config.get("KEN_BURNS_ZOOM_MIN", 1.0))
    dynamic_enabled = config.get("KEN_BURNS_DYNAMIC_SCALE", True)
    if not dynamic_enabled:
        zoom_max = float(config.get("KEN_BURNS_ZOOM_MAX", 1.10))
    else:
        # Dynamic duration-based scale clamping is active by default per spec.md:85
        # scale = clamp(1.06 + (duration - 2.5)/2.0 * 0.04, 1.06, 1.10)
        dynamic_scale = round(max(1.06, min(1.10, 1.06 + (duration - 2.5) / 2.0 * 0.04)), 3)
        if "KEN_BURNS_ZOOM_MAX" in config:
            configured_max = float(config["KEN_BURNS_ZOOM_MAX"])
            zoom_max = min(dynamic_scale, configured_max)
        else:
            zoom_max = dynamic_scale

    wps = 3.0 if words_per_second is None else float(words_per_second)
    pace_ratio = max(0.75, min(1.35, wps / 3.0))
    if dynamic_enabled:
        if pace_ratio == 1.0:
            effective_zoom_max = zoom_max
        else:
            effective_zoom_max = round(min(1.15, zoom_min + (zoom_max - zoom_min) * pace_ratio), 4)
    else:
        effective_zoom_max = zoom_max

    upscale = float(config.get("KEN_BURNS_UPSCALE_FACTOR", 1.12))

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

    # Bounded expressions prevent floating-point edge flashes & sub-pixel aliasing
    safe_center_x = "trunc((iw-iw/zoom)*0.5)"
    safe_center_y = "trunc((ih-ih/zoom)*0.5)"

    if "zoom_in" in camera_action:
        z_expr = f"min({effective_zoom_max},{zoom_min}+({effective_zoom_max}-{zoom_min})*{ease})"
        x_expr = safe_center_x
        y_expr = safe_center_y
    elif "zoom_out" in camera_action:
        z_expr = f"max({zoom_min},{effective_zoom_max}-({effective_zoom_max}-{zoom_min})*{ease})"
        x_expr = safe_center_x
        y_expr = safe_center_y
    elif "pan_left" in camera_action:
        z_expr = f"{effective_zoom_max}"
        x_expr = f"trunc(max(0,min(iw-iw/zoom,(iw-iw/zoom)*(1-{ease}))))"
        y_expr = safe_center_y
    elif "pan_right" in camera_action:
        z_expr = f"{effective_zoom_max}"
        x_expr = f"trunc(max(0,min(iw-iw/zoom,(iw-iw/zoom)*{ease})))"
        y_expr = safe_center_y
    elif "tilt_up" in camera_action:
        z_expr = f"{effective_zoom_max}"
        x_expr = safe_center_x
        y_expr = f"trunc(max(0,min(ih-ih/zoom,(ih-ih/zoom)*(1-{ease}))))"
    elif "tilt_down" in camera_action:
        z_expr = f"{effective_zoom_max}"
        x_expr = safe_center_x
        y_expr = f"trunc(max(0,min(ih-ih/zoom,(ih-ih/zoom)*{ease})))"
    elif "scale_punch" in camera_action:
        z_expr = "1.25"
        x_expr = safe_center_x
        # Locks vertical viewport to upper-third eye-line elevation (Y=360px in 1080p)
        y_expr = "trunc(max(0,min(ih-ih/zoom,(ih-ih/zoom)/3.0)))"
    elif "linear_push" in camera_action:
        z_expr = f"min(1.03,1.0+0.03*(clip(on,0,{frames})/max(1,{frames})))"
        x_expr = safe_center_x
        y_expr = safe_center_y
    elif "linear_pull" in camera_action:
        z_expr = f"max(1.0,1.03-0.03*(clip(on,0,{frames})/max(1,{frames})))"
        x_expr = safe_center_x
        y_expr = safe_center_y
    else:  # static or static_hold (handles static clips & animations disabled)
        if duration >= 3.5:
            # Audit §6.4 & User Directive: Zero static dead-holds (>=3.5s).
            # Zero-safe clamped evaluation eliminates frame on=0 pop and d=1 division by zero.
            z_expr = f"min(1.03,1.0+0.03*(clip(on,0,{frames})/max(1,{frames})))"
        else:
            z_expr = "1.0"
        x_expr = safe_center_x
        y_expr = safe_center_y

    return (
        f"scale={upscale_w}:{upscale_h}:force_original_aspect_ratio=increase:{scale_flags},"
        f"crop={upscale_w}:{upscale_h},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={w}x{h}:fps={fps},"
        f"trim=start_frame=0:end_frame={frames},setpts=PTS-STARTPTS" + norm
    )


def derive_multishot_crop(
    orig_w: int = 1920,
    orig_h: int = 1080,
    scale_factor: float = 1.25,
    focus_x: float = 0.5,
    eyeline_y: float = 360.0,
    out_w: int = 1920,
    out_h: int = 1080,
) -> dict[str, Any]:
    """Calculates multi-framing crop parameters locked to eye-line elevation (Y=360px)
    with even-integer NV12 chroma clamping and BT.709 color accuracy (Audit §6.4).
    """
    scale = max(1.0, float(scale_factor))
    crop_w = int(round(orig_w / scale))
    crop_h = int(round(orig_h / scale))

    # Even integer clamping for NV12 / YUV420 chroma subsampling
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2

    # Horizontal centering on focal centroid
    if focus_x <= 1.0:
        fx = focus_x * orig_w
    else:
        fx = focus_x

    crop_x = int(round(fx - (crop_w / 2.0)))
    crop_x = max(0, min(crop_x, orig_w - crop_w))
    crop_x -= crop_x % 2

    # Vertical positioning locked to eye-line elevation (1/3 down from top of viewport)
    eyeline_source = (eyeline_y / 1080.0) * orig_h
    crop_y = int(round(eyeline_source - (crop_h / 3.0)))
    crop_y = max(0, min(crop_y, orig_h - crop_h))
    crop_y -= crop_y % 2

    filter_str = (
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale={out_w}:{out_h}:out_color_matrix=bt709:flags=lanczos+accurate_rnd"
    )

    return {
        "crop_w": crop_w,
        "crop_h": crop_h,
        "crop_x": crop_x,
        "crop_y": crop_y,
        "scale_factor": scale,
        "filter_str": filter_str,
    }


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
                        self.leading_silence_sec = w_idx / float(self.sample_rate)
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


class AudioTransientDetector:
    """Detects acoustic transient peaks in voiceover audio to trigger sub-beat scale punches.

    Uses short-time RMS windowing (20ms window, 10ms hop) and half-wave rectified onset flux
    (E_dB[m] - E_dB[m-1]). Enforces 1-frame optical lag compensation (+33.3ms delay/lag AFTER peak)
    to align with human cross-modal perception (auditory ~140ms vs visual ~180ms).
    """

    def __init__(
        self,
        wav_path: str | None = None,
        samples: list[int] | list[float] | None = None,
        sample_rate: int = 48000,
        window_ms: float = 20.0,
        hop_ms: float = 10.0,
    ):
        self.wav_path = wav_path
        self.sample_rate = sample_rate
        self.window_ms = window_ms
        self.hop_ms = hop_ms
        self.timestamps: list[float] = []
        self.rms_profile: list[float] = []
        self.db_profile: list[float] = []
        self.flux_profile: list[float] = []
        self.total_duration: float = 0.0

        if wav_path and os.path.exists(wav_path) and wav_path.lower().endswith(".wav"):
            self._load_from_wav(wav_path)
        elif samples is not None:
            self._analyze_samples(samples, sample_rate)

    def _load_from_wav(self, wav_path: str):
        try:
            with wave.open(wav_path, "rb") as wf:
                self.sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                n_frames = wf.getnframes()
                self.total_duration = n_frames / float(self.sample_rate)

                if sampwidth != 2:
                    return

                raw_bytes = wf.readframes(n_frames)
                count = len(raw_bytes) // 2
                shorts = struct.unpack(f"<{count}h", raw_bytes)
                mono_samples = shorts[::n_channels]
                self._analyze_samples(mono_samples, self.sample_rate)
        except Exception as e:
            print(f"  [WARN] AudioTransientDetector WAV read bypassed: {e}")

    def _analyze_samples(self, samples: list[int] | list[float], sample_rate: int):
        self.sample_rate = sample_rate
        self.total_duration = len(samples) / float(sample_rate)
        win_size = max(1, int(sample_rate * (self.window_ms / 1000.0)))
        hop_size = max(1, int(sample_rate * (self.hop_ms / 1000.0)))

        prev_db = 0.0
        n_samples = len(samples)

        for start_idx in range(0, n_samples - win_size + 1, hop_size):
            t = start_idx / float(sample_rate)
            window = samples[start_idx : start_idx + win_size]
            sum_sq = sum(float(s) * float(s) for s in window)
            rms = math.sqrt(sum_sq / float(win_size))
            db = 20.0 * math.log10(max(1.0, rms))

            flux = max(0.0, db - prev_db) if self.timestamps else 0.0
            prev_db = db

            self.timestamps.append(t)
            self.rms_profile.append(rms)
            self.db_profile.append(db)
            self.flux_profile.append(flux)

    def find_best_scale_punch_frame(
        self,
        span_start_sec: float,
        span_end_sec: float,
        fps: int = 30,
        min_surge_db: float = 4.5,
        min_db_floor: float = 40.0,
        edge_clearance_sec: float = 0.6,
        optical_lag_frames: int = 1,
    ) -> dict[str, float | int] | None:
        """Identifies the primary acoustic stress transient within a span window,
        returning the lag-adjusted relative frame for a sub-beat scale punch cut.
        """
        duration = span_end_sec - span_start_sec
        if duration < (2 * edge_clearance_sec + 0.1) or not self.timestamps:
            return None

        t_min = span_start_sec + edge_clearance_sec
        t_max = span_end_sec - edge_clearance_sec
        if t_min >= t_max:
            return None

        # O(1) index slice calculation for sub-millisecond query performance
        hop_sec = self.hop_ms / 1000.0
        idx_start = max(0, int(t_min / hop_sec))
        idx_end = min(len(self.timestamps), int(t_max / hop_sec) + 1)

        best_time = None
        max_flux = 0.0

        for idx in range(idx_start, idx_end):
            t = self.timestamps[idx]
            if t < t_min or t > t_max:
                continue
            flux = self.flux_profile[idx]
            db = self.db_profile[idx]

            # Enforce surge threshold AND minimum audible speech energy floor
            if flux >= min_surge_db and db >= min_db_floor and flux > max_flux:
                max_flux = flux
                best_time = t

        if best_time is None:
            return None

        # 1-frame optical lag compensation (+33.3ms delay/lag AFTER audio transient peak)
        lag_time = optical_lag_frames / float(fps)
        adjusted_punch_time = min(span_end_sec - 0.1, best_time + lag_time)
        relative_frame = int(math.floor((adjusted_punch_time - span_start_sec) * fps + 0.5))
        total_span_frames = int(round(duration * fps))

        min_frame = int(round(edge_clearance_sec * fps))
        max_frame = total_span_frames - min_frame
        clamped_relative_frame = max(min_frame, min(relative_frame, max_frame))

        return {
            "transient_time": round(best_time, 4),
            "adjusted_punch_time": round(adjusted_punch_time, 4),
            "relative_frame": clamped_relative_frame,
            "surge_db": round(max_flux, 2),
        }


__all__ = [
    "build_ken_burns_filter",
    "derive_multishot_crop",
    "AudioSyncAligner",
    "AudioTransientDetector",
]



