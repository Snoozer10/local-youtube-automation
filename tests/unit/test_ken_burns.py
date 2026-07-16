import os
import tempfile
import subprocess
import pytest

import compile_video


@pytest.fixture
def config():
    return compile_video.load_video_config()


@pytest.fixture
def test_image():
    """Generate a small solid-color PNG via ffmpeg for filter dry-runs."""
    d = tempfile.mkdtemp()
    img = os.path.join(d, "test.png")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=200x200", "-frames:v", "1", img
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if r.returncode != 0 or not os.path.exists(img):
        pytest.skip("ffmpeg unavailable for image generation test")
    yield img
    if os.path.exists(img):
        os.remove(img)
    os.rmdir(d)


def test_build_filter_static(config):
    vf = compile_video.build_ken_burns_filter(config, 5.0, "static")
    assert "scale=1920:1080" in vf
    assert "pad=1920:1080" in vf
    assert "zoompan" not in vf


def test_build_filter_zoom_in(config):
    vf = compile_video.build_ken_burns_filter(config, 5.0, "zoom_in")
    assert "zoompan" in vf
    assert "flags=lanczos" in vf  # lanczos interpolation via scale filter
    assert "3840:2160" in vf  # upscale_w x upscale_h (2.0 factor)
    assert "z='" in vf


def test_build_filter_zoom_out(config):
    vf = compile_video.build_ken_burns_filter(config, 5.0, "zoom_out")
    assert "zoompan" in vf
    assert "z='" in vf


def test_build_filter_pan_left(config):
    vf = compile_video.build_ken_burns_filter(config, 5.0, "pan_left")
    assert "zoompan" in vf
    assert "pan_zoom" not in vf  # pan_zoom is computed, not literal
    assert "x='(iw-iw/zoom)*(1-4*" in vf


def test_build_filter_pan_right(config):
    vf = compile_video.build_ken_burns_filter(config, 5.0, "pan_right")
    assert "zoompan" in vf
    assert "x='(iw-iw/zoom)*4*" in vf


def test_build_filter_ffmpeg_accepts_all_actions(config, test_image):
    for action in ["static", "zoom_in", "zoom_out", "pan_left", "pan_right"]:
        vf = compile_video.build_ken_burns_filter(config, 1.0, action)
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", test_image,
            "-vf", vf, "-t", "0.5", "-f", "null", "-"
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        assert r.returncode == 0, f"ffmpeg rejected filter for {action}: {r.stderr}"


def test_build_filter_normalizes_sar_and_pixfmt(config):
    # concat requires every clip to share SAR + pixel format; each branch must
    # end with setsar=1,format=yuv420p regardless of source image aspect ratio.
    for action in ["static", "zoom_in", "zoom_out", "pan_left", "pan_right"]:
        vf = compile_video.build_ken_burns_filter(config, 5.0, action)
        assert vf.endswith(",setsar=1,format=yuv420p"), f"action {action} missing normalization: {vf}"
        assert "setsar=1" in vf and "format=yuv420p" in vf


def test_build_filter_normalized_clips_concat_ok(config, test_image):
    # Two clips from images with different aspect ratios must concat without a
    # "SAR do not match" error (regression test for the concat failure).
    import shutil
    d = tempfile.mkdtemp()
    wide = os.path.join(d, "wide.png")
    tall = os.path.join(d, "tall.png")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=red:s=320x180", "-frames:v", "1", wide],
                   capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=green:s=180x320", "-frames:v", "1", tall],
                   capture_output=True)
    g = (f"[0:v]{compile_video.build_ken_burns_filter(config, 1.0, 'static')}[v0];"
         f"[1:v]{compile_video.build_ken_burns_filter(config, 1.0, 'static')}[v1];"
         f"[v0][v1]concat=n=2:v=1:a=0[vout]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-loop", "1", "-i", wide, "-loop", "1", "-i", tall,
           "-filter_complex", g, "-map", "[vout]", "-t", "0.5", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    shutil.rmtree(d, ignore_errors=True)
    assert r.returncode == 0, f"concat failed: {r.stderr[-400:]}"
