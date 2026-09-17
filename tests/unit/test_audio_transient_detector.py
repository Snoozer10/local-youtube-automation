"""Unit tests for AudioTransientDetector with Post-Transient Delay (+33.3ms Lag) (Audit §6.4, Task 3.2)."""

from __future__ import annotations

import io
import math
import struct
import wave
import pytest

from src.youtube_automation.video.ken_burns import AudioTransientDetector


def _generate_synthetic_pcm(
    duration_sec: float = 3.0,
    sample_rate: int = 48000,
    baseline_amp: int = 200,
    burst_start_sec: float | None = None,
    burst_dur_sec: float = 0.05,
    burst_amp: int = 5000,
) -> list[int]:
    """Generates synthetic 16-bit mono PCM samples with optional high-energy burst."""
    total_samples = int(duration_sec * sample_rate)
    samples = [baseline_amp for _ in range(total_samples)]

    if burst_start_sec is not None:
        burst_start = int(burst_start_sec * sample_rate)
        burst_end = min(total_samples, burst_start + int(burst_dur_sec * sample_rate))
        for i in range(burst_start, burst_end):
            samples[i] = burst_amp

    return samples


def _write_pcm_wav(path: str, samples: list[int], sample_rate: int = 48000) -> None:
    """Writes raw 16-bit mono PCM samples to a WAV file."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw_bytes = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(raw_bytes)


def test_transient_detection_on_synthetic_burst():
    """Verifies that AudioTransientDetector accurately isolates high-energy acoustic burst."""
    samples = _generate_synthetic_pcm(
        duration_sec=3.0,
        baseline_amp=200,
        burst_start_sec=1.50,
        burst_dur_sec=0.05,
        burst_amp=6000,
    )
    detector = AudioTransientDetector(samples=samples, sample_rate=48000)

    punch = detector.find_best_scale_punch_frame(
        span_start_sec=0.0,
        span_end_sec=3.0,
        fps=30,
        min_surge_db=4.5,
        edge_clearance_sec=0.6,
        optical_lag_frames=1,
    )

    assert punch is not None
    assert punch["transient_time"] == pytest.approx(1.50, abs=0.02)
    assert punch["surge_db"] >= 4.5


def test_post_transient_lag_compensation():
    """Verifies 1-frame optical lag compensation (+33.3ms delay/lag AFTER audio transient peak)."""
    samples = _generate_synthetic_pcm(
        duration_sec=3.0,
        baseline_amp=200,
        burst_start_sec=1.50,
        burst_dur_sec=0.05,
        burst_amp=6000,
    )
    fps = 30
    lag_frames = 1
    expected_lag_sec = lag_frames / float(fps)  # ~0.0333s

    detector = AudioTransientDetector(samples=samples, sample_rate=48000)
    punch = detector.find_best_scale_punch_frame(
        span_start_sec=0.0,
        span_end_sec=3.0,
        fps=fps,
        optical_lag_frames=lag_frames,
    )

    assert punch is not None
    # Punch cut time must be strictly after the acoustic transient peak
    assert punch["adjusted_punch_time"] > punch["transient_time"]
    assert punch["adjusted_punch_time"] == pytest.approx(
        punch["transient_time"] + expected_lag_sec, abs=1e-4
    )

    # Relative frame should match math.floor((adjusted - start) * fps + 0.5)
    expected_frame = int(math.floor(punch["adjusted_punch_time"] * fps + 0.5))
    assert punch["relative_frame"] == expected_frame


def test_edge_clearance_suppresses_boundary_punches():
    """Verifies that transient bursts within the 0.6s boundary clearance are suppressed."""
    # Burst at 0.3s (within 0.6s entrance clearance)
    samples_near_start = _generate_synthetic_pcm(
        duration_sec=3.0,
        baseline_amp=200,
        burst_start_sec=0.30,
        burst_amp=6000,
    )
    detector1 = AudioTransientDetector(samples=samples_near_start, sample_rate=48000)
    punch1 = detector1.find_best_scale_punch_frame(
        span_start_sec=0.0, span_end_sec=3.0, edge_clearance_sec=0.6
    )
    assert punch1 is None

    # Burst at 2.7s (within 0.6s exit clearance for 3.0s span)
    samples_near_end = _generate_synthetic_pcm(
        duration_sec=3.0,
        baseline_amp=200,
        burst_start_sec=2.70,
        burst_amp=6000,
    )
    detector2 = AudioTransientDetector(samples=samples_near_end, sample_rate=48000)
    punch2 = detector2.find_best_scale_punch_frame(
        span_start_sec=0.0, span_end_sec=3.0, edge_clearance_sec=0.6
    )
    assert punch2 is None


def test_short_span_suppression():
    """Verifies that clips under 1.3s (2 * edge_clearance + 0.1) return None to avoid visual cramping."""
    samples = _generate_synthetic_pcm(
        duration_sec=1.1,
        baseline_amp=200,
        burst_start_sec=0.55,
        burst_amp=6000,
    )
    detector = AudioTransientDetector(samples=samples, sample_rate=48000)
    punch = detector.find_best_scale_punch_frame(
        span_start_sec=0.0, span_end_sec=1.1, edge_clearance_sec=0.6
    )
    assert punch is None


def test_threshold_rejection_on_flat_audio():
    """Verifies that uniform volume audio with no transients >= 4.5 dB returns None."""
    flat_samples = _generate_synthetic_pcm(
        duration_sec=3.0,
        baseline_amp=1500,
        burst_start_sec=None,
    )
    detector = AudioTransientDetector(samples=flat_samples, sample_rate=48000)
    punch = detector.find_best_scale_punch_frame(span_start_sec=0.0, span_end_sec=3.0)
    assert punch is None


def test_breath_noise_floor_rejection():
    """Verifies that low-level noise surges below min_db_floor=40.0 (RMS < 100) are rejected."""
    # Rise from RMS=1 to RMS=6 is +15.5 dB flux, but signal is inaudible breath/room hiss
    samples = [1] * 48000 * 3
    for i in range(48000, 48000 + 4800):  # 1.0s to 1.1s
        samples[i] = 6

    detector = AudioTransientDetector(samples=samples, sample_rate=48000)
    punch = detector.find_best_scale_punch_frame(
        span_start_sec=0.0,
        span_end_sec=3.0,
        min_surge_db=4.5,
        min_db_floor=40.0,
    )
    assert punch is None


def test_wav_file_ingestion_and_transient_detection(tmp_path):
    """Verifies that AudioTransientDetector loads 16-bit PCM WAV from disk and detects transients accurately."""
    wav_path = str(tmp_path / "voice_clip.wav")
    samples = _generate_synthetic_pcm(
        duration_sec=3.0,
        baseline_amp=300,
        burst_start_sec=1.60,
        burst_dur_sec=0.04,
        burst_amp=7000,
    )
    _write_pcm_wav(wav_path, samples, sample_rate=48000)

    detector = AudioTransientDetector(wav_path=wav_path)
    assert detector.sample_rate == 48000
    assert detector.total_duration == pytest.approx(3.0, abs=1e-4)
    assert len(detector.timestamps) > 0

    punch = detector.find_best_scale_punch_frame(
        span_start_sec=0.0,
        span_end_sec=3.0,
        fps=30,
        edge_clearance_sec=0.6,
        optical_lag_frames=1,
    )
    assert punch is not None
    assert punch["transient_time"] == pytest.approx(1.60, abs=0.02)
    assert punch["adjusted_punch_time"] == pytest.approx(1.60 + 1 / 30.0, abs=0.02)
    assert punch["relative_frame"] > 0
