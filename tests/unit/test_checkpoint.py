import os
import json
import tempfile
import pytest
from datetime import datetime

import compile_video


@pytest.fixture
def temp_run_folder():
    d = tempfile.mkdtemp()
    yield d
    # cleanup
    cp = os.path.join(d, "compile_checkpoint.json")
    if os.path.exists(cp):
        os.remove(cp)
    if os.path.exists(cp + ".tmp"):
        os.remove(cp + ".tmp")


@pytest.fixture
def config():
    return compile_video.load_video_config()


def test_checkpoint_initialize(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "h264_qsv", "encoder_args": ["-preset", "fast"]}
    cm.initialize(5, enc, "full_episode_voice.wav", 120.5, "subs.srt")
    assert cm.data["total_clips"] == 5
    assert cm.data["completed_clips"] == 0
    assert cm.data["encoder"] == "h264_qsv"
    assert len(cm.data["clip_states"]) == 5
    assert cm.data["audio_duration"] == 120.5
    assert os.path.exists(cm.checkpoint_path)


def test_checkpoint_save_atomic(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "libx264", "encoder_args": []}
    cm.initialize(3, enc, "a.wav", 10.0)
    # no .tmp leftover after save
    assert not os.path.exists(cm.checkpoint_path + ".tmp")


def test_checkpoint_resume_loads_existing(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "h264_qsv", "encoder_args": []}
    cm.initialize(4, enc, "a.wav", 10.0)
    clip0 = os.path.join(temp_run_folder, "temp_clips", "clip_0000.mp4")
    os.makedirs(os.path.dirname(clip0), exist_ok=True)
    open(clip0, "w").close()
    cm.mark_clip_done(0, "temp_clips/clip_0000.mp4", 5.0)
    # new manager loads existing
    cm2 = compile_video.CheckpointManager(temp_run_folder, config)
    assert cm2.data["completed_clips"] == 1
    assert cm2.is_clip_done(0)


def test_checkpoint_is_clip_done_missing_file(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "libx264", "encoder_args": []}
    cm.initialize(2, enc, "a.wav", 10.0)
    cm.data["clip_states"]["0"] = {"status": "done", "path": "temp_clips/missing.mp4"}
    cm.save()
    assert cm.is_clip_done(0) is False  # file doesn't exist


def test_checkpoint_pending_indices(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "libx264", "encoder_args": []}
    cm.initialize(3, enc, "a.wav", 10.0)
    clip1 = os.path.join(temp_run_folder, "temp_clips", "clip_0001.mp4")
    os.makedirs(os.path.dirname(clip1), exist_ok=True)
    open(clip1, "w").close()
    cm.mark_clip_done(1, "temp_clips/clip_0001.mp4", 4.0)
    pending = cm.get_pending_indices()
    assert pending == [0, 2]


def test_checkpoint_concat_entries(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "libx264", "encoder_args": []}
    cm.initialize(3, enc, "a.wav", 10.0)
    cm.mark_clip_done(0, "temp_clips/clip_0000.mp4", 4.0)
    cm.mark_clip_done(2, "temp_clips/clip_0002.mp4", 4.0)
    entries = cm.get_concat_entries()
    assert "file 'temp_clips/clip_0000.mp4'" in entries
    assert "file 'temp_clips/clip_0002.mp4'" in entries
    assert "clip_0001" not in "".join(entries)


def test_checkpoint_mark_failed(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "libx264", "encoder_args": []}
    cm.initialize(2, enc, "a.wav", 10.0)
    cm.mark_clip_failed(0, "ffmpeg died")
    assert cm.data["clip_states"]["0"]["status"] == "failed"
    assert 0 in cm.data["failed_clips"]


def test_checkpoint_cleanup_on_success(temp_run_folder, config):
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    enc = {"video_codec": "libx264", "encoder_args": []}
    cm.initialize(1, enc, "a.wav", 10.0)
    assert os.path.exists(cm.checkpoint_path)
    cm.cleanup_on_success()
    assert not os.path.exists(cm.checkpoint_path)


def test_checkpoint_corrupt_file_returns_none(temp_run_folder, config):
    cp = os.path.join(temp_run_folder, "compile_checkpoint.json")
    with open(cp, "w") as f:
        f.write("{ not valid json")
    cm = compile_video.CheckpointManager(temp_run_folder, config)
    assert cm.data is None
