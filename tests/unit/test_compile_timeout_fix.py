"""Regression tests for compile-video-output duration-aware timeout."""

import pytest

import compile_video


def test_effective_timeout_scales_for_large_1440p_cpu():
    cfg = {"FFMPEG_CLIP_TIMEOUT": 300, "OUTPUT_HEIGHT": 1440}
    enc = {"video_codec": "libx264"}
    # 100 s chunk at 1440p CPU: 100*4+90=490 >300 -> 490
    assert compile_video._effective_clip_timeout(cfg, enc, 100) == 490
    # 60 s chunk: 60*4+90=330 >300 ->330
    assert compile_video._effective_clip_timeout(cfg, enc, 60) == 330
    # small chunk 10 s: 130 <300 floor ->300
    assert compile_video._effective_clip_timeout(cfg, enc, 10) == 300


def test_effective_timeout_respects_base_600():
    cfg = {"FFMPEG_CLIP_TIMEOUT": 600, "OUTPUT_HEIGHT": 1440}
    enc = {"video_codec": "libx264"}
    # 100 s scaled 490 <600 base -> 600
    assert compile_video._effective_clip_timeout(cfg, enc, 100) == 600
    # 150 s scaled 690 >600 -> 690
    assert compile_video._effective_clip_timeout(cfg, enc, 150) == 690


def test_effective_timeout_hw_factor():
    cfg = {"FFMPEG_CLIP_TIMEOUT": 300, "OUTPUT_HEIGHT": 1440}
    enc = {"video_codec": "h264_qsv"}
    # qsv factor 1.8: 100*1.8+90=270 <300 floor ->300
    assert compile_video._effective_clip_timeout(cfg, enc, 100) == 300
    cfg2 = {"FFMPEG_CLIP_TIMEOUT": 300, "OUTPUT_HEIGHT": 1080}
    enc2 = {"video_codec": "libx264"}
    # 1080p factor 3.0: 100*3+90=390
    assert compile_video._effective_clip_timeout(cfg2, enc2, 100) == 390


def test_effective_timeout_bypass_for_tiny_base():
    cfg = {"FFMPEG_CLIP_TIMEOUT": 1, "OUTPUT_HEIGHT": 1440}
    enc = {"video_codec": "libx264"}
    assert compile_video._effective_clip_timeout(cfg, enc, 100) == 1
    cfg2 = {"FFMPEG_CLIP_TIMEOUT": 59, "OUTPUT_HEIGHT": 1440}
    assert compile_video._effective_clip_timeout(cfg2, enc, 100) == 59


def test_resolve_workers_capped_on_low_cores(monkeypatch):
    enc = {"video_codec": "libx264"}
    monkeypatch.setattr(compile_video.os, "cpu_count", lambda: 2)
    assert compile_video._resolve_chunk_workers(enc, 6) == 1
    monkeypatch.setattr(compile_video.os, "cpu_count", lambda: 4)
    assert compile_video._resolve_chunk_workers(enc, 6) == 1
    monkeypatch.setattr(compile_video.os, "cpu_count", lambda: 6)
    assert compile_video._resolve_chunk_workers(enc, 6) == 2
    # qsv not capped
    monkeypatch.setattr(compile_video.os, "cpu_count", lambda: 2)
    assert compile_video._resolve_chunk_workers({"video_codec": "h264_qsv"}, 6) == 2
    # single chunk stays 1
    assert compile_video._resolve_chunk_workers(enc, 1) == 1


def test_default_config_timeout_is_600():
    cfg = compile_video.load_video_config()
    assert cfg["FFMPEG_CLIP_TIMEOUT"] == 600
