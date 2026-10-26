"""Public compiler regressions for external ASS subtitles."""

from __future__ import annotations

from pathlib import Path

import pytest

from youtube_automation.video.engine import compile_video
from youtube_automation.video.runner import FakeMediaRunner
from youtube_automation.video.schema import (
    CompilationProfile,
    CompilationRequest,
    CompilationSpan,
    CompilationTarget,
)


class CapturingMediaRunner(FakeMediaRunner):
    """Capture generated filtergraph files at the public FFmpeg runner seam."""

    def __init__(self) -> None:
        super().__init__(
            default_total_frames=90,
            default_duration=3.0,
            default_width=320,
            default_height=180,
            default_fps=30.0,
            default_pix_fmt="yuv420p",
        )
        self.filter_graphs: list[str] = []

    def run_ffmpeg(
        self,
        args: list[str],
        *,
        cwd: Path | str | None = None,
        timeout: float | None = None,
    ) -> tuple[str, str]:
        if "-/filter_complex" in args and cwd is not None:
            graph_index = args.index("-/filter_complex") + 1
            self.filter_graphs.append(
                (Path(cwd) / args[graph_index]).read_text(encoding="utf-8")
            )
        return super().run_ffmpeg(args, cwd=cwd, timeout=timeout)


def _request(tmp_path: Path, subtitles_path: Path) -> CompilationRequest:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"RIFF dummy audio data")
    image_path = tmp_path / "shot.png"
    image_path.write_bytes(b"\x89PNG dummy image")
    spans = (
        CompilationSpan(
            index=0,
            shot_id="shot_00",
            start_frame=0,
            end_frame=45,
            asset_id="asset_00",
        ),
        CompilationSpan(
            index=1,
            shot_id="shot_01",
            start_frame=45,
            end_frame=90,
            asset_id="asset_00",
        ),
    )
    return CompilationRequest(
        spans=spans,
        audio_path=audio_path,
        asset_paths={"asset_00": image_path},
        output_path=tmp_path / "compiled.mp4",
        profile=CompilationProfile.PREVIEW,
        target=CompilationTarget(width=320, height=180, fps=30),
        subtitles_path=subtitles_path,
    )


def test_compile_video_burns_external_ass_and_rebuilds_after_content_change(
    tmp_path: Path,
) -> None:
    subtitles_path = tmp_path / "dynamic_subtitles.ass"
    subtitles_path.write_bytes(
        b"[Script Info]\nPlayResX: 320\nPlayResY: 180\n"
        b"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour\n"
        b"Style: Default,Arial,20,&H00FFFFFF\n"
        b"[Events]\nFormat: Layer, Start, End, Style, Text\n"
        b"Dialogue: 0,0:00:00.600,0:00:01.400,Default,Original\n"
    )
    request = _request(tmp_path, subtitles_path)
    runner = CapturingMediaRunner()

    first = compile_video(request, runner=runner)

    assert first.verified
    assert runner.filter_graphs
    assert any("ass=external_subtitles_" in graph for graph in runner.filter_graphs)
    first_graph_count = len(runner.filter_graphs)
    first_encode_count = len(runner.commands_run)

    subtitles_path.write_bytes(
        b"[Script Info]\nPlayResX: 320\nPlayResY: 180\n"
        b"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour\n"
        b"Style: Default,Arial,20,&H00FFFFFF\n"
        b"[Events]\nFormat: Layer, Start, End, Style, Text\n"
        b"Dialogue: 0,0:00:00.600,0:00:01.400,Default,Changed\n"
    )
    second = compile_video(request, runner=runner)

    assert second.verified
    assert len(runner.commands_run) > first_encode_count
    assert len(runner.filter_graphs) >= first_graph_count + len(request.spans)
    assert first.generation_hash != second.generation_hash
    assert second.reused_clip_count == 0


def test_compile_video_rejects_missing_external_ass_before_encoding(
    tmp_path: Path,
) -> None:
    missing_subtitles = tmp_path / "missing.ass"
    request = _request(tmp_path, missing_subtitles)
    runner = CapturingMediaRunner()

    with pytest.raises(FileNotFoundError, match="External subtitles not found"):
        compile_video(request, runner=runner)

    assert not any(
        "-frames:v" in command or str(request.output_path) in command
        for command in runner.commands_run
    )
