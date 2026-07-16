import tempfile
import os
from compile_video import load_video_config

def test_load_video_config_defaults():
    """Missing keys get defaults."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("# comment\nENABLE_ANIMATIONS=false\n")
        f.flush()
        config = load_video_config(f.name)
    assert config["ENABLE_ANIMATIONS"] is False
    assert config["ENABLE_SUBTITLES"] is True  # default
    assert config["OUTPUT_WIDTH"] == 1920
    os.unlink(f.name)

def test_load_video_config_type_casting():
    """Values cast to correct types."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("OUTPUT_FPS=30\nKEN_BURNS_PAN_SPEED=0.1\nCPU_CRF=20\n")
        f.flush()
        config = load_video_config(f.name)
    assert config["OUTPUT_FPS"] == 30
    assert isinstance(config["OUTPUT_FPS"], int)
    assert config["KEN_BURNS_PAN_SPEED"] == 0.1
    assert isinstance(config["KEN_BURNS_PAN_SPEED"], float)
    assert config["CPU_CRF"] == 20
    os.unlink(f.name)

def test_load_video_config_bool_parsing():
    """Boolean values parsed case-insensitively."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("ENABLE_ANIMATIONS=TRUE\nENABLE_SUBTITLES=FALSE\nENABLE_VBV=TrUe\n")
        f.flush()
        config = load_video_config(f.name)
    assert config["ENABLE_ANIMATIONS"] is True
    assert config["ENABLE_SUBTITLES"] is False
    assert config["ENABLE_VBV"] is True
    os.unlink(f.name)

def test_load_video_config_string_values():
    """String values preserved including special chars."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write('ENCODER_FORCE=h264_qsv\nVBV_MAXRATE=10000k\nSUB_FONT_NAME=Tahoma\n')
        f.flush()
        config = load_video_config(f.name)
    assert config["ENCODER_FORCE"] == "h264_qsv"
    assert config["VBV_MAXRATE"] == "10000k"
    assert config["SUB_FONT_NAME"] == "Tahoma"
    os.unlink(f.name)