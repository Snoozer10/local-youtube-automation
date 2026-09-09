from __future__ import annotations

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
    else:  # static (handles static clips & animations disabled)
        z_expr = "1.0"
        x_expr = safe_center_x
        y_expr = safe_center_y

    return (
        f"scale={upscale_w}:{upscale_h}:force_original_aspect_ratio=increase:{scale_flags},"
        f"crop={upscale_w}:{upscale_h},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={w}x{h}:fps={fps},"
        f"trim=start_frame=0:end_frame={frames},setpts=PTS-STARTPTS" + norm
    )


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


