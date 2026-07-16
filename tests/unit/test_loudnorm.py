import os
import tempfile

import compile_video


def _config():
    c = compile_video.load_video_config()
    return c


def _fake_stderr():
    # ffmpeg prints a JSON summary line (print_format=json) on stderr
    return (
        "[Parsed_loudnorm_0 @ 0x...] \n"
        '{"input_i": "-14.5", "input_tp": "-1.2", "input_lra": "7.8", '
        '"input_thresh": "-25.3", "target_offset": "0.5"}\n'
        "Something else after\n"
    )


def test_extract_parses_measured_values():
    c = _config()
    measured = compile_video._extract_loudnorm_measured(_fake_stderr(), c, tempfile.mkdtemp())
    assert measured["LOUDNORM_MEASURED_I"] == -14.5
    assert measured["LOUDNORM_MEASURED_TP"] == -1.2
    assert measured["LOUDNORM_MEASURED_LRA"] == 7.8
    assert measured["LOUDNORM_MEASURED_THRESH"] == -25.3
    assert measured["LOUDNORM_OFFSET"] == 0.5


def test_extract_persists_local_config():
    d = tempfile.mkdtemp()
    c = _config()
    compile_video._extract_loudnorm_measured(_fake_stderr(), c, d)
    local = os.path.join(d, "video_config.local.txt")
    assert os.path.exists(local)
    with open(local, encoding="utf-8") as f:
        content = f.read()
    assert "LOUDNORM_MEASURED_I=-14.5" in content
    assert "LOUDNORM_MEASURED_TP=-1.2" in content
    assert "LOUDNORM_MEASURED_LRA=7.8" in content
    assert "LOUDNORM_MEASURED_THRESH=-25.3" in content
    assert "LOUDNORM_OFFSET=0.5" in content


def test_extract_updates_config_in_place():
    c = _config()
    compile_video._extract_loudnorm_measured(_fake_stderr(), c, tempfile.mkdtemp())
    assert c["LOUDNORM_MEASURED_I"] == -14.5
    assert c["LOUDNORM_OFFSET"] == 0.5


def test_extract_returns_empty_when_no_json():
    d = tempfile.mkdtemp()
    c = _config()
    measured = compile_video._extract_loudnorm_measured("no json here\njust text", c, d)
    assert measured == {}
    # no local config written when nothing measured
    assert not os.path.exists(os.path.join(d, "video_config.local.txt"))
