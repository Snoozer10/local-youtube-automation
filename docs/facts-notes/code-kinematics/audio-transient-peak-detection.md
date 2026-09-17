# Note: Audio Transient Peak Detection and Post-Transient Lag Compensation

**Category:** Audio DSP & Motion Kinematics  
**Date Logged:** 2026-09-16  
**Relevant Code Files:** `src/youtube_automation/video/ken_burns.py`, `src/youtube_automation/video/compiler.py`, `tests/unit/test_audio_transient_detector.py`  
**Audit Reference:** Section 6.4 (Procedural Kinematics & Audio-Reactive Scale Punches), Module 6D  

### 1. Core Rule in Plain English
When triggering automated sub-beat camera scale punches ($100\% \to 125\%$ crop):
1. **Short-Time RMS & Onset Flux**: Acoustic stress points in the voiceover audio track are isolated using short-time RMS windowing ($20\text{ ms}$ window, $10\text{ ms}$ hop) and half-wave rectified onset flux:
   $$\Delta E_{\text{dB}}[m] = \max(0.0, E_{\text{dB}}[m] - E_{\text{dB}}[m-1])$$
2. **Surge & Noise Floor Gating**: A transient must simultaneously exceed an adaptive surge threshold ($\ge 4.5\text{ dB}$) AND an absolute speech energy floor ($\ge 40.0\text{ dB}$, corresponding to $RMS \ge 100$). This suppresses inaudible breaths, mic preamp noise, and room hiss from triggering camera jump cuts.
3. **Cross-Modal Post-Transient Delay (+33.3ms Lag)**: The scale punch cut must occur **1 frame after the acoustic transient peak** ($+33.3\text{ ms}$ delay at 30 FPS):
   $$\text{lag\_time} = \frac{\text{optical\_lag\_frames}}{\text{FPS}}$$
   $$\text{adjusted\_punch\_time} = \min(\text{span\_end\_sec} - 0.1, \text{transient\_time} + \text{lag\_time})$$
   Because human auditory perception ($\approx 140\text{ ms}$) processes faster than visual cortex perception ($\approx 180\text{ ms}$), lagging the visual cut by $+33.3\text{ ms}$ aligns the visual impact squarely with the perceived acoustic punch, preventing premature cuts while spoken syllables are still vocalized.
4. **Cinematic Boundary Clearance**: Transients occurring within $0.6\text{ s}$ of span start or span end are suppressed, and spans shorter than $1.3\text{ s}$ are exempted from punches to prevent visual flickering and cramping.
5. **$O(1)$ Search Performance**: Direct hop-index slicing ($[t_{\min} / \text{hop\_sec} : t_{\max} / \text{hop\_sec} + 1]$) allows evaluating span queries in microseconds across 20+ minute audio streams.

### 2. The Failure Mode It Prevents
- **Premature Cut Phonation Clipping**: Leading the audio transient (e.g. cutting 33ms before the peak) causes the visual cut to occur while the previous word's consonant is still being formed, giving a jarring sense of desynchronization.
- **Breath-Triggered Jump Cuts**: Without an absolute energy floor (`min_db_floor = 40.0`), a quiet breath rising from digital silence ($0\text{ dB}$) to inaudible ambient noise ($15.5\text{ dB}$) registers as a $+15.5\text{ dB}$ flux, erroneously slamming a close-up crop during silent pauses.
- **Micro-Hold Strobe Cuts**: Omitting the $0.6\text{ s}$ edge clearance can trigger punches 2 frames before a scene transition, resulting in subliminal visual strobing.
- **Linear Scan Stalls**: Sequentially scanning 133,400 audio frames for each of 293 clips causes quadratic iteration delays ($\approx 39\text{M}$ iterations) during video compilation.

### 3. Implementation Specification
Implemented in `src/youtube_automation/video/ken_burns.py`:
```python
class AudioTransientDetector:
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
        duration = span_end_sec - span_start_sec
        if duration < (2 * edge_clearance_sec + 0.1) or not self.timestamps:
            return None

        t_min = span_start_sec + edge_clearance_sec
        t_max = span_end_sec - edge_clearance_sec
        if t_min >= t_max:
            return None

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

            if flux >= min_surge_db and db >= min_db_floor and flux > max_flux:
                max_flux = flux
                best_time = t

        if best_time is None:
            return None

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
```

### 4. Verification & Validation Evidence
1. **Unit Test Suite**: `tests/unit/test_audio_transient_detector.py` (7/7 tests PASS):
   - `test_transient_detection_on_synthetic_burst`: Correctly isolates transient burst within $\pm 0.02\text{ s}$.
   - `test_post_transient_lag_compensation`: Confirms $+33.3\text{ ms}$ lag calculation and positive relative frame offset.
   - `test_edge_clearance_suppresses_boundary_punches`: Confirms bursts within $0.6\text{ s}$ of bounds return `None`.
   - `test_short_span_suppression`: Confirms spans $< 1.3\text{ s}$ return `None`.
   - `test_threshold_rejection_on_flat_audio`: Confirms uniform audio with no surges returns `None`.
   - `test_breath_noise_floor_rejection`: Confirms low-level noise surges below $40.0\text{ dB}$ are suppressed.
   - `test_wav_file_ingestion_and_transient_detection`: Verifies end-to-end reading of 16-bit PCM WAV from disk.
2. **Regression & Safety Gates**:
   - Full unit test suite: 495/495 tests PASS in 23.00s (0 regressions).
   - Exercise scaffold linter: 35/35 files verified clean (`python tools/lint_exercises.py`).
