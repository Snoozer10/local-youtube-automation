import os
import tempfile
import subprocess
import pytest

import compile_video


def _make_test_image(path):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", "color=c=blue:s=200x200", "-frames:v", "1",
           "-update", "1", path]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return r.returncode == 0 and os.path.exists(path)


@pytest.fixture
def mini_run():
    d = tempfile.mkdtemp()
    for n in ["00_00.png", "00_08.png"]:
        _make_test_image(os.path.join(d, n))
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _blocks():
    return [{"name": "00_00", "sec": 0.0}, {"name": "00_08", "sec": 2.0}]


def test_build_graph_returns_triple(mini_run, config):
    c = config.copy()
    c["_audio_duration"] = 4.0
    enc = compile_video.detect_hardware_encoder(c)
    ia, fc, vl = compile_video.build_single_pass_filter_graph(
        c, enc, _blocks(), mini_run, os.path.join(mini_run, "a.wav"),
        None, {}, {}, True)
    assert isinstance(ia, list) and isinstance(fc, str)
    assert vl == "vformat"


def test_build_graph_structure(mini_run, config):
    c = config.copy()
    c["_audio_duration"] = 4.0
    enc = compile_video.detect_hardware_encoder(c)
    ia, fc, vl = compile_video.build_single_pass_filter_graph(
        c, enc, _blocks(), mini_run, os.path.join(mini_run, "a.wav"),
        None, {}, {}, True)
    assert "concat=n=2:v=1:a=0" in fc
    assert "[aout]" in fc
    assert "loudnorm" in fc
    assert "[final]" not in fc  # final concat removed; map directly
    # 2 image inputs + 1 audio input
    assert ia.count("-i") == 3


def test_build_graph_with_subtitles(mini_run, config):
    c = config.copy()
    c["ENABLE_SUBTITLES"] = True
    c["_audio_duration"] = 4.0
    enc = compile_video.detect_hardware_encoder(c)
    srt = os.path.join(mini_run, "sub.srt")
    with open(srt, "w", encoding="utf-8") as f:
        f.write("1\n00:00:00,000 --> 00:00:01,000\nمرحبا\n")
    ia, fc, vl = compile_video.build_single_pass_filter_graph(
        c, enc, _blocks(), mini_run, os.path.join(mini_run, "a.wav"),
        srt, {}, {}, True)
    assert vl == "vformat"
    assert "subtitles=" in fc
