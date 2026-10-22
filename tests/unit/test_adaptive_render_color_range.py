"""Adaptive render outputs must carry converted limited-range video."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from youtube_automation.production import render


@pytest.mark.parametrize(
    ("pixel_format", "color_range"),
    [
        ("yuvj420p", "pc"),
        ("yuv420p", "unknown"),
        ("yuv420p", "pc"),
        ("yuv422p", "tv"),
    ],
)
def test_probe_rejects_noncanonical_pixel_format_or_range(
    monkeypatch: pytest.MonkeyPatch, pixel_format: str, color_range: str
) -> None:
    video = {
        "codec_type": "video",
        "nb_read_frames": "1",
        "avg_frame_rate": "30/1",
        "pix_fmt": pixel_format,
        "color_range": color_range,
    }
    result = SimpleNamespace(stdout=json.dumps({"streams": [video]}))
    monkeypatch.setattr(render.subprocess, "run", lambda *_args, **_kwargs: result)

    with pytest.raises(ValueError):
        render.probe_video(Path("unused.mp4"), 1, 30)


def test_qsv_upload_format_differs_from_decoded_probe_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_format = render._pixel_format_for_encoder({"video_codec": "h264_qsv"})
    assert upload_format == "nv12"
    assert "format=nv12" in render._normalize_color_range_filter(upload_format)

    video = {
        "codec_type": "video",
        "nb_read_frames": "1",
        "avg_frame_rate": "30/1",
        "pix_fmt": "yuv420p",
        "color_range": "tv",
    }
    monkeypatch.setattr(
        render.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=json.dumps({"streams": [video]})
        ),
    )
    assert render.probe_video(Path("unused.mp4"), 1, 30) == video

    video["pix_fmt"] = upload_format
    with pytest.raises(ValueError, match="pixel format"):
        render.probe_video(Path("unused.mp4"), 1, 30)


@pytest.mark.parametrize("source_range", ["rgb-full", "yuv-limited"])
def test_real_ffmpeg_normalizes_to_tv_without_shifting_black_or_white(
    tmp_path: Path, source_range: str
) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.fail("FFmpeg and ffprobe are required for the color-range regression")

    width, height = 4, 2
    limited_luma = bytes([16] * 4 + [235] * 4)
    limited_frame = limited_luma + bytes([128] * 4)
    output = tmp_path / f"{source_range}.mp4"

    if source_range == "rgb-full":
        input_args = [
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-video_size",
            f"{width}x{height}",
            "-framerate",
            "1",
            "-i",
            "pipe:0",
        ]
        source_bytes = bytes([0, 0, 0] * 4 + [255, 255, 255] * 4)
    else:
        source = tmp_path / "limited-source.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "yuv420p",
                "-video_size",
                f"{width}x{height}",
                "-framerate",
                "1",
                "-i",
                "pipe:0",
                "-frames:v",
                "1",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-qp",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-color_range",
                "tv",
                "-bsf:v",
                "h264_metadata=video_full_range_flag=0",
                str(source),
            ],
            input=limited_frame,
            capture_output=True,
            check=True,
        )
        input_args = ["-i", str(source)]
        source_bytes = b""

    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *input_args,
        "-vf",
        render._normalize_color_range_filter("yuv420p"),
        "-frames:v",
        "1",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-qp",
        "0",
        "-pix_fmt",
        "yuv420p",
        "-color_range",
        "tv",
        "-bsf:v",
        "h264_metadata=video_full_range_flag=0",
        str(output),
    ]
    subprocess.run(command, input=source_bytes or None, capture_output=True, check=True)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_streams",
            "-show_entries",
            "stream=width,height,pix_fmt,color_range,nb_read_frames,avg_frame_rate",
            "-of",
            "json",
            str(output),
        ],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    video = json.loads(probe.stdout)["streams"][0]
    assert (video["width"], video["height"]) == (width, height)
    assert video["pix_fmt"] == "yuv420p"
    assert video["color_range"] == "tv"
    assert video["nb_read_frames"] == "1"
    assert video["avg_frame_rate"] == "1/1"

    decoded_yuv = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "yuv420p",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert list(decoded_yuv[:8]) == list(limited_luma)

    decoded_rgb = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    ).stdout
    black = decoded_rgb[:3]
    white = decoded_rgb[width * 3 : width * 3 + 3]
    assert max(black) <= 1
    assert min(white) >= 254

